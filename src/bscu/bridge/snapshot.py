"""
Blender-side mesh snapshot for the measurement pipeline (UX-1).

The only place that touches bpy before the pure maths run. Everything it
produces is plain numpy in millimetres, so ``core/`` never needs Blender types.

Read-only by design: taking a snapshot must not modify the mesh, its seams or
its UV maps.
"""

from dataclasses import dataclass
from typing import Dict, List, Set, Tuple

import bpy
import numpy as np

from ..core.uv_islands import build_edge_faces

BSCU_UV_NAME = "BSCU_UV_Active"
MM_PER_METRE = 1000.0
UV_PRECISION = 9


@dataclass(frozen=True)
class MeshSnapshot:
    """A triangulated surface with its UVs and seam set.

    Vertices are split at UV seams, so ``len(verts_mm)`` can exceed the mesh
    vertex count; see :func:`_split_corners`. Topology checks must use the
    ``source_*`` fields: the split surface is open by construction wherever the
    unwrap was cut, which says nothing about whether the mesh is mappable.
    """

    verts_mm: np.ndarray
    uv: np.ndarray
    faces: np.ndarray
    edge_faces: Dict[Tuple[int, int], List[int]]
    seam_edges: np.ndarray
    source_faces: np.ndarray
    source_edge_faces: Dict[Tuple[int, int], List[int]]

    def __len__(self) -> int:
        return int(self.faces.shape[0])


def _positions_mm(obj) -> np.ndarray:
    """Mesh vertex positions in world space, converted to millimetres."""
    mesh = obj.data
    raw = np.empty(len(mesh.vertices) * 3, dtype=np.float64)
    mesh.vertices.foreach_get("co", raw)
    raw = raw.reshape(-1, 3)

    matrix = np.array(obj.matrix_world, dtype=np.float64)
    world = raw @ matrix[:3, :3].T + matrix[:3, 3]
    return world * _metres_per_unit(obj)


def _metres_per_unit(obj) -> float:
    """How many millimetres one Blender unit represents in this scene."""
    scene = obj.users_scene[0] if obj.users_scene else bpy.context.scene
    return float(scene.unit_settings.scale_length) * MM_PER_METRE


def _loop_uv(mesh, uv_name: str) -> np.ndarray:
    layer = mesh.uv_layers.get(uv_name)
    if layer is None:
        raise ValueError(f"UV layer {uv_name!r} not found on mesh {mesh.name!r}")
    values = np.empty(len(mesh.loops) * 2, dtype=np.float64)
    layer.data.foreach_get("uv", values)
    return values.reshape(-1, 2)


def _corner_loops(mesh) -> np.ndarray:
    """Loop index of every triangle corner, shape (T, 3)."""
    mesh.calc_loop_triangles()
    loops = np.empty(len(mesh.loop_triangles) * 3, dtype=np.int64)
    mesh.loop_triangles.foreach_get("loops", loops)
    return loops.reshape(-1, 3)


def _source_faces(mesh) -> np.ndarray:
    """Mesh triangles in original vertex indices, before any UV splitting."""
    mesh.calc_loop_triangles()
    tris = np.empty(len(mesh.loop_triangles) * 3, dtype=np.int64)
    mesh.loop_triangles.foreach_get("vertices", tris)
    return tris.reshape(-1, 3)


def _split_corners(obj, uv_name: str):
    """Split vertices wherever the UV changes, and return the split surface.

    Blender stores UVs per loop, not per vertex: a cube corner belongs to three
    faces that each give it a different UV. Measuring with one UV per mesh
    vertex would blend those three charts and report faces as flipped. Splitting
    on (vertex, uv) reproduces exactly the corner data each triangle uses, while
    still sharing corners whose UV agrees.

    Returns (verts_mm, uv, faces, source_vertex) where ``source_vertex`` maps
    each split vertex back to the mesh vertex it came from.
    """
    mesh = obj.data
    positions = _positions_mm(obj)
    loop_uv = _loop_uv(mesh, uv_name)
    corner_loops = _corner_loops(mesh)

    loop_vertex = np.empty(len(mesh.loops), dtype=np.int64)
    mesh.loops.foreach_get("vertex_index", loop_vertex)

    key_to_index: Dict[Tuple[int, float, float], int] = {}
    split_positions: List[np.ndarray] = []
    split_uv: List[np.ndarray] = []
    source_vertex: List[int] = []
    faces = np.empty(corner_loops.size, dtype=np.int64)

    for position, loop_index in enumerate(corner_loops.ravel()):
        vertex_index = int(loop_vertex[loop_index])
        uv = loop_uv[loop_index]
        key = (vertex_index, round(float(uv[0]), UV_PRECISION), round(float(uv[1]), UV_PRECISION))
        index = key_to_index.get(key)
        if index is None:
            index = len(split_positions)
            key_to_index[key] = index
            split_positions.append(positions[vertex_index])
            split_uv.append(uv)
            source_vertex.append(vertex_index)
        faces[position] = index

    if not split_positions:
        empty_faces = np.zeros((0, 3), dtype=np.int64)
        return np.zeros((0, 3)), np.zeros((0, 2)), empty_faces, np.zeros(0, dtype=np.int64)

    return (
        np.vstack(split_positions),
        np.vstack(split_uv),
        faces.reshape(-1, 3),
        np.asarray(source_vertex, dtype=np.int64),
    )


def _seam_vertices(mesh) -> Set[Tuple[int, int]]:
    """Undirected vertex pairs marked as seam by the user."""
    if len(mesh.edges) == 0:
        return set()
    flags = np.zeros(len(mesh.edges), dtype=bool)
    mesh.edges.foreach_get("use_seam", flags)
    if not flags.any():
        return set()

    endpoints = np.empty(len(mesh.edges) * 2, dtype=np.int64)
    mesh.edges.foreach_get("vertices", endpoints)
    endpoints = endpoints.reshape(-1, 2)
    return {
        (min(int(a), int(b)), max(int(a), int(b)))
        for a, b in endpoints[flags]
    }


def _seam_split_edges(
    faces: np.ndarray, source_vertex: np.ndarray, seam_pairs: Set[Tuple[int, int]]
) -> np.ndarray:
    """Express the seam set in split-vertex indices."""
    if not seam_pairs:
        return np.zeros((0, 2), dtype=np.int64)

    found: Set[Tuple[int, int]] = set()
    for face in faces:
        a, b, c = int(face[0]), int(face[1]), int(face[2])
        for left, right in ((a, b), (b, c), (c, a)):
            pair = (source_vertex[left], source_vertex[right])
            if (min(pair), max(pair)) in seam_pairs:
                found.add((min(left, right), max(left, right)))

    if not found:
        return np.zeros((0, 2), dtype=np.int64)
    return np.array(sorted(found), dtype=np.int64)


def take_snapshot(obj, uv_name: str = BSCU_UV_NAME) -> MeshSnapshot:
    """Capture one mesh as millimetre positions, UVs, triangles and seams."""
    if obj is None or obj.type != "MESH":
        kind = "None" if obj is None else obj.type
        raise ValueError(f"Snapshot needs a Mesh object, got {kind}")

    verts_mm, uv, faces, source_vertex = _split_corners(obj, uv_name)
    source_faces = _source_faces(obj.data)
    return MeshSnapshot(
        verts_mm=verts_mm,
        uv=uv,
        faces=faces,
        edge_faces=build_edge_faces(faces),
        seam_edges=_seam_split_edges(
            faces, source_vertex, _seam_vertices(obj.data)
        ),
        source_faces=source_faces,
        source_edge_faces=build_edge_faces(source_faces),
    )
