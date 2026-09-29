"""
Pure workflow step-state derivation for the 4-tab BSCU pipeline (UX-0).
NO bpy / mathutils imports: this module only reasons about flags collected elsewhere.

Each step owns exactly one accepted deliverable, mirroring UIUX mục 2.5 / 2.7:
  STOCK  -> stock accepted (a Mesh is selected as the workpiece)
  SEAM   -> accepted UV mapping ("Dùng bản trải này" in Caro)
  LAYOUT -> approved layout (Bản trải)
  RELIEF -> pattern created (Tạo phù điêu)
A tab is unlocked once the previous step's deliverable exists.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Tuple


class StepStatus(str, Enum):
    """State of one step as shown in the step bar (UIUX mục 12, U1)."""

    NOT_DONE = "NOT_DONE"
    COMPUTING = "COMPUTING"
    WARNING = "WARNING"
    NEEDS_FIX = "NEEDS_FIX"
    DONE = "DONE"


STEP_ORDER = ("STOCK", "SEAM", "LAYOUT", "RELIEF")

STEP_LABELS = {
    "STOCK": "Phôi & Chia mảng",
    "SEAM": "Caro",
    "LAYOUT": "Bản trải",
    "RELIEF": "Tạo phù điêu",
}

# Deliverable flag that marks a step as finished.
_DELIVERABLE = {
    "SEAM": "has_uv_active",
    "LAYOUT": "has_approved_layout",
    "RELIEF": "has_pattern",
}

# Error / warning flags owned by the step that produces the deliverable.
_ERROR_FLAGS = {
    "STOCK": "stock_error",
    "SEAM": "uv_error",
    "LAYOUT": "layout_error",
    "RELIEF": "pattern_error",
}

_WARNING_FLAGS = {
    "STOCK": "stock_warning",
    "SEAM": "uv_warning",
    "LAYOUT": "layout_warning",
    "RELIEF": "pattern_warning",
}


@dataclass(frozen=True)
class StepFacts:
    """Observable pipeline state; the UI layer fills this in from Blender."""

    has_stock: bool = False
    stock_is_mesh: bool = False
    has_uv_active: bool = False
    has_approved_layout: bool = False
    has_pattern: bool = False

    stock_error: bool = False
    seam_error: bool = False
    uv_error: bool = False
    layout_error: bool = False
    pattern_error: bool = False

    stock_warning: bool = False
    seam_warning: bool = False
    uv_warning: bool = False
    layout_warning: bool = False
    pattern_warning: bool = False

    computing_step: Optional[str] = None


def stock_accepted(facts: StepFacts) -> bool:
    """A stock counts as accepted only when a Mesh is actually selected."""
    return facts.has_stock and facts.stock_is_mesh


def _delivered(step: str, facts: StepFacts) -> bool:
    """True when the step's accepted deliverable exists."""
    if step == "STOCK":
        return stock_accepted(facts)
    return getattr(facts, _DELIVERABLE[step])


def _status_of(step: str, facts: StepFacts) -> StepStatus:
    if facts.computing_step == step:
        return StepStatus.COMPUTING

    # Every later step presupposes an accepted stock; without one nothing
    # downstream exists yet, so no warning or error there can be meaningful.
    if step != "STOCK" and not stock_accepted(facts):
        return StepStatus.NOT_DONE

    if not _delivered(step, facts):
        return StepStatus.NOT_DONE

    if getattr(facts, _ERROR_FLAGS[step]):
        return StepStatus.NEEDS_FIX

    if getattr(facts, _WARNING_FLAGS[step]):
        return StepStatus.WARNING

    return StepStatus.DONE


def derive_step_status(facts: StepFacts) -> Tuple[StepStatus, ...]:
    """Return one StepStatus per step, in STEP_ORDER."""
    return tuple(_status_of(step, facts) for step in STEP_ORDER)


def is_step_unlocked(step: str, facts: StepFacts) -> Tuple[bool, Optional[str]]:
    """Return (unlocked, blocker_step) for a tab.

    Unlocked means the immediately preceding step's deliverable exists, so the
    user can open the tab and see its real state (UIUX mục 2.2: chuyển tab
    không tự chạy tác vụ nặng).
    """
    if step not in STEP_ORDER:
        raise ValueError(f"Unknown step: {step!r}")

    index = STEP_ORDER.index(step)
    if index == 0:
        return True, None

    previous = STEP_ORDER[index - 1]
    statuses = dict(zip(STEP_ORDER, derive_step_status(facts)))
    if statuses[previous] == StepStatus.NOT_DONE:
        return False, previous
    return True, None
