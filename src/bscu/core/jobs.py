"""
Job lifecycle and staleness rules (UX-2, UIUX D1/K3).

Pure Python, no bpy and no threads: this module only decides *whether* a result
may be applied. The thread that produces the result and the timer that applies
it live in ``bridge/job_runner.py``.

A revision captures what a result depends on: the stock, the topology, the
region, the seam set, the mapping and the parameters. Any of those changing
bumps the revision, and every job built against the old one becomes
unapplicable rather than silently wrong.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Sequence

# Job states.
PENDING = "PENDING"
RUNNING = "RUNNING"
DONE = "DONE"
FAILED = "FAILED"
CANCELLED = "CANCELLED"


class JobKind(str, Enum):
    """The kinds of background work the pipeline schedules."""

    UV = "UV"
    HEIGHT = "HEIGHT"
    PREVIEW = "PREVIEW"
    EXPORT = "EXPORT"


@dataclass(frozen=True)
class Revision:
    """What a result depends on. Two results are comparable only if equal."""

    stock: int = 0
    topology: int = 0
    counter: int = 0

    def next_counter(self) -> "Revision":
        return Revision(self.stock, self.topology, self.counter + 1)


class RevisionTracker:
    """Holds the live revision and invalidates older ones on every bump."""

    def __init__(self, revision: Optional[Revision] = None) -> None:
        self._revision = revision or Revision()

    @property
    def revision(self) -> Revision:
        return self._revision

    def bump(self, stock: Optional[int] = None, topology: Optional[int] = None) -> Revision:
        """Invalidate outstanding work and publish a new revision.

        Called on Undo/Redo/load and whenever the region, seam set, mapping or
        parameters change. The counter always advances, so a job built before
        the bump can never match again even if the other fields look the same.
        """
        next_stock = self._revision.stock if stock is None else stock
        next_topology = self._revision.topology if topology is None else topology
        self._revision = Revision(
            stock=next_stock,
            topology=next_topology,
            counter=self._revision.counter + 1,
        )
        return self._revision



@dataclass
class Job:
    """One unit of background work and the revision it was built against."""

    kind: JobKind
    revision: Revision
    state: str = PENDING
    result: object = None
    error: Optional[str] = None
    cancelled: bool = False

    def cancel(self) -> None:
        """Mark the job as abandoned; a cancelled result is never applied."""
        self.cancelled = True
        self.state = CANCELLED

    def fail(self, reason: str) -> None:
        self.state = FAILED
        self.error = reason

    def is_applicable(self, current: Revision) -> bool:
        """True only for a finished job whose inputs are still current."""
        if self.cancelled or self.state != DONE:
            return False
        return self.revision == current


def current_job_for(jobs: Sequence[Job], kind: JobKind) -> Optional[Job]:
    """The newest job of a kind; only the latest one is ever relevant (K3)."""
    for job in reversed(list(jobs)):
        if job.kind == kind:
            return job
    return None
