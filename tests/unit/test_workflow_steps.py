"""Unit tests for pure workflow step-state derivation (UX-0).

Model: each step owns exactly one accepted deliverable, mirroring UIUX mục 2.5/2.7.
  STOCK  -> stock accepted (mesh selected)
  SEAM   -> accepted UV mapping ("Dung ban trai nay" in Caro)
  LAYOUT -> approved layout (Ban trai)
  RELIEF -> pattern created (Tao phu dieu)
A tab is unlocked when the previous step's deliverable exists.
"""

import unittest

from bscu.core.workflow import (
    STEP_LABELS,
    STEP_ORDER,
    StepFacts,
    StepStatus,
    derive_step_status,
    is_step_unlocked,
)


def facts(**overrides) -> StepFacts:
    """All deliverables present and healthy; apply overrides on top."""
    base = StepFacts(
        has_stock=True,
        stock_is_mesh=True,
        has_uv_active=True,
        has_approved_layout=True,
        has_pattern=False,
        stock_error=False,
        seam_error=False,
        uv_error=False,
        layout_error=False,
        pattern_error=False,
        stock_warning=False,
        seam_warning=False,
        uv_warning=False,
        layout_warning=False,
        pattern_warning=False,
        computing_step=None,
    )
    return StepFacts(**{**base.__dict__, **overrides})


class TestStepOrder(unittest.TestCase):
    def test_four_steps_in_workflow_order(self):
        self.assertEqual(list(STEP_ORDER), ["STOCK", "SEAM", "LAYOUT", "RELIEF"])

    def test_every_step_has_a_non_empty_label(self):
        for step in STEP_ORDER:
            self.assertTrue(STEP_LABELS[step].strip())


class TestDeriveStepStatus(unittest.TestCase):
    def test_no_stock_leaves_every_step_undone(self):
        statuses = derive_step_status(facts(has_stock=False))
        self.assertEqual(statuses, (StepStatus.NOT_DONE,) * 4)

    def test_non_mesh_selection_is_not_an_accepted_stock(self):
        statuses = derive_step_status(
            facts(stock_is_mesh=False, has_uv_active=False,
                  has_approved_layout=False)
        )
        self.assertEqual(statuses[0], StepStatus.NOT_DONE)

    def test_stock_only_marks_first_step_done(self):
        statuses = derive_step_status(
            facts(has_uv_active=False, has_approved_layout=False)
        )
        self.assertEqual(statuses[0], StepStatus.DONE)
        self.assertEqual(statuses[1:], (StepStatus.NOT_DONE,) * 3)

    def test_missing_uv_is_just_not_started_yet(self):
        statuses = derive_step_status(
            facts(has_uv_active=False, has_approved_layout=False)
        )
        self.assertEqual(statuses[1], StepStatus.NOT_DONE)

    def test_error_without_accepted_stock_never_surfaces(self):
        statuses = derive_step_status(
            facts(has_stock=False, uv_error=True, layout_error=True,
                  pattern_error=True)
        )
        self.assertEqual(statuses, (StepStatus.NOT_DONE,) * 4)

    def test_stock_error_takes_precedence_over_done(self):
        statuses = derive_step_status(
            facts(stock_error=True, has_uv_active=False, has_approved_layout=False)
        )
        self.assertEqual(statuses[0], StepStatus.NEEDS_FIX)
        self.assertEqual(statuses[1], StepStatus.NOT_DONE)

    def test_warning_beats_done(self):
        statuses = derive_step_status(facts(uv_warning=True))
        self.assertEqual(statuses[1], StepStatus.WARNING)

    def test_computing_beats_error_and_warning(self):
        statuses = derive_step_status(
            facts(uv_error=True, uv_warning=True, computing_step="SEAM")
        )
        self.assertEqual(statuses[1], StepStatus.COMPUTING)

    def test_pattern_present_marks_last_step_done(self):
        statuses = derive_step_status(facts(has_pattern=True))
        self.assertEqual(statuses[3], StepStatus.DONE)

    def test_later_error_never_revokes_earlier_step(self):
        statuses = derive_step_status(facts(uv_error=True, has_approved_layout=False))
        self.assertEqual(statuses[0], StepStatus.DONE)
        self.assertEqual(statuses[1], StepStatus.NEEDS_FIX)
        self.assertEqual(statuses[2], StepStatus.NOT_DONE)


class TestIsStepUnlocked(unittest.TestCase):
    def test_first_tab_never_locked(self):
        unlocked, blocker = is_step_unlocked("STOCK", facts(has_stock=False))
        self.assertTrue(unlocked)
        self.assertIsNone(blocker)

    def test_caro_tab_unlocked_once_stock_accepted(self):
        unlocked, blocker = is_step_unlocked("SEAM", facts(has_uv_active=False))
        self.assertTrue(unlocked)
        self.assertIsNone(blocker)

    def test_layout_tab_locked_and_names_the_caro_tab(self):
        unlocked, blocker = is_step_unlocked(
            "LAYOUT", facts(has_uv_active=False, has_approved_layout=False)
        )
        self.assertFalse(unlocked)
        self.assertEqual(blocker, "SEAM")

    def test_layout_tab_unlocked_after_uv_accepted(self):
        unlocked, blocker = is_step_unlocked("LAYOUT", facts())
        self.assertTrue(unlocked)
        self.assertIsNone(blocker)

    def test_relief_tab_locked_names_layout_tab(self):
        unlocked, blocker = is_step_unlocked(
            "RELIEF", facts(has_approved_layout=False)
        )
        self.assertFalse(unlocked)
        self.assertEqual(blocker, "LAYOUT")


if __name__ == "__main__":
    unittest.main()
