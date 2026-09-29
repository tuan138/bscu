"""
Blender-side mesh snapshot for the measurement pipeline (UX-1/UX-2).

The only place that touches bpy before the pure maths run. Everything it
produces is plain numpy in millimetres, so ``core/`` never needs Blender types.

Read-only by design: taking a snapshot must not modify the mesh, its seams or
its UV maps.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

import bpy
import numpy as np

from ..core.uv_islands import build_edge_faces

BSCU_UV_NAME = "BSCU_UV_Active"
MM_PER_METRE = 1000.0
UV_PRECISION = 9

# Corner keys are packed into one int64; these bound the packing.
_MAX_PACKED_KEY = 1 << 62
UV_KEY_QUANTUMS = (1e6, 1e3, 1.0)


@dataclass
class MeshSnapshot:
    """A triangulated surface with its UVs and seam set.

    Vertices are split at UV seams, so ``len(verts_mm)`` can exceed the mesh
    vertex count; see :func:`_split_corners`. Topology checks must use the
    ``source_*`` fields: the split surface is open by construction wherever the
    unwrap was cut, which says nothing about whether the mesh is mappable.

    The edge maps are built on first use. Materialising them eagerly cost more
    than the unwrap they describe, and most callers only need face counts.
    """

    verts_mm: np.ndarray
    uv: np.ndarray
    faces: np.ndarray
    seam_edges: np.ndarray
    source_faces: np.ndarray
    _edge_faces: Optional[Dict[Tuple[int, int], List[int]]] = field(
        default=None, repr=False
    )
    _source_edge_faces: Optional[Dict[Tuple[int, int], List[int]]] = field(
        default=None, repr=False
    )

    def __len__(self) -> int:
        return int(self.faces.shape[0])

    @property
    def edge_faces(self) -> Dict[Tuple[int, int], List[int]]:
        """Edge to faces for the split surface."""
        if self._edge_faces is None:
            self._edge_faces = build_edge_faces(self.faces)
        return self._edge_faces

    @property
    def source_edge_faces(self) -> Dict[Tuple[int, int], List[int]]:
        """Edge to faces for the untouched mesh."""
        if self._source_edge_faces is None:
            self._source_edge_faces = build_edge_faces(self.source_faces)
        return self._source_edge_faces


def _metres_per_unit(obj) -> float:
    """How many millimetres one Blender unit represents in this scene."""
    scene = obj.users_scene[0] if obj.users_scene else bpy.context.scene
    return float(scene.unit_settings.scale_length) * MM_PER_METRE


def _positions_mm(obj) -> np.ndarray:
    """Mesh vertex positions in world space, converted to millimetres."""
    mesh = obj.data
    raw = np.empty(len(mesh.vertices) * 3, dtype=np.float64)
    mesh.vertices.foreach_get("co", raw)
    raw = raw.reshape(-1, 3)

    matrix = np.array(obj.matrix_world, dtype=np.float64)
    world = raw @ matrix[:3, :3].T + matrix[:3, 3]
    return world * _metres_per_unit(obj)


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


def _corner_keys(corner_vertex, corner_uv) -> np.ndarray:
    """Pack (vertex, u, v) into one int64 so dedup is a 1-D sort.

    np.unique(axis=0) over float rows costs several times the unwrap it feeds,
    so corners are keyed by a single integer. When the UV span is too wide to
    pack, the quantum is coarsened rather than falling back to a second path.
    """
    vertex_count = int(corner_vertex.max()) + 1
    for quantum in UV_KEY_QUANTUMS:
        quantised = np.rint(corner_uv * quantum).astype(np.int64)
        lowest = quantised.min(axis=0)
        span_u = int(quantised[:, 0].max() - lowest[0]) + 1
        span_v = int(quantised[:, 1].max() - lowest[1]) + 1
        if span_u * span_v * vertex_count <= _MAX_PACKED_KEY:
            shifted = quantised - lowest
            flat = (corner_vertex.astype(np.int64) * span_u + shifted[:, 0]) * span_v
            return flat + shifted[:, 1]
    raise ValueError(
        "UV coordinates span too wide to index; rescale the unwrap before measuring"
    )


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
    corner_loops = _corner_loops(mesh)

    loop_vertex = np.empty(len(mesh.loops), dtype=np.int64)
    mesh.loops.foreach_get("vertex_index", loop_vertex)

    corner_uv = np.round(_loop_uv(mesh, uv_name)[corner_loops.ravel()], UV_PRECISION)
    corner_vertex = loop_vertex[corner_loops.ravel()]

    if corner_uv.shape[0] == 0:
        empty = np.zeros(0, dtype=np.int64)
        return np.zeros((0, 3)), np.zeros((0, 2)), empty.reshape(0, 3), empty

    _, first_seen, inverse = np.unique(
        _corner_keys(corner_vertex, corner_uv),
        return_index=True,
        return_inverse=True,
    )
    source_vertex = corner_vertex[first_seen]

    return (
        positions[source_vertex],
        corner_uv[first_seen],
        inverse.reshape(-1, 3).astype(np.int64),
        source_vertex,
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
    endpoints = endpoints.reshape(-1, 2)[flags]
    return {
        (min(int(a), int(b)), max(int(a), int(b))) for a, b in endpoints
    }


def _seam_split_edges(
    faces: np.ndarray, source_vertex: np.ndarray, seam_pairs: Set[Tuple[int, int]]
) -> np.ndarray:
    """Express the seam set in split-vertex indices."""
    if not seam_pairs or faces.size == 0:
        return np.zeros((0, 2), dtype=np.int64)

    left = faces[:, [0, 1, 2]].ravel()
    right = faces[:, [1, 2, 0]].ravel()
    source_left = source_vertex[left]
    source_right = source_vertex[right]
    canonical = np.minimum(source_left, source_right)
    other = np.maximum(source_left, source_right)

    wanted = sorted(seam_pairs)
    lookup = {pair: index for index, pair in enumerate(wanted)}
    is_seam = np.array(
        [pair in lookup for pair in zip(canonical.tolist(), other.tolist())]
    )
    if not is_seam.any():
        return np.zeros((0, 2), dtype=np.int64)

    seam_left = np.minimum(left[is_seam], right[is_seam])
    seam_right = np.maximum(left[is_seam], right[is_seam])
    unique = np.unique(np.column_stack([seam_left, seam_right]), axis=0)
    return unique.astype(np.int64)


def take_snapshot(obj, uv_name: str = BSCU_UV_NAME) -> MeshSnapshot:
    """Capture one mesh as millimetre positions, UVs, triangles and seams."""
    if obj is None or obj.type != "MESH":
        kind = "None" if obj is None else obj.type
        raise ValueError(f"Snapshot needs a Mesh object, got {kind}")

    verts_mm, uv, faces, source_vertex = _split_corners(obj, uv_name)
    return MeshSnapshot(
        verts_mm=verts_mm,
        uv=uv,
        faces=faces,
        seam_edges=_seam_split_edges(
            faces, source_vertex, _seam_vertices(obj.data)
        ),
        source_faces=_source_faces(obj.data),
    )
