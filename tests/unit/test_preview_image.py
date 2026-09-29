"""Unit tests for the relief preview (UX-10, UIUX 5.4 and D10).

The spec's D10 is the whole point of this file. A cheap preview is a coarse
sampling, and the failure it exists to prevent is a coarse sampling being
presented as though it described the surface. So these tests are mostly about
what the preview *says about itself*, and about the two tiers being genuinely
different rather than the same picture with a different label.
"""

import unittest

import numpy as np

from bscu.bridge import preview_image
from bscu.core.height_field import HeightField
from bscu.core.sdf import Polygon


def pocket(depth_mm: float = 2.0, size: float = 20.0) -> HeightField:
    half = size / 2.0
    return HeightField(
        base=Polygon([(-half, -half), (half, -half), (half, half),
                      (-half, half), (-half, -half)]),
        base_depth_mm=depth_mm,
        stock_thickness_mm=20.0,
    )


class TestSampling(unittest.TestCase):
    def test_the_coarse_tier_samples_at_the_spec_step(self):
        image = preview_image.preview_of(pocket(), (-10, -10), (10, 10))

        self.assertAlmostEqual(image.step_mm, preview_image.COARSE_STEP_MM)

    def test_the_two_tiers_sample_differently(self):
        """If they did not, the cheap tier would buy nothing."""
        field = pocket()
        coarse = preview_image.preview_of(field, (-10, -10), (10, 10), fine=False)
        fine = preview_image.preview_of(field, (-10, -10), (10, 10), fine=True)

        self.assertGreater(fine.heights_mm.size, coarse.heights_mm.size)

    def test_the_field_comes_through_in_millimetres(self):
        image = preview_image.preview_of(pocket(3.0), (-10, -10), (10, 10))

        self.assertAlmostEqual(image.max_mm, 3.0, places=3)

    def test_every_height_sits_on_a_micron_of_the_spec_scale(self):
        image = preview_image.preview_of(pocket(3.0), (-10, -10), (10, 10))
        quantum = preview_image.HEIGHT_QUANTUM_MM
        remainder = np.abs(image.heights_mm / quantum
                           - np.round(image.heights_mm / quantum))

        self.assertLess(float(remainder.max()), 1e-6,
                        "a height sits between the spec's own increments")

    def test_a_sample_matches_the_field_it_came_from(self):
        """A preview that disagrees with the field is worse than no preview."""
        field = pocket(2.0)
        image = preview_image.preview_of(field, (-10, -10), (10, 10))

        centre = image.sample_at((0.0, 0.0))
        direct = float(field.evaluate(np.array([[0.0, 0.0]]))[0])

        self.assertAlmostEqual(centre, direct, places=6)

    def test_a_point_outside_the_sampled_region_reads_as_flat(self):
        image = preview_image.preview_of(pocket(), (-10, -10), (10, 10))

        self.assertEqual(image.sample_at((500.0, 500.0)), 0.0)

    def test_a_backwards_region_is_refused(self):
        with self.assertRaises(ValueError):
            preview_image.sample(pocket(), (10, 10), (-10, -10))

    def test_a_zero_step_is_refused(self):
        with self.assertRaises(ValueError):
            preview_image.sample(pocket(), (-10, -10), (10, 10), 0.0)


class TestHonesty(unittest.TestCase):
    def test_the_coarse_picture_says_how_coarse_it_is(self):
        image = preview_image.preview_of(pocket(), (-10, -10), (10, 10))

        self.assertIn("0.25", image.label_text())

    def test_the_fine_picture_needs_no_caveat(self):
        image = preview_image.preview_of(pocket(), (-10, -10), (10, 10), fine=True)

        self.assertEqual(image.label_text(), "")

    def test_a_carried_picture_is_marked_as_not_current(self):
        first = preview_image.preview_of(pocket(), (-10, -10), (10, 10))

        carried = preview_image.carried_forward(first, "2 of 7 charts left")

        self.assertFalse(carried.current)
        self.assertIn("not up to date", carried.label_text())

    def test_a_carried_picture_keeps_the_picture_it_carried(self):
        """D10's rule: the old image stays, clearly marked, rather than vanishing."""
        first = preview_image.preview_of(pocket(), (-10, -10), (10, 10))

        carried = preview_image.carried_forward(first, "still working")

        self.assertTrue(np.array_equal(carried.heights_mm, first.heights_mm))

    def test_carrying_nothing_is_refused(self):
        with self.assertRaises(ValueError):
            preview_image.carried_forward(None, "nothing to carry")

    def test_a_carried_picture_does_not_share_its_array(self):
        first = preview_image.preview_of(pocket(), (-10, -10), (10, 10))
        carried = preview_image.carried_forward(first, "still working")

        carried.heights_mm[0, 0] = 999.0

        self.assertNotEqual(float(first.heights_mm[0, 0]), 999.0)


if __name__ == "__main__":
    unittest.main()
