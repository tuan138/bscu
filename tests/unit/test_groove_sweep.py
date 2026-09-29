"""Unit tests for the virtual tool sweep (UX-10b, UIUX 5.13).

The spec's own acceptance list is what these tests are built from, because the
numbers in it are the ones that decide whether a toolpath is cuttable:

* a straight V groove with no tilt measures $w = 2d\\tan(\\alpha/2)$;
* two perpendicular grooves of the same depth cross at **that** depth, not at
  twice it - a groove is a shape on the surface, not an amount of material to
  add up;
* a lead-in tilt $\\beta$ shifts the bottom at the start by $d\\tan\\beta$;
* a tilt beyond half the tool angle is an undercut, and the spec is explicit
  that it is **reported and the number kept**, never quietly clamped.
"""

import unittest

import numpy as np

from bscu.core.groove_sweep import (
    SweepChannels,
    combine_grooves,
    combine_ridges,
    groove_half_width,
    half_angle_limit,
    lead_in_offset,
    reverse_path,
    smooth_min,
    total_tilt_deg,
    undercut_of,
)


class TestGeometry(unittest.TestCase):
    def test_a_straight_v_groove_measures_twice_its_half_width(self):
        """The spec's own formula: w = 2 d tan(alpha / 2)."""
        depth, angle = 3.0, 90.0

        half = groove_half_width(depth, angle)

        self.assertAlmostEqual(2.0 * half, 2.0 * 3.0 * np.tan(np.radians(45.0)))

    def test_a_narrower_tool_gives_a_narrower_groove(self):
        self.assertLess(groove_half_width(3.0, 30.0), groove_half_width(3.0, 90.0))

    def test_a_lead_in_shift_is_depth_times_the_tangent_of_the_tilt(self):
        """The spec's second formula, for a flat base."""
        depth, beta = 3.0, 10.0

        offset = lead_in_offset(depth, beta)

        self.assertAlmostEqual(offset, 3.0 * np.tan(np.radians(10.0)))

    def test_no_lead_in_means_no_shift(self):
        self.assertAlmostEqual(lead_in_offset(3.0, 0.0), 0.0)


class TestTilt(unittest.TestCase):
    def test_tilting_one_way_alone_is_just_that_tilt(self):
        self.assertAlmostEqual(total_tilt_deg(0.0, 20.0), 20.0)
        self.assertAlmostEqual(total_tilt_deg(20.0, 0.0), 20.0)

    def test_tilting_both_ways_adds_up(self):
        """The formula is arccos(cos beta cos gamma), not a plain sum."""
        combined = total_tilt_deg(20.0, 20.0)

        self.assertGreater(combined, 20.0)
        self.assertAlmostEqual(combined,
                               np.degrees(np.arccos(
                                   np.cos(np.radians(20.0)) ** 2)))

    def test_the_limit_is_half_the_tool_angle(self):
        self.assertAlmostEqual(half_angle_limit(90.0), 45.0)
        self.assertAlmostEqual(half_angle_limit(30.0), 15.0)

    def test_no_tilt_is_never_an_undercut(self):
        self.assertFalse(undercut_of(0.0, 0.0, 90.0))

    def test_a_tilt_beyond_the_limit_is_an_undercut(self):
        self.assertTrue(undercut_of(46.0, 0.0, 90.0))

    def test_a_tilt_exactly_at_the_limit_is_not_an_undercut(self):
        self.assertFalse(undercut_of(45.0, 0.0, 90.0))

    def test_an_undercut_keeps_the_number_it_was_given(self):
        """Clamping would hide the problem the user needs to solve."""
        result = undercut_of(60.0, 0.0, 90.0)

        self.assertTrue(result.undercut)
        self.assertAlmostEqual(result.beta_deg, 60.0)
        self.assertAlmostEqual(result.limit_deg, 45.0)
        self.assertAlmostEqual(result.total_deg, 60.0)
        self.assertTrue(result.message)


class TestReversal(unittest.TestCase):
    def test_reversing_a_path_reverses_the_channel_positions(self):
        path = np.array([[0.0, 0.0], [1.0, 0.0], [2.0, 0.0]])
        channels = SweepChannels(beta=[5.0, 7.0, 9.0], gamma=[1.0, 2.0, 3.0])

        back_path, back_channels = reverse_path(path, channels)

        self.assertTrue(np.allclose(back_path, path[::-1]))
        self.assertEqual([abs(value) for value in back_channels.beta], [9.0, 7.0, 5.0])

    def test_reversing_a_path_flips_the_sign_of_both_tilts(self):
        """Walking the other way, a left lean is now a right lean."""
        channels = SweepChannels(beta=[5.0, 7.0], gamma=[1.0, 2.0])

        _path, back = reverse_path(np.zeros((2, 2)), channels)

        # Reversing walks the path backwards *and* turns each lean the other
        # way, so the first point's value ends up last and negated.
        self.assertEqual(back.beta, [-7.0, -5.0])
        self.assertEqual(back.gamma, [-2.0, -1.0])

    def test_reversing_twice_gives_back_the_original(self):
        channels = SweepChannels(beta=[5.0, 7.0], gamma=[1.0, 2.0])
        path = np.array([[0.0, 0.0], [1.0, 0.0]])

        back_path, back = reverse_path(path, channels)
        again_path, again = reverse_path(back_path, back)

        self.assertTrue(np.allclose(again_path, path))
        self.assertEqual(again.beta, channels.beta)
        self.assertEqual(again.gamma, channels.gamma)


class TestCombiningPaths(unittest.TestCase):
    def test_two_grooves_cross_at_the_deepest_not_the_sum(self):
        """The spec's third rule: a groove is a shape, not an amount to add up."""
        first = np.array([2.0, 5.0, 3.0])
        second = np.array([1.0, 4.0, 2.0])

        together = combine_grooves(first, second)

        self.assertTrue(np.array_equal(together, np.minimum(first, second)))

    def test_two_ridges_cross_at_the_tallest(self):
        first = np.array([2.0, 5.0, 3.0])
        second = np.array([1.0, 4.0, 2.0])

        together = combine_ridges(first, second)

        self.assertTrue(np.array_equal(together, np.maximum(first, second)))

    def test_a_groove_through_a_ridge_on_one_layer_leaves_the_ridge_standing(self):
        """Grooves cut after ridges, per the layer rule."""
        ridge = np.array([4.0, 4.0, 4.0])
        groove = np.array([0.0, 3.0, 0.0])

        result = combine_ridges(ridge, combine_grooves(groove, np.zeros(3)))

        self.assertTrue(np.allclose(result, [4.0, 4.0, 4.0]))

    def test_a_smooth_min_cuts_the_corner_instead_of_creasing_it(self):
        """The fillet dips below the plain minimum, which is what rounds a join."""
        left = np.array([3.0, 1.0])
        right = np.array([2.0, 2.0])

        creased = np.minimum(left, right)
        blended = smooth_min(left, right, radius=2.0)

        self.assertTrue(np.allclose(creased, [2.0, 1.0]))
        self.assertTrue(np.all(blended <= creased + 1e-12),
                        "a smooth minimum must not sit above the plain one")
        self.assertLess(blended[0], creased[0], "the corner was not cut at all")

    def test_a_smooth_min_leaves_far_apart_fields_alone(self):
        """Where the two fields are further apart than the radius, it is a min."""
        left = np.array([5.0, 0.0])
        right = np.array([0.0, 5.0])

        blended = smooth_min(left, right, radius=0.5)

        self.assertTrue(np.allclose(blended, np.minimum(left, right)))

    def test_a_smooth_min_with_no_radius_is_a_plain_minimum(self):
        left = np.array([3.0, 1.0])
        right = np.array([2.0, 2.0])

        self.assertTrue(np.array_equal(smooth_min(left, right, 0.0),
                                       np.minimum(left, right)))


class TestChannels(unittest.TestCase):
    def test_channels_hold_the_two_tilts_the_spec_names(self):
        channels = SweepChannels(beta=[1.0], gamma=[2.0])

        self.assertEqual(channels.beta, [1.0])
        self.assertEqual(channels.gamma, [2.0])

    def test_channels_with_different_lengths_are_refused(self):
        with self.assertRaises(ValueError):
            SweepChannels(beta=[1.0, 2.0], gamma=[1.0])

    def test_channels_of_different_lengths_are_refused(self):
        with self.assertRaises(ValueError):
            SweepChannels(beta=[1.0, 2.0], gamma=[1.0, 2.0, 3.0])

    def test_a_channel_shorter_than_its_path_is_refused(self):
        channels = SweepChannels(beta=[1.0, 2.0], gamma=[1.0, 2.0])
        path = np.zeros((5, 2))

        with self.assertRaises(ValueError):
            channels.check_against(path)


if __name__ == "__main__":
    unittest.main()
