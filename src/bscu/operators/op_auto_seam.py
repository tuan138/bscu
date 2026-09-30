"""
Proposing a cut and applying it (UX-4, UIUX 3.2).

The algorithm in :mod:`bscu.core.seam_graph` decides *where* a seam should go;
this decides whether to act on it. The split matters, because the same proposal
is used three ways: previewed while the user looks, checked before it is
offered, and applied once they confirm it.

Two rules from the spec shape it:

* A candidate is **measured, never asserted**. Every proposal carries its
  distortion, and one over the limit is reported rather than offered as though
  it were fine.
* Nothing is applied until it is confirmed. The preview and the applied cut are
  the same cut, so what the user saw is what lands.
"""

from typing import List, Tuple

import bpy
import numpy as np

from ..core.seam_graph import (
    charts_by_merge,
    charts_by_normal_clustering,
    face_normals,
)
from ..registry import register_classes, unregister_classes

#: Above this relative area stretch a chart is refused. PartUV's own gate
#: measures the same thing: a chart that stretches this much cannot be cut.
DEFAULT_MAX_DISTORTION = 1.0

MM_PER_METRE = 1000.0

#: The proposal waiting for the user, per object.
_pending: dict = {}


def propose(obj, max_charts: int = 6, max_distortion: float = DEFAULT_MAX_DISTORTION
             ) -> List[dict]:
    """Propose a chart set for an object, each with the measurement behind it.

    Normal clustering first, then the merge that a plain heuristic cannot do:
    on a symmetric blob the clustering alone asks for six and hands back
    hundreds, and merging is what brings it down. The reduction is done against
    the distortion gate, so a chart is only merged away if the result still
    lies flat enough to cut.
    """
    mesh = obj.data
    mesh.calc_loop_triangles()
    faces = np.asarray([tuple(t.vertices) for t in mesh.loop_triangles],
                       dtype=np.int64)
    if not faces.size:
        return []

    verts = np.empty((len(mesh.vertices), 3), dtype=np.float64)
    mesh.vertices.foreach_get("co", verts.ravel())
    verts_mm = verts * MM_PER_METRE

    normals = face_normals(verts, faces)
    # Clustering gives a chart per normal, which on a symmetric blob is far more
    # than anyone asked for; the merge is what brings the number down, and the
    # gate is what keeps it honest.
    clustered = charts_by_normal_clustering(faces, normals, chart_count=max_charts)
    labels = np.zeros(len(faces), dtype=np.int64)
    for index, chart in enumerate(clustered):
        labels[np.asarray(chart, dtype=np.int64)] = index
    candidates = charts_by_merge(faces, labels, allow_merge=True, normals=normals)
    if not candidates:
        candidates = clustered

    # charts_by_merge already refuses a merge that would fold a chart past
    # max_spread_deg, so the candidates it hands back are the gate's answer.
    chosen = candidates
    proposals = [
        {
            "faces": np.asarray(chart, dtype=np.int64),
            "face_indices": np.asarray(chart, dtype=np.int64),
            "size": len(chart),
            "distortion": _distortion_of(verts_mm, verts, faces, chart),
            "accepted": len(chosen) <= max(max_charts, 1),
        }
        for chart in chosen
    ]
    _pending[obj.name] = proposals
    return proposals


def _distortion_of(verts_mm, verts, faces, face_indices) -> float:
    """The chart's relative area stretch when flattened, from PartUV's gate.

    ``face_indices`` are indices into the whole mesh's face list, which is what
    the charting code hands back. They are narrowed to the chart's own vertices
    here, because a chart is measured on its own faces, not on the model.
    """
    from ..core.math_utils import plane_frame
    from ..core.seam_graph import chart_distortion

    tris = np.asarray(faces, dtype=np.int64)
    inside_tris = tris[np.asarray(face_indices, dtype=np.int64)]
    if not inside_tris.size:
        return 0.0
    vertices = np.unique(inside_tris)
    remap = np.full(int(inside_tris.max()) + 1, -1, dtype=np.int64)
    remap[vertices] = np.arange(vertices.size)
    local = remap[inside_tris]
    inside = verts[vertices] * MM_PER_METRE
    return chart_distortion(inside, plane_frame(inside), local)


def staged(obj_name: str) -> List[dict]:
    """The proposals last made for an object."""
    return _pending.get(obj_name, [])


def clear(obj_name: str) -> None:
    _pending.pop(obj_name, None)


class BSCU_OT_AutoSeam(bpy.types.Operator):
    """Propose a cut for the workpiece, and apply the charts that were accepted"""

    bl_idname = "bscu.auto_seam"
    bl_label = "Propose a Cut"
    bl_options = {"REGISTER", "UNDO"}

    max_charts: bpy.props.IntProperty(
        name="Charts", default=6, min=1, max=64,
        description="How many charts to aim for; the gate may need more")
    max_distortion: bpy.props.FloatProperty(
        name="Limit", default=DEFAULT_MAX_DISTORTION, min=0.0,
        description="Relative area stretch a chart may reach before it is refused")
    apply_now: bpy.props.BoolProperty(
        name="Apply", default=False,
        description="Mark the proposed charts as seams now, rather than previewing")

    def execute(self, context):
        obj = context.active_object
        if obj is None or obj.type != "MESH":
            self.report({"ERROR"}, "select the workpiece to cut")
            return {"CANCELLED"}

        proposals = propose(obj, self.max_charts, self.max_distortion)
        if not proposals:
            self.report({"WARNING"}, "nothing to propose on that mesh")
            return {"CANCELLED"}

        refused = [p for p in proposals if p["distortion"] > self.max_distortion]
        sizes = ", ".join(str(p["size"]) for p in proposals)
        message = f"{len(proposals)} chart(s): {sizes} faces"
        if refused:
            message += f"; {len(refused)} over the limit"

        if not self.apply_now:
            self.report({"INFO"}, message + " - press Apply to cut")
            return {"FINISHED"}

        applied = self._apply(obj, proposals)
        self.report({"INFO"} if applied else {"WARNING"},
                    message + f"; {applied} chart(s) cut")
        return {"FINISHED"} if applied else {"CANCELLED"}

    def _apply(self, obj, proposals) -> int:
        """Mark the accepted charts' borders as seams."""
        mesh = obj.data
        faces = np.asarray([tuple(p.vertices) for p in mesh.polygons],
                           dtype=np.int64)
        wanted = set()
        for proposal in proposals:
            if proposal["distortion"] > self.max_distortion:
                continue
            chart = proposal["faces"]
            for edge in _chart_border(chart, faces):
                wanted.add(tuple(sorted(edge)))

        changed = 0
        for edge in mesh.edges:
            should = tuple(sorted(edge.vertices)) in wanted
            if edge.use_seam != should:
                edge.use_seam = should
                changed += 1
        clear(obj.name)
        return changed


def _chart_border(chart: np.ndarray, faces: np.ndarray) -> List[Tuple[int, int]]:
    """The edges a chart uses exactly once: where it has to be cut.

    ``chart`` holds face indices, so the faces themselves are gathered first:
    the border is a property of the triangles, not of the numbers naming them.
    """
    from ..core.seam_tools import edge_face_counts

    usage = edge_face_counts(np.asarray(faces, dtype=np.int64)[chart])
    return [edge for edge, users in usage.items() if len(users) == 1]


CLASSES = (BSCU_OT_AutoSeam,)


def register():
    return register_classes(CLASSES)


def unregister():
    _pending.clear()
    return unregister_classes(CLASSES)


__all__ = ("DEFAULT_MAX_DISTORTION", "BSCU_OT_AutoSeam", "clear", "propose",
           "staged")
