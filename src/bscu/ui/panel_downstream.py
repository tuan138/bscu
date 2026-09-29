"""
Tabs 2-4 panels: Caro, Bản trải, Tạo phù điêu (UX-0 shells).

Blender adapter only; the gating rules and widgets live in draw_downstream.py.
No control here pretends to work: seam, solver, layout and relief tools arrive
in UX-4 through UX-10.
"""

import bpy

from ..core.draw_downstream import draw_gated_tab
from .context import collect_step_facts


class _GatedTabPanel(bpy.types.Panel):
    """Shared behaviour: one step, drawn only while its tab is active."""

    step = ""

    @classmethod
    def poll(cls, context):
        return context.window_manager.bscu_ui.active_tab == cls.step

    def draw(self, context):
        draw_gated_tab(self.layout, collect_step_facts(context), self.step)


class BSCU_PT_caro(_GatedTabPanel):
    bl_label = "Caro"
    bl_idname = "BSCU_PT_caro"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "BSCU"
    step = "SEAM"


class BSCU_PT_layout(_GatedTabPanel):
    bl_label = "Bản trải"
    bl_idname = "BSCU_PT_layout"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "BSCU"
    step = "LAYOUT"


class BSCU_PT_relief(_GatedTabPanel):
    bl_label = "Tạo phù điêu"
    bl_idname = "BSCU_PT_relief"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "BSCU"
    step = "RELIEF"


CLASSES = (BSCU_PT_caro, BSCU_PT_layout, BSCU_PT_relief)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
