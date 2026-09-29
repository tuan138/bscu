"""Unit tests for the two-tier unwrap solver (UX-7, UIUX 3.4).

The rules being pinned here are the ones that stop a preview from quietly
becoming the answer:

* The cache key covers geometry, topology, transform, region, seam, UV and
  solver settings. A mesh can change shape while its seam stays put, so keying
  on the seam alone would serve a layout that no longer fits.
* Only the charts whose key moved are recomputed. That is what makes a
  10 Hz preview possible on a chart of any size, and it is the difference
  between a live drag and a freeze.
* A preview that runs out of its time budget returns the previous layout
  labelled as not current. It never returns stale numbers as a fresh result.
"""

import unittest

import numpy as np

from bscu.core.unwrap_solver import (
    SolverSettings,
    UnwrapSolver,
    revision_of,
)


def grid_faces(columns: int, rows: int) -> np.ndarray:
    quads = []
    for row in range(rows - 1):
        for column in range(columns - 1):
            top_left = row * columns + column
            quads.append([top_left, top_left + columns, top_left + 1])
            quads.append([top_left + 1, top_left + columns, top_left + columns + 1])
    return np.asarray(quads, dtype=np.int64)


def grid_points(columns: int, rows: int, dome: float = 0.0) -> np.ndarray:
    xs = np.linspace(0.0, 1.0, columns)
    ys = np.linspace(0.0, 1.0, rows)
    grid = np.stack(np.meshgrid(xs, ys, indexing="xy"), axis=-1).reshape(-1, 2)
    count = grid.shape[0]
    steps = np.arange(count, dtype=np.float64)
    # A nudge off the lattice, because a regular grid is degenerate for LSCM.
    grid = grid + 0.04 * np.stack([np.cos(steps * 2.4), np.sin(steps * 1.7)], axis=1)
    return np.column_stack([grid, np.full(count, dome * (grid[:, 0] ** 2 + grid[:, 1] ** 2))])


def two_charts() -> tuple:
    """Two separate grid patches, as two charts of one mesh."""
    left_faces = grid_faces(4, 4)
    right_faces = grid_faces(4, 4) + 16
    faces = np.vstack([left_faces, right_faces])
    points = np.vstack([grid_points(4, 4), grid_points(4, 4) + [1.5, 0.0, 0.0]])
    islands = np.concatenate([np.zeros(len(left_faces), dtype=np.int64),
                              np.ones(len(right_faces), dtype=np.int64)])
    return points, faces, islands


def _moved(state: dict, chart: int) -> dict:
    """The same mesh with one chart's surface lifted, and its summary updated."""
    points = state["points"].copy()
    span = np.arange(16 * chart, 16 * (chart + 1))
    points[span, 2] += 0.01
    changed = dict(state)
    changed["points"] = points
    changed["geometry"] = float(np.abs(points).sum())
    return changed


def seed_state() -> dict:
    points, faces, islands = two_charts()
    return {
        "points": points,
        "faces": faces,
        "islands": islands,
        "geometry": float(np.abs(points).sum()),
        "topology": faces.size,
        "transform": 1.0,
        "region": "all",
        "seam": (),
        "uv_revision": 0,
    }


class TestRevisionKey(unittest.TestCase):
    def test_the_same_inputs_give_the_same_revision(self):
        state = seed_state()

        self.assertEqual(revision_of(state), revision_of(dict(state)))

    def test_moving_the_geometry_expires_the_revision(self):
        """A seam can stay put while the surface under it changes shape."""
        before = seed_state()
        after = dict(before)
        after["geometry"] = before["geometry"] + 1e-9

        self.assertNotEqual(revision_of(before), revision_of(after))

    def test_every_input_the_spec_lists_is_part_of_the_key(self):
        base = seed_state()
        for field, value in [("topology", 999), ("transform", 2.0), ("region", "front"),
                             ("seam", ((0, 1),)), ("uv_revision", 7)]:
            changed = dict(base)
            changed[field] = value
            with self.subTest(field=field):
                self.assertNotEqual(revision_of(base), revision_of(changed))

    def test_solver_settings_are_part_of_the_key(self):
        state = seed_state()

        self.assertNotEqual(
            revision_of(state, SolverSettings(blend=0.0)),
            revision_of(state, SolverSettings(blend=1.0)),
        )

    def test_the_revision_is_a_plain_hashable_value(self):
        self.assertIsInstance(revision_of(seed_state()), int)


class TestCaching(unittest.TestCase):
    def setUp(self):
        self.state = seed_state()
        self.solver = UnwrapSolver(SolverSettings(blend=0.0))

    def test_a_second_identical_request_is_served_from_cache(self):
        first = self.solver.solve(self.state)
        first_solves = self.solver.solve_count

        second = self.solver.solve(self.state)

        self.assertEqual(first_solves, self.solver.solve_count)
        self.assertTrue(np.array_equal(first[1], second[1]))

    def test_changing_geometry_recomputes_rather_than_reusing(self):
        self.solver.solve(self.state)
        before = self.solver.solve_count
        moved = _moved(self.state, chart=0)

        self.solver.solve(moved)

        self.assertGreater(self.solver.solve_count, before)

    def test_only_the_chart_whose_input_moved_is_recomputed(self):
        """This is what makes a live drag affordable on a large mesh."""
        self.solver.solve(self.state)
        before = self.solver.solve_count

        self.solver.solve(_moved(self.state, chart=0))

        self.assertEqual(self.solver.solve_count - before, 1,
                         "the untouched chart should have come from cache")

    def test_the_cached_chart_comes_back_unchanged(self):
        first = self.solver.solve(self.state)
        second = self.solver.solve(_moved(self.state, chart=0))

        untouched = np.arange(16, 32)
        self.assertTrue(np.array_equal(first[1][untouched], second[1][untouched]),
                        "the chart that did not change moved anyway")


class TestTwoTiers(unittest.TestCase):
    def setUp(self):
        self.state = seed_state()

    def test_a_preview_works_without_waiting_for_the_full_check(self):
        solver = UnwrapSolver(SolverSettings(blend=0.5))

        preview = solver.preview(self.state)

        self.assertTrue(preview.layout is not None)
        self.assertEqual(sorted(preview.solved + preview.reused), [0, 1])
        self.assertTrue(np.any(np.abs(preview.layout) > 0.0),
                        "the preview produced no layout at all")

    def test_a_full_solve_reports_itself_as_current(self):
        solver = UnwrapSolver(SolverSettings(blend=0.5))

        done = solver.preview(self.state)
        done.finish()

        self.assertTrue(done.current)

    def test_a_preview_that_runs_out_of_time_keeps_the_untouched_charts(self):
        """Progress is kept, the rest stays as it was, and the pass is marked.

        Blanketing the viewport on a slow pass would be worse than showing a
        layout that is one chart ahead, as long as it is not passed off as
        current.
        """
        solver = UnwrapSolver(SolverSettings(blend=0.5))
        first = solver.preview(self.state)
        first.finish()

        # An empty cache, so there is real work left when the budget runs out.
        impatient = UnwrapSolver(SolverSettings(blend=0.5), budget=0.0)
        impatient.last_finished = first
        late = impatient.preview(_moved(self.state, chart=0))

        self.assertFalse(late.current, "an unfinished pass was reported as current")
        self.assertEqual(late.solved, [0], "the pass should have stopped after one chart")
        self.assertTrue(np.any(np.abs(late.layout) > 0.0),
                        "the viewport would have gone blank")
        untouched = np.arange(16, 32)
        self.assertTrue(np.array_equal(late.layout[untouched], first.layout[untouched]),
                        "a chart that was not re-solved moved anyway")

    def test_a_finished_result_is_not_rewritten_by_an_older_revision(self):
        solver = UnwrapSolver(SolverSettings(blend=0.5))
        stale = solver.preview(self.state)
        stale.finish()
        fresh = solver.preview(_moved(self.state, chart=0))

        self.assertGreater(fresh.revision, stale.revision)
        self.assertTrue(solver.is_latest(fresh.revision))
        fresh.finish()
        self.assertFalse(solver.is_latest(stale.revision),
                         "a finished newer result has to retire the older one")

    def test_cancelling_keeps_the_last_finished_result(self):
        solver = UnwrapSolver(SolverSettings(blend=0.5))
        finished = solver.preview(self.state)
        finished.finish()

        solver.preview(_moved(self.state, chart=0)).cancel()

        self.assertTrue(solver.is_latest(finished.revision))
        self.assertEqual(solver.last_finished, finished)

    def test_the_solved_layout_has_a_coordinate_for_every_vertex(self):
        solver = UnwrapSolver(SolverSettings(blend=0.0))

        result = solver.solve(self.state)

        self.assertEqual(result[1].shape, (len(self.state["points"]), 2))


if __name__ == "__main__":
    unittest.main()
