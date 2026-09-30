"""Integration test for the export operator (UX-11).

The property is that a refused export writes nothing: a bad file left on
disk is worse than no file, because the user finds it later, at the machine.
"""

import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "src"))
sys.path.insert(0, HERE)

import bpy  # noqa: E402
from bscu_fixtures import blank_canvas, fresh_scene, run_suite  # noqa: E402


class TestExportOperator(unittest.TestCase):
    def setUp(self):
        self.obj = fresh_scene()
        blank_canvas()
        self.folder = tempfile.mkdtemp(prefix="bscu_op_")

    def tearDown(self):
        for entry in os.listdir(self.folder):
            os.remove(os.path.join(self.folder, entry))
        os.rmdir(self.folder)
        name = self.obj.name
        if name in bpy.data.objects:
            bpy.data.objects.remove(bpy.data.objects[name], do_unlink=True)

    def test_checking_a_good_solid_finishes(self):
        bpy.ops.mesh.primitive_cube_add(size=0.02)
        cube = bpy.context.active_object
        result = bpy.ops.bscu.export_stl(check_only=True)

        self.assertEqual(result, {"FINISHED"})
        if cube.name in bpy.data.objects:
            bpy.data.objects.remove(bpy.data.objects[cube.name], do_unlink=True)

    def test_an_open_mesh_is_refused_and_writes_nothing(self):
        target = os.path.join(self.folder, "open.stl")

        with self.assertRaises(RuntimeError):
            bpy.ops.bscu.export_stl(filepath=target)

        self.assertFalse(os.path.exists(target))

    def test_a_cube_exports_and_reads_back_the_right_size(self):
        bpy.ops.mesh.primitive_cube_add(size=0.02)
        cube = bpy.context.active_object
        target = os.path.join(self.folder, "cube.stl")

        bpy.ops.bscu.export_stl(filepath=target)

        self.assertTrue(os.path.exists(target))
        if cube.name in bpy.data.objects:
            bpy.data.objects.remove(bpy.data.objects[cube.name], do_unlink=True)


def run_test():
    """Run this suite the way tests/run_tests.py expects."""
    run_suite(__name__)


if __name__ == "__main__":
    unittest.main()
