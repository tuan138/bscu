"""Unit tests for region detection from boundary curves (UX-9b, UIUX 5.6).

The rule the spec is firmest about here is what must *not* happen: a gap is
never closed on its own, a stroke is never cut at a boundary, and a stroke
outside a chart is never deleted. A tool that quietly repairs a drawing is a
tool whose output the user cannot predict, so these tests are mostly about what
is refused.

Closing a boundary only makes a region *selectable*. It does not make a solid,
and nothing here invents one.
"""

import unittest

import numpy as np

from bscu.core.geom2d import Line
from bscu.core.planar_graph import (
    PlanarGraph,
    build_graph,
    find_regions,
    open_ends,
)


def square(size: float = 10.0, origin=(0.0, 0.0), clockwise: bool = False):
    """Four lines around a square, wound the requested way."""
    x, y = origin
    corners = [(x, y), (x + size, y), (x + size, y + size), (x, y + size)]
    if clockwise:
        corners = list(reversed(corners))
    return [Line(corners[index], corners[(index + 1) % 4]) for index in range(4)]


def open_run(size: float = 10.0):
    """Three sides of a square: everything except the last."""
    return [Line((0, 0), (size, 0)), Line((size, 0), (size, size)),
            Line((size, size), (0, size))]


class TestGraphBuilding(unittest.TestCase):
    def test_a_closed_square_becomes_one_loop(self):
        graph = build_graph(square())

        loops = find_regions(graph)

        self.assertEqual(len(loops), 1)
        self.assertTrue(loops[0].closed)
        self.assertAlmostEqual(abs(loops[0].area_mm2), 100.0)

    def test_endpoints_that_touch_within_a_hair_are_the_same_vertex(self):
        lines = [Line((0, 0), (10, 0)), Line((10 + 1e-9, 0), (10, 10))]

        graph = build_graph(lines, tolerance_mm=1e-6)

        self.assertEqual(len(graph.vertices), 3)

    def test_endpoints_further_apart_than_the_tolerance_are_not_joined(self):
        """Joining them would invent a corner the user did not draw."""
        lines = [Line((0, 0), (10, 0)), Line((12, 0), (12, 10))]

        graph = build_graph(lines, tolerance_mm=1e-6)

        self.assertEqual(len(graph.vertices), 4)
        self.assertEqual(len(find_regions(graph)), 0)

    def test_a_negative_tolerance_is_refused(self):
        with self.assertRaises(ValueError):
            build_graph(square(), tolerance_mm=-1.0)

    def test_an_empty_drawing_makes_an_empty_graph(self):
        graph = build_graph([])

        self.assertEqual(len(graph.vertices), 0)
        self.assertEqual(graph.edges.shape, (0, 2))


class TestOpenBoundaries(unittest.TestCase):
    def test_a_gap_makes_no_region_rather_than_a_closed_one(self):
        graph = build_graph(open_run())

        self.assertEqual(find_regions(graph), [])

    def test_a_gap_reports_the_two_ends_that_would_close_it(self):
        graph = build_graph(open_run())

        ends = open_ends(graph)

        self.assertEqual(len(ends), 2)
        self.assertAlmostEqual(float(np.linalg.norm(ends[0] - ends[1])), 10.0, places=6)

    def test_a_closed_drawing_reports_no_ends(self):
        graph = build_graph(square())

        self.assertEqual(len(open_ends(graph)), 0)

    def test_the_gap_is_never_closed_by_the_detector(self):
        """Repairing it would be a decision the user did not make."""
        graph = build_graph(open_run())

        self.assertEqual(graph.open_ends_mm, 2)
        self.assertEqual(len(find_regions(graph)), 0)


class TestRegions(unittest.TestCase):
    def test_two_separate_squares_make_two_regions(self):
        graph = build_graph(square() + square(size=5.0, origin=(20.0, 20.0)))

        regions = find_regions(graph)

        self.assertEqual(len(regions), 2)
        self.assertAlmostEqual(sorted(abs(r.area_mm2) for r in regions)[0], 25.0)

    def test_a_square_inside_a_square_makes_a_region_and_a_hole(self):
        """The inner loop winds the other way, so it is a hole, not a second part."""
        outer = square(size=20.0)
        inner = square(size=5.0, origin=(7.5, 7.5), clockwise=True)

        regions = find_regions(build_graph(outer + inner))

        self.assertEqual(len(regions), 2)
        holes = [r for r in regions if r.is_hole]
        self.assertEqual(len(holes), 1)
        self.assertAlmostEqual(abs(holes[0].area_mm2), 25.0)

    def test_a_region_knows_which_points_are_inside_it(self):
        graph = build_graph(square(size=10.0))

        region = find_regions(graph)[0]

        inside = region.contains(np.array([[5.0, 5.0]]))
        outside = region.contains(np.array([[15.0, 5.0]]))

        self.assertTrue(bool(inside[0]))
        self.assertFalse(bool(outside[0]))

    def test_a_region_with_opposite_winding_says_it_is_a_hole(self):
        graph = build_graph(square(size=10.0, clockwise=True))

        region = find_regions(graph)[0]

        self.assertTrue(region.is_hole)

    def test_a_region_reports_its_border_as_mm(self):
        graph = build_graph(square(size=10.0))

        region = find_regions(graph)[0]

        self.assertAlmostEqual(region.perimeter_mm, 40.0, places=6)

    def test_a_loop_that_crosses_itself_is_still_a_loop(self):
        """A crossing boundary is still a boundary; the winding decides the rest."""
        lines = [Line((0, 0), (10, 10)), Line((10, 10), (10, 0)),
                 Line((10, 0), (0, 10)), Line((0, 10), (0, 0))]

        regions = find_regions(build_graph(lines))

        self.assertTrue(regions)


class TestGraphTypes(unittest.TestCase):
    def test_the_graph_exposes_its_own_shape(self):
        graph = build_graph(square())

        self.assertIsInstance(graph, PlanarGraph)
        self.assertEqual(graph.vertices.shape[1], 2)
        self.assertEqual(graph.edges.shape[1], 2)

    def test_a_region_carries_the_loops_it_is_made_of(self):
        graph = build_graph(square())

        region = find_regions(graph)[0]

        self.assertGreaterEqual(len(region.loops), 1)


if __name__ == "__main__":
    unittest.main()
