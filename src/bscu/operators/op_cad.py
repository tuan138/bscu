"""
The corner operations on the canvas (UX-9b, UIUX 5.3).

Trim, fillet, chamfer and extend. Every decision about what the new geometry
should be lives in :mod:`bscu.core.cad_ops` and is tested there; this only
reads the mouse values and puts the result on the canvas.

The split from ``op_draw`` is the project's one-file-one-operator rule, and it
is not cosmetic: a fillet rebuilds the two arms and the new arc as a single
canvas transaction, so one Ctrl+Z takes the whole corner back rather than
leaving a half-finished one on the drawing.
"""

import bpy
import numpy as np

from ..core.cad_ops import chamfer_corner, extend_line, fillet_corner, trim_line
from ..core.geom2d import Line
from ..registry import register_classes, unregister_classes

# The canvas belongs to the drawing operator; this one edits what is on it.
from .op_draw import _persist, canvas_for


class BSCU_OT_Corner(bpy.types.Operator):
    """Round or cut back a corner on the canvas"""

    bl_idname = "bscu.corner"
    bl_label = "Corner"
    bl_options = {"REGISTER", "UNDO"}

    before_start: bpy.props.FloatVectorProperty(name="Before Start", size=2)
    before_end: bpy.props.FloatVectorProperty(name="Before End", size=2)
    after_start: bpy.props.FloatVectorProperty(name="After Start", size=2)
    after_end: bpy.props.FloatVectorProperty(name="After End", size=2)
    radius_mm: bpy.props.FloatProperty(name="Radius", default=1.0, min=0.0)
    fillet: bpy.props.BoolProperty(name="Round", default=True)

    def execute(self, context):
        canvas = canvas_for(context)
        before = Line(self.before_start, self.before_end)
        after = Line(self.after_start, self.after_end)
        corner = np.asarray(self.before_end, dtype=np.float64)
        try:
            result = (fillet_corner(before, after, corner, self.radius_mm)
                      if self.fillet
                      else chamfer_corner(before, after, corner, self.radius_mm))
        except ValueError as problem:
            self.report({"ERROR"}, str(problem))
            return {"CANCELLED"}

        # All three pieces replace together, so one undo takes the whole corner
        # back rather than leaving a half-finished one behind.
        name = f"corner-{len(canvas.strokes) + 1:04d}"
        canvas.add_stroke(name, list(result.pieces()))
        _persist(context.scene, canvas)
        return {"FINISHED"}


class BSCU_OT_EditLine(bpy.types.Operator):
    """Trim or extend a run on the canvas"""

    bl_idname = "bscu.edit_line"
    bl_label = "Trim or Extend"
    bl_options = {"REGISTER", "UNDO"}

    start_mm: bpy.props.FloatVectorProperty(name="Start", size=2)
    end_mm: bpy.props.FloatVectorProperty(name="End", size=2)
    trim_to_mm: bpy.props.FloatVectorProperty(name="Trim To", size=2)
    extend_mm: bpy.props.FloatProperty(name="Extend", default=0.0)
    do_trim: bpy.props.BoolProperty(name="Trim", default=True)

    def execute(self, context):
        canvas = canvas_for(context)
        line = Line(self.start_mm, self.end_mm)
        try:
            edited = (trim_line(line, self.trim_to_mm) if self.do_trim
                      else extend_line(line, end_distance=self.extend_mm))
        except ValueError as problem:
            self.report({"ERROR"}, str(problem))
            return {"CANCELLED"}
        name = f"line-{len(canvas.strokes) + 1:04d}"
        canvas.add_stroke(name, [edited])
        _persist(context.scene, canvas)
        return {"FINISHED"}


CLASSES = (BSCU_OT_Corner, BSCU_OT_EditLine)


def register():
    return register_classes(CLASSES)


def unregister():
    return unregister_classes(CLASSES)
