"""Unit tests for overlay snap links (UX-12, UIUX 10.2 and 10.3).

A link is a promise that a drawn point stays attached to the thing it was
snapped to. The rules that make that promise keepable are the ones under test:

* A link stores **IDs, never indices** (K2). Re-ordering a drawing's paths must
  not move a linked point, because a link that follows an index is a link that
  silently jumps the moment anything is inserted.
* Links flow one way. The relief source never depends on the overlay, so
  painting over a model cannot change the model.
* A link whose source is gone **breaks loudly**: it keeps its last position,
  says so, and the region does not disappear. Guessing a replacement would move
  a painted area without being asked.
"""

import unittest

import numpy as np

from bscu.core.overlay_links import (
    BROKEN_CODE,
    Link,
    LinkTable,
    anchor,
    follow_segment,
    groove_edge,
    intersection,
    midpoint,
    on_curve,
)


def path(points, path_id: str) -> dict:
    return {"id": path_id, "points": np.asarray(points, dtype=np.float64)}


class TestLinkIdentity(unittest.TestCase):
    def test_a_link_stores_an_id_not_an_index(self):
        link = on_curve("stroke-7", 0.25)

        self.assertEqual(link.path_id, "stroke-7")
        self.assertEqual(link.kind, "on_curve")
        self.assertFalse(hasattr(link, "path_index"))

    def test_two_links_to_the_same_path_are_distinct_objects(self):
        first = on_curve("stroke-7", 0.1)
        second = on_curve("stroke-7", 0.9)

        first.t = 0.4

        self.assertAlmostEqual(second.t, 0.9)

    def test_a_link_records_where_it_was_last(self):
        link = on_curve("stroke-7", 0.5)

        self.assertEqual(link.last_point_mm.tolist(), [0.0, 0.0])


class TestResolution(unittest.TestCase):
    def setUp(self):
        self.paths = {
            "stroke-7": path([[0, 0], [10, 0], [10, 10]], "stroke-7"),
        }

    def test_an_on_curve_link_keeps_its_fraction_when_the_path_changes(self):
        """The spec's own rule: on-curve holds t, it does not hold a position."""
        table = LinkTable()
        link = on_curve("stroke-7", 0.5)
        table.add(link)
        table.resolve(self.paths)

        before = table.points_of(link.link_id)
        self.paths["stroke-7"]["points"] = np.array([[0, 0], [20, 0], [20, 20]])
        table.resolve(self.paths)
        after = table.points_of(link.link_id)

        # The path is 20 mm round, so half of it is the corner; doubling the
        # path doubles that too, which is what holding a fraction means.
        self.assertTrue(np.allclose(before[0], [10.0, 0.0]))
        self.assertTrue(np.allclose(after[0], [20.0, 0.0]),
                        "the link held a position instead of a fraction")

    def test_a_midpoint_link_stays_the_midpoint(self):
        table = LinkTable()
        link = midpoint("stroke-7", segment=0)
        table.add(link)
        table.resolve(self.paths)

        self.assertTrue(np.allclose(table.points_of(link.link_id)[0], [5.0, 0.0]))

        self.paths["stroke-7"]["points"] = np.array([[0, 0], [4, 0], [4, 4]])
        table.resolve(self.paths)

        self.assertTrue(np.allclose(table.points_of(link.link_id)[0], [2.0, 0.0]))

    def test_an_anchor_link_follows_the_anchor_itself(self):
        """An anchor moves where the anchor says, not to a fraction of the path."""
        source = self.paths["stroke-7"]
        source["anchors"] = {"anchor-3": [3.0, 7.0]}
        table = LinkTable()
        link = anchor("stroke-7", "anchor-3")
        table.add(link)
        table.resolve(self.paths)

        self.assertEqual(table.broken_links(), [])
        self.assertTrue(np.allclose(table.points_of(link.link_id)[0], [3.0, 7.0]))

        source["anchors"]["anchor-3"] = [4.0, 9.0]
        table.resolve(self.paths)

        self.assertTrue(np.allclose(table.points_of(link.link_id)[0], [4.0, 9.0]))

    def test_an_anchor_that_does_not_exist_leaves_the_link_broken(self):
        table = LinkTable()
        link = anchor("stroke-7", "anchor-that-was-never-there")
        table.add(link)

        table.resolve(self.paths)

        self.assertTrue(table.is_broken(link.link_id))

    def test_a_link_to_a_deleted_path_breaks_and_keeps_its_last_point(self):
        """The spec's rule: keep the position, say so, do not guess."""
        table = LinkTable()
        link = on_curve("stroke-7", 0.5)
        table.add(link)
        table.resolve(self.paths)
        last = table.points_of(link.link_id)[0].copy()

        self.paths.pop("stroke-7")
        table.resolve(self.paths)

        self.assertTrue(table.is_broken(link.link_id))
        self.assertTrue(np.allclose(table.points_of(link.link_id)[0], last),
                        "a broken link moved instead of holding its place")
        self.assertIn(BROKEN_CODE, table.broken_links()[0].code)

    def test_a_broken_link_can_be_made_free_rather_than_repaired(self):
        table = LinkTable()
        link = on_curve("stroke-7", 0.5)
        table.add(link)
        table.resolve(self.paths)
        table.resolve({})

        table.detach(link.link_id)

        self.assertFalse(table.is_broken(link.link_id))
        self.assertIsNone(table.get(link.link_id))

    def test_re_ordering_the_paths_does_not_move_a_linked_point(self):
        """This is the whole reason links store IDs: an index would jump."""
        table = LinkTable()
        link = on_curve("stroke-7", 0.5)
        table.add(link)
        table.resolve(self.paths)
        before = table.points_of(link.link_id)[0].copy()

        reordered = {
            "stroke-0": path([[99, 99], [99, 100]], "stroke-0"),
            "stroke-7": self.paths["stroke-7"],
        }
        table.resolve(reordered)

        self.assertTrue(np.allclose(table.points_of(link.link_id)[0], before))

    def test_an_intersection_link_recomputes_when_a_path_moves(self):
        first = path([[0, 0], [10, 0]], "a")
        second = path([[5, -5], [5, 5]], "b")
        table = LinkTable()
        link = intersection("a", "b", index=0)
        table.add(link)
        table.resolve({"a": first, "b": second})

        self.assertTrue(np.allclose(table.points_of(link.link_id)[0], [5.0, 0.0]))

        table.resolve({"a": first, "b": path([[7, -5], [7, 5]], "b")})

        self.assertTrue(np.allclose(table.points_of(link.link_id)[0], [7.0, 0.0]))

    def test_a_groove_edge_link_keeps_its_side(self):
        table = LinkTable()
        link = groove_edge("stroke-7", 0.5, side="left")
        table.add(link)
        table.resolve(self.paths)

        self.assertEqual(table.get(link.link_id).side, "left")
        self.assertAlmostEqual(table.points_of(link.link_id)[0][1], 0.0)

    def test_a_follow_segment_link_needs_two_ends(self):
        with self.assertRaises(ValueError):
            follow_segment("stroke-7", 0.0)


class TestRegionSurvival(unittest.TestCase):
    def test_losing_every_source_reports_rather_than_deletes_the_region(self):
        table = LinkTable()
        link = on_curve("stroke-7", 0.5)
        table.add(link)
        table.resolve({"stroke-7": path([[0, 0], [10, 0]], "stroke-7")})

        table.resolve({})

        self.assertEqual(len(table.all()), 1, "the region was deleted")
        self.assertEqual(len(table.broken_links()), 1)

    def test_a_broken_link_says_where_it_was(self):
        table = LinkTable()
        link = on_curve("stroke-7", 0.5)
        table.add(link)
        table.resolve({"stroke-7": path([[0, 0], [10, 0]], "stroke-7")})
        table.resolve({})

        broken = table.broken_links()[0]

        self.assertGreaterEqual(len(broken.last_point_mm), 2)
        self.assertIn("stroke-7", broken.message)

    def test_resolving_twice_does_not_duplicate_a_link(self):
        table = LinkTable()
        table.add(on_curve("stroke-7", 0.5))
        paths = {"stroke-7": path([[0, 0], [10, 0]], "stroke-7")}

        table.resolve(paths)
        table.resolve(paths)

        self.assertEqual(len(table.all()), 1)


class TestLinkValue(unittest.TestCase):
    def test_a_link_carries_its_kind_and_its_message(self):
        link = Link(kind="on_curve", path_id="stroke-7", t=0.5)

        self.assertTrue(link.link_id)
        self.assertEqual(link.kind, "on_curve")
        self.assertTrue(link.message)

    def test_an_unknown_kind_is_refused(self):
        with self.assertRaises(ValueError):
            Link(kind="telepathy", path_id="stroke-7")


if __name__ == "__main__":
    unittest.main()
