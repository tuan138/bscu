"""
The mode that turns the canvas drawing on and off (UX-9a, UIUX 1.1).

Its own file because the project keeps one subject per file, and because the
inspector panel and this operator are two different things: one draws, the other
reports.

Turning the canvas off stops it being *drawn*. It does not remove anything
from the design, and it does not touch the Undo stack - hiding is a viewing
act, and the spec is explicit that a temporary view state is not an edit.
"""

import bpy

from ..registry import register_classes, unregister_classes

#: The scene flag the viewport reads on every redraw.
MODE_FLAG = "bscu_canvas_mode"


def is_on(context) -> bool:
    """Whether the canvas is being drawn. On unless it was explicitly turned off."""
    return bool(context.scene.get(MODE_FLAG, True))


class BSCU_OT_CanvasMode(bpy.types.Operator):
    """Turn the canvas drawing on and off for this view"""

    bl_idname = "bscu.canvas_mode"
    bl_label = "Canvas Mode"
    bl_options = {"REGISTER", "UNDO"}

    active: bpy.props.BoolProperty(name="Canvas On", default=True)

    def execute(self, context):
        from ..draw import seam_overlay

        context.scene[MODE_FLAG] = bool(self.active)
        seam_overlay.redraw()
        self.report({"INFO"}, "canvas on" if self.active else "canvas off")
        return {"FINISHED"}


CLASSES = (BSCU_OT_CanvasMode,)


def register():
    return register_classes(CLASSES)


def unregister():
    return unregister_classes(CLASSES)
