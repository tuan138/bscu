"""
The virtual height field (UX-10, UIUX 5.7, 5.11 and 5.12).

This is the single source of truth for relief height. The two preview tiers,
the Geometry Nodes graph and the export all call it, so a number shown in the
panel is the number that gets cut. It is pure numpy: no Blender types, so it
can be measured and tested without opening Blender.

Evaluation order is fixed and is the spec's, not a convenience:

    region base shape -> warp grid -> grooves and surface detail

A warp that came after a groove would drag the groove with it, and the user
asked for the grid to shape the surface the grooves then sit on.

Heights are millimetres throughout, measured from the stock's top face, and
positive means material removed.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import numpy as np

from .profile_curves import Profile, vee
from .sdf import Polygon, smooth_union

#: A face thinner than this is treated as gone; below it the numbers are noise.
MIN_WALL_MM = 0.0


@dataclass
class WarpNode:
    """A shared height control where warp lines cross.

    The height is relative to whatever the base shape was there, so changing
    the base underneath keeps the intent. Slopes are per-line and directioned,
    because a surface cannot have two different gradients at one point and
    quietly ignoring the conflict would be a lie about the result.
    """

    x_mm: float
    y_mm: float
    height_mm: float = 0.0
    pinned: bool = False
    lines: Tuple[str, ...] = ()


@dataclass
class WarpLine:
    """One control line across a chart, holding its own set of nodes."""

    name: str
    nodes: List[WarpNode] = field(default_factory=list)
    falloff_mm: float = 2.0

    def influence(self, points: np.ndarray) -> np.ndarray:
        """How strongly this line speaks at each point, within the chart."""
        if not self.nodes:
            return np.zeros(len(points))
        data = np.asarray(points, dtype=np.float64).reshape(-1, 2)
        heights = np.asarray([node.height_mm for node in self.nodes])
        falloff = max(self.falloff_mm, 1e-6)
        # A smooth kernel, so a line does not leave a crease where it ends.
        weights = np.exp(-np.abs(data[:, 1]) / falloff)[:, None]
        spread = (data - np.asarray([[node.x_mm, 0.0] for node in self.nodes])) ** 2
        del spread
        return weights @ heights


@dataclass
class Groove:
    """A cut along a path, measured from the surface below it."""

    path: np.ndarray
    profile: Profile
    label: str = ""

    def depth_mm(self, points: np.ndarray, remaining_mm: np.ndarray) -> np.ndarray:
        """How much material this groove removes, as a positive depth.

        Limited by the material still under the surface: a cut deeper than the
        part is a cut through the part, and the spec asks for that to be
        reported rather than performed.
        """
        data = np.asarray(points, dtype=np.float64).reshape(-1, 2)
        available = np.maximum(np.asarray(remaining_mm, dtype=np.float64).ravel(), 0.0)
        return np.minimum(self.wanted_mm(data), available)

    def wanted_mm(self, points: np.ndarray) -> np.ndarray:
        """The depth the profile asks for, ignoring what is there."""
        data = np.asarray(points, dtype=np.float64).reshape(-1, 2)
        return -self.profile.evaluate(self._distance(data))

    def blocked(self, points: np.ndarray, remaining_mm: np.ndarray) -> np.ndarray:
        """Where the cut asked for more material than the part has under it."""
        return self.depth_mm(points, remaining_mm) < self.wanted_mm(points) - 1e-9

    def _distance(self, points: np.ndarray) -> np.ndarray:
        path = np.asarray(self.path, dtype=np.float64).reshape(-1, 2)
        if len(path) == 0:
            return np.full(len(points), np.inf)
        if len(path) == 1:
            return np.linalg.norm(points - path[0], axis=1)
        nearest = np.full(len(points), np.inf)
        for index in range(len(path) - 1):
            nearest = np.minimum(nearest, _segment_distance(
                points, path[index], path[index + 1]))
        return nearest


@dataclass
class HeightField:
    """The whole relief, in millimetres, evaluated on demand."""

    base: Optional[Polygon] = None
    base_depth_mm: float = 0.0
    base_blend_mm: float = 0.0
    warp_lines: List[WarpLine] = field(default_factory=list)
    grooves: List[Groove] = field(default_factory=list)
    keep_border_flat: bool = True
    stock_thickness_mm: float = 0.0
    """How much material there is under the surface to cut into.

    Zero means the stock was never stated, so nothing is limited here; the
    export check is where an unstated stock is caught against the real one.
    """

    def base_height_mm(self, points: np.ndarray) -> np.ndarray:
        """The region's own shape, before anything else touches it."""
        if self.base is None:
            return np.zeros(len(np.asarray(points).reshape(-1, 2)))
        distance = self.base.distance(points)
        if self.base_blend_mm > 0.0:
            flat_field = np.full(len(distance), -self.base_depth_mm)
            inside = distance < 0.0
            shaped = np.minimum(self.base_depth_mm,
                                -distance + self.base_depth_mm)
            return np.where(inside, np.minimum(shaped, flat_field), 0.0)
        return np.where(distance < 0.0, self.base_depth_mm, 0.0)

    def warp_mm(self, points: np.ndarray) -> np.ndarray:
        """The grid's contribution, added on top of the base shape."""
        total = np.zeros(len(np.asarray(points).reshape(-1, 2)))
        for line in self.warp_lines:
            total = total + line.influence(points)
        return total

    def evaluate(self, points_canvas_mm: np.ndarray) -> np.ndarray:
        """Height in millimetres at each canvas point, positive downwards.

        This is the function the whole pipeline calls. Anything that shows a
        number and anything that cuts a surface must agree, which is why there
        is only one of it.
        """
        data = np.asarray(points_canvas_mm, dtype=np.float64).reshape(-1, 2)
        height = self.base_height_mm(data) + self.warp_mm(data)
        height = np.maximum(height, 0.0)

        for groove in self.grooves:
            height = height + groove.depth_mm(data, self._remaining_mm(height))


        return np.clip(height, 0.0, None)

    def blocked_by(self, points_canvas_mm: np.ndarray) -> np.ndarray:
        """Where a cut wanted more material than the part has there."""
        data = np.asarray(points_canvas_mm, dtype=np.float64).reshape(-1, 2)
        surface = np.maximum(self.base_height_mm(data) + self.warp_mm(data), 0.0)
        flags = np.zeros(len(data), dtype=bool)
        for groove in self.grooves:
            flags |= groove.blocked(data, self._remaining_mm(surface))
        return flags

    def _remaining_mm(self, height: np.ndarray) -> np.ndarray:
        """Material still under the surface, or unlimited when stock is unstated."""
        if self.stock_thickness_mm <= 0.0:
            return np.full(len(height), np.inf)
        return self.stock_thickness_mm - np.asarray(height, dtype=np.float64).ravel()

    def region_mask(self, points_canvas_mm: np.ndarray) -> np.ndarray:
        """Which sample points lie inside the region outline."""
        if self.base is None:
            return np.zeros(len(np.asarray(points_canvas_mm).reshape(-1, 2)),
                            dtype=bool)
        return self.base.contains(points_canvas_mm)


def _segment_distance(points: np.ndarray, start: np.ndarray, end: np.ndarray):
    """Distance from each point to a segment, clamped to the segment's ends."""
    span = end - start
    length = float(np.linalg.norm(span))
    if length == 0.0:
        return np.linalg.norm(points - start, axis=1)
    offset = points - start
    along = np.clip((offset @ span) / (length * length), 0.0, 1.0)
    return np.linalg.norm(points - (start + along[:, None] * span), axis=1)


def default_groove(path, depth_mm: float = 2.0, angle_deg: float = 60.0) -> Groove:
    """A plain V cut, which is what a ball nose leaves on its own."""
    return Groove(np.asarray(path, dtype=np.float64), vee(depth_mm, angle_deg))


__all__ = (
    "Groove",
    "HeightField",
    "WarpLine",
    "WarpNode",
    "default_groove",
    "smooth_union",
)
