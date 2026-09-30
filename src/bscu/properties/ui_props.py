"""
Blender-side UI state for the BSCU N-panel (UX-0).

Tab selection lives on WindowManager because it is per-window session state,
not part of the saved .blend document. Pipeline deliverables are derived from
the scene by ui/context.py, never stored here.
"""

import bpy
from bpy.props import EnumProperty

from ..core.workflow import STEP_LABELS, STEP_ORDER
from ..registry import register_classes, unregister_classes

_STEP_ITEMS = [(step, STEP_LABELS[step], STEP_LABELS[step]) for step in STEP_ORDER]


class BSCU_PG_ui(bpy.types.PropertyGroup):
    """Session-only UI state; nothing here is written to the .blend file."""

    active_tab: EnumProperty(
        name="Bước",
        description="Bước đang mở trong thanh 4 bước",
        items=_STEP_ITEMS,
        default="STOCK",
    )


CLASSES = (BSCU_PG_ui,)


def register():
    register_classes(CLASSES)
    bpy.types.WindowManager.bscu_ui = bpy.props.PointerProperty(type=BSCU_PG_ui)
    # A view state, not document state: kept on the window so that
    # looking at a part from above is not an undo step.
    bpy.types.WindowManager.bscu_canvas_mode = bpy.props.BoolProperty(
        name="Canvas Mode", default=True,
        description="Draw the BSCU canvas in this window")


def unregister():
    unregister_classes(CLASSES)
    for name in ("bscu_ui", "bscu_canvas_mode"):
        if hasattr(bpy.types.WindowManager, name):
            delattr(bpy.types.WindowManager, name)
