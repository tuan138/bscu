"""
Two-dimensional distance fields for the 2.5D canvas (UX-10, UIUX 5.6).

Everything the user draws lives in a flat canvas in millimetres, and the tools
that need to reason about a region - is this point inside, how far is it from
the border, what does a corner look like - all want a signed distance. Having
one honest signed distance per primitive is what makes the rest of the relief
code simple instead of a pile of special cases.

A positive distance is outside and a negative one inside, so a region's
interior is simply where the field is negative.
"""

import math
from dataclasses import dataclass
from typing import Sequence, Tuple

import numpy as np

Point = Tuple[float, float]


@dataclass(frozen=True)
class Segment:
    """A straight run between two canvas points, in millimetres."""

    start: Point
    end: Point

    def distance(self, points: np.ndarray) -> np.ndarray:
        """Distance from each point to this segment, never to its infinite line."""
        data = np.asarray(points, dtype=np.float64).reshape(-1, 2)
        first = np.asarray(self.start, dtype=np.float64)
        second = np.asarray(self.end, dtype=np.float64)
        span = second - first
        length = float(np.linalg.norm(span))
        if length == 0.0:
            return np.linalg.norm(data - first, axis=1)
        offset = data - first
        along = np.clip((offset @ span) / (length * length), 0.0, 1.0)
        closest = first + along[:, None] * span
        return np.linalg.norm(data - closest, axis=1)


@dataclass(frozen=True)
class Circle:
    """A circle on the canvas."""

    centre: Point
    radius: float

    def distance(self, points: np.ndarray) -> np.ndarray:
        data = np.asarray(points, dtype=np.float64).reshape(-1, 2)
        centre = np.asarray(self.centre, dtype=np.float64)
        return np.linalg.norm(data - centre, axis=1) - self.radius


@dataclass(frozen=True)
class Arc:
    """A circular arc, from ``start`` to ``end`` the short way round."""

    centre: Point
    radius: float
    start_angle: float
    end_angle: float

    def distance(self, points: np.ndarray) -> np.ndarray:
        """Distance to the arc itself, or to the closed shape when it is a half.

        An arc that sweeps a full turn is a circle, and treating it as an open
        arc would leave a gap that a user drawing a round boss would see.
        """
        data = np.asarray(points, dtype=np.float64).reshape(-1, 2)
        centre = np.asarray(self.centre, dtype=np.float64)
        radial = data - centre
        angles = np.arctan2(radial[:, 1], radial[:, 0])
        sweep = abs(self.end_angle - self.start_angle)
        if sweep >= 2.0 * math.pi - 1e-9:
            return np.linalg.norm(radial, axis=1) - self.radius

        sweep = self.end_angle - self.start_angle
        # How far the point sits along the sweep, counting from the start.
        turned = np.mod(angles - self.start_angle, 2.0 * math.pi)
        within = (turned <= sweep) if sweep >= 0.0 else (turned >= sweep + 2.0 * math.pi)
        to_rim = np.abs(np.linalg.norm(radial, axis=1) - self.radius)
        corners = np.minimum(
            np.linalg.norm(data - self.point_at(self.start_angle), axis=1),
            np.linalg.norm(data - self.point_at(self.end_angle), axis=1),
        )
        return np.where(within, to_rim, corners)

    def point_at(self, angle: float) -> Point:
        return (self.centre[0] + self.radius * math.cos(angle),
                self.centre[1] + self.radius * math.sin(angle))


@dataclass(frozen=True)
class Polygon:
    """A closed outline, as the user drew it."""

    points: Sequence[Point]

    def distance(self, query: np.ndarray) -> np.ndarray:
        """Signed distance: negative inside, positive outside."""
        data = np.asarray(query, dtype=np.float64).reshape(-1, 2)
        ring = np.asarray(self.points, dtype=np.float64).reshape(-1, 2)
        if len(ring) < 2:
            raise ValueError("a region needs at least two points")
        if len(ring) == 2:
            return Segment(tuple(ring[0]), tuple(ring[1])).distance(data)

        outside = np.full(len(data), np.inf)
        for index in range(len(ring)):
            outside = np.minimum(
                outside,
                Segment(tuple(ring[index]), tuple(ring[(index + 1) % len(ring)])).distance(data),
            )
        return np.where(self.contains(data), -outside, outside)

    def contains(self, points: np.ndarray) -> np.ndarray:
        """Winding test, so nested and self-overlapping outlines still work.

        A crossing-number test would flip its answer wherever two runs of the
        outline cross, and users draw those without meaning anything by it. A
        winding number only changes where the drawing genuinely encircles a
        point, which is the question being asked.
        """
        data = np.asarray(points, dtype=np.float64).reshape(-1, 2)
        ring = np.asarray(self.points, dtype=np.float64).reshape(-1, 2)
        winding = np.zeros(len(data), dtype=np.int64)
        for index in range(len(ring)):
            start = ring[index]
            end = ring[(index + 1) % len(ring)]
            side = (end[0] - start[0]) * (data[:, 1] - start[1]) - \
                   (end[1] - start[1]) * (data[:, 0] - start[0])
            upward = (start[1] <= data[:, 1]) & (end[1] > data[:, 1])
            downward = (end[1] <= data[:, 1]) & (start[1] > data[:, 1])
            winding += np.where(upward & (side > 0.0), 1, 0)
            winding -= np.where(downward & (side < 0.0), 1, 0)
        return winding != 0

    def is_closed(self, tolerance: float = 1e-6) -> bool:
        """Whether the outline comes back to where it started.

        An open outline makes a region that can be picked but not yet carved,
        which the spec insists on, so this has to be answerable without guessing.
        """
        ring = np.asarray(self.points, dtype=np.float64).reshape(-1, 2)
        if len(ring) < 3:
            return False
        return float(np.linalg.norm(ring[0] - ring[-1])) <= tolerance


def smooth_union(first: np.ndarray, second: np.ndarray, radius: float) -> np.ndarray:
    """Join two distance fields with a fillet, or with a crease when asked.

    A plain minimum leaves a hard crease where two walls meet, which a cutter
    leaves too. A smooth minimum rounds that corner off over ``radius``
    millimetres. The crease is the default because a knife edge is sometimes
    exactly what is wanted, and silently rounding it would be a decision the
    user did not make.
    """
    if radius <= 0.0:
        return np.minimum(first, second)
    weight = np.clip(0.5 + 0.5 * (second - first) / radius, 0.0, 1.0)
    return (first * weight + second * (1.0 - weight)
            - radius * weight * (1.0 - weight))


def grid_samples(low: Point, high: Point, step: float) -> np.ndarray:
    """A regular sample grid covering a rectangle, in millimetres.

    The step is the coarseness of the sampled field, and the spec is explicit
    that it is a sampling artefact rather than a promise about the surface.
    """
    width = high[0] - low[0]
    height = high[1] - low[1]
    if width <= 0.0 or height <= 0.0 or step <= 0.0:
        raise ValueError("a sampling grid needs a positive area and a positive step")
    xs = np.arange(low[0], high[0] + step * 0.5, step)
    ys = np.arange(low[1], high[1] + step * 0.5, step)
    return np.stack(np.meshgrid(xs, ys, indexing="xy"), axis=-1).reshape(-1, 2)


__all__ = (
    "Arc",
    "Circle",
    "Polygon",
    "Segment",
    "grid_samples",
    "smooth_union",
)
