"""Unit tests for chart selection and packing (UX-8, UIUX 4.3, 4.7).

Two promises are pinned here.

**Packing never changes the projection.** A packed layout may only move a
chart. Rotating one, rescaling one, or letting two charts share UV area would
all mean the millimetre a pixel covers depends on where it landed, which is
exactly the distortion the whole pipeline exists to remove.

**A broken candidate never overwrites a good layout.** The user's work is the
thing at risk, so the write is refused while anything in the candidate is an
error, and the refusal has to say why.
"""

import unittest

import numpy as np

from bscu.core.uv_refine import (
    PackingReport,
    pack_charts,
    top_down_charts,
)


def grid_faces(columns: int, rows: int, offset: int = 0) -> np.ndarray:
    quads = []
    for row in range(rows - 1):
        for column in range(columns - 1):
            top_left = offset + row * columns + column
            quads.append([top_left, top_left + columns, top_left + 1])
            quads.append([top_left + 1, top_left + columns, top_left + columns + 1])
    return np.asarray(quads, dtype=np.int64)


def grid_points(columns: int, rows: int, offset: int = 0, dome: float = 0.0):
    xs = np.linspace(0.0, 0.4, columns) + offset
    ys = np.linspace(0.0, 0.4, rows)
    grid = np.stack(np.meshgrid(xs, ys, indexing="xy"), axis=-1).reshape(-1, 2)
    count = grid.shape[0]
    steps = np.arange(count, dtype=np.float64)
    grid = grid + 0.01 * np.stack([np.cos(steps * 2.4), np.sin(steps * 1.7)], axis=1)
    return np.column_stack([grid, np.full(count, dome * (grid[:, 0] ** 2
                                                         + grid[:, 1] ** 2))])


def joined_grid(columns: int, rows: int):
    """One connected grid, big enough to be worth splitting."""
    points = grid_points(columns, rows, dome=0.2)
    return points, grid_faces(columns, rows)


def joined_panels(count: int):
    """``count`` grid panels laid side by side, sharing no vertices."""
    faces = []
    points = []
    for index in range(count):
        faces.append(grid_faces(4, 4, offset=index * 16))
        points.append(grid_points(4, 4, offset=index * 0.6))
    return np.vstack(points), np.vstack(faces)


class TestTopDownSearch(unittest.TestCase):
    def test_a_connected_surface_can_be_reduced_to_the_asked_number_of_charts(self):
        points, faces = joined_grid(8, 8)

        charts = top_down_charts(points, faces, target_charts=2, max_distortion=1e9)

        self.assertEqual(len(charts), 2, f"asked for 2, got {len(charts)}")

    def test_pieces_with_nothing_in_common_stay_apart(self):
        """A chart has to be connected; there is no merge across a gap.

        Panels that share no vertex cannot become one chart however permissive
        the ceiling is, and pretending otherwise would produce a layout with a
        hole the validator would reject later.
        """
        points, faces = joined_panels(4)

        charts = top_down_charts(points, faces, target_charts=2, max_distortion=1e9)

        self.assertEqual(len(charts), 4)

    def test_the_answer_covers_every_face_exactly_once(self):
        points, faces = joined_panels(4)

        charts = top_down_charts(points, faces, target_charts=2, max_distortion=1e9)

        seen = np.concatenate([np.asarray(chart, dtype=np.int64) for chart in charts])
        self.assertEqual(sorted(seen.tolist()), list(range(len(faces))),
                         "a face was left out or listed twice")

    def test_a_ceiling_that_cannot_be_met_is_reported_not_faked(self):
        """Asking for one chart from a shape that will not lie flat is a no-go."""
        columns = rows = 8
        faces = grid_faces(columns, rows)
        xs = np.linspace(0, 1, columns)
        ys = np.linspace(0, 1, rows)
        grid = np.stack(np.meshgrid(xs, ys, indexing="xy"), axis=-1).reshape(-1, 2)
        points = np.column_stack([grid, 30.0 * (grid[:, 0] ** 2 + grid[:, 1] ** 2)])

        charts = top_down_charts(points, faces, target_charts=1, max_distortion=0.01)

        self.assertGreater(len(charts), 1, "the gate was ignored and a bad chart passed")

    def test_a_single_chart_request_on_a_flat_panel_keeps_one_chart(self):
        points, faces = joined_grid(6, 6)

        charts = top_down_charts(points, faces, target_charts=1, max_distortion=1e9)

        self.assertEqual(len(charts), 1)

    def test_an_empty_mesh_produces_no_charts(self):
        self.assertEqual(top_down_charts(np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int64),
                                         4, 1.0), [])

    def test_mismatched_geometry_and_topology_is_refused(self):
        faces = np.array([[0, 1, 2], [1, 2, 3]], dtype=np.int64)

        with self.assertRaises(ValueError):
            top_down_charts(np.zeros((3, 3)), faces, 1, 1.0)


class TestPacking(unittest.TestCase):
    def _layout(self):
        """Three panels, one chart each, laid out as the solver left them."""
        points, faces = joined_panels(3)
        islands = np.concatenate([np.full(len(grid_faces(4, 4)), index)
                                  for index in range(3)])
        layout = points[:, :2].copy()
        return points, faces, islands, layout

    @staticmethod
    def _chart_vertices(faces, islands, chart):
        """A chart's own vertices; islands label faces and layouts label vertices."""
        return np.unique(faces[islands == chart])

    def test_packing_moves_a_chart_and_never_rotates_or_rescales_it(self):
        """The projection is the promise; packing may only translate."""
        points, faces, islands, layout = self._layout()

        packed, report = pack_charts(layout, faces, islands)

        self.assertIsInstance(report, PackingReport)
        for index in np.unique(islands):
            span = self._chart_vertices(faces, islands, index)
            offset = packed[span] - layout[span]
            self.assertLess(np.abs(offset - offset[0]).max(), 1e-9,
                            f"chart {index} was moved by more than a translation")

    def test_packing_ends_up_inside_the_unit_square(self):
        points, faces, islands, layout = self._layout()

        packed, _ = pack_charts(layout, faces, islands)

        self.assertGreaterEqual(packed.min(), -1e-9)
        self.assertLessEqual(packed.max(), 1.0 + 1e-9)

    def test_packing_does_not_scale_a_chart_to_fit(self):
        """A chart that does not fit is left big and reported, not shrunk."""
        points, faces, islands, layout = self._layout()
        layout[:, 0] *= 3.0  # far too wide for the unit square

        packed, report = pack_charts(layout, faces, islands)

        span = self._chart_vertices(faces, islands, 0)
        width_before = layout[span, 0].max() - layout[span, 0].min()
        width_after = packed[span, 0].max() - packed[span, 0].min()
        self.assertAlmostEqual(width_before, width_after, places=9)
        self.assertTrue(report.overflow,
                        "a layout that does not fit should say so")

    def test_packed_charts_do_not_overlap(self):
        points, faces, islands, layout = self._layout()

        packed, report = pack_charts(layout, faces, islands)

        self.assertEqual(report.overlaps, [], report.overlaps)

    def test_packing_moves_every_chart_exactly_once(self):
        points, faces, islands, layout = self._layout()

        packed, report = pack_charts(layout, faces, islands)

        self.assertEqual(len(report.moves), len(np.unique(islands)))
        self.assertEqual(packed.shape, layout.shape)
        moved = set(chart for chart, _ in report.moves)
        self.assertEqual(moved, {int(c) for c in np.unique(islands)})

    def test_a_single_chart_is_packed_without_moving_it_relatively(self):
        points, faces = joined_panels(1)
        islands = np.zeros(len(faces), dtype=np.int64)
        layout = np.column_stack([points[:, 0], points[:, 1]])

        packed, _ = pack_charts(layout, faces, islands)

        span = np.unique(faces[islands == 0])
        self.assertAlmostEqual(packed[span, 0].max() - packed[span, 0].min(),
                               layout[span, 0].max() - layout[span, 0].min(),
                               places=12)


if __name__ == "__main__":
    unittest.main()
