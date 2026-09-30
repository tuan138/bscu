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

import json

import bpy
import numpy as np

from ..core.geom2d import Arc, Line
from ..draw import canvas_2d, snap
from ..registry import register_classes, unregister_classes

#: One canvas per scene, so switching scenes never mixes two drawings. Keyed by
#: name rather than held in a single global, because a reload would otherwise
#: leave the user looking at an empty canvas and think their drawing was lost.
_SCENES: dict = {}


def canvas_for(context) -> canvas_2d.Canvas:
    """The canvas for a scene, made on first use and saved with the file.

    The strokes go into the scene's own ID properties rather than staying in
    memory: the spec asks that a save and reopen keeps the drawing, and a
    drawing that only exists while Blender is open is not that.
    """
    scene = context.scene
    found = _SCENES.get(scene.name)
    if found is None:
        found = canvas_2d.Canvas()
        _SCENES[scene.name] = found
        _restore(scene, found)
    return found


def _restore(scene, canvas: canvas_2d.Canvas) -> None:
    """Read the canvas back out of the scene's own properties."""
    stored = scene.get("bscu_strokes", "{}")
    try:
        payload = json.loads(stored)
    except (TypeError, ValueError):
        return
    for name, pieces in payload.items():
        canvas.add_stroke(name, [_rebuild(piece) for piece in pieces])


def _rebuild(piece: dict):
    """One stored piece back as geometry, arcs included.

    The kind is stored rather than assumed. Reading every piece back as a line
    would turn a filleted corner into two loose strokes the first time the file
    was reopened, which looks like data loss to the user.
    """
    if piece.get("kind") == "arc":
        return Arc(piece["centre"], piece["radius"],
                   piece["start_deg"], piece["end_deg"])
    return Line(piece["start"], piece["end"])


def _persist(scene, canvas: canvas_2d.Canvas) -> None:
    """Write the canvas into the scene, so saving the file saves the drawing."""
    payload = {}
    for name, shapes in canvas.strokes.items():
        pieces = []
        for shape in shapes:
            if isinstance(shape, Arc):
                pieces.append({
                    "kind": "arc", "centre": list(shape.centre),
                    "radius": shape.radius, "start_deg": shape.start_deg,
                    "end_deg": shape.end_deg,
                })
            else:
                pieces.append({"kind": "line", "start": list(shape.start),
                               "end": list(shape.end)})
        payload[name] = pieces
    scene["bscu_strokes"] = json.dumps(payload)
    scene["bscu_hidden"] = json.dumps(sorted(canvas.hidden))


def forget(scene_name: str) -> None:
    """Drop a scene's in-memory canvas, on file load where it is meaningless.

    The next read comes back from the file, which is the copy that is right.
    """
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
        _persist(context.scene, canvas)
        if link is not None:
            self.report({"INFO"}, f"{name} snapped to a {link.kind} link")
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
        _persist(context.scene, canvas)
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
        _persist(context.scene, canvas)
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


CLASSES = (BSCU_OT_DrawLine, BSCU_OT_CanvasVisibility,
           BSCU_OT_RemoveStroke)


def register():
    return register_classes(CLASSES)


def unregister():
    return unregister_classes(CLASSES)
