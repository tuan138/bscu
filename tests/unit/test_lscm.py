"""Unit tests for the weighted least-squares conformal map (UX-5, UIUX 3B.4).

LSCM asks for a UV layout that distorts angles as little as possible. A flat,
already-conformal chart is the case where the answer is known in advance, which
makes it the honest way to check the solver. Everything else here pins the
behaviour the brush hints depend on: a heavier face pulls the layout harder, and
pinned vertices stay exactly where they were pinned.
"""

import unittest

import numpy as np

from bscu.core.lscm import ChartProblem, face_areas, solve_chart


def grid_faces(columns: int, rows: int) -> np.ndarray:
    """Triangles over a columns x rows vertex grid, indexed row-major."""
    quads = []
    for row in range(rows - 1):
        for column in range(columns - 1):
            top_left = row * columns + column
            top_right = top_left + 1
            bottom_left = top_left + columns
            bottom_right = bottom_left + 1
            quads.append([top_left, bottom_left, top_right])
            quads.append([top_right, bottom_left, bottom_right])
    return np.asarray(quads, dtype=np.int64)


def grid_coords(columns: int, rows: int, size: float = 1.0) -> np.ndarray:
    """A planar grid layout with coordinates that are generic.

    An axis-aligned grid is a degenerate test case for LSCM: on it, *every*
    function of x alone satisfies the conformal equations, so the chart's null
    space is six-dimensional instead of two and no solver can recover a unique
    layout. Nudging the coordinates off the lattice gives a generic planar
    chart, which is what a real unwrap of a real surface looks like.
    """
    xs = np.linspace(0.0, size, columns)
    ys = np.linspace(0.0, size, rows)
    grid = np.stack(np.meshgrid(xs, ys, indexing="xy"), axis=-1).reshape(-1, 2)
    count = grid.shape[0]
    steps = np.arange(count, dtype=np.float64)
    return grid + 0.04 * np.stack([np.cos(steps * 2.4), np.sin(steps * 1.7)], axis=1)


def corner_angles(triangle: np.ndarray) -> np.ndarray:
    """The three interior angles of a triangle, from three-dimensional points."""
    points = np.asarray(triangle, dtype=np.float64).reshape(3, 3)
    angles = []
    for corner in range(3):
        here = points[corner]
        first = points[(corner + 1) % 3] - here
        second = points[(corner + 2) % 3] - here
        cosine = (first @ second) / (
            np.linalg.norm(first) * np.linalg.norm(second)
        )
        angles.append(np.degrees(np.arccos(np.clip(cosine, -1.0, 1.0))))
    return np.asarray(angles)


def angle_error(positions: np.ndarray, uv: np.ndarray, face: np.ndarray) -> float:
    """How far one face's UV angles are from its real surface angles.

    A conformal map preserves angles, so this is the number a heavier weight
    has to bring down. Measuring the returned coordinates against the input
    coordinates would only measure that the layout moved, which is not the
    property the brush is supposed to buy.
    """
    in_three_d = positions[face]
    laid_out = in_three_d.copy()
    laid_out[:, 0] = uv[face, 0]
    laid_out[:, 1] = uv[face, 1]
    return float(np.abs(corner_angles(in_three_d) - corner_angles(laid_out)).max())


def bowl(flat: np.ndarray, curvature: float) -> np.ndarray:
    """Lift a layout onto a curved surface, so its angles are not conformal."""
    return np.stack(
        [flat[:, 0], flat[:, 1],
         curvature * (flat[:, 0] ** 2 + flat[:, 1] ** 2)],
        axis=1,
    )


def similarity_error(uv: np.ndarray, target: np.ndarray) -> float:
    """Max distance left after the best rigid fit of uv onto target."""
    from bscu.core.math_utils import similarity_fit

    moved = similarity_fit(uv, target).apply(uv)
    return float(np.abs(moved - target).max())


class TestChartProblem(unittest.TestCase):
    def test_flat_grid_comes_back_where_it_started(self):
        """A conformal chart is a fixed point: the map may only move it rigidly."""
        columns = rows = 6
        faces = grid_faces(columns, rows)
        coords = grid_coords(columns, rows)
        problem = ChartProblem(
            faces=faces,
            coords=coords,
            weights=np.ones(len(faces)),
            pins=(0, columns * rows - 1),
        )
        uv, info = solve_chart(problem, iterations=400)

        self.assertTrue(info.converged, info)
        # Two pinned vertices fix translation, scale and rotation, so the
        # recovered layout has to match the input up to a similarity.
        self.assertLess(similarity_error(uv, coords), 1e-3, uv)

    def test_pinned_vertices_land_exactly_where_they_were_pinned(self):
        columns = rows = 5
        faces = grid_faces(columns, rows)
        coords = grid_coords(columns, rows)
        first, last = 0, columns * rows - 1
        problem = ChartProblem(
            faces=faces,
            coords=coords,
            weights=np.ones(len(faces)),
            pins=(first, last),
        )
        uv, _ = solve_chart(problem, iterations=400)

        self.assertTrue(np.allclose(uv[first], coords[first], atol=1e-2), uv[first])
        self.assertTrue(np.allclose(uv[last], coords[last], atol=1e-2), uv[last])

    def test_layout_stays_finite_on_a_degenerate_chart(self):
        """Zero-length edges would make the conformal equations vanish."""
        coords = np.zeros((3, 2))
        faces = np.array([[0, 1, 2]], dtype=np.int64)
        problem = ChartProblem(
            faces=faces,
            coords=coords,
            weights=np.zeros(1),
            pins=(0, 1),
        )
        uv, info = solve_chart(problem, iterations=50)

        self.assertTrue(np.all(np.isfinite(uv)), uv)
        self.assertIsInstance(info.converged, bool)

    def test_an_empty_chart_is_reported_not_guessed(self):
        problem = ChartProblem(
            faces=np.zeros((0, 3), dtype=np.int64),
            coords=np.zeros((2, 2)),
            weights=np.zeros(0),
            pins=(0, 1),
        )
        uv, info = solve_chart(problem, iterations=50)

        self.assertEqual(uv.shape, (2, 2))
        self.assertFalse(info.converged, "an empty chart has no solution to claim")


class TestWeights(unittest.TestCase):
    def test_scaling_every_weight_leaves_the_layout_alone(self):
        """Weights are relative: only how faces compare to each other matters.

        Least squares minimises a sum of weighted terms, so multiplying them all
        by the same number cannot move the answer. A brush that raised every
        region at once therefore changes nothing, which is the honest result.
        """
        columns = rows = 6
        faces = grid_faces(columns, rows)
        coords = grid_coords(columns, rows)
        first, last = 0, columns * rows - 1

        uniform = solve_chart(
            ChartProblem(faces, coords, np.ones(len(faces)), (first, last)), 400
        )[0]
        heavy = solve_chart(
            ChartProblem(faces, coords, np.full(len(faces), 50.0), (first, last)), 400
        )[0]

        self.assertLess(np.abs(heavy - uniform).max(), 1e-6, heavy - uniform)

    def test_a_density_hint_grows_the_painted_face(self):
        """The promise the expand brush makes: the painted area gets bigger."""
        columns = rows = 8
        faces = grid_faces(columns, rows)
        coords = grid_coords(columns, rows)
        first, last = 0, columns * rows - 1
        target = len(faces) // 2

        density = np.ones(len(faces))
        density[target] = 2.0
        plain = solve_chart(
            ChartProblem(faces, coords, np.ones(len(faces)), (first, last), blend=0.5), 400
        )[0]
        hinted = solve_chart(
            ChartProblem(faces, coords, np.ones(len(faces)), (first, last),
                         density=density, blend=0.5), 400
        )[0]

        ratio = np.abs(face_areas(hinted, faces)) / np.abs(face_areas(plain, faces))
        self.assertGreater(ratio[target], 1.5,
                           f"painted face only reached {ratio[target]:.3f}")

    def test_density_redistributes_area_rather_than_inventing_it(self):
        """UV area is a shared budget: one face grows at another's expense.

        This is the honest limit of what a density hint can do, and the reason
        the spec pairs it with a chart that the user can re-run. A solver that
        grew the painted face without shrinking the rest would be handing out
        area from nowhere, and the grid would drift every time it was run.
        """
        columns = rows = 8
        faces = grid_faces(columns, rows)
        coords = grid_coords(columns, rows)
        first, last = 0, columns * rows - 1
        target = len(faces) // 2

        density = np.ones(len(faces))
        density[target] = 2.0
        plain = solve_chart(
            ChartProblem(faces, coords, np.ones(len(faces)), (first, last), blend=0.5), 400
        )[0]
        hinted = solve_chart(
            ChartProblem(faces, coords, np.ones(len(faces)), (first, last),
                         density=density, blend=0.5), 400
        )[0]

        before = np.abs(face_areas(plain, faces)).sum()
        after = np.abs(face_areas(hinted, faces)).sum()
        self.assertLess(after / before, 1.25, "the chart inflated instead of redistributing")
        self.assertLess(np.abs(face_areas(hinted, faces)).min(),
                        np.abs(face_areas(plain, faces)).min(),
                        "some face should have paid for the growth")

    def test_density_hints_stay_where_they_were_painted(self):
        columns = rows = 8
        faces = grid_faces(columns, rows)
        coords = grid_coords(columns, rows)
        first, last = 0, columns * rows - 1
        target = len(faces) // 2

        density = np.ones(len(faces))
        density[target] = 2.0
        plain = solve_chart(
            ChartProblem(faces, coords, np.ones(len(faces)), (first, last), blend=0.5), 400
        )[0]
        hinted = solve_chart(
            ChartProblem(faces, coords, np.ones(len(faces)), (first, last),
                         density=density, blend=0.5), 400
        )[0]

        ratio = np.abs(face_areas(hinted, faces)) / np.abs(face_areas(plain, faces))
        distance = np.abs(np.arange(len(faces)) - target)
        self.assertGreater(ratio[distance <= 6].mean(), ratio[distance > 12].mean() * 2.0,
                           "the effect reached further than it should have")

    def test_keeping_shape_holds_angles_on_a_curved_surface(self):
        """With the blend at zero, the conformal term is what decides."""
        columns = rows = 7
        faces = grid_faces(columns, rows)
        coords = grid_coords(columns, rows)
        positions = bowl(coords, 3.0)
        first, last = 0, columns * rows - 1

        shape_first = solve_chart(
            ChartProblem(faces, coords, np.ones(len(faces)), (first, last), blend=0.0), 400
        )[0]
        self.assertLess(angle_error(positions, shape_first, faces[20]), 1.0)

        size_first = solve_chart(
            ChartProblem(faces, coords, np.ones(len(faces)), (first, last), blend=1.0), 400
        )[0]
        self.assertGreater(angle_error(positions, size_first, faces[20]),
                           angle_error(positions, shape_first, faces[20]))

    def test_negative_weights_are_refused(self):
        """A negative weight inverts the equation it scales."""
        faces = grid_faces(4, 4)
        coords = grid_coords(4, 4)
        weights = np.ones(len(faces))
        weights[0] = -1.0

        with self.assertRaises(ValueError):
            solve_chart(ChartProblem(faces, coords, weights, (0, 15)), 50)

if __name__ == "__main__":
    unittest.main()
