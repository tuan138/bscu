"""
Tabs 2-4 panels: Caro, Bản trải, Tạo phù điêu (UX-0 shells).

Each panel is gated on the previous step's deliverable and states plainly what
is still missing. No control here pretends to work: seam, solver, layout and
relief tools arrive in UX-4 through UX-10.
"""

import bpy

from ..core.workflow import STEP_LABELS, is_step_unlocked
from .panel_steps import step_ui_state

# What the user must finish before this tab becomes usable.
TAB_PREREQUISITES = {
    "SEAM": "Chưa có phôi",
    "LAYOUT": "Chưa có bản trải Caro",
    "RELIEF": "Chưa duyệt bản trải",
}

TAB_ROADMAP = {
    "SEAM": "Đề xuất cách chia, 4 công cụ seam và cọ chỉ dẫn (UX-4, UX-5, UX-6)",
    "LAYOUT": "Dàn đều, bản đồ nhiệt méo, cọ chỉ dẫn và duyệt bản trải (UX-5, UX-8)",
    "RELIEF": "Vẽ đường, dáng mảng, lưới nắn và xuất STL (UX-9a, UX-10, UX-11)",
}


def _draw_gated_tab(layout, context, step):
    """Show either the blocker or the roadmap for the tab's own scope."""
    facts, _ = step_ui_state(context)
    unlocked, blocker = is_step_unlocked(step, facts)

    if not unlocked:
        box = layout.box()
        box.label(text=TAB_PREREQUISITES[step], icon="LOCKED")
        box.label(text=f"Hoàn thành “{STEP_LABELS[blocker]}” trước")
        return

    layout.label(text="Chưa có gì để hiển thị ở bước này", icon="INFO")
    layout.separator()
    box = layout.box()
    box.label(text="Sẽ có ở giai đoạn sau:", icon="INFO")
    box.label(text=TAB_ROADMAP[step])


class BSCU_PT_caro(bpy.types.Panel):
    bl_label = "Caro"
    bl_idname = "BSCU_PT_caro"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "BSCU"

    @classmethod
    def poll(cls, context):
        return context.window_manager.bscu_ui.active_tab == "SEAM"

    def draw(self, context):
        _draw_gated_tab(self.layout, context, "SEAM")


class BSCU_PT_layout(bpy.types.Panel):
    bl_label = "Bản trải"
    bl_idname = "BSCU_PT_layout"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "BSCU"

    @classmethod
    def poll(cls, context):
        return context.window_manager.bscu_ui.active_tab == "LAYOUT"

    def draw(self, context):
        _draw_gated_tab(self.layout, context, "LAYOUT")


class BSCU_PT_relief(bpy.types.Panel):
    bl_label = "Tạo phù điêu"
    bl_idname = "BSCU_PT_relief"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "BSCU"

    @classmethod
    def poll(cls, context):
        return context.window_manager.bscu_ui.active_tab == "RELIEF"

    def draw(self, context):
        _draw_gated_tab(self.layout, context, "RELIEF")


CLASSES = (BSCU_PT_caro, BSCU_PT_layout, BSCU_PT_relief)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
