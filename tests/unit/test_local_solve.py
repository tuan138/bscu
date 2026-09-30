"""Unit tests for local solving around a brush stroke (UX-7, UIUX 3B.5).

The spec asks the preview to re-solve *locally* around the stroke while the
user drags, and to re-solve the whole chart when they let go. That is not an
optimisation detail: solving the whole chart on every mouse move is what makes
a live brush impossible, and the measurement is unambiguous - one chart of ten
thousand faces takes about three seconds, so a 10 Hz preview has to do roughly
one three-hundredth of that work.

The property that matters is therefore not just speed but *containment*: a
local solve must not move anything outside the stroke's reach, or the surface
would ripple under the cursor and the user would be watching a lie.
"""

import time
import unittest

import numpy as np

from bscu.core.local_solve import (
    LocalResult,
    patch_around,
    solve_locally,
)
from bscu.core.unwrap_solver import SolverSettings, UnwrapSolver


def grid_faces(columns: int, rows: int) -> np.ndarray:
    quads = []
    for row in range(rows - 1):
        for column in range(columns - 1):
            top_left = row * columns + column
            quads.append([top_left, top_left + columns, top_left + 1])
            quads.append([top_left + 1, top_left + columns, top_left + columns + 1])
    return np.asarray(quads, dtype=np.int64)


def chart(columns: int = 60, rows: int = 60, dome: float = 0.4):
    """A domed chart with a starting layout already on it."""
    from bscu.core.math_utils import plane_frame

    faces = grid_faces(columns, rows)
    xs = np.linspace(0.0, 40.0, columns)
    ys = np.linspace(0.0, 40.0, rows)
    grid = np.stack(np.meshgrid(xs, ys, indexing="xy"), axis=-1).reshape(-1, 2)
    points = np.column_stack([grid, dome * (grid[:, 0] ** 2 + grid[:, 1] ** 2)
                              / 1600.0])
    state = {
        "points": points,
        "faces": faces,
        "islands": np.zeros(len(faces), dtype=np.int64),
        "geometry": float(np.abs(points).sum()),
        "topology": int(faces.size),
        "transform": 1.0,
        "region": "all",
        "seam": (),
        "uv_revision": 0,
    }
    return state, plane_frame(points)


class TestPatchAround(unittest.TestCase):
    def test_the_patch_holds_the_faces_that_reach_the_centre(self):
        state, _layout = chart(20, 20)

        patch = patch_around(state, centre_mm=(20.0, 20.0), radius_mm=4.0)

        self.assertGreater(len(patch.faces), 0)
        self.assertLess(len(patch.faces), len(state["faces"]))

    def test_the_patch_has_its_own_vertex_numbering(self):
        """A patch is solved as a chart in its own right, so it needs local ids."""
        state, _layout = chart(20, 20)

        patch = patch_around(state, centre_mm=(20.0, 20.0), radius_mm=4.0)

        self.assertLessEqual(int(patch.faces.max()), len(patch.vertices) - 1)

    def test_the_patch_remembers_where_its_vertices_live(self):
        state, _layout = chart(20, 20)

        patch = patch_around(state, centre_mm=(20.0, 20.0), radius_mm=4.0)

        original = state["points"]
        picked = original[patch.vertices]
        self.assertEqual(picked.shape[0], len(patch.vertices))

    def test_a_radius_that_reaches_nothing_returns_an_empty_patch(self):
        state, _layout = chart(20, 20)

        patch = patch_around(state, centre_mm=(-500.0, -500.0), radius_mm=2.0)

        self.assertEqual(len(patch.faces), 0)

    def test_a_negative_radius_is_refused(self):
        state, _layout = chart(10, 10)

        with self.assertRaises(ValueError):
            patch_around(state, centre_mm=(5.0, 5.0), radius_mm=-1.0)


class TestLocalSolve(unittest.TestCase):
    def _state(self):
        state, layout = chart(40, 40)
        state["layout"] = layout
        return state

    def test_a_local_solve_leaves_the_rest_of_the_chart_alone(self):
        """A stroke may not ripple the surface outside its own reach."""
        state = self._state()
        solver = UnwrapSolver(SolverSettings(blend=0.0))

        result = solve_locally(solver, state, centre_mm=(20.0, 20.0),
                               radius_mm=5.0)

        moved = np.flatnonzero(np.abs(result.layout - state["layout"]).max(axis=1) > 1e-9)
        touched = set(np.unique(result.patch.faces).tolist()) if result.patch.faces.size else set()
        del touched
        for vertex in moved:
            self.assertIn(int(vertex), result.vertices.tolist(),
                          f"vertex {vertex} moved but is outside the stroke")

    def test_the_untouched_vertices_are_bit_for_bit_identical(self):
        state = self._state()
        solver = UnwrapSolver(SolverSettings(blend=0.0))

        result = solve_locally(solver, state, centre_mm=(20.0, 20.0),
                               radius_mm=5.0)

        outside = np.setdiff1d(np.arange(len(state["layout"])),
                               result.vertices)
        self.assertTrue(np.array_equal(result.layout[outside], state["layout"][outside]))

    def test_a_local_solve_produces_a_layout_for_every_vertex(self):
        state = self._state()
        solver = UnwrapSolver(SolverSettings(blend=0.0))

        result = solve_locally(solver, state, centre_mm=(20.0, 20.0),
                               radius_mm=5.0)

        self.assertEqual(result.layout.shape, state["layout"].shape)
        self.assertTrue(np.all(np.isfinite(result.layout)))

    def test_a_local_solve_says_whether_it_is_current(self):
        state = self._state()
        solver = UnwrapSolver(SolverSettings(blend=0.0))

        result = solve_locally(solver, state, centre_mm=(20.0, 20.0),
                               radius_mm=5.0)

        self.assertIsInstance(result, LocalResult)
        self.assertIsInstance(result.current, bool)

    def test_an_empty_patch_leaves_the_layout_untouched(self):
        state = self._state()
        solver = UnwrapSolver(SolverSettings(blend=0.0))

        result = solve_locally(solver, state, centre_mm=(-900.0, -900.0),
                               radius_mm=2.0)

        self.assertTrue(np.array_equal(result.layout, state["layout"]))
        self.assertFalse(result.current)


class TestLocalSolveIsCheap(unittest.TestCase):
    def test_a_local_solve_costs_a_fraction_of_a_whole_chart_solve(self):
        """The whole point: a drag has to be affordable at ten hertz."""
        state, layout = chart(90, 90)
        state["layout"] = layout
        solver = UnwrapSolver(SolverSettings(blend=0.0))

        started = time.perf_counter()
        local = solve_locally(solver, state, centre_mm=(45.0, 45.0),
                              radius_mm=6.0)
        local_ms = (time.perf_counter() - started) * 1000.0

        started = time.perf_counter()
        solver.preview(state)
        whole_ms = (time.perf_counter() - started) * 1000.0

        self.assertGreater(whole_ms, 0.0)
        self.assertLess(local_ms, whole_ms,
                        f"a local solve ({local_ms:.0f} ms) was no cheaper than "
                        f"the whole chart ({whole_ms:.0f} ms)")
        self.assertLess(len(local.vertices), len(state["layout"]) // 2,
                        "the patch swallowed the chart")

    def test_the_patch_grows_with_the_radius_not_the_chart(self):
        state, layout = chart(90, 90)
        state["layout"] = layout
        solver = UnwrapSolver(SolverSettings(blend=0.0))

        tight = solve_locally(solver, state, centre_mm=(45.0, 45.0), radius_mm=3.0)
        loose = solve_locally(solver, state, centre_mm=(45.0, 45.0), radius_mm=9.0)

        self.assertLess(len(tight.vertices), len(loose.vertices))
        self.assertLess(len(loose.vertices), len(state["layout"]))


if __name__ == "__main__":
    unittest.main()


class TestFocusedPreview(unittest.TestCase):
    """The focused tier: the part of the chart under the cursor moves, fast."""

    def test_a_focus_picks_the_chart_whose_faces_reach_that_point(self):
        from bscu.core.unwrap_solver import UnwrapSolver

        state, _layout = chart(24, 24)
        picked = UnwrapSolver._focused_chart(
            state, (5.0, 5.0), state["points"], state["faces"], state["islands"])

        self.assertEqual(picked, 0)
        self.assertIsNone(UnwrapSolver._focused_chart(
            state, None, state["points"], state["faces"], state["islands"]))

    def test_a_focused_preview_leaves_the_far_side_of_the_chart_alone(self):
        from bscu.core.unwrap_solver import UnwrapSolver

        state, _layout = chart(40, 40)
        solver = UnwrapSolver()
        solver.solve(state)
        whole = solver.preview(state).layout

        # Push the layout near the focus away from where it should be, so the
        # re-solve has something to correct; an already-correct patch is
        # supposed to come back unchanged.
        near, far = (5.0, 5.0), (35.0, 35.0)
        nudged = whole.copy()
        bump = (np.hypot(state["points"][:, 0] - near[0],
                         state["points"][:, 1] - near[1]) < 8.0)
        nudged[bump, 0] += 3.0
        state["layout"] = nudged
        focused = solver.preview(state, focus=near, focus_radius_mm=4.0).layout
        moved = np.linalg.norm(focused - whole, axis=1)
        near_distance = np.hypot(state["points"][:, 0] - near[0],
                                 state["points"][:, 1] - near[1])
        far_distance = np.hypot(state["points"][:, 0] - far[0],
                                state["points"][:, 1] - far[1])

        self.assertLess(float(moved[near_distance < 4.0].max(initial=0.0)), 0.5,
                        "the patch under the focus should be pulled back into place")
        self.assertEqual(float(moved[far_distance > 20.0].max(initial=0.0)), 0.0,
                         "vertices far from the focus must be left alone")

    def test_a_focused_preview_stays_inside_the_interaction_budget(self):
        from bscu.core.unwrap_solver import UnwrapSolver

        state, _layout = chart(120, 120)
        solver = UnwrapSolver()
        solver.solve(state)
        state["layout"] = solver.preview(state).layout

        started = time.perf_counter()
        solver.preview(state, focus=(20.0, 20.0), focus_radius_mm=4.0)
        spent_ms = (time.perf_counter() - started) * 1000.0

        self.assertLess(spent_ms, 100.0,
                        f"a drag frame took {spent_ms:.0f} ms, over the 100 ms budget")
