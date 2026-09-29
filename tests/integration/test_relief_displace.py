"""Integration test for the relief displace graph (UX-10, UIUX 5.11).

The graph is where the height field stops being numbers and becomes geometry,
so the test checks the two properties that decide whether a cut is the cut the
user asked for: the heights survive the round trip through a Blender attribute,
and the modifier leaves the object's own material and slot alone.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src"))

import bpy  # noqa: E402
import numpy as np  # noqa: E402

from bscu.core.height_field import HeightField  # noqa: E402
from bscu.core.sdf import Polygon  # noqa: E402
from bscu.nodes import relief_displace  # noqa: E402


def grid(size: float = 0.02, subdivisions: int = 3):
    bpy.ops.mesh.primitive_grid_add(x_subdivisions=subdivisions,
                                    y_subdivisions=subdivisions, size=size)
    return bpy.context.active_object


class TestHeightAttribute(unittest.TestCase):
    def setUp(self):
        self.obj = grid()
        self.count = len(self.obj.data.vertices)

    def tearDown(self):
        name = self.obj.name
        if name in bpy.data.objects:
            bpy.data.objects.remove(bpy.data.objects[name], do_unlink=True)

    def test_heights_survive_the_round_trip(self):
        heights = np.linspace(0.0, 5.0, self.count, dtype=np.float32)

        written = relief_displace.write_height_attribute(self.obj, heights)
        read_back = relief_displace.read_height_attribute(self.obj)

        self.assertEqual(written, self.count)
        self.assertTrue(np.allclose(read_back, heights, atol=1e-6),
                        f"max difference {np.abs(read_back - heights).max()}")

    def test_heights_arrive_in_millimetres(self):
        """A 2 mm cut must be stored as 2, not as 0.002."""
        heights = np.full(self.count, 2.0, dtype=np.float32)

        relief_displace.write_height_attribute(self.obj, heights)

        self.assertAlmostEqual(float(relief_displace.read_height_attribute(self.obj)[0]),
                               2.0, places=5)

    def test_the_attribute_is_the_one_the_graph_reads(self):
        self.assertEqual(relief_displace.HEIGHT_ATTRIBUTE, "cnc_height")

    def test_a_wrong_number_of_heights_is_refused(self):
        with self.assertRaises(ValueError):
            relief_displace.write_height_attribute(self.obj, np.zeros(3))

    def test_writing_twice_replaces_rather_than_appends(self):
        relief_displace.write_height_attribute(self.obj,
                                               np.zeros(self.count, dtype=np.float32))
        relief_displace.write_height_attribute(self.obj,
                                               np.ones(self.count, dtype=np.float32))

        self.assertTrue(np.allclose(relief_displace.read_height_attribute(self.obj), 1.0))

    def test_reading_a_mesh_with_no_attribute_gives_nothing_rather_than_failing(self):
        self.assertEqual(relief_displace.read_height_attribute(self.obj).size, 0)


class TestModifier(unittest.TestCase):
    def setUp(self):
        relief_displace.build_group()
        self.obj = grid()

    def tearDown(self):
        name = self.obj.name
        if name in bpy.data.objects:
            bpy.data.objects.remove(bpy.data.objects[name], do_unlink=True)
        relief_displace.clear_all()

    def test_the_group_is_built_and_readable(self):
        group = bpy.data.node_groups.get(relief_displace.GROUP_NAME)

        self.assertIsNotNone(group)
        self.assertGreater(len(group.nodes), 0)

    def test_the_group_has_a_geometry_in_and_out(self):
        group = bpy.data.node_groups.get(relief_displace.GROUP_NAME)

        names = [socket.name for socket in group.interface.items_tree]
        self.assertGreaterEqual(names.count("Geometry"), 2)

    def test_building_twice_leaves_one_group(self):
        """A reloaded add-on must not orphan the group it made last time."""
        relief_displace.build_group()

        matches = [g for g in bpy.data.node_groups
                   if g.name.startswith(relief_displace.GROUP_NAME)]
        self.assertEqual(len(matches), 1)

    def test_attaching_adds_one_modifier(self):
        modifier = relief_displace.attach(self.obj)

        self.assertIsNotNone(modifier)
        self.assertEqual(modifier.node_group.name, relief_displace.GROUP_NAME)

    def test_attaching_twice_does_not_stack_a_second_modifier(self):
        """Two displace modifiers would double every depth."""
        relief_displace.attach(self.obj)
        relief_displace.attach(self.obj)

        self.assertEqual(len([m for m in self.obj.modifiers
                              if m.type == "NODES"]), 1)

    def test_attaching_leaves_the_object_material_alone(self):
        """D2: the user's own material and slot are not BSCU's to change."""
        self.obj.data.materials.append(bpy.data.materials.new("User material"))
        before = [m.name for m in self.obj.data.materials]

        relief_displace.attach(self.obj)

        self.assertEqual([m.name for m in self.obj.data.materials], before)

    def test_detaching_leaves_the_user_modifiers_alone(self):
        """BSCU removes what it added and nothing else."""
        relief_displace.attach(self.obj)
        self.obj.modifiers.new(name="User bevel", type="BEVEL")

        relief_displace.detach(self.obj)

        names = [m.name for m in self.obj.modifiers]
        self.assertIn("User bevel", names)
        self.assertFalse([n for n in names if n.startswith("BSCU")])

    def test_detaching_something_that_is_not_there_says_so(self):
        self.assertFalse(relief_displace.detach(self.obj))


class TestFieldThroughToBlender(unittest.TestCase):
    def setUp(self):
        self.obj = grid()
        field = HeightField(
            # The grid is 20 mm across, so the region covers it in millimetres.
            base=Polygon([(-10.0, -10.0), (10.0, -10.0),
                          (10.0, 10.0), (-10.0, 10.0), (-10.0, -10.0)]),
            base_depth_mm=3.0,
            stock_thickness_mm=20.0,
        )
        points = np.asarray([vertex.co[:2] for vertex in self.obj.data.vertices],
                            dtype=np.float64) * 1000.0
        self.heights = field.evaluate(points)
        self.heights_mm = self.heights

    def tearDown(self):
        name = self.obj.name
        if name in bpy.data.objects:
            bpy.data.objects.remove(bpy.data.objects[name], do_unlink=True)

    def test_the_field_and_the_attribute_agree(self):
        """The number on screen has to be the number the mesh will be cut to."""
        relief_displace.write_height_attribute(self.obj, self.heights_mm)

        read_back = relief_displace.read_height_attribute(self.obj)

        self.assertTrue(np.allclose(read_back, self.heights_mm, atol=1e-4),
                        "the attribute and the field disagree")

    def test_the_deepest_point_is_the_depth_the_field_asked_for(self):
        self.assertAlmostEqual(float(self.heights_mm.max()), 3.0, places=4)




def run_test():
    """Run this suite, the way tests/run_tests.py expects.

    The add-on is registered, not re-imported. Purging ``bscu`` and importing
    it again would build a *second* copy of every module: the operators would
    be registered from the new copy and would write to that copy's state, while
    the test file still holds the old one. Everything would then look empty for
    reasons that have nothing to do with the code under test.
    """
    import unittest

    import bscu

    bscu.register()
    try:
        result = unittest.TextTestRunner(verbosity=1).run(
            unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
        )
    finally:
        bscu.unregister()
    if not result.wasSuccessful():
        raise AssertionError(
            f"{result.testsRun} test(s) ran, "
            f"{len(result.failures)} failed and {len(result.errors)} errored")
    print(f"[OK] {result.testsRun} test(s) passed in {__name__}")


if __name__ == "__main__":
    unittest.main()
