"""
Pure drawing helpers for the step bar (UX-0).

No bpy import: the layout is duck-typed, so these functions run under plain
pytest and any mistake in the widget API shows up there instead of only while a
real UI is drawing.
"""

from .workflow import STEP_LABELS, is_step_unlocked

# Icon per status, so state is not conveyed by color alone (UIUX mục 2.2).
STATUS_ICONS = {
    "NOT_DONE": "RADIOBUT_OFF",
    "COMPUTING": "SORTTIME",
    "WARNING": "ERROR",
    "NEEDS_FIX": "CANCEL",
    "DONE": "CHECKMARK",
}

STATUS_TEXT = {
    "NOT_DONE": "Chưa làm",
    "COMPUTING": "Đang tính",
    "WARNING": "Có cảnh báo",
    "NEEDS_FIX": "Cần sửa",
    "DONE": "Xong",
}


def draw_step_row(layout, facts, step, status, active_step):
    """Draw one step row: a button plus its status.

    ``layout.operator()`` returns a properties struct that only accepts the
    operator's own properties, so enablement goes on the row, never on ``op``.
    """
    unlocked, blocker = is_step_unlocked(step, facts)

    button_row = layout.row(align=True)
    op = button_row.operator(
        "bscu.set_step", text=STEP_LABELS[step], depress=(active_step == step)
    )
    op.step = step
    button_row.enabled = unlocked

    status_row = layout.row(align=True)
    status_row.label(text="", icon=STATUS_ICONS[status.value])
    if not unlocked:
        status_row.label(text=f"Hoàn thành {STEP_LABELS[blocker]} trước")
    else:
        status_row.label(text=STATUS_TEXT[status.value])
