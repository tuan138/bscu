"""
Blender-side seam access for the four seam tools (UX-6).

``core/`` works on plain arrays; this is the only place that reads and writes
``edge.use_seam``. Applying a seam goes through a normal operator so Blender's
Undo takes it, and applying never touches topology: the spec is explicit that
the near-plane tool suggests a path along existing edges rather than cutting
the mesh, and the confirm step holds to that.
"""

from mathutils import Vector

from ..core.seam_tools import (
    ChainError,
    chain_over_edges,
    nearest_plane_chain,
    selection_boundary,
    view_contour,
)
from ..core.uv_validate import validate_chart

#: A seam the user is looking at but has not confirmed. Cleared on Esc.
_pending: dict = {}


def mesh_faces(mesh) -> list:
    """Every polygon as a vertex-index triple.

    A quad grid is the normal way to model a workpiece, so the tools need
    triangles whatever the mesh is built from. Blender's own loop triangles are
    used rather than anything that would modify the mesh.
    """
    mesh.calc_loop_triangles()
    return [tuple(triangle.vertices) for triangle in mesh.loop_triangles]


def mesh_edge_pairs(mesh) -> list:
    """The mesh's real edges, as vertex pairs.

    These are the only edges a seam can be marked on, so every proposal is built
    from this list rather than from a triangulation.
    """
    return [tuple(sorted(edge.vertices)) for edge in mesh.edges]


def seam_edges(mesh) -> set:
    """The mesh's current seam set, as sorted vertex pairs."""
    found = set()
    for edge in mesh.edges:
        if edge.use_seam:
            found.add(tuple(sorted(edge.vertices)))
    return found


def set_seams(mesh, edges) -> int:
    """Replace the mesh's seam set and report how many edges changed."""
    wanted = {tuple(sorted(edge)) for edge in edges}
    available = set(mesh_edge_pairs(mesh))
    impossible = sorted(wanted - available)
    if impossible:
        raise ValueError(
            f"{len(impossible)} proposed edge(s) are not edges of this mesh, so "
            f"they cannot carry a seam; first of them: {impossible[0]}")
    changed = 0
    for edge in mesh.edges:
        should = tuple(sorted(edge.vertices)) in wanted
        if edge.use_seam != should:
            edge.use_seam = should
            changed += 1
    return changed


def staged(obj) -> dict:
    """The candidate seam waiting for the user to confirm it."""
    return _pending.get(obj.name, {"edges": [], "kind": None, "label": ""})


def stage(obj, edges, kind: str, label: str) -> dict:
    """Hold a candidate seam and what produced it, without touching the mesh."""
    _pending[obj.name] = {
        "edges": sorted({tuple(sorted(edge)) for edge in edges}),
        "kind": kind,
        "label": label,
    }
    return _pending[obj.name]


def clear_stage(obj_name: str) -> None:
    _pending.pop(obj_name, None)


def confirm(obj) -> int:
    """Apply the staged seam, then forget it."""
    candidate = _pending.pop(obj.name, None)
    if not candidate:
        return 0
    return set_seams(obj.data, candidate["edges"])


def surface_positions(mesh, uv_name: str) -> list:
    """Vertex positions in the mesh's own space, flattened to two axes.

    The near-plane tool reasons in the surface's own plane; on a stock the top
    face is XY, and anything flat enough for a cut is flat in those axes too.
    """
    return [[vertex.co.x, vertex.co.y] for vertex in mesh.vertices]


def face_normals(mesh) -> list:
    """Each polygon's normal, so the contour tool has something to compare."""
    return [[polygon.normal.x, polygon.normal.y, polygon.normal.z]
            for polygon in mesh.polygons]


def view_direction(context) -> Vector:
    """Where the eye is looking, from the region 3D view."""
    region = context.region
    rv3d = getattr(region, "data", None)
    if rv3d is None:
        raise ChainError("no 3D view to look from; the contour tool needs one")
    return Vector(rv3d.view_rotation) @ Vector((0.0, 0.0, -1.0))


def nearest_faces(obj, point, limit: int = 8):
    """The faces nearest a point on the object, closest first.

    Picking a point on the surface is the user's job; the tool only has to say
    which faces that point belongs to, and it says the closest ones rather than
    pretending to know which side the user meant.
    """
    hit, _location, normal, face = obj.closest_point_on_mesh(Vector(point))
    del hit, normal
    if face is None or face < 0:
        return []
    return [int(face)]


def validate_object(obj, seam=None):
    """Run the chart validator on whatever layout the mesh currently has."""
    mesh = obj.data
    faces = mesh_faces(mesh)
    if not faces:
        return validate_chart([], [], [])
    layout = _current_layout(obj)
    islands = _island_ids(mesh, obj)
    return validate_chart(faces, layout, islands, seam_edges(mesh) if seam is None else seam)


def _current_layout(obj) -> list:
    """The layout under test: the active BSCU map, or the first UV map."""
    mesh = obj.data
    layer = mesh.uv_layers.active
    points = [[0.0, 0.0] for _ in mesh.vertices]
    if layer is None:
        return points
    for loop in mesh.loops:
        uv = layer.data[loop.index].uv
        points[loop.vertex_index] = [uv.x, uv.y]
    return points


def _island_ids(mesh, obj) -> list:
    """Which chart each face belongs to, from the active map's own seams."""
    from ..core.uv_islands import extract_islands

    faces = mesh_faces(mesh)
    if not faces:
        return []
    edges = [edge for edge in seam_edges(mesh)]
    faces_array = _as_arrays(faces)
    opened = extract_islands(faces_array, edges)
    return list(opened)


def _as_arrays(faces):
    import numpy as np

    return np.asarray(faces, dtype=np.int64)


def propose_chain(obj, start: int, goal: int) -> dict:
    """Stage the chain between two vertices, or explain why there is none."""
    edges = chain_over_edges(mesh_edge_pairs(obj.data), start, goal)
    return stage(obj, edges, "chain", f"Chain {start} to {goal}")


def polygon_selection_to_triangles(mesh, selected) -> list:
    """Turn a polygon selection into the triangle selection the tools work on.

    A user selects faces; the mesh may hold quads; the seam tools reason about
    triangles. Expanding here keeps that translation in one place, where a
    mismatch would otherwise show up as a selection covering the wrong count.
    """
    flags = list(selected)
    if len(flags) != len(mesh.polygons):
        raise ValueError(
            f"selection covers {len(flags)} polygons, the mesh has {len(mesh.polygons)}")
    mesh.calc_loop_triangles()
    return [bool(flags[triangle.polygon_index])
            for triangle in mesh.loop_triangles]


def propose_selection_border(obj, selected) -> dict:
    """Stage the border of the selected faces."""
    triangles = polygon_selection_to_triangles(obj.data, selected)
    edges = selection_boundary(mesh_faces(obj.data), triangles)
    return stage(obj, edges, "selection", f"{len(edges)} border edge(s)")


def propose_near_plane(obj, origin, normal, tolerance) -> dict:
    """Stage the existing edges that sit near a reference plane."""
    mesh = obj.data
    edges = nearest_plane_chain(mesh_faces(mesh), surface_positions(mesh, ""),
                                origin, normal, tolerance)
    return stage(obj, edges, "plane", f"{len(edges)} edge(s) near the plane")


def propose_contour(obj, direction) -> dict:
    """Stage the silhouette the face normals suggest, and nothing more."""
    mesh = obj.data
    proposal = view_contour(mesh_faces(mesh), face_normals(mesh), direction)
    return stage(obj, proposal.silhouette, "contour",
                 f"{len(proposal.silhouette)} candidate(s), "
                 f"{len(proposal.undecided)} undecided")


__all__ = (
    "ChainError",
    "clear_stage",
    "confirm",
    "face_normals",
    "mesh_edge_pairs",
    "mesh_faces",
    "nearest_faces",
    "polygon_selection_to_triangles",
    "propose_chain",
    "propose_contour",
    "propose_near_plane",
    "propose_selection_border",
    "seam_edges",
    "set_seams",
    "staged",
    "stage",
    "surface_positions",
    "validate_object",
    "view_direction",
)
