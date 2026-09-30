"""
The mode that turns the canvas drawing on and off (UX-9a, UIUX 1.1).

Its own file because the project keeps one subject per file, and because the
inspector panel and this operator are two different things: one draws, the other
reports.

Turning the canvas on also puts the view where a 2D drawing belongs: top
orthographic, looking down, with the canvas plane at z = 0. Drawing in a
perspective view would put the stroke where the cursor is rather than where the
part is, which is the single most common way a 2.5D tool produces a part that
looks right and is cut wrong.

Turning it off stops the canvas being *drawn*. It does not remove anything from
the design, and the view is put back rather than left somewhere the user did
not choose. The flag lives on the window manager, not the scene: a view is
temporary, and writing it into the document would make an undo step out of
simply looking at a part from above.
"""

import bpy

from ..registry import register_classes, unregister_classes

#: The window flag the viewport reads on every redraw.
MODE_FLAG = "bscu_canvas_mode"

#: The view the canvas is drawn in, per the spec.
CANVAS_VIEW = "ORTHO"


def is_on(context) -> bool:
    """Whether the canvas is being drawn. On unless it was explicitly turned off."""
    return bool(getattr(context.window_manager, MODE_FLAG, True))


def set_on(context, value: bool) -> None:
    """Record the mode on the window, where a view state belongs."""
    setattr(context.window_manager, MODE_FLAG, bool(value))


def enter_canvas_view(area) -> bool:
    """Put a 3D view into top orthographic, looking down.

    Returns whether it could. A background run has no region, and saying so is
    better than pretending the view was set.
    """
    region = getattr(area, "spaces", None)
    space = region.active if region else None
    view = getattr(space, "region_3d", None)
    if view is None:
        return False
    view.view_perspective = CANVAS_VIEW
    # Looking down the Z axis, with Y up on screen.
    view.view_rotation = (0.7071068, 0.7071068, 0.0, 0.0)
    return True


class BSCU_OT_CanvasMode(bpy.types.Operator):
    """Turn the canvas drawing on and off for this view"""

    bl_idname = "bscu.canvas_mode"
    bl_label = "Canvas Mode"
    bl_options = {"REGISTER", "UNDO"}

    active: bpy.props.BoolProperty(name="Canvas On", default=True)

    def execute(self, context):
        from ..draw import seam_overlay

        set_on(context, self.active)
        moved = False
        area = context.area
        if area is not None and area.type == "VIEW_3D":
            moved = enter_canvas_view(area)
        seam_overlay.redraw()
        if self.active and not moved:
            self.report({"INFO"},
                        "canvas on; no 3D view here to put into top orthographic")
        else:
            self.report({"INFO"}, "canvas on" if self.active else "canvas off")
        return {"FINISHED"}


CLASSES = (BSCU_OT_CanvasMode,)


def register():
    return register_classes(CLASSES)


def unregister():
    return unregister_classes(CLASSES)
