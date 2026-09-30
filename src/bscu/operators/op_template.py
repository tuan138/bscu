"""
Making a reusable symbol from the drawn strokes (UX-13, UIUX 10.4).

Its own file under the one-file-one-operator rule. The geometry work - building
a mesh a user can place ten times - lives in
:mod:`bscu.operators.op_import_vector` beside the reader that fills it.
"""

import bpy

from ..registry import register_classes, unregister_classes

# The mesh builder lives with the vector reader that fills the canvas.
from .op_import_vector import make_template


class BSCU_OT_MakeTemplate(bpy.types.Operator):
    """Turn the selected strokes into a reusable symbol"""

    bl_idname = "bscu.make_template"
    bl_label = "Make Template"
    bl_options = {"REGISTER", "UNDO"}

    name: bpy.props.StringProperty(name="Name", default="BSCU_Template")

    def execute(self, context):
        from . import op_draw

        canvas = op_draw.canvas_for(context)
        if not canvas.has_content():
            self.report({"WARNING"}, "the canvas is empty; there is nothing to make")
            return {"CANCELLED"}
        template = make_template(context, self.name, canvas.strokes)
        self.report({"INFO"}, f"made {template.name} from "
                              f"{len(canvas.strokes)} stroke(s)")
        return {"FINISHED"}


CLASSES = (BSCU_OT_MakeTemplate,)


def register():
    return register_classes(CLASSES)


def unregister():
    return unregister_classes(CLASSES)
