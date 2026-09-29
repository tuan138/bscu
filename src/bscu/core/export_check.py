"""
Pre-export checks (UX-11, UIUX 9.3 and 9.4).

A relief is only worth exporting if the mesh a cutter will read is closed,
correctly wound, and the right size. Those are checkable facts, so they are
checked here rather than discovered at the machine.

The dimensional check is the interesting one. The spec allows 0.05 mm, which is
small enough that the comparison has to happen on the *evaluated* surface
rather than on control points: a mesh whose control cage is right can still
come out the wrong size once a profile is applied.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

import numpy as np

#: The spec's tolerance for exported dimensions.
TOLERANCE_MM = 0.05

#: A wall thinner than this is reported; the spec leaves the limit to the job.
DEFAULT_MIN_WALL_MM = 1.0

#: A triangle with an edge shorter than this is a sliver, not a face.
DEGENERATE_EDGE_MM = 1e-6


@dataclass
class Check:
    """One thing to tell the user before they export."""

    code: str
    ok: bool
    message: str
    detail: str = ""


@dataclass
class ExportReport:
    """Everything the export panel shows, in one place."""

    checks: List[Check] = field(default_factory=list)
    watertight: bool = False
    max_error_mm: float = 0.0
    min_wall_mm: float = float("inf")

    @property
    def failures(self) -> List[Check]:
        return [check for check in self.checks if not check.ok]

    @property
    def passed(self) -> bool:
        return not self.failures


def check_watertight(faces: np.ndarray) -> Check:
    """Whether the mesh is closed and consistently wound.

    Every edge must be used exactly twice, once in each direction. An edge used
    twice in the same direction is a flipped face, which reads as watertight to
    a naive edge count and shows up as an inside-out relief.
    """
    tris = np.asarray(faces, dtype=np.int64).reshape(-1, 3)
    if not tris.size:
        return Check("WATERTIGHT", False, "the mesh has no faces to export")

    directed = np.concatenate([tris[:, [0, 1]], tris[:, [1, 2]], tris[:, [2, 0]]])
    stride = int(directed.max()) + 1
    stride = max(stride, 1)
    forward = directed[:, 0].astype(np.int64) * stride + directed[:, 1]
    backward = directed[:, 1].astype(np.int64) * stride + directed[:, 0]

    # Each undirected edge of a closed mesh is used exactly twice, once from
    # each side. Counting directed edges would call every one of them single.
    undirected = np.minimum(forward, backward)
    unique, counts = np.unique(undirected, return_counts=True)
    single = int((counts == 1).sum())
    if single:
        return Check("WATERTIGHT", False,
                     f"{single} edge(s) are used once, so the mesh is open",
                     "close the chart with a seam before exporting")

    crowded = int((counts > 2).sum())
    if crowded:
        return Check("WATERTIGHT", False,
                     f"{crowded} edge(s) are shared by more than two faces",
                     "the mesh has non-manifold edges")

    # A closed mesh runs every edge once in each direction. An edge used twice
    # the same way is a flipped face: an edge count alone would call that
    # watertight, and the relief would come out inside out.
    both = set(np.unique(forward).tolist())
    if both != set(np.unique(backward).tolist()):
        mismatched = len(both.symmetric_difference(set(np.unique(backward).tolist())))
        return Check("WATERTIGHT", False,
                     f"{mismatched} edge(s) run the same way in both faces",
                     "the mesh is wound inconsistently")

    return Check("WATERTIGHT", True, "the mesh is closed and consistently wound")


def check_dimensions(measured_mm: Sequence[float], expected_mm: Sequence[float],
                     tolerance_mm: float = TOLERANCE_MM) -> Tuple[Check, float]:
    """Compare measured extents against what the design asked for.

    This compares the surface the cutter will actually see, not the design's
    control points. A cage can be the right size and the relief still come out
    wrong, and that is the case worth catching.
    """
    measured = np.asarray(measured_mm, dtype=np.float64).ravel()
    expected = np.asarray(expected_mm, dtype=np.float64).ravel()
    if measured.size != expected.size:
        raise ValueError(f"got {measured.size} measured extents and "
                         f"{expected.size} expected ones; they must match")
    if measured.size == 0:
        return Check("DIMENSIONS", True, "nothing to compare"), 0.0

    error = float(np.abs(measured - expected).max())
    if error <= tolerance_mm:
        return Check("DIMENSIONS", True,
                     f"within {error:.4f} mm of the design"), error
    return Check("DIMENSIONS", False,
                 f"off by {error:.4f} mm, more than the {tolerance_mm} mm allowed",
                 "check the stock size, the transform and the layout scale"), error


def check_walls(remaining_mm: np.ndarray, minimum_mm: float = DEFAULT_MIN_WALL_MM
                ) -> Tuple[Check, float]:
    """Whether any part of the cut is left thinner than the job allows."""
    remaining = np.asarray(remaining_mm, dtype=np.float64).ravel()
    if remaining.size == 0:
        return Check("WALLS", True, "no surface to measure"), float("inf")
    thinnest = float(remaining.min())
    if thinnest < minimum_mm:
        return Check("WALLS", False,
                     f"a wall is down to {thinnest:.3f} mm, under the "
                     f"{minimum_mm} mm minimum",
                     "raise the base, reduce the cut, or allow a thinner wall "
                     "for this job"), thinnest
    return Check("WALLS", True, f"thinnest wall is {thinnest:.3f} mm"), thinnest


def check_degenerate(verts_mm: np.ndarray, faces: np.ndarray) -> Check:
    """Whether any triangle has collapsed or is a sliver."""
    points = np.asarray(verts_mm, dtype=np.float64).reshape(-1, 3)
    tris = np.asarray(faces, dtype=np.int64).reshape(-1, 3)
    if not tris.size:
        return Check("DEGENERATE", False, "the mesh has no faces")

    corners = points[tris]
    lengths = np.linalg.norm(np.roll(corners, -1, axis=1) - corners, axis=2)
    short = int((lengths.min(axis=1) < DEGENERATE_EDGE_MM).sum())
    if short:
        return Check("DEGENERATE", False,
                     f"{short} face(s) have an edge under {DEGENERATE_EDGE_MM} mm",
                     "remove the collapsed faces before exporting")

    area = 0.5 * np.linalg.norm(np.cross(
        corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0]), axis=1)
    flat = int((area < DEGENERATE_EDGE_MM).sum())
    if flat:
        return Check("DEGENERATE", False,
                     f"{flat} face(s) have no area",
                     "a face with no area cannot be cut")
    return Check("DEGENERATE", True, "no collapsed or zero-area faces")


def build_report(verts_mm, faces, measured_mm, expected_mm,
                 remaining_mm: Optional[np.ndarray] = None,
                 minimum_wall_mm: float = DEFAULT_MIN_WALL_MM,
                 tolerance_mm: float = TOLERANCE_MM) -> ExportReport:
    """Run every check and collect the answers for the export panel."""
    tris = np.asarray(faces, dtype=np.int64).reshape(-1, 3)
    report = ExportReport()

    report.checks.append(check_watertight(tris))
    report.checks.append(check_degenerate(verts_mm, tris))

    dimensions, error = check_dimensions(measured_mm, expected_mm, tolerance_mm)
    report.checks.append(dimensions)
    report.max_error_mm = error
    report.watertight = report.checks[0].ok

    if remaining_mm is not None:
        walls, thinnest = check_walls(remaining_mm, minimum_wall_mm)
        report.checks.append(walls)
        report.min_wall_mm = thinnest
    return report


__all__ = (
    "DEFAULT_MIN_WALL_MM",
    "TOLERANCE_MM",
    "Check",
    "ExportReport",
    "build_report",
    "check_degenerate",
    "check_dimensions",
    "check_walls",
    "check_watertight",
)
