"""
Applying a layout to the mesh (UX-8, UIUX 3B.6 and 3.7).

This exists as an operator rather than a plain function for one concrete
reason: Blender only records data changes made inside an operator, so a
function that writes UVs directly produces a layout the user cannot undo.
The spec asks for Undo to bring back the layout along with everything else, and
that only works if the write goes through here.

The gate still lives in :mod:`bscu.bridge.uv_bridge`. This is the operator that
puts it in front of the user.
"""

import bpy

from ..bridge import uv_bridge
from ..registry import register_classes, unregister_classes

#: The candidate waiting to be applied, kept per object until it is decided on.
_pending: dict = {}


def stage(obj, layout, report=None) -> None:
    """Hold a candidate layout for the operator to apply or refuse."""
    _pending[obj.name] = (layout, report)


def staged(obj):
    return _pending.get(obj.name)


def clear(obj_name: str) -> None:
    _pending.pop(obj_name, None)


class BSCU_OT_ApplyLayout(bpy.types.Operator):
    """Write the staged layout into the active map, if it passes the checks"""

    bl_idname = "bscu.apply_layout"
    bl_label = "Use This Layout"
    bl_options = {"REGISTER", "UNDO"}

    take_new: bpy.props.BoolProperty(
        name="Replace the current layout",
        default=True,
        description="What to do with the layout already applied, if there is one")

    def execute(self, context):
        obj = context.active_object
        if obj is None or obj.type != "MESH":
            self.report({"ERROR"}, "select the mesh to lay out first")
            return {"CANCELLED"}

        candidate = staged(obj)
        if candidate is None:
            self.report({"WARNING"}, "no candidate layout to apply")
            return {"CANCELLED"}

        layout, report = candidate
        decision = uv_bridge.Decision.TAKE_NEW if self.take_new \
            else uv_bridge.Decision.KEEP_OLD
        outcome = uv_bridge.apply_candidate(obj, layout, decision=decision,
                                            report=report)
        if not outcome:
            self.report({"ERROR"}, outcome.reason)
            return {"CANCELLED"}

        clear(obj.name)
        self.report({"INFO"}, outcome.reason)
        return {"FINISHED"}


CLASSES = (BSCU_OT_ApplyLayout,)


def register():
    return register_classes(CLASSES)


def unregister():
    return unregister_classes(CLASSES)
