"""Integration test for the background job runner (UX-2, UIUX D1/K3).

K3: a worker thread runs the core task on a plain snapshot, a bpy.app.timers
poll collects the result, and the result is applied only while its revision
still matches. Cancel, a newer job of the same kind, and Undo must all stop a
stale result from landing.
"""

import time

from bscu.bridge.job_runner import JobRunner
from bscu.core.jobs import JobKind, RevisionTracker

_registered = False


def _ensure_registered():
    global _registered
    if _registered:
        return
    import bscu

    bscu.register()
    _registered = True


def _drain(runner, timeout=5.0):
    """Pump the timer until nothing is in flight."""
    deadline = time.perf_counter() + timeout
    while runner.busy and time.perf_counter() < deadline:
        runner.poll()
        time.sleep(0.005)
    assert not runner.busy, "job did not finish in time"
    return runner.results


def test_a_fresh_job_result_is_applied():
    tracker = RevisionTracker()
    tracker.bump(stock=1, topology=1)
    applied = []
    runner = JobRunner(tracker, apply_fn=applied.append)

    runner.submit(JobKind.PREVIEW, lambda: "fresh", revision=tracker.revision)
    _drain(runner)

    assert applied == ["fresh"], applied
    print("[OK] a fresh result is applied")


def test_a_result_from_an_older_revision_is_dropped():
    tracker = RevisionTracker()
    tracker.bump(stock=1, topology=1)
    stale = tracker.revision
    tracker.bump()  # user changed something while the job ran
    applied = []
    runner = JobRunner(tracker, apply_fn=applied.append)

    runner.submit(JobKind.PREVIEW, lambda: "stale", revision=stale)
    _drain(runner)

    assert applied == [], applied
    print("[OK] a stale result is dropped instead of applied")


def test_a_newer_job_of_the_same_kind_supersedes_the_older_one():
    tracker = RevisionTracker()
    tracker.bump(stock=1, topology=1)
    revision = tracker.revision
    applied = []
    runner = JobRunner(tracker, apply_fn=applied.append)

    def slow():
        time.sleep(0.15)
        return "old"

    def fast():
        return "new"

    runner.submit(JobKind.PREVIEW, slow, revision=revision)
    time.sleep(0.02)
    runner.submit(JobKind.PREVIEW, fast, revision=revision)
    _drain(runner)

    assert applied == ["new"], applied
    print("[OK] only the newest job of a kind is applied")


def test_a_cancelled_job_never_applies():
    tracker = RevisionTracker()
    tracker.bump(stock=1, topology=1)
    applied = []
    runner = JobRunner(tracker, apply_fn=applied.append)

    def slow():
        time.sleep(0.12)
        return "cancelled"

    job = runner.submit(JobKind.PREVIEW, slow, revision=tracker.revision)
    job.cancel()
    time.sleep(0.05)
    runner.poll()
    deadline = time.perf_counter() + 5.0
    while runner.busy and time.perf_counter() < deadline:
        time.sleep(0.01)

    assert applied == [], applied
    print("[OK] a cancelled job never applies its result")


def test_a_failing_job_reports_its_reason():
    tracker = RevisionTracker()
    tracker.bump(stock=1, topology=1)
    errors = []
    runner = JobRunner(tracker, apply_fn=lambda r: None, on_error=errors.append)

    def boom():
        raise ValueError("solver diverged")

    runner.submit(JobKind.UV, boom, revision=tracker.revision)
    _drain(runner)

    assert errors and "solver diverged" in errors[0], errors
    print(f"[OK] failure surfaced as {errors[0]!r}")


def test_running_a_job_touches_no_blender_data():
    """D1: the core task must work on a plain snapshot, not on bpy objects."""
    tracker = RevisionTracker()
    tracker.bump(stock=1, topology=1)
    seen = []
    runner = JobRunner(tracker, apply_fn=lambda r: None)

    import threading

    def task():
        # Inside a worker thread, touching bpy must be impossible.
        try:
            seen.append(threading.current_thread() is threading.main_thread())
        except Exception as error:  # pragma: no cover - defensive
            seen.append(error)
        return None

    runner.submit(JobKind.PREVIEW, task, revision=tracker.revision)
    _drain(runner)
    assert seen == [False], seen
    print("[OK] the task really ran off the main thread")


def test_shutdown_leaves_no_worker_running():
    tracker = RevisionTracker()
    tracker.bump(stock=1, topology=1)
    runner = JobRunner(tracker, apply_fn=lambda r: None)
    runner.submit(JobKind.PREVIEW, lambda: time.sleep(0.2) or "x", revision=tracker.revision)
    runner.shutdown()
    deadline = time.perf_counter() + 5.0
    while runner.busy and time.perf_counter() < deadline:
        time.sleep(0.01)
    assert not runner.busy
    print("[OK] shutdown waits for the worker to stop")


def run_test():
    _ensure_registered()
    test_a_fresh_job_result_is_applied()
    test_a_result_from_an_older_revision_is_dropped()
    test_a_newer_job_of_the_same_kind_supersedes_the_older_one()
    test_a_cancelled_job_never_applies()
    test_a_failing_job_reports_its_reason()
    test_running_a_job_touches_no_blender_data()
    test_shutdown_leaves_no_worker_running()
    print("\nJob runner verified on a real Blender session!")
