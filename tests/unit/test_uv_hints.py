"""Unit tests for the Tab 2 brush hints (UX-5, UIUX 3B.3).

The brushes never touch UV. They write hints on faces, and the solver reads
those hints back every time the layout is produced. That is the whole reason a
seam edit does not throw the user's work away, so these tests are mostly about
the hints surviving, staying inside their limits, and refusing to be silently
dropped when a seam cuts through a pinned region.
"""

import unittest

import numpy as np

from bscu.core.uv_hints import (
    MAX_DENSITY,
    MIN_DENSITY,
    BrushHints,
    neighbour_pairs,
    paint,
    relax,
    split_pins,
)


def strip_faces(count: int) -> np.ndarray:
    """A single row of quads: two triangles per cell, easy to reason about."""
    faces = []
    for index in range(count - 1):
        left, right = index, index + 1
        faces.append([left, left + 1, right])
        faces.append([right, left + 1, right + 1])
    return np.asarray(faces, dtype=np.int64)


def make_hints(count: int) -> BrushHints:
    faces = strip_faces(count)
    return BrushHints(
        faces=faces,
        density=np.ones(len(faces)),
        pin=np.zeros(len(faces), dtype=bool),
        priority=np.zeros(len(faces)),
        direction=np.zeros((len(faces), 2)),
    )


class TestPainting(unittest.TestCase):
    def test_expand_raises_density_only_where_the_brush_landed(self):
        hints = make_hints(6)
        mask = np.zeros(len(hints.faces), dtype=bool)
        mask[:2] = True

        paint(hints, mask, "expand", strength=1.0)

        self.assertAlmostEqual(hints.density[0], 2.0)
        self.assertAlmostEqual(hints.density[1], 2.0)
        self.assertTrue(np.allclose(hints.density[2:], 1.0))

    def test_shrink_lowers_density_and_never_reaches_zero(self):
        hints = make_hints(6)
        mask = np.zeros(len(hints.faces), dtype=bool)
        mask[:2] = True

        for _ in range(40):
            paint(hints, mask, "shrink", strength=1.0)

        self.assertGreaterEqual(hints.density.min(), MIN_DENSITY)
        self.assertLess(hints.density[0], 1.0)

    def test_density_stays_inside_its_limits_both_ways(self):
        hints = make_hints(4)
        mask = np.ones(len(hints.faces), dtype=bool)

        for _ in range(30):
            paint(hints, mask, "expand", strength=1.0)
        self.assertLessEqual(hints.density.max(), MAX_DENSITY)

        for _ in range(60):
            paint(hints, mask, "shrink", strength=1.0)
        self.assertGreaterEqual(hints.density.min(), MIN_DENSITY)

    def test_pin_and_priority_are_written_not_multiplied(self):
        """Priority is a setting, so a stroke should set it, not accumulate it."""
        hints = make_hints(6)
        mask = np.zeros(len(hints.faces), dtype=bool)
        mask[3] = True

        paint(hints, mask, "pin")
        paint(hints, mask, "priority", strength=0.25)

        self.assertTrue(hints.pin[3])
        self.assertFalse(hints.pin[0])
        self.assertAlmostEqual(hints.priority[3], 0.25)
        self.assertAlmostEqual(hints.priority[0], 0.0)

    def test_direction_stores_a_unit_vector(self):
        hints = make_hints(6)
        mask = np.zeros(len(hints.faces), dtype=bool)
        mask[1] = True

        paint(hints, mask, "direction", direction=np.array([3.0, 4.0]))

        self.assertAlmostEqual(np.linalg.norm(hints.direction[1]), 1.0, places=9)
        self.assertAlmostEqual(hints.direction[1][0], 0.6, places=9)

    def test_a_direction_of_zero_length_is_refused(self):
        hints = make_hints(4)
        mask = np.ones(len(hints.faces), dtype=bool)

        with self.assertRaises(ValueError):
            paint(hints, mask, "direction", direction=np.array([0.0, 0.0]))

    def test_painting_nothing_changes_nothing(self):
        hints = make_hints(6)
        before = hints.density.copy()

        changed = paint(hints, np.zeros(len(hints.faces), dtype=bool), "expand")

        self.assertEqual(changed, 0)
        self.assertTrue(np.array_equal(hints.density, before))

    def test_an_unknown_brush_name_is_refused(self):
        hints = make_hints(4)
        mask = np.ones(len(hints.faces), dtype=bool)

        with self.assertRaises(ValueError):
            paint(hints, mask, "sideways")


class TestRelax(unittest.TestCase):
    def test_relax_flattens_a_spike_back_towards_the_neighbours(self):
        hints = make_hints(9)
        mask = np.zeros(len(hints.faces), dtype=bool)
        mask[8] = True
        paint(hints, mask, "expand", strength=2.0)
        spiked = hints.density[8]

        neighbours = neighbour_pairs(hints.faces)
        relax(hints, neighbours, passes=8)

        self.assertLess(hints.density[8], spiked)
        self.assertGreater(hints.density[8], 1.0)

    def test_relax_on_a_flat_hint_set_changes_nothing(self):
        hints = make_hints(9)
        before = hints.density.copy()

        relax(hints, neighbour_pairs(hints.faces), passes=4)

        self.assertTrue(np.allclose(hints.density, before))

    def test_relax_leaves_the_pin_marker_alone(self):
        """Relax smooths what the user painted; it must not unlock pinned areas."""
        hints = make_hints(9)
        mask = np.zeros(len(hints.faces), dtype=bool)
        mask[4] = True
        paint(hints, mask, "pin")

        relax(hints, neighbour_pairs(hints.faces), passes=5)

        self.assertTrue(hints.pin[4])


class TestSeamInteraction(unittest.TestCase):
    def test_a_pin_region_cut_by_a_seam_is_reported(self):
        """A pinned region the seam now runs through has to reach the user."""
        hints = make_hints(7)
        mask = np.zeros(len(hints.faces), dtype=bool)
        mask[2:5] = True
        paint(hints, mask, "pin")

        islands = np.zeros(len(hints.faces), dtype=np.int64)
        islands[3] = 1  # a seam landed in the middle of the pinned strip

        broken = split_pins(hints, islands)

        self.assertEqual(len(broken), 1)
        self.assertGreater(len(broken[0]), 1, "the split should name both halves")

    def test_a_pin_region_the_seam_misses_is_left_alone(self):
        hints = make_hints(7)
        mask = np.zeros(len(hints.faces), dtype=bool)
        mask[2:5] = True
        paint(hints, mask, "pin")

        islands = np.zeros(len(hints.faces), dtype=np.int64)
        islands[len(hints.faces) - 1] = 1  # the seam is far away

        self.assertEqual(split_pins(hints, islands), [])

    def test_an_unpinned_chart_reports_nothing(self):
        hints = make_hints(7)
        islands = np.arange(len(hints.faces), dtype=np.int64)

        self.assertEqual(split_pins(hints, islands), [])


class TestRoundTrip(unittest.TestCase):
    def test_hints_survive_a_save_and_reload(self):
        """Saved in the .blend, so a reopened file has to behave identically."""
        hints = make_hints(8)
        mask = np.zeros(len(hints.faces), dtype=bool)
        mask[2:5] = True
        paint(hints, mask, "expand", strength=0.5)
        paint(hints, mask, "pin")
        paint(hints, mask, "priority", strength=0.75)
        paint(hints, mask, "direction", direction=np.array([1.0, 0.0]))

        # Faces come from the mesh itself, not from the hint attributes, so
        # only the four hint arrays have to survive the round trip.
        restored = BrushHints.from_arrays(*hints.to_arrays(), len(hints.faces))

        self.assertTrue(np.allclose(restored.density, hints.density))
        self.assertTrue(np.array_equal(restored.pin, hints.pin))
        self.assertTrue(np.allclose(restored.priority, hints.priority))
        self.assertTrue(np.allclose(restored.direction, hints.direction))

    def test_a_hint_set_built_from_nothing_has_neutral_values(self):
        hints = BrushHints.from_arrays(
            np.zeros(0), np.zeros(0), np.zeros(0), np.zeros((0, 2)), 3
        )

        self.assertEqual(len(hints.density), 3)
        self.assertTrue(np.allclose(hints.density, 1.0))
        self.assertFalse(hints.pin.any())


if __name__ == "__main__":
    unittest.main()
