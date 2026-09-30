"""Integration test for the canvas draw and edit operators (UX-9b, UX-9a).

Geometry decisions live in core and are tested there; what is checked here
is that an operator lands what the core decided, on the canvas, and that a
refused operation leaves nothing behind.
"""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "src"))
sys.path.insert(0, HERE)

import bpy  # noqa: E402
import numpy as np  # noqa: E402
from bscu_fixtures import blank_canvas, fresh_scene, run_suite  # noqa: E402

from bscu.operators import op_draw  # noqa: E402


class TestDrawOperators(unittest.TestCase):
    def setUp(self):
        self.obj = fresh_scene()
        blank_canvas()

    def tearDown(self):
        name = self.obj.name
        blank_canvas()
        if name in bpy.data.objects:
            bpy.data.objects.remove(bpy.data.objects[name], do_unlink=True)

    def test_a_line_is_drawn_where_it_was_asked_for(self):
        bpy.ops.bscu.draw_line(start_mm=(0.0, 0.0), to_mm=(10.0, 5.0))
        canvas = op_draw.canvas_for(bpy.context)

        stroke = list(canvas.strokes.values())[0][0]
        self.assertTrue(np.allclose(stroke.end, [10.0, 5.0]))

    def test_a_zero_length_stroke_is_refused(self):
        result = bpy.ops.bscu.draw_line(start_mm=(1.0, 1.0), to_mm=(1.0, 1.0))

        self.assertEqual(result, {"CANCELLED"})
        self.assertEqual(len(op_draw.canvas_for(bpy.context).strokes), 0)

    def test_a_fillet_replaces_the_two_arms_with_three_pieces(self):
        bpy.ops.bscu.corner(before_start=(0, 0), before_end=(10, 0),
                            after_start=(10, 0), after_end=(10, 10),
                            radius_mm=2.0, fillet=True)
        canvas = op_draw.canvas_for(bpy.context)

        self.assertEqual(len(list(canvas.strokes.values())[0]), 3)

    def test_a_fillet_too_big_for_the_arms_is_refused(self):
        """A refused operator raises, which is how the reason reaches the user."""
        with self.assertRaises(RuntimeError) as caught:
            bpy.ops.bscu.corner(before_start=(0, 0), before_end=(1, 0),
                                after_start=(1, 0), after_end=(1, 10),
                                radius_mm=9.0, fillet=True)

        self.assertIn("only 1.000 mm is there", str(caught.exception))
        self.assertEqual(op_draw.canvas_for(bpy.context).strokes, {})

    def test_extending_pushes_the_end_out(self):
        bpy.ops.bscu.edit_line(start_mm=(0, 0), end_mm=(10, 0), extend_mm=5.0,
                               do_trim=False)
        canvas = op_draw.canvas_for(bpy.context)

        self.assertTrue(np.allclose(list(canvas.strokes.values())[0][0].end, [15.0, 0.0]))

    def test_a_hidden_stroke_stays_on_the_canvas(self):
        bpy.ops.bscu.draw_line(start_mm=(0, 0), to_mm=(10, 0))
        bpy.ops.bscu.canvas_visibility(stroke="stroke-0001", hide=True)
        canvas = op_draw.canvas_for(bpy.context)

        self.assertIn("stroke-0001", canvas.strokes)
        self.assertEqual(len(canvas.to_batches()), 0)

    def test_hiding_a_stroke_that_is_not_there_says_so(self):
        self.assertEqual(bpy.ops.bscu.canvas_visibility(stroke="nope", hide=True),
                         {"CANCELLED"})

    def test_removing_a_stroke_that_is_not_there_says_so(self):
        self.assertEqual(bpy.ops.bscu.remove_stroke(stroke="nope"), {"CANCELLED"})

    def test_a_stroke_survives_being_written_out_and_read_back(self):
        bpy.ops.bscu.draw_line(start_mm=(0, 0), to_mm=(10, 0))
        op_draw.forget(bpy.context.scene.name)

        restored = op_draw.canvas_for(bpy.context)

        self.assertEqual(len(restored.strokes), 1)
        self.assertTrue(np.allclose(list(restored.strokes.values())[0][0].end, [10.0, 0.0]))


def run_test():
    """Run this suite the way tests/run_tests.py expects."""
    run_suite(__name__)


if __name__ == "__main__":
    unittest.main()
