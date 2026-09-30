"""Integration test for the overlay layer node group (UX-12, UIUX 10.1).

The group is the user's to edit, so it has to be a real group they can open
rather than shading buried in the material. The masks it reads are baked per
layer, because two overlays sharing one attribute would paint over each
other's bookkeeping.

Padding is the other thing worth pinning: it is expressed against the part's
own physical size, so the same padding in millimetres gives the same band of
unpainted seam whichever resolution the image was baked at.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src"))

import bpy  # noqa: E402
import numpy as np  # noqa: E402
from bscu_fixtures import fresh_scene, run_suite  # noqa: E402

from bscu.nodes import overlay_material  # noqa: E402


class TestLayerGroup(unittest.TestCase):
    def setUp(self):
        self.obj = fresh_scene()
        overlay_material.clear_all()

    def tearDown(self):
        overlay_material.clear_all()
        name = self.obj.name
        if name in bpy.data.objects:
            bpy.data.objects.remove(bpy.data.objects[name], do_unlink=True)

    def test_a_layer_gets_a_group_the_user_can_open(self):
        group = overlay_material.build_group("engraving", (0.0, 1.0, 0.0, 1.0))

        self.assertIn("engraving", group.name)
        self.assertGreater(len(group.nodes), 0)

    def test_the_group_takes_a_mask_and_a_strength(self):
        group = overlay_material.build_group("engraving")

        names = [socket.name for socket in group.interface.items_tree]
        self.assertGreaterEqual(names.count("Mask"), 2)
        self.assertIn("Strength", names)

    def test_the_group_reads_the_bscu_map(self):
        """A group sampling the wrong map paints the wrong chart."""
        group = overlay_material.build_group("engraving")

        uv = [n for n in group.nodes if n.bl_idname == "ShaderNodeUVMap"]
        self.assertEqual(len(uv), 1)
        self.assertEqual(uv[0].uv_map, "BSCU_UV_Active")

    def test_building_the_same_layer_twice_leaves_one_group(self):
        overlay_material.build_group("engraving")
        overlay_material.build_group("engraving")

        matches = [g for g in bpy.data.node_groups
                   if g.name == overlay_material.group_name("engraving")]
        self.assertEqual(len(matches), 1)

    def test_the_group_is_built_on_demand_rather_than_at_enable(self):
        self.assertIsNone(bpy.data.node_groups.get(
            overlay_material.group_name("lazy")))

        built = overlay_material.ensure_group("lazy")

        self.assertIsNotNone(built)
        self.assertIs(overlay_material.ensure_group("lazy"), built)


class TestMasks(unittest.TestCase):
    def setUp(self):
        self.obj = fresh_scene()

    def tearDown(self):
        name = self.obj.name
        if name in bpy.data.objects:
            bpy.data.objects.remove(bpy.data.objects[name], do_unlink=True)

    def test_a_mask_survives_the_round_trip(self):
        count = len(self.obj.data.polygons)
        values = np.linspace(0.0, 1.0, count, dtype=np.float32)

        name = overlay_material.write_mask(self.obj, values, "engraving")

        self.assertIn("engraving", name)
        self.assertTrue(np.allclose(overlay_material.read_mask(self.obj, "engraving"),
                                    values, atol=1e-6))

    def test_two_layers_keep_separate_masks(self):
        """One shared attribute would let one overlay erase the other's."""
        count = len(self.obj.data.polygons)
        overlay_material.write_mask(self.obj, np.zeros(count, dtype=np.float32), "a")
        overlay_material.write_mask(self.obj, np.ones(count, dtype=np.float32), "b")

        first = overlay_material.read_mask(self.obj, "a")
        second = overlay_material.read_mask(self.obj, "b")

        self.assertAlmostEqual(float(first.max()), 0.0)
        self.assertAlmostEqual(float(second.max()), 1.0)

    def test_reading_a_layer_that_was_never_painted_gives_nothing(self):
        self.assertEqual(overlay_material.read_mask(self.obj, "unpainted").size, 0)

    def test_a_wrong_number_of_mask_values_is_refused(self):
        with self.assertRaises(ValueError):
            overlay_material.write_mask(self.obj, np.zeros(3))

    def test_shutting_down_removes_the_groups_bscu_owns(self):
        overlay_material.build_group("engraving")

        overlay_material.clear_all()

        self.assertFalse([g for g in bpy.data.node_groups
                          if g.name.startswith(overlay_material.GROUP_PREFIX)])


class TestPadding(unittest.TestCase):
    def test_padding_scales_with_the_part_and_its_resolution(self):
        """The same millimetres of pad, whatever the image resolution."""
        small_part = overlay_material.padding_in_uv(1.0, 10.0)
        large_part = overlay_material.padding_in_uv(1.0, 1000.0)

        self.assertAlmostEqual(small_part, 0.1)
        self.assertAlmostEqual(large_part, 0.001)
        self.assertLess(large_part, small_part,
                        "a bigger part needs a narrower band in UV units for the "
                        "same millimetres of padding")

    def test_padding_of_nothing_is_refused(self):
        with self.assertRaises(ValueError):
            overlay_material.padding_in_uv(1.0, 0.0)

    def test_padding_is_never_negative(self):
        self.assertEqual(overlay_material.padding_in_uv(-5.0, 100.0), 0.0)


def run_test():
    """Run this suite the way tests/run_tests.py expects."""
    run_suite(__name__)


if __name__ == "__main__":
    unittest.main()
