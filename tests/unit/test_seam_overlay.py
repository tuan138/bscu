"""Unit tests for what the seam overlay shows (UX-7, UIUX 3.5).

The overlay's job is to be honest about what it is showing, and these tests
pin the three ways it can be dishonest:

* a seam hidden behind a chart drawn as if it were in front, so the user clicks
  something they cannot see;
* a preview that has fallen out of date drawn with no label, which looks like
  an answer;
* a hidden chart quietly removed from the design instead of just from view.

Batch building is separated from drawing so all of that is checkable without a
GPU, which is why these run as plain unit tests.
"""

import unittest

import numpy as np

from bscu.draw import seam_overlay
from bscu.draw.seam_overlay import (
    MIN_WIDTH_PX,
    PALETTES,
    OverlayState,
    build_batches,
    label_positions,
    visible_seams,
)


def seams(count: int) -> np.ndarray:
    """A run of seam edges along a line, in millimetres."""
    return np.asarray([[[float(index), 0.0, 0.0], [float(index + 1), 0.0, 0.0]]
                       for index in range(count)], dtype=np.float64)


class TestBatches(unittest.TestCase):
    def test_seams_come_back_as_a_batch(self):
        state = OverlayState(seam_mm=seams(4))

        batches = build_batches(state)

        self.assertTrue(batches)
        self.assertEqual(batches[0].points.shape[1], 3)

    def test_a_batch_of_n_edges_holds_two_points_each(self):
        state = OverlayState(seam_mm=seams(3))

        batch = build_batches(state)[0]

        self.assertEqual(len(batch), 3)
        self.assertEqual(batch.points.shape, (6, 3))

    def test_nothing_to_show_means_nothing_drawn(self):
        self.assertEqual(build_batches(OverlayState()), [])

    def test_a_thin_seam_is_still_worth_drawing(self):
        state = OverlayState(seam_mm=seams(2), width_px=0.1)

        batch = build_batches(state)[0]

        self.assertGreaterEqual(batch.width_px, MIN_WIDTH_PX)

    def test_each_palette_gives_a_different_colour(self):
        seen = set()
        for name in PALETTES:
            state = OverlayState(seam_mm=seams(2), palette=name)
            seen.add(build_batches(state)[0].colour)
        self.assertEqual(len(seen), len(PALETTES))

    def test_an_unknown_palette_falls_back_rather_than_drawing_nothing(self):
        state = OverlayState(seam_mm=seams(2), palette="chartreuse")

        self.assertTrue(build_batches(state))

    def test_the_occluded_part_looks_different_from_the_front(self):
        """Drawing a hidden seam like a visible one sends the user clicking blind."""
        state = OverlayState(seam_mm=seams(4), hidden_edges={0, 1},
                             show_hidden=True)

        batches = build_batches(state)

        self.assertEqual(len(batches), 2, "the hidden part was not drawn at all")
        shown, hidden = batches
        self.assertEqual(len(shown), 2)
        self.assertEqual(len(hidden), 2)
        self.assertNotEqual(hidden.colour, shown.colour)

    def test_hiding_the_hidden_part_leaves_only_what_is_in_front(self):
        state = OverlayState(seam_mm=seams(4), hidden_edges={0, 1},
                             show_hidden=False)

        batches = build_batches(state)

        self.assertEqual(len(batches), 1)

    def test_one_hidden_edge_leaves_the_others_alone(self):
        state = OverlayState(seam_mm=seams(4), hidden_edges={2})

        self.assertEqual(len(visible_seams(state)), 3)

    def test_hiding_is_only_about_looking(self):
        state = OverlayState(seam_mm=seams(4), hidden_edges={0, 1, 2, 3})

        self.assertEqual(len(visible_seams(state)), 0)
        self.assertEqual(len(seam_overlay.seam_points_mm(state)), 4,
                         "hiding deleted the seams instead of just showing fewer")


class TestPreviewHonesty(unittest.TestCase):
    def test_a_current_preview_carries_no_label(self):
        state = OverlayState(preview_current=True)

        self.assertEqual(state.label_for_preview(), "")
        self.assertEqual(label_positions(state), [])

    def test_a_stale_preview_says_so(self):
        state = OverlayState(preview_current=False)

        self.assertIn("not up to date", state.label_for_preview())
        self.assertTrue(label_positions(state))

    def test_a_stale_preview_uses_the_message_it_was_given(self):
        state = OverlayState(preview_current=False,
                             preview_label="2 of 7 charts left")

        self.assertIn("2 of 7", label_positions(state)[0][0])

    def test_a_candidate_seam_is_labelled_when_it_is_stale(self):
        state = OverlayState(candidate_mm=seams(2), preview_current=False)

        candidate = [b for b in build_batches(state) if b.label]

        self.assertTrue(candidate, "the candidate was drawn with no label at all")

    def test_a_candidate_seam_is_not_labelled_when_it_is_current(self):
        state = OverlayState(candidate_mm=seams(2), preview_current=True)

        candidate = [b for b in build_batches(state) if b.label]

        self.assertEqual(candidate, [])


class TestHandlerState(unittest.TestCase):
    def test_the_overlay_keeps_one_state_the_panel_can_change(self):
        seam_overlay.set_state(OverlayState(seam_mm=seams(2)))

        self.assertEqual(len(seam_overlay.state().seam_mm), 2)

    def test_setting_the_state_leaves_the_previous_one_alone(self):
        first = OverlayState(seam_mm=seams(2))
        seam_overlay.set_state(first)
        seam_overlay.set_state(OverlayState(seam_mm=seams(5)))

        self.assertEqual(len(first.seam_mm), 2)


if __name__ == "__main__":
    unittest.main()
