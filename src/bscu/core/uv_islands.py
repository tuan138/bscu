"""
UV island extraction and seam topology diagnostics (UX-1, UIUX 2.4 / 3.7).

Pure numpy, no bpy. Two faces belong to the same island when they share an
edge that is not a seam.

The severity split follows the spec: an open boundary is a legitimate design
base and is only reported, never treated as an error, while topology that
cannot be mapped (non-manifold edges, duplicate or malformed faces) blocks.
A vertex of valence 1 is never an error on its own.
"""

from dataclasses import dataclass
from typing import Dict, List, Sequence, Tuple

import numpy as np

# Blocking topology reasons.
NON_MANIFOLD_EDGE = "NON_MANIFOLD_EDGE"
DUPLICATE_FACE = "DUPLICATE_FACE"
REPEATED_VERTEX = "REPEATED_VERTEX"

# An edge shared by more than this many faces cannot be mapped.
MAX_FACES_PER_EDGE = 2


@dataclass(frozen=True)
class TopologyReport:
    """What the seam tools need to know before any unwrap is attempted."""

    boundary_edges: int = 0
    non_manifold_edges: int = 0
    duplicate_faces: int = 0
    malformed_faces: int = 0

    @property
    def has_open_boundary(self) -> bool:
        return self.boundary_edges > 0

    @property
    def blocking_codes(self) -> Tuple[str, ...]:
        codes = []
        if self.non_manifold_edges:
            codes.append(NON_MANIFOLD_EDGE)
        if self.duplicate_faces:
            codes.append(DUPLICATE_FACE)
        if self.malformed_faces:
            codes.append(REPEATED_VERTEX)
        return tuple(codes)

    @property
    def is_mappable(self) -> bool:
        return not self.blocking_codes


def _face_edges(faces: np.ndarray):
    """Yield the three undirected edges of every triangular face."""
    for face in faces:
        a, b, c = int(face[0]), int(face[1]), int(face[2])
        yield (min(a, b), max(a, b))
        yield (min(b, c), max(b, c))
        yield (min(c, a), max(c, a))


def build_edge_faces(faces: np.ndarray) -> Dict[Tuple[int, int], List[int]]:
    """Map each undirected edge to the indices of the faces using it.

    Grouping uses a single argsort over packed edge keys: a Python loop over the
    faces cost 24 ms on a 9k-triangle mesh, more than the unwrap it supports.
    """
    tris = np.asarray(faces, dtype=np.int64).reshape(-1, 3)
    if tris.size == 0:
        return {}

    count = tris.shape[0]
    left = tris[:, [0, 1, 2]].ravel()
    right = tris[:, [1, 2, 0]].ravel()
    lower = np.minimum(left, right)
    upper = np.maximum(left, right)
    keys = lower * (int(upper.max()) + 1) + upper
    owners = np.repeat(np.arange(count, dtype=np.int64), 3)

    order = np.argsort(keys, kind="stable")
    ordered_keys = keys[order]
    ordered_owners = owners[order]
    starts = np.flatnonzero(np.r_[True, ordered_keys[1:] != ordered_keys[:-1]])
    bounds = np.r_[starts[1:], ordered_owners.size]

    return {
        (int(lower[order[start]]), int(upper[order[start]])): ordered_owners[start:stop].tolist()
        for start, stop in zip(starts, bounds)
    }

def edge_face_counts(faces: np.ndarray) -> np.ndarray:
    """How many faces use each distinct undirected edge.

    Backs :func:`check_topology` without materialising a Python dict: building
    one cost 28 ms on a 9k-triangle mesh, more than the unwrap it validates.
    """
    tris = np.asarray(faces, dtype=np.int64).reshape(-1, 3)
    if tris.size == 0:
        return np.zeros(0, dtype=np.int64)
    left = tris[:, [0, 1, 2]].ravel()
    right = tris[:, [1, 2, 0]].ravel()
    keys = np.minimum(left, right) * (int(right.max()) + 1) + np.maximum(left, right)
    unique, counts = np.unique(keys, return_counts=True)
    return counts



class _UnionFind:
    def __init__(self, size: int):
        self._parent = list(range(size))

    def find(self, item: int) -> int:
        while self._parent[item] != item:
            self._parent[item] = self._parent[self._parent[item]]
            item = self._parent[item]
        return item

    def union(self, left: int, right: int) -> None:
        a, b = self.find(left), self.find(right)
        if a != b:
            self._parent[b] = a


def extract_islands(faces: np.ndarray, seam_edges: Sequence[Tuple[int, int]]) -> np.ndarray:
    """Assign each face an island index, splitting across seam edges.

    Seam edges given as plain vertex pairs are honoured even when no face uses
    them, so a seam drawn ahead of the unwrap still counts.
    """
    tris = np.asarray(faces, dtype=np.int64)
    count = tris.shape[0]
    if count == 0:
        return np.zeros(0, dtype=np.int64)

    seams = {(min(int(a), int(b)), max(int(a), int(b))) for a, b in seam_edges}
    edge_faces = build_edge_faces(tris)
    union = _UnionFind(count)

    for edge, users in edge_faces.items():
        if edge in seams:
            continue
        first = users[0]
        for other in users[1:]:
            union.union(first, other)

    roots = [union.find(index) for index in range(count)]
    # Renumber in first-seen order so island ids are dense and stable.
    order: Dict[int, int] = {}
    for index, root in enumerate(roots):
        if root not in order:
            order[root] = len(order)
        roots[index] = order[root]
    return np.asarray(roots, dtype=np.int64)


def island_face_counts(island_ids: np.ndarray) -> List[int]:
    """Face count per island, in island id order."""
    if len(island_ids) == 0:
        return []
    counts = np.bincount(np.asarray(island_ids, dtype=np.int64))
    return [int(c) for c in counts]


def seam_endpoint_vertices(
    seam_edges: np.ndarray, edges: np.ndarray, vertex_count: int
) -> np.ndarray:
    """Vertices where the seam stops: seam valence of exactly one.

    A junction where three seam edges meet is a valid seam configuration, not a
    free end, so only valence one counts.
    """
    if len(edges) == 0:
        return np.zeros(0, dtype=np.int64)

    members = np.zeros(vertex_count, dtype=np.int64)
    for a, b in np.asarray(edges, dtype=np.int64):
        members[int(a)] += 1
        members[int(b)] += 1
    return np.flatnonzero(members == 1).astype(np.int64)


def check_topology(faces: np.ndarray, edge_faces=None) -> TopologyReport:
    """Classify a mesh as mappable or blocked.

    ``edge_faces`` is optional: pass the mapping from :func:`build_edge_faces`
    when it is already built, otherwise the edge counts are computed from the
    faces directly, which is what the hot path does.
    """
    tris = np.asarray(faces, dtype=np.int64).reshape(-1, 3)

    if tris.size:
        distinct = np.sort(tris, axis=1)
        _, first_index = np.unique(distinct, axis=0, return_index=True)
        duplicate = int(tris.shape[0] - first_index.size)
        malformed = int((distinct[:, 0] == distinct[:, 1]).sum())
        malformed += int((distinct[:, 1] == distinct[:, 2]).sum())
    else:
        duplicate = 0
        malformed = 0

    if edge_faces is not None:
        counts = np.array([len(users) for users in edge_faces.values()])
    else:
        counts = edge_face_counts(tris)

    boundary = int((counts == 1).sum())
    non_manifold = int((counts > MAX_FACES_PER_EDGE).sum())

    return TopologyReport(
        boundary_edges=boundary,
        non_manifold_edges=non_manifold,
        duplicate_faces=duplicate,
        malformed_faces=malformed,
    )
