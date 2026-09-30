"""
Importing vectors and making templates (UX-13, UIUX 10.4 and 10.6).

The spec's rule for import is narrow on purpose: one layer only, converted by
the file's own stated units, into a layer of its own that the user can undo as
a single action. A file with fifty layers comes in asking a question, and the
answer is never "all of them silently".

Templates are the other half: a symbol made from selected strokes, kept with the
effects and overlay regions inside it. It is a *copy* - placed many times, it is
still one undo step to move, and deleting a copy never touches the original.
"""

import os
import uuid
from typing import Tuple

import bpy
import numpy as np

from ..core.dxf_import import DxfError, parse_dxf
from ..core.geom2d import Arc, Line
from ..core.svg_import import parse_svg
from ..draw.batches import ARC_STEPS
from ..registry import register_classes, unregister_classes

#: The formats the spec asks for, by the extension the user picked.
READERS = {".dxf": "dxf", ".svg": "svg"}

#: The collection templates live in, so a copy is never confused with a stroke.
TEMPLATE_COLLECTION = "BSCU_Templates"


class ImportResult:
    """What an import produced, and what it would not do."""

    def __init__(self, shapes: list, issues: list, layer: str):
        self.shapes = list(shapes)
        self.issues = list(issues)
        self.layer = layer

    @property
    def ok(self) -> bool:
        return bool(self.shapes) and not any("STOP" in issue
                                              for issue in self.issues)

    def __bool__(self) -> bool:
        return self.ok


def read_file(path: str, layer: str = "layer-0") -> ImportResult:
    """Read a vector file, whatever its extension says it is."""
    extension = os.path.splitext(path)[1].lower()
    reader = READERS.get(extension)
    if reader is None:
        raise ValueError(f"{extension or 'that file'} is not a format this "
                         f"reads; expected one of {sorted(READERS)}")
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        text = handle.read()
    result = parse_dxf(text) if reader == "dxf" else parse_svg(text)
    # Parsed once. The earlier version read the file twice and returned the
    # reader's empty shape list rather than a result when a file held no
    # geometry, so the caller crashed on it and the reader's reasons were lost.
    return ImportResult(_geometry_of(result), list(result.issues), layer)


def _geometry_of(result) -> list:
    """A reader's output as canvas geometry, in millimetres."""
    shapes = []
    for entry in result.shapes:
        if entry["kind"] == "arc":
            shapes.append(Arc(tuple(entry["centre_mm"]), entry["radius_mm"],
                              entry["start_deg"], entry["end_deg"]))
            continue
        points = np.asarray(entry["points"], dtype=np.float64).reshape(-1, 2)
        for index in range(len(points) - 1):
            shapes.append(Line(points[index], points[index + 1]))
    return shapes


def shapes_of(result: ImportResult) -> list:
    """Only the geometry, with the reader's complaints set aside."""
    return [shape for shape in result.shapes if isinstance(shape, (Line, Arc))]


class BSCU_OT_ImportVector(bpy.types.Operator):
    """Bring a DXF or SVG file onto the canvas, as one undoable layer"""

    bl_idname = "bscu.import_vector"
    bl_label = "Import Vector File"
    bl_options = {"REGISTER", "UNDO"}

    filepath: bpy.props.StringProperty(name="File", subtype="FILE_PATH")
    layer: bpy.props.StringProperty(name="Layer", default="layer-0")

    def execute(self, context):
        from . import op_draw

        try:
            result = read_file(self.filepath, self.layer)
        except (OSError, ValueError, DxfError) as problem:
            self.report({"ERROR"}, str(problem))
            return {"CANCELLED"}

        geometry = shapes_of(result)
        if not geometry:
            for issue in result.shapes:
                self.report({"WARNING"}, str(issue))
            self.report({"ERROR"}, "nothing in that file became geometry")
            return {"CANCELLED"}

        canvas = op_draw.canvas_for(context)
        stem = os.path.splitext(os.path.basename(self.filepath))[0]
        # Suffixed, because importing the same file twice would otherwise land
        # the second import on top of the first and lose it.
        name = stem if stem not in canvas.strokes else f"{stem}-{uuid.uuid4().hex[:4]}"
        canvas.add_stroke(name, geometry)
        op_draw._persist(context.scene, canvas)
        self.report({"INFO"}, f"{name}: {len(geometry)} piece(s)")
        return {"FINISHED"}

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}


def template_collection(context):
    """The collection templates live in, made on first use."""
    found = bpy.data.collections.get(TEMPLATE_COLLECTION)
    if found is None:
        found = bpy.data.collections.new(TEMPLATE_COLLECTION)
        context.scene.collection.children.link(found)
    return found


def make_template(context, name: str, strokes: dict) -> bpy.types.Object:
    """A reusable symbol built from a copy of the given strokes.

    The geometry is built from the strokes, not merely declared: a template with
    an empty mesh and every instance empty with it is a feature that looks like
    it works until someone places one.
    """
    points, edges = _stroke_geometry(strokes)
    mesh = bpy.data.meshes.new(name)
    if points and edges:
        mesh.from_pydata([tuple(point) for point in points], edges, [])
        mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    template_collection(context).objects.link(obj)
    obj["bscu_template"] = len(strokes)
    return obj


def _stroke_geometry(strokes: dict) -> Tuple[list, list]:
    """The canvas strokes as a vertex and edge list, in metres.

    Millimetres in, metres out, because an object's geometry lives in the
    scene's units and a template a thousand times too big is the symptom.
    """
    points: list = []
    edges: list = []
    for shapes in strokes.values():
        for shape in shapes:
            if isinstance(shape, Arc):
                run = shape.sample(ARC_STEPS)
            else:
                run = np.asarray([shape.start, shape.end], dtype=np.float64)
            first = len(points)
            for point in run:
                points.append((float(point[0]) / 1000.0, float(point[1]) / 1000.0, 0.0))
            for index in range(len(run) - 1):
                edges.append((first + index, first + index + 1))
    return points, edges


def instances_of(template) -> list:
    """The placed copies of a template.

    They share the template's mesh on purpose: the spec wants a copy of a lens
    or a rosette to cost nothing but its transform, and editing one to change
    all of them is the behaviour a linked copy gives.
    """
    return [obj for obj in bpy.data.objects
            if obj.type == "MESH" and obj.data is template.data
            and obj is not template]


def place_instance(template, location=(0.0, 0.0, 0.0)) -> bpy.types.Object:
    """Put another copy of a template down, linked to the same geometry.

    Linked on purpose: the spec wants a copy of a lens or a rosette to cost
    nothing but its transform, and editing one of them to change all of them is
    the behaviour a linked copy gives.
    """
    copy = bpy.data.objects.new(f"{template.name}_instance_{uuid.uuid4().hex[:8]}",
                                template.data)
    for collection in template.users_collection:
        collection.objects.link(copy)
    copy.location = location
    return copy


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


CLASSES = (BSCU_OT_ImportVector, BSCU_OT_MakeTemplate)


def register():
    return register_classes(CLASSES)


def unregister():
    return unregister_classes(CLASSES)
