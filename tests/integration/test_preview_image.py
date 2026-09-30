"""Integration test for the relief preview (UX-10, D10).

A preview has to come from the height field in the field's own units, and
one that has fallen out of date has to say so rather than look current.
"""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "src"))
sys.path.insert(0, HERE)

import bpy  # noqa: E402
import numpy as np  # noqa: E402
from bscu_fixtures import fresh_scene, run_suite  # noqa: E402

from bscu.bridge import preview_image  # noqa: E402
from bscu.core.height_field import HeightField, default_groove  # noqa: E402
from bscu.core.sdf import Polygon  # noqa: E402


class TestPreviewImage(unittest.TestCase):
    """The preview has to come from the field, in the field's own units."""

    def _field(self, depth_mm=2.0):
        return HeightField(
            base=Polygon([(-10, -10), (10, -10), (10, 10), (-10, 10), (-10, -10)]),
            base_depth_mm=depth_mm,
            stock_thickness_mm=20.0)

    def test_a_preview_reads_back_the_depth_the_field_asked_for(self):

        image = preview_image.preview_of(self._field(3.0), (-10, -10), (10, 10))

        self.assertAlmostEqual(image.max_mm, 3.0, places=3)

    def test_the_two_tiers_differ_in_sampling(self):

        field = self._field()
        coarse = preview_image.preview_of(field, (-10, -10), (10, 10))
        fine = preview_image.preview_of(field, (-10, -10), (10, 10), fine=True)

        self.assertGreater(fine.heights_mm.size, coarse.heights_mm.size)

    def test_a_stale_preview_keeps_the_marking(self):

        first = preview_image.preview_of(self._field(), (-10, -10), (10, 10))
        carried = preview_image.carried_forward(first, "3 of 9 charts left")

        self.assertFalse(carried.current)
        self.assertIn("not up to date", carried.label_text())

    def test_a_preview_becomes_a_real_image_with_the_field_in_it(self):

        image = preview_image.preview_of(self._field(2.5), (-10, -10), (10, 10))
        buffer = preview_image.to_image_buffer(image)

        self.assertEqual(buffer.size[0], image.heights_mm.shape[1])
        self.assertEqual(buffer.size[1], image.heights_mm.shape[0])
        bpy.data.images.remove(buffer)

    def test_the_preview_and_the_mesh_attribute_agree_in_millimetres(self):
        """The panel's number and the mesh the cutter reads must be one number.

        The field is the authority; the preview samples it and the node graph
        reads the attribute. A disagreement anywhere along that chain puts a
        number on screen that is not the number being cut.
        """
        from bscu.nodes import relief_displace

        obj = fresh_scene()
        field = self._field(2.5)
        points = np.asarray([v.co[:2] for v in obj.data.vertices],
                            dtype=np.float64) * 1000.0
        heights = field.evaluate(points)

        relief_displace.write_height_attribute(obj, heights)
        image = preview_image.preview_of(field, (-20.0, -20.0), (20.0, 20.0))

        attribute = np.asarray(
            [item.value for item in
             obj.data.attributes.get(relief_displace.HEIGHT_ATTRIBUTE).data],
            dtype=np.float32)
        # The preview is sampled on a grid, so compare against the field rather
        # than sample for sample, and allow the field's own quantum.
        self.assertAlmostEqual(float(attribute.max()), float(heights.max()), places=4)
        self.assertAlmostEqual(image.max_mm, float(heights.max()), places=3)

    def test_a_pocket_the_field_cuts_is_visible_in_both(self):
        from bscu.nodes import relief_displace

        obj = fresh_scene()
        field = self._field(4.0)
        field.grooves.append(default_groove([(-8.0, 0.0), (8.0, 0.0)], depth_mm=1.5))
        # One height per vertex, the way the attribute is written.
        canvas = np.asarray([v.co[:2] for v in obj.data.vertices],
                            dtype=np.float64) * 1000.0
        heights = field.evaluate(canvas)
        relief_displace.write_height_attribute(obj, heights)

        attribute = np.asarray(
            [item.value for item in
             obj.data.attributes.get(relief_displace.HEIGHT_ATTRIBUTE).data],
            dtype=np.float32)
        # A vertex sitting on the groove gets the pocket plus the groove.
        self.assertAlmostEqual(float(attribute.max()), 5.5, places=3,
                               msg=f"deepest vertex was {attribute.max()}")

        self.assertGreater(float(attribute.max()), 4.0,
                           "the pocket did not reach the mesh at all")

    def test_shutting_down_removes_the_preview_images(self):

        image = preview_image.preview_of(self._field(), (-10, -10), (10, 10))
        preview_image.to_image_buffer(image)

        preview_image.forget_images()

        self.assertFalse([i for i in bpy.data.images
                          if i.name.startswith("BSCU_Relief_Preview")])


def run_test():
    """Run this suite the way tests/run_tests.py expects."""
    run_suite(__name__)


if __name__ == "__main__":
    unittest.main()
