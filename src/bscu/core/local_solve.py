"""
Local solving around a brush stroke (UX-7, UIUX 3B.5).

The spec asks for two different things from the same solver. While the user
drags, it re-solves *locally* around the stroke so the surface updates under the
cursor. When the user lets go, it re-solves the whole chart. Those are not the
same operation with different settings, and the measurement settles it: one
chart of ten thousand faces takes about three seconds, so a 10 Hz preview has
to do roughly a three-hundredth of that work.

The property that makes a local solve safe is containment. A patch is a chart
in its own right, solved on its own terms, and only the vertices it covers are
written back. Anything outside keeps its coordinates exactly, because a preview
that ripples the surface outside the brush would be showing the user something
other than what the tool would do.
"""

import time
from dataclasses import dataclass, field
from typing import Tuple

import numpy as np

from .lscm import ChartProblem, solve_chart
from .math_utils import plane_frame


@dataclass(frozen=True)
class Patch:
    """A piece of one chart, cut out around a point."""

    faces: np.ndarray
    """(F, 3) faces of the patch, renumbered onto ``vertices``."""

    vertices: np.ndarray
    """The chart's vertex indices the patch owns."""

    positions_mm: np.ndarray
    """Those vertices' positions, for seeding the local frame."""

    def __len__(self) -> int:
        return int(self.faces.shape[0])


@dataclass
class LocalResult:
    """What a local solve produced."""

    layout: np.ndarray
    """The whole chart's layout, with the patch written back."""

    patch: Patch
    vertices: np.ndarray
    current: bool = False
    elapsed_ms: float = 0.0
    issues: list = field(default_factory=list)

    def __bool__(self) -> bool:
        return self.current


def patch_around(state: dict, centre_mm, radius_mm: float) -> Patch:
    """The faces of a chart that reach a point, cut out as their own chart.

    A face is in the patch when any of its corners is within the radius, so a
    stroke cannot leave a one-face gap in its own wake.
    """
    if radius_mm <= 0.0:
        raise ValueError(f"a stroke needs a positive radius, got {radius_mm}")

    faces = np.asarray(state["faces"], dtype=np.int64).reshape(-1, 3)
    points = np.asarray(state["points"], dtype=np.float64).reshape(-1, 3)
    centre = np.asarray(centre_mm, dtype=np.float64).ravel()[:2]
    planar = points[:, :2]

    inside = np.flatnonzero(np.linalg.norm(planar - centre, axis=1) <= radius_mm)
    if inside.size == 0:
        return Patch(np.zeros((0, 3), dtype=np.int64), inside, points[inside])

    corners = np.isin(faces, inside).any(axis=1)
    chosen = faces[corners]
    vertices = np.unique(chosen)
    remap = np.full(int(vertices.max()) + 1, -1, dtype=np.int64)
    remap[vertices] = np.arange(vertices.size)
    return Patch(remap[chosen], vertices, points[vertices])


def solve_locally(solver, state: dict, centre_mm, radius_mm: float,
                  hints=None) -> LocalResult:
    """Re-solve only the patch around a stroke, and write back just that much.

    ``state`` carries a ``layout`` key: the layout currently on screen. Without
    one there is nothing to be local to, and the caller should run a full solve
    instead.
    """
    started = time.perf_counter()
    patch = patch_around(state, centre_mm, radius_mm)
    current = np.asarray(state.get("layout", np.zeros((0, 2))), dtype=np.float64)

    if patch.faces.size == 0:
        return LocalResult(current, patch, patch.vertices, False,
                           (time.perf_counter() - started) * 1000.0)

    seed = plane_frame(patch.positions_mm)
    if current.shape[0] == len(np.asarray(state["points"])):
        existing = current[patch.vertices]
        if np.any(np.abs(existing) > 0.0):
            seed = existing.copy()

    problem = ChartProblem(
        faces=patch.faces,
        coords=seed,
        weights=np.ones(len(patch)),
        pins=_spread_pins(len(patch.vertices)),
        blend=getattr(solver.settings, "blend", 0.0),
    )
    solved, info = solve_chart(problem,
                               iterations=getattr(solver.settings, "iterations", 400))

    layout = current.copy()
    layout[patch.vertices] = solved
    issues = [] if info.converged else [
        "the patch around the stroke did not converge, so it was left as it was"]
    return LocalResult(layout, patch, patch.vertices, info.converged,
                       (time.perf_counter() - started) * 1000.0, issues)


def full_solve(solver, state: dict) -> LocalResult:
    """Re-solve the whole chart, which is what happens when the stroke ends.

    Returned in the same shape as a local solve so the two tiers of the preview
    can be swapped without the caller changing shape.
    """
    started = time.perf_counter()
    preview = solver.preview(state)
    vertices = np.arange(preview.layout.shape[0], dtype=np.int64)
    patch = Patch(preview.islands, vertices,
                  np.asarray(state["points"], dtype=np.float64))
    return LocalResult(preview.layout, patch, vertices, preview.current,
                       (time.perf_counter() - started) * 1000.0)


def _spread_pins(vertex_count: int) -> Tuple[int, int]:
    if vertex_count < 2:
        return (0, 0)
    return (0, vertex_count - 1)


__all__ = ("LocalResult", "Patch", "full_solve", "patch_around", "solve_locally")
