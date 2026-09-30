"""
Region detection from boundary curves (UX-9b, UIUX 5.6).

A region is what a user gets when they close a boundary. That is all it is: a
selectable area, with nothing carved until they ask for it. The spec is
unusually firm about what must not happen here, and this module is shaped by
those refusals:

* a gap is **never** closed. A boundary with two free ends produces no region,
  and the two ends are reported so the panel can offer to go to them;
* strokes are never cut, trimmed or deleted for being outside a chart;
* a boundary that crosses itself is still a boundary. Winding decides what it
  means, not whether it counts.

Regions are built by tracing loops in a planar graph rather than by testing
point-in-polygon, so a region knows its own border, its area, its holes and
which loops it is made of.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Sequence, Tuple

import numpy as np

from .geom2d import Arc, Line

#: How close two endpoints have to be to be the same point, in millimetres.
DEFAULT_TOLERANCE_MM = 1e-6


@dataclass
class PlanarGraph:
    """Boundary strokes reduced to shared vertices and the edges between them."""

    vertices: np.ndarray
    edges: np.ndarray
    tolerance_mm: float = DEFAULT_TOLERANCE_MM

    def __post_init__(self) -> None:
        self.vertices = np.asarray(self.vertices, dtype=np.float64).reshape(-1, 2)
        self.edges = np.asarray(self.edges, dtype=np.int64).reshape(-1, 2)

    @property
    def degree(self) -> np.ndarray:
        """How many edges meet at each vertex."""
        counts = np.bincount(self.edges.ravel(), minlength=len(self.vertices))
        return counts.astype(np.int64)

    @property
    def open_ends_mm(self) -> int:
        """How many vertices have a free end, which is how many gaps there are."""
        return int((self.degree == 1).sum())

    def neighbours(self, vertex: int) -> List[int]:
        touching = self.edges[(self.edges[:, 0] == vertex) |
                              (self.edges[:, 1] == vertex)]
        return [int(other) for other in touching.reshape(-1) if other != vertex]


@dataclass
class Region:
    """A closed area, and the loops that make it."""

    loops: List[np.ndarray] = field(default_factory=list)
    winding: int = 1
    tolerance_mm: float = DEFAULT_TOLERANCE_MM

    @property
    def closed(self) -> bool:
        return bool(self.loops)

    @property
    def signed_area_mm2(self) -> float:
        """Area with the sign of the winding; negative means a hole."""
        return float(sum(_polygon_area(loop) for loop in self.loops))

    @property
    def area_mm2(self) -> float:
        return abs(self.signed_area_mm2)

    @property
    def is_hole(self) -> bool:
        """A loop wound the other way is a hole, not a second part."""
        return self.winding < 0

    @property
    def perimeter_mm(self) -> float:
        return float(sum(_perimeter(loop) for loop in self.loops))

    def contains(self, points) -> np.ndarray:
        """Which points fall inside, holes included."""
        data = np.asarray(points, dtype=np.float64).reshape(-1, 2)
        winding = np.zeros(len(data), dtype=np.int64)
        for loop in self.loops:
            winding += _winding_numbers(loop, data)
        return winding != 0


def build_graph(strokes: Sequence, tolerance_mm: float = DEFAULT_TOLERANCE_MM
                ) -> PlanarGraph:
    """Reduce boundary strokes to a planar graph.

    Endpoints closer together than the tolerance are the same point; anything
    further apart stays apart. Joining them would invent a corner the user did
    not draw, and an unclosed boundary has to stay unclosed so the panel can
    offer to fix it.
    """
    if tolerance_mm < 0.0:
        raise ValueError(f"a tolerance cannot be negative, got {tolerance_mm}")

    points: List[np.ndarray] = []
    buckets: Dict[Tuple[int, int], int] = {}
    scale = 1.0 / max(tolerance_mm, 1e-12)
    edges: List[Tuple[int, int]] = []

    def identify(point) -> int:
        data = np.asarray(point, dtype=np.float64).ravel()[:2]
        key = (int(round(float(data[0]) * scale)),
               int(round(float(data[1]) * scale)))
        # A bucket is a cell, so check the neighbours for a near miss.
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                found = buckets.get((key[0] + dx, key[1] + dy))
                if found is None:
                    continue
                if float(np.linalg.norm(points[found] - data)) <= tolerance_mm:
                    return found
        index = len(points)
        points.append(data)
        buckets[key] = index
        return index

    for stroke in strokes:
        ends = _stroke_ends(stroke)
        if ends is None:
            continue
        first, last = identify(ends[0]), identify(ends[1])
        if first != last:
            edges.append((min(first, last), max(first, last)))

    return PlanarGraph(np.asarray(points).reshape(-1, 2),
                       np.asarray(edges, dtype=np.int64).reshape(-1, 2),
                       tolerance_mm)


def find_regions(graph: PlanarGraph) -> List[Region]:
    """The closed loops in a boundary, each as a region.

    Only fully closed loops count. A loop with a free end is a drawing the user
    has not finished, and making a region out of it would be a decision made on
    their behalf.
    """
    regions = []
    for loop in _closed_loops(graph):
        regions.append(Region([loop], _winding(loop)))
    return regions


def open_ends(graph: PlanarGraph) -> np.ndarray:
    """The free ends a user would have to join, so the panel can point at them."""
    if graph.open_ends_mm == 0:
        return np.zeros((0, 2), dtype=np.float64)
    return graph.vertices[graph.degree == 1]


def _stroke_ends(stroke):
    if isinstance(stroke, Line):
        return stroke.start, stroke.end
    if isinstance(stroke, Arc):
        return stroke.start, stroke.end
    points = getattr(stroke, "points", None)
    if points is not None and len(points) >= 2:
        return points[0], points[-1]
    return None


def _closed_loops(graph: PlanarGraph) -> List[np.ndarray]:
    """Every closed walk in the graph, once each."""
    seen = set()
    loops = []
    for start in range(len(graph.vertices)):
        if graph.degree[start] != 2:
            continue
        walk = _walk_from(graph, start)
        if walk is None:
            continue
        key = tuple(sorted(walk))
        if key in seen or len(walk) < 3:
            continue
        seen.add(key)
        loops.append(graph.vertices[np.asarray(walk, dtype=np.int64)])
    return loops


def _walk_from(graph: PlanarGraph, start: int):
    """Follow degree-two vertices until the walk closes or falls off the end."""
    walk = [start]
    previous, current = None, start
    for _ in range(len(graph.vertices) + 1):
        options = [n for n in graph.neighbours(current) if n != previous]
        if not options:
            return None
        following = options[0]
        if following == start:
            return walk
        walk.append(following)
        previous, current = current, following
    return None


def _winding(loop: np.ndarray) -> int:
    area = _polygon_area(loop)
    return 1 if area >= 0.0 else -1


def _polygon_area(loop: np.ndarray) -> float:
    data = np.asarray(loop, dtype=np.float64).reshape(-1, 2)
    if len(data) < 3:
        return 0.0
    following = np.roll(data, -1, axis=0)
    return float((data[:, 0] * following[:, 1] - following[:, 0] * data[:, 1]).sum() * 0.5)


def _perimeter(loop: np.ndarray) -> float:
    data = np.asarray(loop, dtype=np.float64).reshape(-1, 2)
    if len(data) < 2:
        return 0.0
    return float(np.linalg.norm(np.roll(data, -1, axis=0) - data, axis=1).sum())


def _winding_numbers(loop: np.ndarray, points: np.ndarray) -> np.ndarray:
    """The winding number of a loop around each point, using the crossing rule."""
    data = np.asarray(loop, dtype=np.float64).reshape(-1, 2)
    total = np.zeros(len(points), dtype=np.int64)
    for index in range(len(data)):
        start = data[index]
        end = data[(index + 1) % len(data)]
        side = (end[0] - start[0]) * (points[:, 1] - start[1]) - \
               (end[1] - start[1]) * (points[:, 0] - start[0])
        upward = (start[1] <= points[:, 1]) & (end[1] > points[:, 1])
        downward = (end[1] <= points[:, 1]) & (start[1] > points[:, 1])
        total += np.where(upward & (side > 0.0), 1, 0)
        total -= np.where(downward & (side < 0.0), 1, 0)
    return total


__all__ = ("DEFAULT_TOLERANCE_MM", "PlanarGraph", "Region", "build_graph",
           "find_regions", "open_ends")
