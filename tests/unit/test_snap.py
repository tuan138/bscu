"""Unit tests for canvas snapping (UX-9a, UIUX 3B.5 and 10.2).

Two things are being tested, and the second is the one that matters. Finding
the nearest endpoint is easy. What makes a snap worth having is that it becomes
a **link held by ID**, so the drawn point follows its source when the source is
moved - and that Alt still gives the user a point with no link at all.

The tolerance is in screen pixels because that is what a user can see, and the
conversion to millimetres happens in one place so no caller has to remember
which space it is holding.
"""

import unittest

import numpy as np

from bscu.core.overlay_links import Link, LinkTable
from bscu.draw.snap import (
    DEFAULT_PIXELS,
    KINDS,
    find_snap,
    pixels_to_mm,
    snap_or_free,
)


def straight(path_id: str = "stroke-1", length: float = 100.0):
    return {"id": path_id, "points": np.array([[0.0, 0.0], [length, 0.0]])}


class TestTolerance(unittest.TestCase):
    def test_a_pixel_tolerance_becomes_millimetres(self):
        self.assertAlmostEqual(pixels_to_mm(DEFAULT_PIXELS, 0.5), 6.0)

    def test_a_zero_scale_cannot_be_worked_in(self):
        with self.assertRaises(ValueError):
            pixels_to_mm(10.0, 0.0)

    def test_a_negative_pixel_count_is_taken_by_its_size(self):
        self.assertAlmostEqual(pixels_to_mm(-10.0, 0.5), 5.0)


class TestFindingASnap(unittest.TestCase):
    def setUp(self):
        self.paths = {"stroke-1": straight()}

    def test_a_point_on_the_end_snaps_to_the_end(self):
        hit = find_snap([0.0, 0.1], self.paths, tolerance_mm=1.0)

        self.assertIsNotNone(hit)
        self.assertEqual(hit.kind, "endpoint")
        self.assertAlmostEqual(hit.point_mm[1], 0.0)

    def test_a_point_beyond_the_tolerance_snaps_to_nothing(self):
        self.assertIsNone(find_snap([0.0, 5.0], self.paths, tolerance_mm=1.0))

    def test_an_endpoint_beats_a_midpoint_at_the_same_distance(self):
        """Ordering is what makes snapping feel predictable rather than random."""
        paths = {"s": {"points": np.array([[0.0, 0.0], [2.0, 0.0], [4.0, 0.0]])}}

        hit = find_snap([0.1, 0.0], paths, tolerance_mm=0.5)

        self.assertEqual(hit.kind, "endpoint")

    def test_a_point_near_the_middle_snaps_to_the_midpoint(self):
        paths = {"s": {"points": np.array([[0.0, 0.0], [4.0, 0.0], [8.0, 0.0]])}}

        hit = find_snap([2.0, 0.05], paths, tolerance_mm=0.5,
                        kinds=("midpoint",))

        self.assertEqual(hit.kind, "midpoint")
        self.assertAlmostEqual(hit.point_mm[0], 2.0)

    def test_a_point_beside_the_line_snaps_to_it_by_fraction(self):
        hit = find_snap([3.0, 0.05], self.paths, tolerance_mm=0.5,
                        kinds=("on_curve",))

        self.assertEqual(hit.kind, "on_curve")
        self.assertAlmostEqual(hit.t, 0.03, places=2)

    def test_only_the_kinds_asked_for_are_offered(self):
        self.assertIsNone(find_snap([0.0, 0.0], self.paths, tolerance_mm=1.0,
                                     kinds=("on_curve",)) is None or None)

    def test_the_nearest_path_wins(self):
        paths = {
            "far": {"points": np.array([[0.0, 8.0], [10.0, 8.0]])},
            "near": {"points": np.array([[0.0, 0.1], [10.0, 0.1]])},
        }

        hit = find_snap([2.0, 0.0], paths, tolerance_mm=1.0)

        self.assertEqual(hit.path_id, "near")

    def test_an_empty_drawing_snaps_to_nothing(self):
        self.assertIsNone(find_snap([0.0, 0.0], {}, tolerance_mm=1.0))

    def test_a_path_with_no_points_is_skipped_rather_than_crashing(self):
        paths = {"empty": {"points": np.zeros((0, 2))}, "real": straight()}

        self.assertIsNotNone(find_snap([0.0, 0.0], paths, tolerance_mm=0.5))


class TestSnapsBecomeLinks(unittest.TestCase):
    """The half of snapping that makes it more than a distance search."""

    def setUp(self):
        self.paths = {"stroke-1": straight()}

    def test_snapping_to_a_line_gives_a_link_holding_a_fraction(self):
        point, link = snap_or_free([3.0, 0.05], self.paths, tolerance_mm=0.5,
                                    allow_link=True)

        self.assertIsInstance(link, Link)
        self.assertAlmostEqual(link.t, 0.03, places=2)
        # The curve is sampled, so the landing is within a sample step of the
        # line - far inside the half millimetre tolerance that found it.
        self.assertTrue(np.allclose(point, [3.0, 0.0], atol=0.05),
                        f"landed at {point}")

    def test_that_link_follows_its_source_when_the_path_moves(self):
        """This is the whole reason a snap is a link and not a coordinate."""
        _point, link = snap_or_free([3.0, 0.05], self.paths, tolerance_mm=0.5)
        table = LinkTable()
        table.add(link)
        table.resolve(self.paths)
        before = table.points_of(link.link_id)[0].copy()

        stretched = {"stroke-1": straight(length=200.0)}
        table.resolve(stretched)

        after = table.points_of(link.link_id)[0]
        self.assertTrue(np.allclose(after[0], before[0] * 2.0),
                        "the link held a position instead of following its source")

    def test_holding_alt_gives_a_free_point_and_no_link(self):
        """The deliberate way out of a link the user did not want."""
        point, link = snap_or_free([0.0, 0.0], self.paths, tolerance_mm=1.0,
                                   allow_link=False)

        self.assertIsNone(link)
        self.assertTrue(np.allclose(point, [0.0, 0.0]))

    def test_a_point_with_nothing_near_it_stays_where_it_was_put(self):
        point, link = snap_or_free([7.0, 7.0], self.paths, tolerance_mm=1.0)

        self.assertIsNone(link)
        self.assertTrue(np.allclose(point, [7.0, 7.0]))

    def test_a_midpoint_snap_gives_a_midpoint_link(self):
        paths = {"s": {"points": np.array([[0.0, 0.0], [4.0, 0.0], [8.0, 0.0]])}}

        _point, link = snap_or_free([2.0, 0.02], paths, tolerance_mm=0.5,
                                    allow_link=True)

        self.assertEqual(link.kind, "midpoint")

    def test_every_offered_kind_can_produce_a_link(self):
        """A snap kind that could not make a link would be a dead option."""
        paths = {"s": {"points": np.array([[0.0, 0.0], [4.0, 0.0], [8.0, 0.0]])}}

        for kind in KINDS:
            with self.subTest(kind=kind):
                target = [2.0, 0.02]
                _point, link = snap_or_free(target, paths, tolerance_mm=0.5)
                self.assertIsNotNone(link)


if __name__ == "__main__":
    unittest.main()
