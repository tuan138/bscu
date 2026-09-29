"""Unit tests for job revision and staleness rules (UX-2, UIUX D1/K3).

K3: a job carries the revision of the stock, topology, region, seam, mapping and
parameters it was built from, and its result is applied only while that revision
still matches. Cancel, Undo, a stock change or a new job of the same kind all
invalidate whatever is in flight.
"""

import unittest

from bscu.core.jobs import (
    DONE,
    FAILED,
    PENDING,
    RUNNING,
    Job,
    JobKind,
    Revision,
    RevisionTracker,
    current_job_for,
)


def done_job(kind, revision):
    job = Job(kind=kind, revision=revision)
    job.state = DONE
    return job


class TestRevision(unittest.TestCase):
    def test_equal_revisions_compare_equal(self):
        self.assertEqual(Revision(1, 2, 3), Revision(1, 2, 3))

    def test_any_differing_field_makes_a_different_revision(self):
        self.assertNotEqual(Revision(1, 2, 3), Revision(9, 2, 3))
        self.assertNotEqual(Revision(1, 2, 3), Revision(1, 9, 3))
        self.assertNotEqual(Revision(1, 2, 3), Revision(1, 2, 9))

    def test_revision_is_hashable(self):
        self.assertEqual(len({Revision(1, 2, 3), Revision(1, 2, 3)}), 1)


class TestRevisionTracker(unittest.TestCase):
    def test_new_tracker_starts_at_revision_zero(self):
        self.assertEqual(RevisionTracker().revision, Revision(0, 0, 0))

    def test_bump_returns_the_new_revision(self):
        tracker = RevisionTracker()
        self.assertEqual(tracker.bump(stock=1, topology=1), Revision(1, 1, 1))
        self.assertEqual(tracker.revision, Revision(1, 1, 1))

    def test_bump_with_no_arguments_advances_only_the_counter(self):
        tracker = RevisionTracker(Revision(4, 5, 6))
        self.assertEqual(tracker.bump(), Revision(4, 5, 7))
    def test_bump_invalidates_a_previously_issued_revision(self):
        tracker = RevisionTracker(Revision(1, 1, 1))
        old = tracker.revision
        tracker.bump()
        self.assertNotEqual(tracker.revision, old)


class TestJobFreshness(unittest.TestCase):
    def test_a_pending_job_starts_pending(self):
        self.assertEqual(Job(kind="uv", revision=Revision(1, 1, 1)).state, PENDING)

    def test_a_fresh_finished_job_may_be_applied(self):
        tracker = RevisionTracker(Revision(1, 1, 1))
        job = done_job(JobKind.UV, Revision(1, 1, 1))
        self.assertTrue(job.is_applicable(tracker.revision))

    def test_a_job_from_an_older_revision_may_not_be_applied(self):
        tracker = RevisionTracker(Revision(2, 1, 1))
        job = done_job(JobKind.UV, Revision(1, 1, 1))
        self.assertFalse(job.is_applicable(tracker.revision))

    def test_only_finished_jobs_may_be_applied(self):
        tracker = RevisionTracker(Revision(1, 1, 1))
        for state in (PENDING, RUNNING, FAILED):
            job = Job(kind=JobKind.UV, revision=Revision(1, 1, 1))
            job.state = state
            self.assertFalse(job.is_applicable(tracker.revision), state)

    def test_cancelling_makes_a_job_unusable(self):
        tracker = RevisionTracker(Revision(1, 1, 1))
        job = done_job(JobKind.UV, Revision(1, 1, 1))
        job.cancel()
        self.assertFalse(job.is_applicable(tracker.revision))

    def test_failing_records_the_reason(self):
        job = Job(kind=JobKind.UV, revision=Revision(1, 1, 1))
        job.fail("solver diverged")
        self.assertEqual(job.state, FAILED)
        self.assertEqual(job.error, "solver diverged")


class TestOnlyTheNewestJobPerKindSurvives(unittest.TestCase):
    def test_a_new_job_of_the_same_kind_supersedes_the_old_one(self):
        old = done_job(JobKind.UV, Revision(1, 1, 1))
        new = Job(kind=JobKind.UV, revision=Revision(1, 1, 2))
        new.state = DONE
        self.assertIs(current_job_for([old, new], JobKind.UV), new)

    def test_jobs_of_different_kinds_do_not_supersede_each_other(self):
        uv = done_job(JobKind.UV, Revision(1, 1, 1))
        height = done_job(JobKind.HEIGHT, Revision(1, 1, 1))
        self.assertIs(current_job_for([uv, height], JobKind.UV), uv)
        self.assertIs(current_job_for([uv, height], JobKind.HEIGHT), height)

    def test_no_job_of_a_kind_returns_none(self):
        self.assertIsNone(current_job_for([], JobKind.UV))

    def test_the_newest_job_wins_even_when_it_is_still_running(self):
        old = done_job(JobKind.UV, Revision(1, 1, 1))
        new = Job(kind=JobKind.UV, revision=Revision(1, 1, 2))
        self.assertIs(current_job_for([old, new], JobKind.UV), new)


if __name__ == "__main__":
    unittest.main()
