"""
Step bar: the 4-step navigator at the top of the BSCU N-panel (UX-0, UIUX U1).

Blender adapter only; the widgets themselves live in draw_steps.py so they stay
testable without a UI.
"""

import bpy

from ..core.draw_steps import draw_step_row
from ..core.workflow import STEP_ORDER, derive_step_status
from ..registry import register_classes, unregister_classes
from .context import collect_step_facts

STEP_OPERATOR = "bscu.set_step"


def step_ui_state(context):
    """Return (facts, {step: status}) for the current scene."""
    facts = collect_step_facts(context)
    return facts, dict(zip(STEP_ORDER, derive_step_status(facts)))


def draw_step_bar(layout, context):
    """Draw the whole step bar: facts are collected once, never per row."""
    facts, statuses = step_ui_state(context)
    active_step = context.window_manager.bscu_ui.active_tab
    for step in STEP_ORDER:
        draw_step_row(layout, facts, step, statuses[step], active_step)


class BSCU_PT_steps(bpy.types.Panel):
    bl_label = "Quy trình"
    bl_idname = "BSCU_PT_steps"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "BSCU"

    def draw(self, context):
        draw_step_bar(self.layout, context)


class BSCU_OT_set_step(bpy.types.Operator):
    bl_idname = STEP_OPERATOR
    bl_label = "Chuyển bước"
    bl_description = "Mở bước tương ứng trong quy trình BSCU"
    bl_options = {"REGISTER", "UNDO"}

    step: bpy.props.StringProperty(default="STOCK")

    def execute(self, context):
        context.window_manager.bscu_ui.active_tab = self.step
        return {"FINISHED"}


CLASSES = (BSCU_OT_set_step, BSCU_PT_steps)


def register():
    return register_classes(CLASSES)


def unregister():
    return unregister_classes(CLASSES)
