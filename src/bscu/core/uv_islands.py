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
    """Map each undirected edge to the indices of the faces using it."""
    edge_faces: Dict[Tuple[int, int], List[int]] = {}
    for face_index, face in enumerate(faces):
        a, b, c = int(face[0]), int(face[1]), int(face[2])
        for edge in (
            (min(a, b), max(a, b)),
            (min(b, c), max(b, c)),
            (min(c, a), max(c, a)),
        ):
            edge_faces.setdefault(edge, []).append(face_index)
    return edge_faces


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


def check_topology(faces: np.ndarray, edge_faces) -> TopologyReport:
    """Classify a mesh as mappable or blocked.

    ``edge_faces`` maps each undirected edge to the faces using it; use
    :func:`build_edge_faces` to produce it.
    """
    tris = np.asarray(faces, dtype=np.int64)

    malformed = int(sum(1 for f in tris if len(set(f.tolist())) != 3))

    signatures = [tuple(sorted(f.tolist())) for f in tris]
    duplicate = len(signatures) - len(set(signatures))

    boundary = 0
    non_manifold = 0
    for users in edge_faces.values():
        if len(users) == 1:
            boundary += 1
        elif len(users) > MAX_FACES_PER_EDGE:
            non_manifold += 1

    return TopologyReport(
        boundary_edges=boundary,
        non_manifold_edges=non_manifold,
        duplicate_faces=duplicate,
        malformed_faces=malformed,
    )
