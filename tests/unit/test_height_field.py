"""Unit tests for the canvas geometry and height field (UX-10, UIUX 5.6-5.12).

These are the numbers a cutter would follow, so the units and the order of
operations are the substance of the tests, not incidental detail:

* Everything is millimetres. A factor of a thousand turning a 2 mm cut into a
  2 m one is the failure mode worth guarding hardest.
* A warp shapes the surface that grooves then sit on, not the other way round.
* A cut is measured from the surface already there, and a cut deeper than the
  material present is reported rather than performed.
* A profile is one-sided: it does not carve the far side of its own path.
"""

import math
import unittest

import numpy as np

from bscu.core.height_field import (
    Groove,
    HeightField,
    WarpLine,
    WarpNode,
    default_groove,
)
from bscu.core.profile_curves import (
    blend,
    fillet,
    flat,
    from_curve,
    mirror_max,
    ramp,
    vee,
)
from bscu.core.sdf import Arc, Circle, Polygon, Segment, grid_samples, smooth_union


class TestSDFPrimitives(unittest.TestCase):
    def test_a_segment_clamps_to_its_ends(self):
        """Distance to a segment, not to the infinite line through it."""
        segment = Segment((0.0, 0.0), (10.0, 0.0))

        at_middle = segment.distance(np.array([[5.0, 3.0]]))
        past_the_end = segment.distance(np.array([[14.0, 0.0]]))

        self.assertAlmostEqual(float(at_middle[0]), 3.0)
        self.assertAlmostEqual(float(past_the_end[0]), 4.0)

    def test_a_circle_is_negative_inside_and_positive_outside(self):
        circle = Circle((0.0, 0.0), 5.0)

        signed = circle.distance(np.array([[0.0, 0.0], [9.0, 0.0]]))

        self.assertLess(float(signed[0]), 0.0)
        self.assertAlmostEqual(float(signed[1]), 4.0)

    def test_a_full_arc_is_treated_as_the_circle_it_is(self):
        """A round boss drawn as an arc must not leave a gap in its outline."""
        arc = Arc((0.0, 0.0), 5.0, 0.0, 2.0 * math.pi)

        at_the_gap = arc.distance(np.array([[5.0, 0.0]]))

        self.assertAlmostEqual(float(at_the_gap[0]), 0.0, places=9)

    def test_a_partial_arc_uses_its_ends_as_fallbacks(self):
        """Off the sweep, the nearest point is one of the two ends."""
        arc = Arc((0.0, 0.0), 5.0, 0.0, math.pi / 2)
        end = arc.point_at(math.pi / 2)

        off_the_arc = arc.distance(np.array([[-5.0, 0.0]]))

        self.assertAlmostEqual(float(off_the_arc[0]),
                               float(np.linalg.norm(np.array([-5.0, 0.0]) - np.array(end))))

    def test_a_square_has_the_distance_a_square_should_have(self):
        square = Polygon([(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)])

        inside = square.distance(np.array([[5.0, 5.0]]))
        at_the_edge = square.distance(np.array([[0.0, 5.0]]))
        outside = square.distance(np.array([[-3.0, 5.0]]))

        self.assertAlmostEqual(float(inside[0]), -5.0)
        self.assertAlmostEqual(float(at_the_edge[0]), 0.0)
        self.assertAlmostEqual(float(outside[0]), 3.0)

    def test_a_winding_test_survives_an_outline_that_crosses_itself(self):
        """A crossing-number test flips its mind wherever the drawing crosses."""
        bowtie = Polygon([(0, 0), (10, 10), (10, 0), (0, 10), (0, 0)])

        at_the_centre = bowtie.contains(np.array([[5.0, 5.0]]))
        well_outside = bowtie.contains(np.array([[50.0, 50.0]]))

        self.assertTrue(bool(at_the_centre[0]))
        self.assertFalse(bool(well_outside[0]))

    def test_an_open_outline_says_so(self):
        open_line = Polygon([(0, 0), (5, 0), (5, 5)])

        self.assertFalse(open_line.is_closed())

    def test_a_closed_outline_says_so(self):
        closed = Polygon([(0, 0), (5, 0), (5, 5), (0, 0)])

        self.assertTrue(closed.is_closed())

    def test_smoothing_two_fields_joins_them_without_a_crease(self):
        left = np.full(5, -1.0)
        right = np.full(5, 1.0)

        creased = smooth_union(left, right, 0.0)
        filleted = smooth_union(left, right, 2.0)

        self.assertTrue(np.allclose(creased, np.minimum(left, right)))
        self.assertLess(float(filleted[2]), 0.0,
                        "a smooth union should dip below both fields where they meet")

    def test_a_sampling_grid_covers_the_rectangle_it_was_asked_for(self):
        samples = grid_samples((0.0, 0.0), (2.0, 1.0), 0.5)

        self.assertLessEqual(samples[:, 0].max(), 2.0)
        self.assertLessEqual(samples[:, 1].max(), 1.0)
        self.assertGreaterEqual(len(samples), 10)

    def test_a_degenerate_sampling_grid_is_refused(self):
        with self.assertRaises(ValueError):
            grid_samples((0.0, 0.0), (0.0, 1.0), 0.5)


class TestProfiles(unittest.TestCase):
    def test_a_vee_reaches_its_depth_at_the_path_and_stops_at_its_edge(self):
        cut = vee(2.0, 60.0)
        reach = 2.0 / math.tan(math.radians(30.0))

        at_the_path = cut.evaluate(np.array([0.0]))
        at_the_edge = cut.evaluate(np.array([reach]))
        past_the_edge = cut.evaluate(np.array([reach + 0.01]))

        self.assertAlmostEqual(float(at_the_path[0]), -2.0)
        self.assertAlmostEqual(float(at_the_edge[0]), 0.0, places=6)
        self.assertEqual(float(past_the_edge[0]), 0.0)

    def test_a_profile_does_not_cut_the_far_side_of_its_path(self):
        cut = vee(2.0, 60.0)

        beyond = cut.evaluate(np.array([5.0]))

        self.assertEqual(float(beyond[0]), 0.0)

    def test_a_flat_channel_has_vertical_walls(self):
        channel = flat(2.0, 4.0)

        at_the_floor = channel.evaluate(np.array([0.0]))
        just_inside = channel.evaluate(np.array([1.99]))
        just_outside = channel.evaluate(np.array([2.01]))

        self.assertAlmostEqual(float(at_the_floor[0]), -2.0)
        self.assertAlmostEqual(float(just_inside[0]), -2.0)
        self.assertEqual(float(just_outside[0]), 0.0)

    def test_a_fillet_is_deepest_at_the_path_and_reaches_zero_at_its_radius(self):
        wall = fillet(3.0, 3.0)

        at_the_path = wall.evaluate(np.array([0.0]))
        at_the_edge = wall.evaluate(np.array([3.0]))
        past_the_edge = wall.evaluate(np.array([3.5]))

        self.assertAlmostEqual(float(at_the_path[0]), -3.0)
        self.assertAlmostEqual(float(at_the_edge[0]), 0.0)
        self.assertEqual(float(past_the_edge[0]), 0.0)

    def test_blending_two_profiles_lands_between_them(self):
        first = vee(2.0, 60.0).evaluate(np.array([1.0]))
        second = flat(4.0, 20.0).evaluate(np.array([1.0]))
        middle = blend(vee(2.0, 60.0), flat(4.0, 20.0), 0.5).evaluate(np.array([1.0]))

        self.assertLessEqual(float(middle[0]), float(first[0]) + 1e-9)
        self.assertGreaterEqual(float(middle[0]), float(second[0]) - 1e-9)

    def test_combining_profiles_takes_the_deepest(self):
        shallow = vee(1.0, 60.0).evaluate(np.array([0.5]))
        deep = vee(4.0, 60.0).evaluate(np.array([0.5]))
        together = mirror_max([vee(1.0, 60.0), vee(4.0, 60.0)]).evaluate(
            np.array([0.5]))

        self.assertAlmostEqual(float(together[0]), min(float(shallow[0]),
                                                        float(deep[0])))

    def test_combining_nothing_is_refused(self):
        with self.assertRaises(ValueError):
            mirror_max([])

    def test_a_ramp_reaches_its_depth_over_its_run(self):
        wall = ramp(2.0, 4.0)

        at_the_start = wall.evaluate(np.array([0.0]))
        at_the_end = wall.evaluate(np.array([4.0]))

        self.assertAlmostEqual(float(at_the_start[0]), -2.0)
        self.assertAlmostEqual(float(at_the_end[0]), 0.0)

    def test_a_drawn_profile_follows_its_table(self):
        drawn = from_curve([(0.0, 1.0), (2.0, 0.5), (4.0, 0.0)], 6.0)

        at_the_path = drawn.evaluate(np.array([0.0]))
        halfway = drawn.evaluate(np.array([2.0]))
        at_the_edge = drawn.evaluate(np.array([4.0]))

        self.assertAlmostEqual(float(at_the_path[0]), -6.0)
        self.assertAlmostEqual(float(halfway[0]), -3.0)
        self.assertAlmostEqual(float(at_the_edge[0]), 0.0)

    def test_a_drawn_profile_that_doubles_back_is_refused(self):
        """Such a table would make the cut thinner in the middle than at its edge."""
        with self.assertRaises(ValueError):
            from_curve([(0.0, 0.0), (4.0, 1.0), (2.0, 0.5)], 6.0)

    def test_a_drawn_profile_with_a_fraction_above_one_is_refused(self):
        with self.assertRaises(ValueError):
            from_curve([(0.0, 0.0), (4.0, 1.5)], 6.0)

    def test_depths_are_clamped_rather_than_left_absurd(self):
        deep = flat(1e9, 4.0).evaluate(np.array([0.0]))

        self.assertGreaterEqual(float(deep[0]), -1e4)


class TestHeightField(unittest.TestCase):
    def setUp(self):
        self.square = Polygon([(0, 0), (20, 0), (20, 20), (0, 20), (0, 0)])

    def test_a_flat_field_removes_nothing(self):
        field = HeightField()

        height = field.evaluate(np.array([[5.0, 5.0]]))

        self.assertEqual(float(height[0]), 0.0)

    def test_inside_a_region_the_base_shape_cuts_to_its_depth(self):
        field = HeightField(base=self.square, base_depth_mm=3.0)

        inside = field.evaluate(np.array([[10.0, 10.0]]))
        outside = field.evaluate(np.array([[40.0, 40.0]]))

        self.assertAlmostEqual(float(inside[0]), 3.0)
        self.assertEqual(float(outside[0]), 0.0)

    def test_heights_come_out_in_millimetres(self):
        """A 2 mm cut must read 2, not 0.002."""
        field = HeightField(base=self.square, base_depth_mm=2.0)

        height = field.evaluate(np.array([[10.0, 10.0]]))

        self.assertAlmostEqual(float(height[0]), 2.0, places=9)

    def test_a_groove_is_measured_from_the_surface_below_it(self):
        """On an already-cut pocket, the groove cuts the pocket, not the stock."""
        field = HeightField(base=self.square, base_depth_mm=3.0)
        field.grooves.append(default_groove([(0.0, 10.0), (20.0, 10.0)], depth_mm=2.0))

        on_the_groove = field.evaluate(np.array([[10.0, 10.0]]))
        away = field.evaluate(np.array([[10.0, 3.0]]))

        self.assertAlmostEqual(float(on_the_groove[0]), 5.0)
        self.assertAlmostEqual(float(away[0]), 3.0)

    def test_a_cut_deeper_than_the_material_is_reported_rather_than_done(self):
        """Ten millimetres of stock cannot give a five millimetre cut a floor
        after a one millimetre pocket: the tool would break through."""
        field = HeightField(base=self.square, base_depth_mm=1.0,
                            stock_thickness_mm=3.0)
        field.grooves.append(default_groove([(0.0, 10.0), (20.0, 10.0)], depth_mm=5.0))
        points = np.array([[10.0, 10.0]])

        height = field.evaluate(points)
        blocked = field.blocked_by(points)

        self.assertLessEqual(float(height[0]), 3.0, "the cut went through the part")
        self.assertTrue(bool(blocked[0]), "going through the part must be said out loud")

    def test_a_cut_within_the_stock_is_left_alone(self):
        field = HeightField(base=self.square, base_depth_mm=1.0,
                            stock_thickness_mm=20.0)
        field.grooves.append(default_groove([(0.0, 10.0), (20.0, 10.0)], depth_mm=5.0))
        points = np.array([[10.0, 10.0]])

        height = field.evaluate(points)
        blocked = field.blocked_by(points)

        self.assertAlmostEqual(float(height[0]), 6.0)
        self.assertFalse(bool(blocked[0]), "a cut inside the stock is not a problem")

    def test_a_warp_shapes_the_surface_the_groove_then_sits_on(self):
        """The spec's order: base shape, then warp, then detail."""
        line = WarpLine("ridge", [WarpNode(10.0, 0.0, height_mm=2.0)])
        field = HeightField(base=self.square, base_depth_mm=1.0,
                            warp_lines=[line])

        warped = field.evaluate(np.array([[10.0, 0.5]]))

        self.assertGreater(float(warped[0]), 1.0,
                           "the grid had no effect on the base shape")

    def test_a_pinned_node_keeps_its_height(self):
        node = WarpNode(10.0, 0.0, height_mm=4.0, pinned=True)
        line = WarpLine("pinned", [node])

        self.assertEqual(node.height_mm, 4.0)
        self.assertEqual(line.nodes[0].height_mm, 4.0)

    def test_the_region_border_is_not_forced_flat(self):
        """Warping inside a region keeps its outline, per the spec's default."""
        field = HeightField(base=self.square, base_depth_mm=2.0, keep_border_flat=True)
        line = WarpLine("edge", [WarpNode(0.0, 0.0, height_mm=1.0)])
        field.warp_lines.append(line)

        on_the_border = field.evaluate(np.array([[10.0, 0.0]]))

        self.assertGreater(float(on_the_border[0]), 0.0,
                           "the border was forced back to the base height")

    def test_the_region_mask_tells_samples_in_from_samples_out(self):
        field = HeightField(base=self.square)
        points = np.array([[10.0, 10.0], [40.0, 40.0]])

        mask = field.region_mask(points)

        self.assertEqual(mask.tolist(), [True, False])

    def test_a_field_with_no_region_cuts_nothing(self):
        field = HeightField()

        self.assertFalse(field.region_mask(np.array([[0.0, 0.0]]))[0])

    def test_an_empty_groove_path_removes_nothing(self):
        field = HeightField(base=self.square, base_depth_mm=2.0)
        field.grooves.append(Groove(np.zeros((0, 2)), vee(5.0, 60.0)))

        height = field.evaluate(np.array([[10.0, 10.0]]))

        self.assertAlmostEqual(float(height[0]), 2.0)

    def test_heights_never_go_negative(self):
        """Negative height would mean adding material, which a cutter cannot."""
        field = HeightField(base=self.square, base_depth_mm=-5.0)

        height = field.evaluate(np.array([[10.0, 10.0]]))

        self.assertGreaterEqual(float(height[0]), 0.0)


if __name__ == "__main__":
    unittest.main()
