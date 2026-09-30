"""
Painting the Tab 2 hints onto a workpiece (UX-5, UIUX 3B.3 and 3B.5).

The brushes never touch UV. They write four per-face hints, and the solver reads
those back every time a layout is produced. That is the whole reason a seam edit
does not throw the user's work away, and it is why this operator writes hints and
nothing else.

Three rules from the spec shape it:

* **Alt on release makes a free point**, with no link to anything. That is the
  deliberate way out of a link the user did not ask for, so it is reachable
  without an undo afterwards.
* **A stroke is one undo step.** The hints go on the mesh, where Blender's undo
  covers them.
* **A stroke that lands on nothing says so** rather than quietly painting every
  face the brush touched on the way.
"""

from typing import Optional

import bpy
import numpy as np

from ..core.overlay_links import Link, LinkTable
from ..core.uv_hints import BrushHints, neighbour_pairs, paint, relax
from ..draw import snap
from ..registry import register_classes, unregister_classes

#: The four hint attributes, as the spec names them.
DENSITY = "bscu_density"
PIN = "bscu_pin"
PRIORITY = "bscu_priority"
DIRECTION = "bscu_dir"

#: Brush size in screen pixels, and the millimetres a pixel is worth at the
#: pointer. The panel shows the conversion so the size is never a mystery.
DEFAULT_SIZE_PX = 40.0
MM_PER_PIXEL = 0.5

_LINKS: dict = {}


def hints_for(obj) -> BrushHints:
    """The workpiece's hints, read back from the mesh attributes."""
    faces = _faces(obj)
    mesh = obj.data
    return BrushHints.from_arrays(
        _attribute(mesh, DENSITY, faces), _attribute(mesh, PIN, faces),
        _attribute(mesh, PRIORITY, faces),
        _unit_directions(_attribute(mesh, DIRECTION, faces)), len(faces))


def loop_of_face(mesh, faces) -> np.ndarray:
    """Which loops each triangle owns.

    Hints are per triangle, and a face attribute holds one number per polygon -
    which on a quad mesh is half as many, so half the brush strokes would land
    nowhere. The corner domain holds one number per loop, which is the only
    place a per-triangle value fits on any mesh.
    """
    mesh.calc_loop_triangles()
    return np.asarray([triangle.loops[0] for triangle in mesh.loop_triangles],
                      dtype=np.int64)


def write_hints(obj, hints: BrushHints) -> int:
    """Write the hints back onto the mesh, where Undo and save/load will see them."""
    mesh = obj.data
    count = len(hints.density)
    # Each triangle is carried by the loops it owns; the attribute is per loop,
    # so a hint is written to every loop of the triangle that earned it.
    owned = loop_of_face(mesh, _faces(obj))
    take = min(owned.size, count)

    for name, values in ((DENSITY, hints.density), (PIN, hints.pin),
                         (PRIORITY, hints.priority), (DIRECTION,
                                                     _angles(hints.direction))):
        flat = np.zeros(len(mesh.loops), dtype=np.float32)
        source = np.asarray(values, dtype=np.float32).reshape(-1)
        if take:
            flat[owned[:take]] = source[:take]
        attribute = mesh.attributes.get(name) or mesh.attributes.new(
            name=name, type="FLOAT", domain="CORNER")
        attribute.data.foreach_set("value", flat)
    mesh.update()
    return count


def _angles(direction) -> np.ndarray:
    """Each face's wanted U direction as one angle.

    A face attribute holds one number, and a direction is a unit vector, which
    is two. The angle says the same thing and fits: the direction is always a
    tangent, so an angle between zero and two pi is the whole of it.
    """
    vectors = np.asarray(direction, dtype=np.float64).reshape(-1, 2)
    return np.arctan2(vectors[:, 1], vectors[:, 0]).astype(np.float32)


def _unit_directions(stored) -> np.ndarray:
    """Stored angles back into unit vectors."""
    angles = np.asarray(stored, dtype=np.float64).reshape(-1)
    return np.column_stack([np.cos(angles), np.sin(angles)])


def links_for(obj_name: str) -> LinkTable:
    """The link table for a workpiece, made on first use."""
    table = _LINKS.get(obj_name)
    if table is None:
        table = LinkTable()
        _LINKS[obj_name] = table
    return table


def relief_paths(context) -> dict:
    """The design's strokes, as the paths a brush can snap to."""
    from .op_draw import canvas_for

    canvas = canvas_for(context)
    found = {}
    for name, shapes in canvas.visible():
        points = []
        for shape in shapes:
            run = getattr(shape, "sample", None)
            points.extend((run(8) if callable(run) else
                           np.asarray([shape.start, shape.end])).tolist())
        found[name] = {"id": name,
                       "points": np.asarray(points, dtype=np.float64).reshape(-1, 2)}
    return found


def brush_mask(obj, centre_mm, radius_mm: float) -> np.ndarray:
    """The faces a circular brush covers, on the faces' own centres.

    Face centres rather than vertices: a brush that caught every vertex in
    range would reach a whole triangle beyond its size, and the user would be
    painting an area they never pointed at.
    """
    mesh = obj.data
    faces = _faces(obj)
    if not len(faces):
        return np.zeros(0, dtype=bool)
    points = _face_centres(mesh, faces)
    centre = np.asarray(centre_mm, dtype=np.float64).ravel()[:2]
    return np.linalg.norm(points - centre, axis=1) <= max(float(radius_mm), 0.0)


def _face_centres(mesh, faces):
    """Each triangle's centre in canvas millimetres."""
    coords = np.empty((len(mesh.vertices), 3), dtype=np.float64)
    mesh.vertices.foreach_get("co", coords.ravel())
    return coords[np.asarray(faces, dtype=np.int64)].mean(axis=1)[:, :2] * 1000.0


def _faces(obj) -> list:
    mesh = obj.data
    mesh.calc_loop_triangles()
    return [tuple(t.vertices) for t in mesh.loop_triangles]


def _attribute(mesh, name: str, faces=None):
    """A hint attribute read back as one value per triangle."""
    found = mesh.attributes.get(name)
    if found is None:
        return np.zeros(0)
    values = np.asarray([item.value for item in found.data], dtype=np.float32)
    if faces is None:
        return values
    mesh.calc_loop_triangles()
    owned = np.asarray([t.loops[0] for t in mesh.loop_triangles], dtype=np.int64)
    take = min(owned.size, len(faces) if faces is not None else owned.size)
    return values[owned[:take]] if take else np.zeros(0, np.float32)


def forget(obj_name: str) -> None:
    """Drop a workpiece's links, on undo or file load where they are stale."""
    _LINKS.pop(obj_name, None)


class BSCU_OT_CaroBrush(bpy.types.Operator):
    """Paint a brush hint onto the faces under the cursor"""

    bl_idname = "bscu.caro_brush"
    bl_label = "Paint Brush Hint"
    bl_options = {"REGISTER", "UNDO"}

    brush: bpy.props.EnumProperty(
        name="Brush",
        items=[("expand", "Expand", "More UV area here"),
               ("shrink", "Shrink", "Less UV area here"),
               ("relax", "Relax", "Smooth what has been painted"),
               ("pin", "Pin", "Hold this area in place"),
               ("priority", "Priority", "Keep shape instead of size"),
               ("direction", "Direction", "The U direction wanted here")],
        default="expand")
    centre_mm: bpy.props.FloatVectorProperty(name="At", size=2, default=(0.0, 0.0))
    size_px: bpy.props.FloatProperty(name="Size", default=DEFAULT_SIZE_PX, min=1.0)
    strength: bpy.props.FloatProperty(name="Strength", default=1.0)
    free: bpy.props.BoolProperty(
        name="Free",
        default=False,
        description="Paint with no link, as holding Alt does")
    direction: bpy.props.FloatVectorProperty(name="Direction", size=2,
                                            default=(1.0, 0.0))

    def execute(self, context):
        obj = context.active_object
        if obj is None or obj.type != "MESH":
            self.report({"ERROR"}, "select the workpiece to paint on")
            return {"CANCELLED"}

        hints = hints_for(obj)
        radius = float(self.size_px) * MM_PER_PIXEL

        if self.brush == "relax":
            moved = relax(hints, _neighbours(obj), passes=2, strength=self.strength)
            if moved == 0:
                self.report({"INFO"}, "nothing to relax there")
                return {"CANCELLED"}
        else:
            mask = brush_mask(obj, self.centre_mm, radius)
            if not mask.any():
                self.report({"WARNING"}, "the brush reached no faces")
                return {"CANCELLED"}
            if self.brush == "direction":
                paint(hints, mask, "direction",
                      direction=np.asarray(self.direction, dtype=np.float64))
            else:
                paint(hints, mask, self.brush, strength=self.strength)

        write_hints(obj, hints)
        taken = self._link(context, mask)
        if taken is not None:
            links_for(obj.name).add(taken)
        touched = int(mask.sum()) if self.brush != "relax" else moved
        where = "" if taken is None else f", linked to a {taken.kind}"
        self.report({"INFO"}, f"{self.brush} on {touched} face(s){where}")
        return {"FINISHED"}

    def _link(self, context, mask) -> Optional[Link]:
        """The link this stroke takes, or none when Alt was held.

        A brush stroke that snapped to relief geometry is a link, not a
        coordinate: it follows its source when the source moves. Alt on release
        is the spec's way out of that, and it has to be reachable without an
        undo afterwards.
        """
        if self.free or self.brush in ("relax", "direction"):
            return None
        paths = relief_paths(context)
        if not paths:
            return None
        centre = np.asarray(self.centre_mm, dtype=np.float64)
        hit = snap.find_snap(centre, paths,
                             snap.pixels_to_mm(self.size_px, MM_PER_PIXEL))
        return None if hit is None else hit.link()


def _neighbours(obj):
    """Face adjacency, for the relax brush."""
    return neighbour_pairs(np.asarray(_faces(obj), dtype=np.int64))


CLASSES = (BSCU_OT_CaroBrush,)


def register():
    return register_classes(CLASSES)


def unregister():
    _LINKS.clear()
    return unregister_classes(CLASSES)


__all__ = ("DEFAULT_SIZE_PX", "DENSITY", "DIRECTION", "MM_PER_PIXEL",
           "PIN", "PRIORITY", "BSCU_OT_CaroBrush", "brush_mask", "forget",
           "hints_for", "links_for", "relief_paths", "write_hints")
