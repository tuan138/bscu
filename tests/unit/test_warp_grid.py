"""Unit tests for the shaping grid (UX-10, UIUX 5.7).

The grid's rules are about what the user may rely on. A crossing has one height
or the surface is not a surface; a pinned node holds or the pin is a lie; and a
line eases out rather than ending in a crease. Those are what is under test.

The grid is kept out of ``height_field`` on purpose: the field combines a base
shape, a grid and a set of grooves, and a second model of the grid inside the
field is how the two would start disagreeing.
"""

import unittest

import numpy as np

from bscu.core.warp_grid import WarpGrid, WarpLine, WarpNode


def line(name: str, points, heights, falloff: float = 2.0) -> WarpLine:
    return WarpLine(name, [tuple(p) for p in points], list(heights), falloff)


class TestNodes(unittest.TestCase):
    def test_a_node_is_a_value_and_moving_it_returns_a_new_one(self):
        node = WarpNode(1.0, 2.0, 3.0)

        moved = node.move_to(4.0, 5.0)

        self.assertEqual(node.position, (1.0, 2.0))
        self.assertEqual(moved.position, (4.0, 5.0))
        self.assertAlmostEqual(moved.height_mm, 3.0, msg="the height was lost")

    def test_a_pinned_node_cannot_be_moved(self):
        node = WarpNode(1.0, 2.0, 3.0, pinned=True)

        with self.assertRaises(ValueError):
            node.move_to(4.0, 5.0)

    def test_raising_a_pinned_node_still_works_because_that_is_a_setting(self):
        node = WarpNode(1.0, 2.0, 3.0, pinned=True)

        raised = node.raised_by(1.0)

        self.assertAlmostEqual(raised.height_mm, 4.0)
        self.assertTrue(raised.pinned)


class TestSharedNodes(unittest.TestCase):
    def test_two_lines_crossing_share_one_node(self):
        grid = WarpGrid([
            line("a", [(0, 5), (10, 5)], [0.0, 0.0]),
            line("b", [(5, 0), (5, 10)], [0.0, 0.0]),
        ])

        nodes = grid.shared_nodes()

        self.assertEqual(len(nodes), 1)
        self.assertEqual(set(nodes[0].lines), {"a", "b"},
                         "the crossing does not know both lines meet there")

    def test_lines_that_do_not_meet_share_nothing(self):
        grid = WarpGrid([
            line("a", [(0, 0), (10, 0)], [0.0, 0.0]),
            line("b", [(0, 3), (10, 3)], [0.0, 0.0]),
        ])

        self.assertEqual(grid.shared_nodes(), [])

    def test_three_lines_through_one_point_share_one_node(self):
        grid = WarpGrid([
            line("a", [(5, 0), (5, 10)], [0.0, 0.0]),
            line("b", [(0, 5), (10, 5)], [0.0, 0.0]),
            line("c", [(0, 0), (10, 10)], [0.0, 0.0]),
        ])

        nodes = grid.shared_nodes()

        self.assertEqual(len(nodes), 1)
        self.assertEqual(set(nodes[0].lines), {"a", "b", "c"})

    def test_a_line_kept_entirely_outside_a_chart_meets_nothing(self):
        grid = WarpGrid([line("a", [(0, 0), (1, 0)], [0.0, 0.0])])

        self.assertEqual(grid.shared_nodes(), [])

    def test_a_one_point_line_does_not_meet_every_line_on_the_canvas(self):
        """A point is only a meeting where another line actually passes."""
        grid = WarpGrid([
            WarpLine("dot", [(3.0, 3.0)], [1.0]),
            line("a", [(0, 0), (10, 0)], [0.0, 0.0]),
            line("b", [(0, 9), (10, 9)], [0.0, 0.0]),
        ])

        self.assertEqual(grid.shared_nodes(), [],
                         "a lone point claimed meetings it was not part of")

    def test_a_one_point_line_on_another_line_is_a_meeting(self):
        grid = WarpGrid([
            WarpLine("dot", [(5.0, 0.0)], [1.0]),
            line("a", [(0, 0), (10, 0)], [0.0, 0.0]),
        ])

        nodes = grid.shared_nodes()

        self.assertEqual(len(nodes), 1)
        self.assertEqual(set(nodes[0].lines), {"a", "dot"})


class TestInfluence(unittest.TestCase):
    def test_a_line_lifts_the_surface_along_its_whole_length(self):
        grid = WarpGrid([line("a", [(0, 5), (10, 5)], [2.0, 2.0], falloff=3.0)])

        on_the_line = grid.influence(np.array([[5.0, 5.0]]))
        far_away = grid.influence(np.array([[5.0, 40.0]]))

        self.assertGreater(float(on_the_line[0]), 1.0)
        # An exponential has a tail; what matters is that a line has no say
        # well away from the chart it belongs to.
        self.assertLess(float(far_away[0]), 1e-3)

    def test_the_falloff_is_smooth_rather_than_a_step(self):
        """A line must ease out, not end in a crease the cutter would feel."""
        grid = WarpGrid([line("a", [(0, 0), (20, 0)], [2.0, 2.0], falloff=4.0)])

        distances = [0.0, 2.0, 4.0, 8.0, 16.0]
        values = [float(grid.influence(np.array([[0.0, d]]))[0]) for d in distances]

        for nearer, farther in zip(values, values[1:]):
            self.assertLess(farther, nearer, "the influence did not decay")
            self.assertGreater(farther, -1e-9)

    def test_an_empty_grid_shapes_nothing(self):
        self.assertTrue(np.allclose(WarpGrid().influence(np.zeros((3, 2))), 0.0))

    def test_two_lines_add_where_they_overlap(self):
        grid = WarpGrid([
            line("a", [(0, 0), (10, 0)], [1.0, 1.0], falloff=5.0),
            line("b", [(0, 0), (10, 0)], [2.0, 2.0], falloff=5.0),
        ])

        total = float(grid.influence(np.array([[5.0, 0.0]]))[0])

        self.assertAlmostEqual(total, 3.0, places=6)


class TestRelaxation(unittest.TestCase):
    def test_relaxation_eases_a_spike_towards_its_neighbours(self):
        grid = WarpGrid([line("a", [(0, 0), (1, 0), (2, 0)], [0.0, 10.0, 0.0])])
        nodes = grid.shared_nodes()
        del nodes

        grid.relax(passes=10, strength=0.5)

        middle = grid.lines[0].heights_mm[1]
        self.assertLess(middle, 10.0, "the spike never came down")

    def test_a_pinned_node_is_never_moved_by_relaxation(self):
        """The pin is a decision; easing through it would be a lie."""
        grid = WarpGrid([
            line("a", [(0, 0), (1, 0)], [0.0, 0.0]),
            line("b", [(1, 0), (2, 0)], [0.0, 0.0]),
        ])
        crossing = grid.shared_nodes()[0]
        crossing.pinned = True
        crossing.height_mm = 5.0
        grid.lines[0].heights_mm[1] = 5.0
        grid.lines[1].heights_mm[0] = 5.0

        grid.relax(passes=5)

        self.assertAlmostEqual(crossing.height_mm, 5.0,
                               msg="relaxation overrode a pinned node")

    def test_relaxing_an_empty_grid_does_nothing(self):
        self.assertEqual(WarpGrid().relax(), 0)


class TestBookkeeping(unittest.TestCase):
    def test_adding_a_line_twice_replaces_rather_than_duplicates(self):
        grid = WarpGrid()

        grid.add(line("a", [(0, 0), (1, 0)], [1.0, 1.0]))
        grid.add(line("a", [(0, 0), (2, 0)], [3.0, 3.0]))

        self.assertEqual(len(grid.lines), 1)
        self.assertEqual(len(grid.lines[0].points_mm), 2)

    def test_removing_a_line_says_whether_it_was_there(self):
        grid = WarpGrid([line("a", [(0, 0), (1, 0)], [0.0, 0.0])])

        self.assertTrue(grid.remove("a"))
        self.assertFalse(grid.remove("a"))

    def test_bounds_cover_every_line(self):
        grid = WarpGrid([
            line("a", [(0, 0), (10, 0)], [0.0, 0.0]),
            line("b", [(5, 5), (5, 20)], [0.0, 0.0]),
        ])

        low, high = grid.bounds()

        self.assertTrue(np.allclose(low, [0.0, 0.0]))
        self.assertTrue(np.allclose(high, [10.0, 20.0]))

    def test_an_empty_grid_has_no_bounds_rather_than_a_fake_one(self):
        self.assertIsNone(WarpGrid().bounds())


if __name__ == "__main__":
    unittest.main()
