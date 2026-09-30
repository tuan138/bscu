"""
The shaping grid (UX-10, UIUX 5.7).

The grid is not the workpiece's UV map. It is a set of control lines drawn inside
a design chart, whose crossings share a height node, and which shape the surface
the grooves are then cut into. It is kept in its own module because it is a
distinct idea with distinct rules, and because the height field should not grow
a second model of it.

Three rules from the spec shape everything here:

* **Nodes are relative to the base shape.** A node's height is a lift from
  whatever the base was underneath, so changing the base keeps the shaping
  intent rather than flattening it.
* **Crossing lines share a node.** Two lines meeting at the same point use one
  node, and editing either moves the other. A grid where a crossing has two
  heights is not a surface.
* **A pinned node keeps its height.** Relaxation eases towards the neighbours;
  it never overrides a node the user has set, and a node shared with another
  line is pinned automatically for the same reason.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

import numpy as np

#: Lines closer together than this, in millimetres, are the same point.
JOIN_TOLERANCE_MM = 1e-6

#: Below this a segment is treated as a point rather than a direction.
DEGENERATE_MM = 1e-12


@dataclass
class WarpNode:
    """A shared height control where control lines meet.

    ``lines`` names the lines that meet here, so the panel can show which ones
    will move together and offer to break them apart.
    """

    x_mm: float
    y_mm: float
    height_mm: float = 0.0
    pinned: bool = False
    lines: Tuple[str, ...] = ()

    @property
    def position(self) -> Tuple[float, float]:
        return (self.x_mm, self.y_mm)

    def move_to(self, x_mm: float, y_mm: float) -> "WarpNode":
        """A moved copy. Nodes are values; the grid is rebuilt around them."""
        if self.pinned:
            raise ValueError(
                f"the node at {self.position} is pinned, so it keeps its place")
        return WarpNode(float(x_mm), float(y_mm), self.height_mm, self.pinned,
                        self.lines)

    def raised_by(self, amount_mm: float) -> "WarpNode":
        """A copy lifted by a height, which is what the panel's slider does."""
        return WarpNode(self.x_mm, self.y_mm, self.height_mm + float(amount_mm),
                        self.pinned, self.lines)

    @property
    def key(self) -> Tuple[float, float]:
        """The point, rounded for use as a dictionary key."""
        return (round(self.x_mm, 6), round(self.y_mm, 6))


@dataclass
class WarpLine:
    """One control line across a chart, holding its own nodes in order."""

    name: str
    points_mm: List[Tuple[float, float]] = field(default_factory=list)
    heights_mm: List[float] = field(default_factory=list)
    falloff_mm: float = 2.0

    def __len__(self) -> int:
        return len(self.points_mm)

    @property
    def keys(self) -> List[Tuple[float, float]]:
        return [(round(x, 6), round(y, 6)) for x, y in self.points_mm]

    def influence(self, points: np.ndarray) -> np.ndarray:
        """How strongly this line shapes the surface at each point.

        Two separate things, and conflating them is why a line either sags
        between its nodes or reaches everywhere at once. The *value* is a blend
        of the node heights, held level along the line however far apart the
        nodes are; the *strength* fades with distance from the line, so it eases
        out instead of ending in a crease.
        """
        data = np.asarray(points, dtype=np.float64).reshape(-1, 2)
        if not self.heights_mm or not self.points_mm:
            return np.zeros(len(data))
        falloff = max(float(self.falloff_mm), 1e-6)
        heights = np.asarray(self.heights_mm, dtype=np.float64)

        total = np.zeros(len(data))
        weighted = np.zeros(len(data))
        for index, node in enumerate(self.points_mm):
            place = np.asarray(node, dtype=np.float64)
            weight = np.exp(-np.linalg.norm(data - place, axis=1) / falloff)
            total += weight
            weighted += weight * heights[index]
        blend = np.divide(weighted, total, out=np.zeros_like(weighted),
                          where=total > 1e-12)
        return blend * np.exp(-self.distance_to(data) / falloff)

    def distance_to(self, points: np.ndarray) -> np.ndarray:
        """How far each point is from the line itself, in millimetres."""
        data = np.asarray(points, dtype=np.float64).reshape(-1, 2)
        if not self.points_mm:
            return np.full(len(data), np.inf)
        if len(self.points_mm) == 1:
            node = np.asarray(self.points_mm[0], dtype=np.float64)
            return np.linalg.norm(data - node, axis=1)

        nearest = np.full(len(data), np.inf)
        for index in range(len(self.points_mm) - 1):
            first = np.asarray(self.points_mm[index], dtype=np.float64)
            second = np.asarray(self.points_mm[index + 1], dtype=np.float64)
            nearest = np.minimum(nearest, _distance_to_segment(data, first, second))
        return nearest

    def distance_along(self, point) -> float:
        """How far along the line a point sits, in millimetres."""
        target = np.asarray(point, dtype=np.float64).ravel()[:2]
        best = np.full(len(self.points_mm) - 1, np.inf)
        for index in range(len(self.points_mm) - 1):
            first = np.asarray(self.points_mm[index], dtype=np.float64)
            second = np.asarray(self.points_mm[index + 1], dtype=np.float64)
            best[index] = float(np.linalg.norm(_closest_on_segment(
                target, first, second) - target))
        return float(best.min()) if best.size else float("inf")


@dataclass
class WarpGrid:
    """Every control line in a chart, and the nodes they share."""

    lines: List[WarpLine] = field(default_factory=list)

    def __bool__(self) -> bool:
        return bool(self.lines)

    def find(self, name: str) -> Optional[WarpLine]:
        for line in self.lines:
            if line.name == name:
                return line
        return None

    def add(self, line: WarpLine) -> WarpLine:
        """Add a line, replacing one of the same name rather than duplicating it."""
        found = self.find(line.name)
        if found is not None:
            self.lines[self.lines.index(found)] = line
        else:
            self.lines.append(line)
        return line

    def remove(self, name: str) -> bool:
        line = self.find(name)
        if line is None:
            return False
        self.lines.remove(line)
        return True

    def shared_nodes(self) -> List[WarpNode]:
        """The places two control lines meet, one node each.

        Found from the geometry rather than from the nodes the lines happen to
        carry. Two lines drawn across each other meet in the middle of their
        runs, and that meeting is where the two shaping decisions have to agree:
        a grid giving it two heights would not be a surface.
        """
        nodes: List[WarpNode] = []
        for index, line in enumerate(self.lines):
            for later in self.lines[index + 1:]:
                for crossing in _meetings(line, later):
                    found = _near(nodes, crossing)
                    names = tuple(sorted({line.name, later.name}))
                    if found is not None:
                        found.lines = tuple(sorted(set(found.lines) | set(names)))
                    else:
                        nodes.append(WarpNode(float(crossing[0]),
                                              float(crossing[1]), 0.0, False,
                                              names))
        return nodes

    def influence(self, points: np.ndarray) -> np.ndarray:
        """The grid's contribution at each point, in millimetres."""
        data = np.asarray(points, dtype=np.float64).reshape(-1, 2)
        total = np.zeros(len(data))
        for line in self.lines:
            total = total + line.influence(data)
        return total

    def relax(self, passes: int = 1, strength: float = 0.5) -> int:
        """Smooth the shaping, easing each node towards its neighbours.

        Runs over every line's own nodes, not only the crossings, because a
        spike left on a single line is the common case. Endpoints are left
        alone: they anchor the line, and easing them would let the whole line
        drift. A node shared with another line is held automatically, because
        two lines meeting at one point are one decision.
        """
        if passes <= 0:
            return 0
        shared = {node.key: node.height_mm for node in self.shared_nodes()}

        moved = 0
        for _ in range(passes):
            for line in self.lines:
                if len(line.heights_mm) < 3:
                    continue
                heights = list(line.heights_mm)
                keys = line.keys
                for index in range(1, len(heights) - 1):
                    if keys[index] in shared:
                        heights[index] = shared[keys[index]]
                        continue
                    target = (heights[index - 1] + heights[index + 1]) * 0.5
                    heights[index] += (target - heights[index]) * strength
                for index in range(1, len(heights) - 1):
                    if abs(heights[index] - line.heights_mm[index]) > 1e-12:
                        moved += 1
                    line.heights_mm[index] = heights[index]
        return moved

    def bounds(self) -> Optional[Tuple[np.ndarray, np.ndarray]]:
        """The grid's extent in millimetres, or None when it is empty."""
        points = [point for line in self.lines for point in line.points_mm]
        if not points:
            return None
        stacked = np.asarray(points, dtype=np.float64)
        return stacked.min(axis=0), stacked.max(axis=0)


def _meetings(first: WarpLine, second: WarpLine) -> List[Tuple[float, float]]:
    """Every point at which two lines are the same piece of the surface."""
    found: List[Tuple[float, float]] = []
    for a in range(len(first.points_mm) - 1):
        for b in range(len(second.points_mm) - 1):
            hit = _segment_crossing(
                np.asarray(first.points_mm[a], dtype=np.float64),
                np.asarray(first.points_mm[a + 1], dtype=np.float64),
                np.asarray(second.points_mm[b], dtype=np.float64),
                np.asarray(second.points_mm[b + 1], dtype=np.float64))
            if hit is not None and not _already(found, hit):
                found.append(hit)

    # A line drawn as a single point, or with a repeated point in it, still
    # meets another line passing through it. The point has to be near *both*
    # lines: testing it against the line it came from is always true, and that
    # would make a one-point line meet every line on the canvas.
    for point in _degenerate_points(first) + _degenerate_points(second):
        probe = np.asarray([point], dtype=np.float64)
        near_first = float(first.distance_to(probe)[0]) <= JOIN_TOLERANCE_MM
        near_second = float(second.distance_to(probe)[0]) <= JOIN_TOLERANCE_MM
        if near_first and near_second and not _already(found, point):
            found.append((float(point[0]), float(point[1])))
    return found


def _degenerate_points(line: WarpLine) -> List[Tuple[float, float]]:
    """Points of a line with fewer than two, or with a repeated one."""
    if not line.points_mm:
        return []
    if len(line.points_mm) == 1:
        return [tuple(line.points_mm[0])]
    found = []
    for index in range(len(line.points_mm) - 1):
        a = np.asarray(line.points_mm[index], dtype=np.float64)
        b = np.asarray(line.points_mm[index + 1], dtype=np.float64)
        if float(np.linalg.norm(b - a)) <= DEGENERATE_MM:
            found.append(tuple(line.points_mm[index]))
    return found


def _segment_crossing(p1, p2, p3, p4):
    """Where two segments meet, or None.

    Collinear segments that overlap still meet: a line continued is written as
    two lines, and that is one shaping decision, not two.
    """
    r = p2 - p1
    s = p4 - p3
    denominator = r[0] * s[1] - r[1] * s[0]
    if abs(denominator) < 1e-12:
        if abs(r[0] * (p3[1] - p1[1]) - r[1] * (p3[0] - p1[0])) > 1e-9:
            return None
        # Each segment's ends are tested against the *other* segment. Testing
        # an end against its own segment is always true, which would report a
        # meeting for any two collinear segments however far apart they are.
        for point in (p3, p4):
            if _on_segment(point, p1, p2):
                return (float(point[0]), float(point[1]))
        for point in (p1, p2):
            if _on_segment(point, p3, p4):
                return (float(point[0]), float(point[1]))
        return None

    offset = p3 - p1
    t = (offset[0] * s[1] - offset[1] * s[0]) / denominator
    u = (offset[0] * r[1] - offset[1] * r[0]) / denominator
    if -1e-9 <= t <= 1.0 + 1e-9 and -1e-9 <= u <= 1.0 + 1e-9:
        return (float(p1[0] + t * r[0]), float(p1[1] + t * r[1]))
    return None


def _on_segment(point, start, end) -> bool:
    """Whether a point lies on a segment, ends included."""
    return float(np.linalg.norm(
        point - _closest_on_segment(point, start, end))) <= JOIN_TOLERANCE_MM


def _closest_on_segment(point, start, end) -> np.ndarray:
    """The nearest point on a segment, clamped to its ends."""
    span = end - start
    length = float(np.linalg.norm(span))
    if length <= DEGENERATE_MM:
        return start
    ratio = float(np.clip((point - start) @ span / (length * length), 0.0, 1.0))
    return start + ratio * span


def _distance_to_segment(points, start, end) -> np.ndarray:
    """Distance from each point to a segment, clamped to its ends."""
    return np.linalg.norm(points - _closest_rows(points, start, end), axis=1)


def _closest_rows(points, start, end) -> np.ndarray:
    """The nearest point on a segment for each of several points."""
    span = end - start
    length = float(np.linalg.norm(span))
    if length <= DEGENERATE_MM:
        return np.repeat(start[None, :], len(points), axis=0)
    offset = points - start
    ratio = np.clip((offset @ span) / (length * length), 0.0, 1.0)
    return start + ratio[:, None] * span


def _near(nodes: Sequence[WarpNode], point,
          tolerance: float = JOIN_TOLERANCE_MM) -> Optional[WarpNode]:
    """The node at a point, if one is already there."""
    for node in nodes:
        if float(np.linalg.norm(
                np.asarray(node.position) - np.asarray(point))) <= tolerance:
            return node
    return None


def _already(found: Sequence[Tuple[float, float]],
             point: Tuple[float, float]) -> bool:
    """Whether a meeting has already been recorded, within the tolerance."""
    for other in found:
        if float(np.linalg.norm(np.asarray(other) - np.asarray(point))) \
                <= JOIN_TOLERANCE_MM:
            return True
    return False


__all__ = ("DEGENERATE_MM", "JOIN_TOLERANCE_MM", "WarpGrid", "WarpLine", "WarpNode")
