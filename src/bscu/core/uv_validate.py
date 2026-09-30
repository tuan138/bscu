"""
Chart validation (UX-6, UIUX 3.3).

Everything here runs on the *opened* surface: the chart with its seam cut, so
the vertices and edges that the cut duplicated are counted twice. Taking
V - E + F from the original face set is the classic way to conclude a perfectly
good chart is broken, and the spec calls that out by name.

Two rules shape the output:

* A loose seam end is a place to look, not a fault. Cutting a closed surface
  open leaves ends; that is what cutting it open means. Forcing the count to
  zero would push the user into closing loops they did not ask for.
* A high-curvature vertex that is not on the seam is not a topology problem at
  all. It belongs to the distortion report, not to this one.

Every finding carries a location, a reason and a suggestion, because a warning
the user cannot act on is noise they will learn to dismiss.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Sequence, Tuple

import numpy as np

from .seam_tools import edge_face_counts
from .uv_islands import _face_keys, _sorted_corners

#: Worst first, so the first match decides the chart's state.
SEVERITIES = ("error", "warning", "note")

#: A UV triangle smaller than this, as a fraction of the chart's own scale,
#: is treated as collapsed rather than merely small.
COLLAPSED_RATIO = 1e-9


@dataclass(frozen=True)
class Finding:
    """One thing worth telling the user, and what to do about it."""

    severity: str
    code: str
    message: str
    faces: np.ndarray
    suggestion: str


@dataclass(frozen=True)
class ChartSummary:
    """The shape of one opened chart."""

    island: int
    faces: int
    edges: int
    vertices: int
    euler: int
    boundary_loops: int
    genus: int


@dataclass
class ChartReport:
    """Everything the validator found, plus the state the panel shows."""

    findings: List[Finding] = field(default_factory=list)
    charts: List[ChartSummary] = field(default_factory=list)
    checked_charts: int = 0

    @property
    def errors(self) -> List[Finding]:
        return [f for f in self.findings if f.severity == "error"]

    @property
    def warnings(self) -> List[Finding]:
        return [f for f in self.findings if f.severity == "warning"]

    @property
    def state(self) -> str:
        """The single worst severity, or a clean bill of health."""
        for severity in SEVERITIES:
            if any(f.severity == severity for f in self.findings):
                return severity
        return "clean"


def _boundary_loops(faces: np.ndarray) -> int:
    """How many closed loops the opened chart's border makes."""
    border = [edge for edge, users in edge_face_counts(faces).items() if len(users) == 1]
    if not border:
        return 0
    links: Dict[int, set] = {}
    for left, right in border:
        links.setdefault(left, set()).add(right)
        links.setdefault(right, set()).add(left)

    seen = set()
    loops = 0
    for start in links:
        if start in seen:
            continue
        loops += 1
        stack = [start]
        while stack:
            vertex = stack.pop()
            if vertex in seen:
                continue
            seen.add(vertex)
            stack.extend(links[vertex] - seen)
    return loops


def validate_chart(faces: np.ndarray, uv: np.ndarray, island_ids: np.ndarray,
                   seam_edges: Sequence[Tuple[int, int]] = ()) -> ChartReport:
    """Check every chart of a candidate layout and report what is wrong.

    ``uv`` holds one coordinate per mesh vertex, ``island_ids`` says which chart
    each face belongs to, and ``seam_edges`` is the seam under test, used only
    to point out loose ends.
    """
    tris = np.asarray(faces, dtype=np.int64).reshape(-1, 3)
    layout = np.asarray(uv, dtype=np.float64).reshape(-1, 2)
    islands = np.asarray(island_ids, dtype=np.int64).ravel()
    if layout.shape[0] < (int(tris.max()) + 1 if tris.size else 0):
        raise ValueError(f"layout has {layout.shape[0]} vertices, "
                         f"the mesh needs {int(tris.max()) + 1 if tris.size else 0}")
    if islands.size != tris.shape[0]:
        raise ValueError(f"island ids cover {islands.size} faces, "
                         f"the mesh has {tris.shape[0]}")

    report = ChartReport()
    report.findings.extend(_structural_checks(tris))
    report.findings.extend(_layout_checks(tris, layout, islands))
    report.findings.extend(_loose_end_checks(seam_edges))
    report.charts = [_summarise(index, tris[islands == index])
                     for index in np.unique(islands)]
    report.checked_charts = len(report.charts)
    return report


def _structural_checks(tris: np.ndarray) -> List[Finding]:
    """Problems with the mesh's own topology, independent of any layout."""
    findings: List[Finding] = []
    if not tris.size:
        return findings

    usage = edge_face_counts(tris)
    crowded = sorted(edge for edge, users in usage.items() if len(users) > 2)
    if crowded:
        faces = sorted({index for edge in crowded for index in usage[edge]})
        findings.append(Finding(
            "error", "NON_MANIFOLD_EDGE",
            f"{len(crowded)} edge(s) are shared by more than two faces",
            np.asarray(faces, dtype=np.int64),
            "Remove the extra faces, or split the mesh, before unwrapping.",
        ))

    low, middle, high = _sorted_corners(tris)
    repeated = np.flatnonzero((low == middle) | (middle == high))
    if repeated.size:
        findings.append(Finding(
            "error", "MALFORMED_FACE",
            f"{repeated.size} face(s) use the same vertex twice",
            repeated.astype(np.int64),
            "Delete the degenerate faces; they carry no surface.",
        ))

    keys = _face_keys(low, middle, high)
    _, counts = np.unique(keys, return_counts=True)
    if (counts > 1).any():
        duplicated = np.flatnonzero(np.isin(keys, np.unique(keys)[counts > 1]))
        findings.append(Finding(
            "error", "DUPLICATE_FACE",
            f"{int((counts > 1).sum())} face(s) appear more than once",
            duplicated.astype(np.int64),
            "Delete the duplicates, or merge them by distance, before unwrapping.",
        ))
    return findings


def _layout_checks(tris: np.ndarray, layout: np.ndarray,
                   islands: np.ndarray) -> List[Finding]:
    """Problems the UV layout introduces: flips, collapses and overlaps."""
    findings: List[Finding] = []
    if not tris.size:
        return findings

    corners = layout[tris]
    signed = _signed_areas(corners)
    scale = float(np.abs(signed).max(initial=0.0)) or 1.0

    flipped = np.flatnonzero(signed < 0.0)
    if flipped.size:
        findings.append(Finding(
            "error", "FLIPPED_FACE",
            f"{flipped.size} face(s) are wound the wrong way in UV",
            flipped.astype(np.int64),
            "Reverse those faces, or re-run the layout: a flip displaces the "
            "wrong way and the depth comes out inside out.",
        ))

    collapsed = np.flatnonzero(np.abs(signed) < scale * COLLAPSED_RATIO)
    if collapsed.size:
        findings.append(Finding(
            "error", "DEGENERATE_FACE",
            f"{collapsed.size} face(s) have collapsed to nothing in UV",
            collapsed.astype(np.int64),
            "Give those faces some area, or cut them away with a seam.",
        ))

    overlapping = _overlapping_pairs(tris, corners, islands)
    if overlapping.size:
        findings.append(Finding(
            "error", "UV_OVERLAP",
            f"{overlapping.size // 2} pair(s) of faces cover the same UV area",
            np.unique(overlapping.reshape(-1)),
            "Separate the charts before applying, or re-pack them apart.",
        ))
    return findings


def _signed_areas(corners: np.ndarray) -> np.ndarray:
    first = corners[:, 1] - corners[:, 0]
    second = corners[:, 2] - corners[:, 0]
    return first[:, 0] * second[:, 1] - first[:, 1] * second[:, 0]


def _overlapping_pairs(tris: np.ndarray, corners: np.ndarray,
                       islands: np.ndarray) -> np.ndarray:
    """Face pairs whose UV interiors overlap without being neighbours.

    Charts that share an edge or a corner are packed correctly and are not an
    overlap, so only pairs with no shared vertex are considered. Candidates
    come from a coarse UV grid; the test itself is exact.
    """
    count = tris.shape[0]
    if count < 2:
        return np.zeros((0, 2), dtype=np.int64)

    lows = corners.min(axis=1)
    highs = corners.max(axis=1)
    cell = max(float((highs - lows).max()), 1e-12) / 32.0
    buckets: Dict[Tuple[int, int], List[int]] = {}
    for face in range(count):
        for row in range(int(lows[face, 1] // cell), int(highs[face, 1] // cell) + 1):
            for column in range(int(lows[face, 0] // cell), int(highs[face, 0] // cell) + 1):
                buckets.setdefault((row, column), []).append(face)

    found = set()
    for members in buckets.values():
        for position, first in enumerate(members):
            for second in members[position + 1:]:
                if islands[first] == islands[second]:
                    continue
                if set(tris[first]).intersection(tris[second]):
                    continue
                if _triangles_overlap(corners[first], corners[second]):
                    found.add((min(first, second), max(first, second)))
    if not found:
        return np.zeros((0, 2), dtype=np.int64)
    return np.asarray(sorted(found), dtype=np.int64)


def _triangles_overlap(first: np.ndarray, second: np.ndarray) -> bool:
    """True when two UV triangles share area, not merely touch.

    Clipping one triangle against the other and measuring what is left is exact
    for the cases that matter here: charts packed edge to edge clip down to
    nothing, and two charts stacked in the same place clip down to a full
    triangle. Testing whether a vertex falls inside the other one would miss
    coincident triangles entirely, and those are the worst case of all.
    """
    clipped = _clip_to_triangle(first, second)
    if len(clipped) < 3:
        return False
    shared = abs(_polygon_area(clipped))
    smallest = min(abs(_polygon_area(first)), abs(_polygon_area(second)))
    return shared > smallest * 1e-9


def _clip_to_triangle(subject: np.ndarray, clip: np.ndarray) -> list:
    """Sutherland-Hodgman: cut a polygon down to one triangle's half-planes."""
    polygon = [tuple(point) for point in subject]
    for index in range(3):
        inside_edge = clip[index]
        outside_edge = clip[(index + 1) % 3]
        if not polygon:
            return []
        kept = []
        for position, current in enumerate(polygon):
            following = polygon[(position + 1) % len(polygon)]
            current_in = _side(inside_edge, outside_edge, current) >= 0.0
            following_in = _side(inside_edge, outside_edge, following) >= 0.0
            if current_in:
                kept.append(current)
            if current_in != following_in:
                crossing = _line_crossing(inside_edge, outside_edge, current, following)
                if crossing is not None:
                    kept.append(crossing)
        polygon = kept
    return polygon


def _side(start, end, point) -> float:
    """Which side of a directed edge a point falls on."""
    return (end[0] - start[0]) * (point[1] - start[1]) - \
           (end[1] - start[1]) * (point[0] - start[0])


def _line_crossing(start, end, current, following):
    """Where the segment between two points meets an edge's line."""
    first = _side(start, end, current)
    second = _side(start, end, following)
    span = first - second
    if span == 0.0:
        return None
    ratio = first / span
    return (current[0] + ratio * (following[0] - current[0]),
            current[1] + ratio * (following[1] - current[1]))


def _polygon_area(polygon) -> float:
    total = 0.0
    for index in range(len(polygon)):
        x0, y0 = polygon[index]
        x1, y1 = polygon[(index + 1) % len(polygon)]
        total += x0 * y1 - x1 * y0
    return total * 0.5


def _loose_end_checks(seam_edges: Sequence[Tuple[int, int]]) -> List[Finding]:
    """Seam vertices that end in mid-air: worth showing, not worth failing."""
    degree: Dict[int, int] = {}
    for left, right in seam_edges:
        degree[int(left)] = degree.get(int(left), 0) + 1
        degree[int(right)] = degree.get(int(right), 0) + 1
    ends = sorted(vertex for vertex, count in degree.items() if count == 1)
    if not ends:
        return []
    return [Finding(
        "note", "LOOSE_SEAM_END",
        f"{len(ends)} seam end(s) stop in the middle of the surface",
        np.asarray([], dtype=np.int64),
        "Loose ends are normal when a closed surface is cut open. Extend the "
        "seam or accept it; only close it if the chart needs to be a disc.",
    )]


def _summarise(island: int, faces: np.ndarray) -> ChartSummary:
    """Describe one opened chart."""
    tris = np.asarray(faces, dtype=np.int64).reshape(-1, 3)
    if not tris.size:
        return ChartSummary(int(island), 0, 0, 0, 0, 0, 0)
    edge_count = len(edge_face_counts(tris))
    vertex_count = int(np.unique(tris).size)
    loops = _boundary_loops(tris)
    euler = vertex_count - edge_count + tris.shape[0]
    genus = (2 - loops - euler) // 2
    return ChartSummary(int(island), tris.shape[0], edge_count, vertex_count,
                        euler, loops, genus)
