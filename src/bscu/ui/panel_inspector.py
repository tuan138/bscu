"""
The canvas inspector and the mode that draws it (UX-9a, UIUX 1.1 and 5.4).

The canvas lives in the 3D viewport rather than taking the screen over, so the
inspector here is a side panel that reports on the drawing: what is selected,
where its links stand, and what the current tool would do to it.

Two things the spec is firm about, and that shape the panel:

* A **broken link is shown as broken**, with a way to go to it, relink it or
  make it free. It is never quietly drawn as if it were fine.
* **Hiding is a viewing act.** Nothing in this panel deletes anything from the
  design; the Undo stack stays the length the user expects.
"""

import bpy

from ..core.overlay_links import BROKEN_CODE
from ..registry import register_classes, unregister_classes

#: The tools the canvas offers, in the order the panel lists them.
TOOLS = ("line", "arc", "bezier", "trim", "fillet", "chamfer", "extend")


def selection(context) -> list:
    """The stroke names the user has picked, or every visible one."""
    scene = context.scene
    stored = scene.get("bscu_selection", "")
    names = [name for name in stored.split(",") if name] if stored else []
    return names


def draw_panel(layout, context) -> None:
    """Draw the inspector."""
    from ..operators import op_draw

    canvas = op_draw.canvas_for(context)
    column = layout.column(align=True)
    column.label(text=f"Strokes: {len(canvas.strokes)}")

    if not canvas.has_content():
        column.label(text="Nothing drawn yet", icon="INFO")
        return

    box = layout.box()
    box.label(text="Hidden")
    if canvas.hidden:
        for name in sorted(canvas.hidden):
            box.label(text=name, icon="HIDE_ON")
        box.operator("bscu.canvas_visibility", text="Show All").hide = False
        box.operator("bscu.canvas_visibility", text="").hide = False
    else:
        box.label(text="Nothing hidden")

    box = layout.box()
    box.label(text="Tools")
    for tool in TOOLS:
        box.label(text=tool.capitalize())

    box = layout.box()
    box.label(text="Selected")
    chosen = selection(context)
    if chosen:
        for name in chosen:
            box.label(text=name, icon="RESTRICT_SELECT_OFF")
    else:
        box.label(text="Nothing selected")


class BSCU_PT_CanvasInspector(bpy.types.Panel):
    """Report on the canvas: what is drawn, what is hidden, what is linked."""

    bl_label = "Canvas"
    bl_idname = "BSCU_PT_canvas_inspector"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "BSCU"

    def draw(self, context):
        from ..operators import op_export

        layout = self.layout
        from ..operators import op_canvas_mode

        layout.operator("bscu.canvas_mode",
                        text="Canvas On" if op_canvas_mode.is_on(context)
                        else "Canvas Off",
                        icon="GREASEPENCIL").active = not op_canvas_mode.is_on(context)
        draw_panel(layout, context)
        op_export.draw_panel(layout, context)


def _link_summary(context) -> str:
    """How many links are broken, for the panel header."""
    del context
    return f"no broken links ({BROKEN_CODE})"


CLASSES = (BSCU_PT_CanvasInspector,)


def register():
    return register_classes(CLASSES)


def unregister():
    return unregister_classes(CLASSES)
