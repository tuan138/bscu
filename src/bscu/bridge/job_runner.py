"""
Background job execution for the pipeline (UX-2, UIUX D1/K3).

D1 keeps every ``bpy`` call on the main thread: a worker thread runs the core
task on a plain snapshot, and only the main thread ever applies a result. K3
makes the result conditional - it lands only while its revision still matches,
and only the newest job of a kind is ever relevant.

The scheduler is a plain :meth:`poll` the caller schedules through
``bpy.app.timers``; this class does not reach into Blender itself, so the whole
mechanism can be exercised without a window.
"""

import threading
from typing import Callable, List, Optional

from ..core.jobs import CANCELLED, DONE, FAILED, PENDING, RUNNING, Job, JobKind, RevisionTracker

RESOLVED_STATES = (DONE, FAILED, CANCELLED)


class JobRunner:
    """Runs core tasks off the main thread and applies fresh results on it."""

    def __init__(
        self,
        tracker: RevisionTracker,
        apply_fn: Callable,
        on_error: Optional[Callable] = None,
    ) -> None:
        self._tracker = tracker
        self._apply = apply_fn
        self._on_error = on_error
        self._lock = threading.Lock()
        self._jobs: List[Job] = []
        self._threads: List[threading.Thread] = []
        self._results: List = []
        self._stopped = False

    @property
    def stopped(self) -> bool:
        return self._stopped

    @property
    def results(self) -> tuple:
        """Results applied so far, oldest first."""
        with self._lock:
            return tuple(self._results)

    @property
    def busy(self) -> bool:
        """True while work is unresolved, including a result not yet applied.

        Jobs leave the pending list only when polled or shut down, so a finished
        result still waiting to be applied keeps the runner busy. Otherwise a
        caller looping on this could stop polling and lose that result.
        """
        with self._lock:
            if any(thread.is_alive() for thread in self._threads):
                return True
            return bool(self._jobs)

    def submit(self, kind: JobKind, task: Callable, revision=None) -> Job:
        """Start a task on a worker thread against the given revision."""
        job = Job(kind=kind, revision=revision or self._tracker.revision)

        def run() -> None:
            job.state = RUNNING
            try:
                job.result = task()
                job.state = DONE
            except Exception as error:  # noqa: BLE001 - reported, never swallowed
                job.fail(f"{type(error).__name__}: {error}")

        thread = threading.Thread(target=run, daemon=True)
        with self._lock:
            self._supersede(kind)
            self._jobs.append(job)
            self._threads = [t for t in self._threads if t.is_alive()] + [thread]
        thread.start()
        return job

    def _supersede(self, kind: JobKind) -> None:
        """K3: only the newest job of a kind survives."""
        for job in self._jobs:
            if job.kind == kind and job.state in (PENDING, RUNNING):
                job.cancel()

    def poll(self) -> int:
        """Apply any finished, still-current result. Main thread only."""
        with self._lock:
            finished = [job for job in self._jobs if job.state in RESOLVED_STATES]
            self._jobs = [job for job in self._jobs if job.state not in RESOLVED_STATES]

        for job in finished:
            if job.state == FAILED:
                if self._on_error is not None:
                    self._on_error(job.error)
                continue
            if not job.is_applicable(self._tracker.revision):
                continue
            self._apply(job.result)
            with self._lock:
                self._results.append(job.result)
        return 0

    def shutdown(self, timeout: Optional[float] = None) -> None:
        """Stop accepting work, cancel what is queued and join the workers."""
        self._stopped = True
        with self._lock:
            jobs = list(self._jobs)
            threads = list(self._threads)
            self._jobs = []
        for job in jobs:
            job.cancel()
        for thread in threads:
            thread.join(timeout)
        with self._lock:
            self._threads = [t for t in self._threads if t.is_alive()]
