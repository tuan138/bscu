"""Integration test for the relief overlay material (UX-12, UIUX 10.1 and 10.3).

The property under test throughout is D2: BSCU adds its own slot and leaves the
user's material and slot exactly as they were. A test that only checked the
overlay appeared would pass while the user's shading was being replaced, which
is the failure the spec names specifically.

The second property is that removing the overlay is as complete as adding it.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src"))

import bpy  # noqa: E402
import numpy as np  # noqa: E402

from bscu.bridge import material_builder  # noqa: E402


def workpiece():
    bpy.ops.mesh.primitive_grid_add(x_subdivisions=3, y_subdivisions=3)
    obj = bpy.context.active_object
    obj.data.uv_layers.new(name="BSCU_UV_Active")
    return obj


class TestEnabling(unittest.TestCase):
    def setUp(self):
        self.obj = workpiece()
        self.user_material = bpy.data.materials.new("User material")
        self.obj.data.materials.append(self.user_material)

    def tearDown(self):
        name = self.obj.name
        for material in list(bpy.data.materials):
            if material.name.startswith(material_builder.OVERLAY_MATERIAL_PREFIX):
                bpy.data.materials.remove(material)
        if name in bpy.data.objects:
            bpy.data.objects.remove(bpy.data.objects[name], do_unlink=True)

    def test_enabling_adds_one_slot(self):
        before = len(self.obj.material_slots)

        self.assertTrue(material_builder.enable(self.obj))

        self.assertEqual(len(self.obj.material_slots), before + 1)

    def test_the_user_material_is_still_there_afterwards(self):
        material_builder.enable(self.obj)

        self.assertIn(self.user_material, [s.material for s in self.obj.material_slots])

    def test_the_overlay_slot_is_object_linked(self):
        """A data-linked slot would replace every face on the object (D2)."""
        material_builder.enable(self.obj)

        material = material_builder.find_material(self.obj)
        slot = next(s for s in self.obj.material_slots if s.material is material)

        self.assertEqual(slot.link, "OBJECT")

    def test_enabling_twice_does_not_add_a_second_slot(self):
        material_builder.enable(self.obj)
        material_builder.enable(self.obj)

        materials = [s.material for s in self.obj.material_slots]
        overlay = material_builder.find_material(self.obj)
        self.assertEqual(materials.count(overlay), 1)

    def test_the_overlay_slot_actually_carries_its_material(self):
        """An object-linked slot that was not assigned renders nothing at all."""
        material_builder.enable(self.obj)
        material = material_builder.find_material(self.obj)
        slot = next(s for s in self.obj.material_slots if s.link == "OBJECT")

        self.assertEqual(slot.material, material)

    def test_a_mesh_with_no_bscu_map_is_left_alone(self):
        bpy.ops.mesh.primitive_cube_add(size=0.02)
        other = bpy.context.active_object
        before = len(other.material_slots)

        self.assertFalse(material_builder.enable(other))
        self.assertEqual(len(other.material_slots), before)
        if other.name in bpy.data.objects:
            bpy.data.objects.remove(bpy.data.objects[other.name], do_unlink=True)

    def test_enabling_something_that_is_not_a_mesh_says_no(self):
        self.assertFalse(material_builder.enable(None))

    def test_building_twice_leaves_one_material(self):
        material_builder.enable(self.obj)
        material_builder.build_material(self.obj)

        matches = [m for m in bpy.data.materials
                   if m.name.startswith(material_builder.OVERLAY_MATERIAL_PREFIX)]
        self.assertEqual(len(matches), 1)


class TestDisabling(unittest.TestCase):
    def setUp(self):
        self.obj = workpiece()
        self.user_material = bpy.data.materials.new("User material")
        self.obj.data.materials.append(self.user_material)
        material_builder.enable(self.obj)

    def tearDown(self):
        name = self.obj.name
        for material in list(bpy.data.materials):
            if material.name.startswith(material_builder.OVERLAY_MATERIAL_PREFIX):
                bpy.data.materials.remove(material)
        if name in bpy.data.objects:
            bpy.data.objects.remove(bpy.data.objects[name], do_unlink=True)

    def test_disabling_removes_only_the_overlay_slot(self):
        before = len(self.obj.material_slots)

        self.assertTrue(material_builder.disable(self.obj))

        self.assertEqual(len(self.obj.material_slots), before - 1)
        self.assertIn(self.user_material, [s.material for s in self.obj.material_slots])

    def test_disabling_something_with_no_overlay_says_no(self):
        bpy.ops.mesh.primitive_cube_add(size=0.02)
        fresh = bpy.context.active_object

        self.assertFalse(material_builder.disable(fresh))
        if fresh.name in bpy.data.objects:
            bpy.data.objects.remove(bpy.data.objects[fresh.name], do_unlink=True)

    def test_enabling_and_disabling_twice_comes_back_to_the_start(self):
        before = [s.material for s in self.obj.material_slots]

        material_builder.disable(self.obj)
        material_builder.disable(self.obj)
        material_builder.enable(self.obj)

        self.assertEqual([s.material for s in self.obj.material_slots], before)


class TestMaskAttribute(unittest.TestCase):
    def setUp(self):
        self.obj = workpiece()

    def tearDown(self):
        name = self.obj.name
        if name in bpy.data.objects:
            bpy.data.objects.remove(bpy.data.objects[name], do_unlink=True)

    def test_a_mask_survives_the_round_trip(self):
        count = len(self.obj.data.polygons)
        values = np.linspace(0.0, 1.0, count, dtype=np.float32)

        written = material_builder.write_mask_attribute(self.obj, values)
        attribute = self.obj.data.attributes.get(material_builder.MASK_ATTRIBUTE)

        self.assertEqual(written, count)
        read_back = np.asarray([item.value for item in attribute.data],
                               dtype=np.float32)
        self.assertTrue(np.allclose(read_back, values, atol=1e-6))

    def test_a_wrong_number_of_mask_values_is_refused(self):
        with self.assertRaises(ValueError):
            material_builder.write_mask_attribute(self.obj, np.zeros(3))

    def test_padding_grows_with_the_sampling_rate(self):
        """Padding is in pixels, so a higher resolution pads further."""
        low = material_builder.padding_for(2.0, 1.0)
        high = material_builder.padding_for(8.0, 1.0)

        self.assertAlmostEqual(low, 2.0)
        self.assertAlmostEqual(high, 8.0)

    def test_padding_at_a_zero_sampling_rate_is_refused(self):
        with self.assertRaises(ValueError):
            material_builder.padding_for(0.0, 1.0)


class TestLayerSpec(unittest.TestCase):
    def test_an_unknown_blend_mode_is_refused(self):
        with self.assertRaises(ValueError):
            material_builder.LayerSpec("layer", blend="SCREEN")

    def test_opacity_outside_zero_to_one_is_refused(self):
        with self.assertRaises(ValueError):
            material_builder.LayerSpec("layer", opacity=1.5)

    def test_a_layer_with_sensible_values_is_accepted(self):
        layer = material_builder.LayerSpec("engraving", blend="MIX", opacity=0.5)

        self.assertEqual(layer.name, "engraving")




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
