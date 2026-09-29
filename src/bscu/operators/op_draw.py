"""
Drawing on the canvas and the CAD operations, as operators (UX-9b, UIUX 5.3).

Thin on purpose. Every decision about geometry lives in
:mod:`bscu.core.geom2d` and :mod:`bscu.core.cad_ops` and is tested there; these
operators do the two things only Blender can do: read the mouse, and make the
edit one undo step.

That last part is the reason they exist as operators rather than as functions
called from a panel. A fillet rebuilds the two arms and the new arc as one
transaction, so one Ctrl+Z takes the whole corner back rather than leaving a
half-finished one on the canvas.
"""

import bpy
import numpy as np

from ..core.cad_ops import chamfer_corner, extend_line, fillet_corner, trim_line
from ..core.geom2d import Line
from ..draw import canvas_2d, snap
from ..registry import register_classes, unregister_classes

#: One canvas per scene, so switching scenes never mixes two drawings. Keyed by
#: name rather than held in a single global, because a reload would otherwise
#: leave the user looking at an empty canvas and think their drawing was lost.
_SCENES: dict = {}


def canvas_for(context) -> canvas_2d.Canvas:
    """The canvas for a scene, made on first use."""
    scene = context.scene
    found = _SCENES.get(scene.name)
    if found is None:
        found = canvas_2d.Canvas()
        _SCENES[scene.name] = found
    return found


def forget(scene_name: str) -> None:
    """Drop a scene's canvas, on file load where the old one is meaningless."""
    _SCENES.pop(scene_name, None)


class BSCU_OT_DrawLine(bpy.types.Operator):
    """Draw a straight run on the canvas from the last point to the cursor"""

    bl_idname = "bscu.draw_line"
    bl_label = "Draw Line"
    bl_options = {"REGISTER", "UNDO"}

    to_mm: bpy.props.FloatVectorProperty(name="To", size=2, default=(0.0, 0.0))
    snap_links: bpy.props.BoolProperty(name="Snap", default=True)
    start_mm: bpy.props.FloatVectorProperty(name="From", size=2, default=(0.0, 0.0))

    def execute(self, context):
        canvas = canvas_for(context)
        start = np.asarray(self.start_mm, dtype=np.float64)
        end = np.asarray(self.to_mm, dtype=np.float64)
        link = None
        if self.snap_links:
            end, link = snap.snap_or_free(end, _paths_of(context),
                                         snap.pixels_to_mm(12.0, 0.5))
        stroke = Line(start, end)
        if stroke.length <= 0.0:
            self.report({"WARNING"}, "the stroke had no length")
            return {"CANCELLED"}
        name = f"stroke-{len(canvas.strokes) + 1:04d}"
        canvas.add_stroke(name, [stroke])
        if link is not None:
            self.report({"INFO"}, f"{name} snapped to a {link.kind} link")
        return {"FINISHED"}


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
        return {"FINISHED"}


class BSCU_OT_CanvasVisibility(bpy.types.Operator):
    """Hide or show a stroke, without taking it off the canvas"""

    bl_idname = "bscu.canvas_visibility"
    bl_label = "Canvas Visibility"
    bl_options = {"REGISTER", "UNDO"}

    stroke: bpy.props.StringProperty(name="Stroke", default="")
    hide: bpy.props.BoolProperty(name="Hide", default=True)

    def execute(self, context):
        canvas = canvas_for(context)
        if self.hide and not canvas.hide(self.stroke):
            self.report({"WARNING"}, f"there is no stroke called {self.stroke}")
            return {"CANCELLED"}
        if not self.hide and not canvas.show(self.stroke):
            self.report({"WARNING"}, f"there is no stroke called {self.stroke}")
            return {"CANCELLED"}
        return {"FINISHED"}


class BSCU_OT_RemoveStroke(bpy.types.Operator):
    """Take one stroke off the canvas"""

    bl_idname = "bscu.remove_stroke"
    bl_label = "Remove Stroke"
    bl_options = {"REGISTER", "UNDO"}

    stroke: bpy.props.StringProperty(name="Stroke", default="")

    def execute(self, context):
        canvas = canvas_for(context)
        if not canvas.remove_stroke(self.stroke):
            self.report({"WARNING"}, f"there is no stroke called {self.stroke}")
            return {"CANCELLED"}
        return {"FINISHED"}


def _paths_of(context) -> dict:
    """The canvas strokes, as the paths a snap can search."""
    canvas = canvas_for(context)
    found = {}
    for name, shapes in canvas.visible():
        points = []
        for shape in shapes:
            data = getattr(shape, "sample", None)
            if callable(data):
                points.extend(data(8).tolist())
            else:
                points.append(np.asarray(shape.start, dtype=np.float64).tolist())
                points.append(np.asarray(shape.end, dtype=np.float64).tolist())
        found[name] = {"id": name,
                       "points": np.asarray(points, dtype=np.float64).reshape(-1, 2)}
    return found


CLASSES = (BSCU_OT_DrawLine, BSCU_OT_Corner, BSCU_OT_EditLine,
           BSCU_OT_CanvasVisibility, BSCU_OT_RemoveStroke)


def register():
    return register_classes(CLASSES)


def unregister():
    return unregister_classes(CLASSES)
