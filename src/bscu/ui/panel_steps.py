"""
Step bar: the 4-step navigator at the top of the BSCU N-panel (UX-0, UIUX U1).

Clicking a step switches tabs only. It never runs a heavy job, edits the mesh
or rearranges the viewport (UIUX mục 2.2).
"""

import bpy

from ..core.workflow import (
    STEP_LABELS,
    STEP_ORDER,
    StepStatus,
    derive_step_status,
    is_step_unlocked,
)
from .context import collect_step_facts

# Icon per status, so state is not conveyed by color alone (UIUX mục 2.2).
STATUS_ICONS = {
    StepStatus.NOT_DONE: "RADIOBUT_OFF",
    StepStatus.COMPUTING: "SORTTIME",
    StepStatus.WARNING: "ERROR",
    StepStatus.NEEDS_FIX: "CANCEL",
    StepStatus.DONE: "CHECKMARK",
}

STATUS_TEXT = {
    StepStatus.NOT_DONE: "Chưa làm",
    StepStatus.COMPUTING: "Đang tính",
    StepStatus.WARNING: "Có cảnh báo",
    StepStatus.NEEDS_FIX: "Cần sửa",
    StepStatus.DONE: "Xong",
}


def step_ui_state(context):
    """Return (facts, {step: status}) for the current scene."""
    facts = collect_step_facts(context)
    return facts, dict(zip(STEP_ORDER, derive_step_status(facts)))


def draw_step_row(layout, facts, step, status, active_step):
    """Draw one clickable step row; locked steps stay visible but disabled."""
    row = layout.row(align=True)
    unlocked, blocker = is_step_unlocked(step, facts)

    op = row.operator(
        "bscu.set_step", text=STEP_LABELS[step], depress=(active_step == step)
    )
    op.step = step
    op.enabled = unlocked

    row.label(text="", icon=STATUS_ICONS[status])
    if not unlocked:
        row.label(text=f"Hoàn thành {STEP_LABELS[blocker]} trước")
    else:
        row.label(text=STATUS_TEXT[status])


class BSCU_PT_steps(bpy.types.Panel):
    bl_label = "Quy trình"
    bl_idname = "BSCU_PT_steps"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "BSCU"

    def draw(self, context):
        layout = self.layout
        facts, statuses = step_ui_state(context)
        active_step = context.window_manager.bscu_ui.active_tab
        for step in STEP_ORDER:
            draw_step_row(layout, facts, step, statuses[step], active_step)


class BSCU_OT_set_step(bpy.types.Operator):
    bl_idname = "bscu.set_step"
    bl_label = "Chuyển bước"
    bl_description = "Mở bước tương ứng trong quy trình BSCU"
    bl_options = {"REGISTER", "UNDO"}

    step: bpy.props.StringProperty(default="STOCK")

    def execute(self, context):
        context.window_manager.bscu_ui.active_tab = self.step
        return {"FINISHED"}


CLASSES = (BSCU_OT_set_step, BSCU_PT_steps)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
