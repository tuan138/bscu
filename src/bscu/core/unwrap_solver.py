"""
The chart unwrap pipeline and its cache (UX-7, UIUX 3.4).

Two tiers, deliberately different jobs:

* **Preview** runs while the user drags. It solves only the charts whose own
  inputs moved, and it is allowed to run out of time - when it does, the
  previous layout stays on screen marked as not current, which is honest and far
  more useful than blanking the viewport, or worse, reporting stale numbers as a
  fresh result.
* **Full** runs when the user stops. It solves everything still missing and
  produces something the validator and the approval step can act on.

Cache keys are per chart, not per mesh. A key that included the whole mesh
would expire every chart the moment any one of them changed, which is exactly
the cost the spec is trying to avoid. A chart's key covers its own geometry and
topology, the shared settings, the region and the UV revision: everything that
can change its answer, and nothing that cannot.

The maths lives in :mod:`bscu.core.lscm`. This module decides *what* to solve,
*when*, and *what may be reused*.
"""

import hashlib
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

from bscu.core.lscm import ChartProblem, solve_chart
from bscu.core.math_utils import plane_frame
from bscu.core.uv_hints import BrushHints


@dataclass(frozen=True)
class SolverSettings:
    """The knobs the panel exposes, all of which change the answer."""

    blend: float = 0.5
    iterations: int = 400
    hint_strength: float = 1.0

    def as_key(self) -> tuple:
        return (round(self.blend, 6), int(self.iterations),
                round(self.hint_strength, 6))


def _digest(*parts) -> int:
    """A short, stable hash of anything stringifiable."""
    hasher = hashlib.blake2b(digest_size=8)
    for part in parts:
        hasher.update(repr(part).encode("utf-8"))
    return int.from_bytes(hasher.digest(), "big")


def revision_of(state: dict, settings: Optional[SolverSettings] = None) -> int:
    """A hash of everything a whole-mesh result depends on.

    Every field the spec lists is in here on purpose. Leaving one out is how a
    preview ends up showing a layout computed for a different shape of the same
    mesh, which is worse than showing nothing.
    """
    settings = settings or SolverSettings()
    return _digest(
        round(float(state.get("geometry", 0.0)), 9),
        int(state.get("topology", 0)),
        round(float(state.get("transform", 1.0)), 9),
        str(state.get("region", "")),
        tuple(sorted(tuple(edge) for edge in state.get("seam", ()))),
        int(state.get("uv_revision", 0)),
        settings.as_key(),
    )


@dataclass
class Preview:
    """One pass of the solver, finished or not."""

    revision: int
    layout: np.ndarray
    islands: np.ndarray
    current: bool = False
    solved: List[int] = field(default_factory=list)
    reused: List[int] = field(default_factory=list)
    elapsed_ms: float = 0.0
    _solver: Optional["UnwrapSolver"] = None

    def finish(self) -> "Preview":
        """Accept this pass as the current result."""
        self.current = True
        if self._solver is not None:
            self._solver.last_finished = self
            self._solver._accepted = max(self._solver._accepted or 0, self.revision)
        return self

    def cancel(self) -> None:
        """Give up on this pass without disturbing the last finished one."""
        self.current = False


class UnwrapSolver:
    """Solves charts, and remembers which ones it has already solved."""

    def __init__(self, settings: Optional[SolverSettings] = None,
                 budget: float = 0.25) -> None:
        self.settings = settings or SolverSettings()
        #: Wall-clock a preview may spend before handing back what it has.
        self.budget = budget
        self.solve_count = 0
        self._cache: Dict[int, np.ndarray] = {}
        self._latest: Optional[int] = None
        self._accepted: Optional[int] = None
        self.last_finished: Optional[Preview] = None

    def is_latest(self, revision: int) -> bool:
        """Whether a result is still worth applying.

        Only a *finished* result can retire an older one. A preview that was
        abandoned - cancelled, or overtaken and thrown away - must not push the
        last good layout out of date, or cancelling would lose the user's work.
        """
        return self._accepted is None or revision >= self._accepted

    def solve(self, state: dict) -> Tuple[np.ndarray, np.ndarray]:
        """The full layout for a mesh state, solving only what is missing."""
        result = self.preview(state)
        result.finish()
        return result.islands, result.layout

    def preview(self, state: dict) -> Preview:
        """One tier of the pipeline, bounded by the time budget.

        Returns whatever it managed: a solved layout, or the previous one if
        the budget ran out first.
        """
        started = time.perf_counter()
        revision = revision_of(state, self.settings)
        points = np.asarray(state["points"], dtype=np.float64)
        faces = np.asarray(state["faces"], dtype=np.int64).reshape(-1, 3)
        islands = np.asarray(state["islands"], dtype=np.int64).ravel()
        hints = _hints_from(state, faces.shape[0])

        layout = self._carried_layout(len(points))
        solved: List[int] = []
        reused: List[int] = []

        for chart in np.unique(islands):
            key = self._chart_key(state, chart, points, faces, islands, hints)
            cached = self._cache.get(key)
            if cached is not None:
                layout[vertices_of(faces, islands, chart)] = cached
                reused.append(int(chart))
                continue
            if solved and (time.perf_counter() - started) > self.budget:
                self._latest = max(self._latest or 0, revision)
                return Preview(revision, layout, islands, False, solved, reused,
                               (time.perf_counter() - started) * 1000.0, self)
            layout = self._solve_chart(chart, points, faces, islands, hints, state,
                                       layout, key)
            solved.append(int(chart))

        self._latest = max(self._latest or 0, revision)
        return Preview(revision, layout, islands, True, solved, reused,
                       (time.perf_counter() - started) * 1000.0, self)

    def _carried_layout(self, vertex_count: int) -> np.ndarray:
        """The last finished layout for a mesh of this size, or a flat one."""
        if self.last_finished is not None and \
                len(self.last_finished.layout) == vertex_count:
            return self.last_finished.layout.copy()
        return np.zeros((vertex_count, 2), dtype=np.float64)

    def _chart_key(self, state: dict, chart, points, faces, islands, hints) -> int:
        """A key covering one chart's own inputs and the shared settings.

        Deliberately not the whole-mesh revision: that would expire every chart
        whenever any one of them changed, which is the cost this design exists
        to avoid.
        """
        member = np.flatnonzero(islands == chart)
        sub_faces = faces[member]
        vertices = np.unique(sub_faces)
        return _digest(
            self.settings.as_key(),
            str(state.get("region", "")),
            round(float(state.get("transform", 1.0)), 9),
            int(state.get("uv_revision", 0)),
            vertices.tobytes(), sub_faces.tobytes(),
            np.ascontiguousarray(points[vertices]).tobytes(),
            np.ascontiguousarray(hints.density[member]).tobytes(),
            np.ascontiguousarray(hints.pin[member]).tobytes(),
            np.ascontiguousarray(hints.priority[member]).tobytes(),
        )

    def _solve_chart(self, chart, points, faces, islands, hints, state, layout,
                     key: int) -> np.ndarray:
        """Solve one chart, file the result, and leave the rest of the mesh be."""
        member = np.flatnonzero(islands == chart)
        sub_faces = faces[member]
        vertices = np.unique(sub_faces)
        lookup = {int(vertex): index for index, vertex in enumerate(vertices)}
        local = np.vectorize(lookup.get, otypes=[np.int64])(sub_faces)

        seed = plane_frame(points[vertices])
        existing = layout[vertices]
        if np.any(np.abs(existing) > 0.0):
            seed = existing.copy()

        problem = ChartProblem(
            faces=local,
            coords=seed,
            weights=np.ones(len(member)),
            pins=_spread_pins(len(vertices)),
            density=hints.density[member],
            blend=self.settings.blend,
        )
        solved, info = solve_chart(problem, iterations=self.settings.iterations)
        self.solve_count += 1
        if info.converged:
            self._cache[key] = solved.copy()
            layout[vertices] = solved
        del state
        return layout


def vertices_of(faces: np.ndarray, islands: np.ndarray, chart) -> np.ndarray:
    """The mesh vertices a chart covers."""
    return np.unique(faces[np.flatnonzero(islands == chart)])


def _spread_pins(vertex_count: int) -> Tuple[int, int]:
    """Two vertices to hold the chart still, as far apart as its numbering goes."""
    if vertex_count < 2:
        return (0, 0)
    return (0, vertex_count - 1)


def _hints_from(state: dict, face_count: int) -> BrushHints:
    """Brush hints for this mesh state, neutral when the state carries none."""
    return BrushHints.from_arrays(
        state.get("density", np.zeros(0)),
        state.get("pin", np.zeros(0)),
        state.get("priority", np.zeros(0)),
        state.get("direction", np.zeros((0, 2))),
        face_count,
    )


__all__ = (
    "Preview",
    "SolverSettings",
    "UnwrapSolver",
    "revision_of",
    "vertices_of",
)
