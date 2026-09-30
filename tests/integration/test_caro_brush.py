"""Integration test for the Tab 2 brush operator (UX-5, UIUX 3B.3).

The brushes never touch UV, so the property worth testing is that they write
hints onto the mesh, that those hints survive Undo and a save, and that a stroke
which reaches nothing says so rather than quietly painting what it passed over.

The mesh is a quad grid on purpose. A face attribute holds one number per
polygon, which is half as many as the triangles the brush actually covers, and
that mismatch is exactly what silently loses half the strokes.
"""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "src"))
sys.path.insert(0, HERE)

import bpy  # noqa: E402
import numpy as np  # noqa: E402
from bscu_fixtures import run_suite  # noqa: E402

from bscu.operators import op_caro_brush  # noqa: E402

#: A 40 mm grid with 4 mm cells, so a 10 mm brush reaches a known number of faces.
SIZE_M = 0.04


def workpiece():
    clear_hints()
    bpy.ops.mesh.primitive_grid_add(x_subdivisions=4, y_subdivisions=4, size=SIZE_M)
    return bpy.context.active_object


def clear_hints():
    """Drop the hints and the drawing: both live on the shared scene.

    The canvas is stored on the scene on purpose, so saving the file saves the
    drawing. That is right for the product and wrong for tests, which share one
    scene, so each of them starts from an empty one.
    """
    from bscu.operators import op_draw

    for obj in bpy.data.objects:
        for name in (op_caro_brush.DENSITY, op_caro_brush.PIN,
                     op_caro_brush.PRIORITY, op_caro_brush.DIRECTION):
            if obj.type == "MESH" and name in obj.data.attributes:
                obj.data.attributes.remove(obj.data.attributes[name])
    op_caro_brush.forget("")
    scene = bpy.context.scene
    op_draw.forget(scene.name)
    for key in ("bscu_strokes", "bscu_hidden", "bscu_selection"):
        scene[key] = "{}"


class TestHintsReachTheMesh(unittest.TestCase):
    def setUp(self):
        self.obj = workpiece()
        bpy.context.view_layer.objects.active = self.obj

    def tearDown(self):
        name = self.obj.name
        clear_hints()
        if name in bpy.data.objects:
            bpy.data.objects.remove(bpy.data.objects[name], do_unlink=True)

    def test_an_unpainted_workpiece_reads_as_neutral(self):
        hints = op_caro_brush.hints_for(self.obj)

        self.assertEqual(len(hints.density), len(op_caro_brush._faces(self.obj)))
        self.assertTrue(np.allclose(hints.density, 1.0))

    def test_expanding_raises_the_density_where_the_brush_landed(self):
        bpy.ops.bscu.caro_brush(brush="expand", centre_mm=(0.0, 0.0), size_px=20.0)

        hints = op_caro_brush.hints_for(self.obj)
        painted = hints.density > 1.0

        self.assertGreater(int(painted.sum()), 0, "the brush painted nothing")
        self.assertLess(int(painted.sum()), len(hints.density),
                        "the brush painted the whole workpiece at once")

    def test_shrinking_lowers_the_density(self):
        bpy.ops.bscu.caro_brush(brush="shrink", centre_mm=(0.0, 0.0), size_px=20.0)

        hints = op_caro_brush.hints_for(self.obj)

        self.assertLess(float(hints.density.min()), 1.0)

    def test_pinning_marks_the_faces_it_reached(self):
        bpy.ops.bscu.caro_brush(brush="pin", centre_mm=(0.0, 0.0), size_px=12.0)

        pinned = int(op_caro_brush.hints_for(self.obj).pin.sum())

        self.assertGreater(pinned, 0)
        self.assertLess(pinned, len(op_caro_brush._faces(self.obj)))

    def test_a_direction_stroke_stores_a_unit_vector(self):
        bpy.ops.bscu.caro_brush(brush="direction", centre_mm=(0.0, 0.0),
                                size_px=12.0, direction=(0.0, 1.0))

        directions = op_caro_brush.hints_for(self.obj).direction
        painted = directions[np.abs(directions).sum(axis=1) > 0]

        self.assertGreater(len(painted), 0)
        self.assertTrue(np.allclose(np.linalg.norm(painted, axis=1), 1.0, atol=1e-5))

    def test_a_brush_that_reaches_nothing_says_so(self):
        result = bpy.ops.bscu.caro_brush(brush="expand",
                                          centre_mm=(9999.0, 9999.0), size_px=5.0)

        self.assertEqual(result, {"CANCELLED"})
        self.assertTrue(np.allclose(op_caro_brush.hints_for(self.obj).density, 1.0))


class TestBrushSize(unittest.TestCase):
    def setUp(self):
        self.obj = workpiece()

    def tearDown(self):
        name = self.obj.name
        clear_hints()
        if name in bpy.data.objects:
            bpy.data.objects.remove(bpy.data.objects[name], do_unlink=True)

    def test_a_bigger_brush_reaches_more_faces(self):
        tight = op_caro_brush.brush_mask(self.obj, (0.0, 0.0), 4.0)
        wide = op_caro_brush.brush_mask(self.obj, (0.0, 0.0), 12.0)

        self.assertGreater(int(wide.sum()), int(tight.sum()))

    def test_the_mask_is_in_millimetres_not_metres(self):
        """A mask in metres would be a hundred thousand times too small."""
        faces = len(op_caro_brush._faces(self.obj))
        self.assertEqual(len(op_caro_brush.brush_mask(self.obj, (0.0, 0.0), 5.0)), faces)

    def test_a_brush_off_the_workpiece_covers_nothing(self):
        self.assertEqual(int(op_caro_brush.brush_mask(
            self.obj, (900.0, 900.0), 5.0).sum()), 0)


class TestBrushLinks(unittest.TestCase):
    def setUp(self):
        self.obj = workpiece()
        bpy.context.view_layer.objects.active = self.obj
        op_caro_brush.forget(self.obj.name)

    def tearDown(self):
        name = self.obj.name
        clear_hints()
        if name in bpy.data.objects:
            bpy.data.objects.remove(bpy.data.objects[name], do_unlink=True)

    def test_a_stroke_that_snaps_to_a_stroke_takes_a_link(self):
        bpy.ops.bscu.draw_line(start_mm=(0.0, 0.0), to_mm=(10.0, 0.0),
                                snap_links=False)

        bpy.ops.bscu.caro_brush(brush="expand", centre_mm=(10.0, 0.0), size_px=20.0)

        self.assertTrue(op_caro_brush.links_for(self.obj.name).all(),
                        "the snapped stroke took no link")

    def test_holding_alt_gives_a_stroke_with_no_link(self):
        bpy.ops.bscu.draw_line(start_mm=(0.0, 0.0), to_mm=(10.0, 0.0),
                                snap_links=False)

        bpy.ops.bscu.caro_brush(brush="expand", centre_mm=(10.0, 0.0), size_px=20.0,
                                free=True)

        self.assertEqual(op_caro_brush.links_for(self.obj.name).all(), [])

    def test_a_stroke_with_nothing_to_snap_to_takes_no_link(self):
        bpy.ops.bscu.caro_brush(brush="expand", centre_mm=(0.0, 0.0), size_px=20.0)

        self.assertEqual(op_caro_brush.links_for(self.obj.name).all(), [])


def run_test():
    """Run this suite the way tests/run_tests.py expects."""
    run_suite(__name__)


if __name__ == "__main__":
    unittest.main()
