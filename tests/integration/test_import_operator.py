"""Integration test for the vector import and template operators (UX-13).

A template that has no geometry still *looks* like it works right up until
someone places one, so the mesh is checked for the geometry it should have.
"""

import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "src"))
sys.path.insert(0, HERE)

import bpy  # noqa: E402
import numpy as np  # noqa: E402
from bscu_fixtures import blank_canvas, fresh_scene, run_suite  # noqa: E402

from bscu.operators import op_draw, op_import_vector  # noqa: E402


class TestImportOperator(unittest.TestCase):
    def setUp(self):
        self.obj = fresh_scene()
        blank_canvas()
        self.folder = tempfile.mkdtemp(prefix="bscu_import_")

    def tearDown(self):
        for entry in os.listdir(self.folder):
            os.remove(os.path.join(self.folder, entry))
        os.rmdir(self.folder)
        name = self.obj.name
        blank_canvas()
        if name in bpy.data.objects:
            bpy.data.objects.remove(bpy.data.objects[name], do_unlink=True)

    def _write(self, name: str, text: str) -> str:
        path = os.path.join(self.folder, name)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
        return path

    def test_an_svg_lands_on_the_canvas_in_millimetres(self):
        path = self._write("plate.svg",
                           '<svg xmlns="http://www.w3.org/2000/svg" '
                           'width="100mm" height="50mm" viewBox="0 0 100 50">'
                           '<path d="M0 0 L50 0 L50 25"/></svg>')

        bpy.ops.bscu.import_vector(filepath=path)

        canvas = op_draw.canvas_for(bpy.context)
        self.assertIn("plate", canvas.strokes)
        self.assertTrue(np.allclose(canvas.strokes["plate"][0].end, [50.0, 0.0]))

    def test_an_unknown_extension_is_refused_by_name(self):
        path = self._write("notes.txt", "not a drawing")

        with self.assertRaises(RuntimeError) as caught:
            bpy.ops.bscu.import_vector(filepath=path)

        self.assertIn("not a format", str(caught.exception))

    def test_a_file_with_nothing_in_it_writes_no_stroke(self):
        path = self._write("empty.svg",
                           '<svg xmlns="http://www.w3.org/2000/svg" '
                           'width="10mm" height="10mm"></svg>')

        with self.assertRaises(RuntimeError):
            bpy.ops.bscu.import_vector(filepath=path)

        self.assertEqual(op_draw.canvas_for(bpy.context).strokes, {})

    def test_a_template_is_a_copy_and_its_instances_share_the_geometry(self):
        bpy.ops.bscu.draw_line(start_mm=(0, 0), to_mm=(10, 0), snap_links=False)
        bpy.ops.bscu.make_template(name="rosette")
        template = bpy.data.objects["rosette"]

        copy = op_import_vector.place_instance(template, (0.01, 0.0, 0.0))

        self.assertIsNot(copy, template)
        self.assertIs(copy.data, template.data)
        self.assertEqual(len(op_import_vector.instances_of(template)), 1)

    def test_a_template_actually_carries_the_drawn_geometry(self):
        """An empty mesh would make the feature look fine and place nothing."""
        bpy.ops.bscu.draw_line(start_mm=(0, 0), to_mm=(10, 0), snap_links=False)
        bpy.ops.bscu.draw_line(start_mm=(0, 0), to_mm=(0, 8), snap_links=False)
        bpy.ops.bscu.make_template(name="filled")
        template = bpy.data.objects["filled"]

        self.assertGreater(len(template.data.vertices), 0, "the template is empty")
        self.assertGreater(len(template.data.edges), 0, "the template has no edges")
        self.assertAlmostEqual(template.dimensions.x * 1000.0, 10.0, places=3,
                               msg="the template is not the size it was drawn at")

    def test_a_placed_instance_is_shown_where_the_template_was(self):
        bpy.ops.bscu.draw_line(start_mm=(0, 0), to_mm=(10, 0), snap_links=False)
        bpy.ops.bscu.make_template(name="placed")
        template = bpy.data.objects["placed"]

        copy = op_import_vector.place_instance(template, (0.02, 0.0, 0.0))

        self.assertGreater(len(copy.data.vertices), 0)
        self.assertAlmostEqual(copy.location.x, 0.02)

    def test_importing_the_same_file_twice_keeps_both_layers(self):
        path = self._write("twice.svg",
                           '<svg xmlns="http://www.w3.org/2000/svg" '
                           'width="100mm" height="50mm" viewBox="0 0 100 50">'
                           '<path d="M0 0 L50 0"/></svg>')

        bpy.ops.bscu.import_vector(filepath=path)
        bpy.ops.bscu.import_vector(filepath=path)

        self.assertEqual(len(op_draw.canvas_for(bpy.context).strokes), 2)

    def test_an_svg_without_a_view_box_is_read_as_pixels(self):
        """The format says user units are px without one, and we say so."""
        path = self._write("noviewbox.svg",
                           '<svg xmlns="http://www.w3.org/2000/svg" '
                           'width="100mm" height="50mm">'
                           '<path d="M0 0 L96 0"/></svg>')

        bpy.ops.bscu.import_vector(filepath=path)

        stroke = list(op_draw.canvas_for(bpy.context).strokes.values())[0][0]
        self.assertAlmostEqual(float(stroke.end[0]), 96.0 * 25.4 / 96.0, places=4)

    def test_making_a_template_from_an_empty_canvas_says_so(self):
        result = bpy.ops.bscu.make_template(name="nothing")

        self.assertEqual(result, {"CANCELLED"})


def run_test():
    """Run this suite the way tests/run_tests.py expects."""
    run_suite(__name__)


if __name__ == "__main__":
    unittest.main()
