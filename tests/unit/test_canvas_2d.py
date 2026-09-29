"""Unit tests for the 2D canvas drawn in the viewport (UX-9a, UIUX 1.1).

The canvas shares the 3D viewport rather than taking over the screen, and the
spec is specific about how: top orthographic, on the z = 0 plane, in
millimetres. Those are the properties under test, because a canvas drawn in
perspective or in the wrong unit looks right until someone cuts to it.

The canvas is also the single drawing surface for the whole product - seams,
Caro preview and relief all draw through it - so the batch builder being pure
numpy is what keeps those three from each growing their own drawing code.
"""

import unittest

import numpy as np

from bscu.core.geom2d import Arc, Line
from bscu.draw import batches, canvas_2d
from bscu.draw.canvas_2d import Canvas, canvas_plane
from bscu.draw.seam_overlay import Batch


def square(size: float = 20.0):
    return [Line((0, 0), (size, 0)), Line((size, 0), (size, size)),
            Line((size, size), (0, size)), Line((0, size), (0, 0))]


class TestBatches(unittest.TestCase):
    def test_a_line_becomes_two_points(self):
        built = batches.from_shapes([Line((0, 0), (10, 0))])

        self.assertEqual(built.points.shape, (2, 2))
        self.assertEqual(len(built), 1)

    def test_four_lines_become_four_edges(self):
        built = batches.from_shapes(square())

        self.assertEqual(built.points.shape[0], 8)
        self.assertEqual(len(built), 4)

    def test_points_stay_in_millimetres(self):
        """A canvas in the wrong unit is a part cut at the wrong size."""
        built = batches.from_shapes([Line((0, 0), (137.5, 0))])

        self.assertAlmostEqual(float(built.points[1][0]), 137.5)

    def test_an_arc_becomes_a_run_of_points(self):
        built = batches.from_shapes([Arc((0.0, 0.0), 5.0, 0.0, 90.0)])

        self.assertGreater(built.points.shape[0], 2)
        self.assertTrue(built.sampled)

    def test_a_mixed_list_stops_at_the_change_of_kind(self):
        """A batch never mislabels a curve as straight edges, or the reverse."""
        built = batches.from_shapes([Line((0, 0), (1, 0)),
                                     Arc((0, 0), 5.0, 0.0, 90.0)])

        self.assertFalse(built.sampled)
        self.assertEqual(built.points.shape, (2, 2),
                         "the arc leaked into the straight run")

    def test_a_single_point_geometry_is_skipped(self):
        self.assertEqual(batches.from_shapes([Line((0, 0), (0, 0))]).points.shape[0], 0)

    def test_no_geometry_means_no_batch(self):
        self.assertEqual(batches.from_shapes([]).points.shape, (0, 2))

    def test_a_batch_carries_the_colour_and_width_it_was_given(self):
        built = batches.from_shapes(square(), colour=(1.0, 0.0, 0.0, 1.0), width_px=6.0)

        self.assertEqual(built.colour, (1.0, 0.0, 0.0, 1.0))
        self.assertAlmostEqual(built.width_px, 6.0)

    def test_a_run_of_points_can_be_added_to_the_same_batch(self):
        built = batches.from_shapes([Line((0, 0), (5, 0))])
        grown = built.extend([[5.0, 5.0], [10.0, 5.0]])

        self.assertEqual(grown.points.shape[0], 4)
        self.assertEqual(len(grown), 2)


class TestCanvasPlane(unittest.TestCase):
    def test_the_canvas_sits_on_the_stock_top_face(self):
        plane = canvas_plane(z_mm=12.5)

        self.assertTrue(np.allclose(plane, [0.0, 0.0, 12.5]))

    def test_a_canvas_in_the_working_plane_is_at_zero(self):
        self.assertTrue(np.allclose(canvas_plane(z_mm=0.0), [0.0, 0.0, 0.0]))

    def test_millimetres_become_the_units_the_viewport_uses(self):
        """Blender's scene is metres; the canvas is drawn in millimetres."""
        placed = canvas_2d.to_scene(canvas_plane(z_mm=10.0))

        self.assertAlmostEqual(placed[2], 0.01)

    def test_a_canvas_point_keeps_its_millimetres_in_the_scene(self):
        placed = canvas_2d.to_scene(np.array([25.0, 40.0, 0.0]))

        self.assertAlmostEqual(placed[0], 0.025)
        self.assertAlmostEqual(placed[1], 0.040)


class TestCanvas(unittest.TestCase):
    def test_a_new_canvas_is_empty(self):
        canvas = Canvas()

        self.assertEqual(len(canvas.strokes), 0)
        self.assertEqual(canvas.to_points().shape, (0, 2))

    def test_a_stroke_can_be_removed(self):
        """One stroke is one undo step, so it has to be removable on its own."""
        canvas = Canvas()
        canvas.add_stroke("s1", [Line((0, 0), (5, 0))])

        self.assertTrue(canvas.remove_stroke("s1"))
        self.assertEqual(len(canvas.strokes), 0)

    def test_removing_a_stroke_that_is_not_there_says_so(self):
        self.assertFalse(Canvas().remove_stroke("missing"))

    def test_a_stroke_keeps_its_name(self):
        canvas = Canvas()
        canvas.add_stroke("outline", [Line((0, 0), (1, 0))])

        self.assertIn("outline", canvas.strokes)

    def test_adding_the_same_stroke_twice_replaces_it(self):
        """A re-solved stroke should not appear twice on the canvas."""
        canvas = Canvas()
        canvas.add_stroke("s1", [Line((0, 0), (1, 0))])
        canvas.add_stroke("s1", [Line((0, 0), (2, 0))])

        self.assertEqual(len(canvas.strokes), 1)
        self.assertTrue(np.allclose(canvas.strokes["s1"][0].end, [2.0, 0.0]))

    def test_the_canvas_says_whether_it_has_anything_on_it(self):
        canvas = Canvas()

        self.assertFalse(canvas.has_content())
        canvas.add_stroke("s1", [Line((0, 0), (1, 0))])
        self.assertTrue(canvas.has_content())

    def test_an_empty_stroke_does_not_count_as_content(self):
        canvas = Canvas()
        canvas.add_stroke("s1", [])

        self.assertFalse(canvas.has_content())

    def test_the_canvas_draws_into_batches(self):
        canvas = Canvas()
        canvas.add_stroke("s1", square())
        canvas.add_stroke("s2", [Arc((0.0, 0.0), 5.0, 0.0, 90.0)])

        built = canvas.to_batches()

        self.assertEqual(len(built), 2)
        self.assertFalse(built[0].sampled)
        self.assertTrue(built[1].sampled)

    def test_bounding_the_canvas_covers_every_stroke(self):
        canvas = Canvas()
        canvas.add_stroke("s1", square(20.0))

        low, high = canvas.bounds()

        self.assertTrue(np.allclose(low, [0.0, 0.0]))
        self.assertTrue(np.allclose(high, [20.0, 20.0]))

    def test_an_empty_canvas_has_no_bounds_rather_than_a_fake_one(self):
        self.assertIsNone(Canvas().bounds())

    def test_batches_are_the_same_kind_the_overlay_draws(self):
        """One drawing path for the seam overlay and the canvas, not two."""
        canvas = Canvas()
        canvas.add_stroke("s1", square())

        self.assertIsInstance(canvas.to_batches()[0], Batch)


class TestVisibility(unittest.TestCase):
    def test_a_hidden_stroke_is_not_drawn(self):
        """Hiding is for looking, not for deleting: it is still on the canvas."""
        canvas = Canvas()
        canvas.add_stroke("a", square())
        canvas.add_stroke("b", square(5.0))
        canvas.hide("b")

        drawn = canvas.to_batches()

        self.assertEqual(len(drawn), 1)
        self.assertIn("b", canvas.strokes)

    def test_showing_everything_puts_a_hidden_stroke_back(self):
        canvas = Canvas()
        canvas.add_stroke("a", square())
        canvas.add_stroke("b", square(5.0))
        canvas.hide("b")
        canvas.show_all()

        self.assertEqual(len(canvas.to_batches()), 2)

    def test_hiding_something_that_is_not_there_says_so(self):
        self.assertFalse(Canvas().hide("missing"))


if __name__ == "__main__":
    unittest.main()
