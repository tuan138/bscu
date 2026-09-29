"""
The four seam tools (UX-6, UIUX 3.2).

Two are primary, two are support, and all four produce a *proposal* the user
previews before it is applied. The preview and the applied chain are the same
chain, because a seam the user could not see before it landed would be a
surprise rather than a tool.

The limits are deliberate and named:

* A chain between two points is a shortest walk over the mesh's existing edges.
  It is not a geodesic on the surface, and it is not computed on the surface.
* The near-plane tool suggests a path along existing edges near a plane. It
  never cuts the mesh, and it does not promise an exact intersection.
* The view-contour tool proposes silhouette candidates from normals alone. It
  cannot see occlusion and says so, rather than pretending the candidates are
  the outline of what the user can see.
* The selection border counts edges with exactly one selected face. That is not
  the same thing as the mesh's own border, which is why it is computed here
  rather than read off ``edge.is_boundary``.
"""

import heapq
from dataclasses import dataclass
from typing import Dict, List, Sequence, Tuple

import numpy as np

Edge = Tuple[int, int]


class ChainError(ValueError):
    """No chain exists, or the request does not make sense on this mesh."""


def undirected_edges(faces: np.ndarray) -> np.ndarray:
    """Every edge of every triangle, as (F, 3, 2) rows with a <= b."""
    tris = np.asarray(faces, dtype=np.int64).reshape(-1, 3)
    if not tris.size:
        return np.zeros((0, 3, 2), dtype=np.int64)
    pairs = np.stack([tris[:, [0, 1]], tris[:, [1, 2]], tris[:, [2, 0]]], axis=1)
    return np.sort(pairs, axis=2)


def _vertex_adjacency(faces: np.ndarray) -> Dict[int, List[int]]:
    """Neighbouring vertices over the mesh's own edges."""
    links: Dict[int, set] = {}
    for row in undirected_edges(faces):
        for left, right in row:
            links.setdefault(int(left), set()).add(int(right))
            links.setdefault(int(right), set()).add(int(left))
    return {vertex: sorted(neighbours) for vertex, neighbours in links.items()}


def chain_between(faces: np.ndarray, start: int, goal: int) -> List[Edge]:
    """The shortest walk over existing edges from one vertex to another.

    This is a shortest path in the mesh's edge graph. On a curved surface the
    geometrically shortest route is a different path, and the difference grows
    with curvature; the tool is named for what it does rather than for
    something it does not do.
    """
    if start == goal:
        return []
    links = _vertex_adjacency(faces)
    if start not in links or goal not in links:
        raise ChainError(f"vertex {start if start not in links else goal} "
                         f"is not on this mesh")

    previous: Dict[int, int] = {}
    seen = {start}
    queue = [(0, start)]
    while queue:
        distance, vertex = heapq.heappop(queue)
        if vertex == goal:
            break
        for neighbour in links[vertex]:
            if neighbour in seen:
                continue
            seen.add(neighbour)
            previous[neighbour] = vertex
            heapq.heappush(queue, (distance + 1, neighbour))
    if goal not in previous:
        raise ChainError(f"no edge path joins vertex {start} to {goal}; "
                         f"they are in different pieces of the mesh")

    path = [goal]
    while path[-1] != start:
        path.append(previous[path[-1]])
    path.reverse()
    return [(a, b) for a, b in zip(path, path[1:])]


def edge_face_counts(faces: np.ndarray) -> Dict[Edge, List[int]]:
    """Map each edge to the faces that use it."""
    usage: Dict[Edge, List[int]] = {}
    for index, row in enumerate(undirected_edges(faces)):
        for left, right in row:
            usage.setdefault((int(left), int(right)), []).append(index)
    return usage


def selection_boundary(faces: np.ndarray, selected) -> List[Edge]:
    """Edges with exactly one selected face: the border of the chosen region.

    An edge of the open mesh also counts when its one face is selected, which
    is the whole point of computing the count instead of reading the mesh's own
    border flag.
    """
    chosen = np.asarray(selected, dtype=bool).ravel()
    tris = np.asarray(faces, dtype=np.int64).reshape(-1, 3)
    if chosen.size != tris.shape[0]:
        raise ValueError(f"selection covers {chosen.size} faces, "
                         f"the mesh has {tris.shape[0]}")
    if not chosen.any():
        return []

    boundary = []
    for edge, users in edge_face_counts(tris).items():
        if sum(1 for face in users if chosen[face]) == 1:
            boundary.append(edge)
    return sorted(boundary)


def plane_offset(points: np.ndarray, origin: np.ndarray, normal: np.ndarray) -> np.ndarray:
    """Signed distance from a plane, positive on the side the normal points to."""
    data = np.asarray(points, dtype=np.float64).reshape(-1, 2)
    base = np.asarray(origin, dtype=np.float64).ravel()[:2]
    direction = np.asarray(normal, dtype=np.float64).ravel()[:2]
    return (data - base) @ direction


def nearest_plane_chain(faces: np.ndarray, positions: np.ndarray, origin, normal,
                        tolerance: float) -> List[Edge]:
    """Existing edges that sit within a tolerance of a reference plane.

    Nothing is cut and nothing is projected: the tool only points out edges the
    user can then confirm, which is what the spec's "near" means.
    """
    direction = np.asarray(normal, dtype=np.float64).ravel()[:2]
    if float(np.linalg.norm(direction)) == 0.0:
        raise ValueError("a plane needs a direction; the given normal has no length")
    points = np.asarray(positions, dtype=np.float64).reshape(-1, 2)
    edges = undirected_edges(faces).reshape(-1, 2)

    midpoints = points[edges].mean(axis=1)
    distance = np.abs(plane_offset(midpoints, origin, direction))
    return sorted({(int(a), int(b)) for a, b, keep in
                   zip(edges[:, 0], edges[:, 1], distance <= tolerance) if keep})


@dataclass(frozen=True)
class ContourProposal:
    """What the view tool can and cannot tell the user.

    ``silhouette`` is where two faces genuinely face opposite ways. ``undecided``
    is the open border: with one face there is nothing to compare against, so
    it is neither a hit nor a miss, and lumping it in with the silhouette would
    be a claim the normals cannot support.
    """

    silhouette: List[Edge]
    undecided: List[Edge]
    notes: Dict[Edge, str]


def view_contour(faces: np.ndarray, face_normals: np.ndarray,
                 view_direction: np.ndarray) -> ContourProposal:
    """Silhouette candidates from face normals, and what is still unknown.

    A face whose normal points back at the viewer next to one that points away
    marks a silhouette. Visibility is a separate question this cannot answer,
    so every candidate carries that caveat.
    """
    normals = np.asarray(face_normals, dtype=np.float64).reshape(-1, 3)
    tris = np.asarray(faces, dtype=np.int64).reshape(-1, 3)
    if normals.shape[0] != tris.shape[0]:
        raise ValueError(f"got {normals.shape[0]} normals for {tris.shape[0]} faces")
    eye = np.asarray(view_direction, dtype=np.float64).ravel()[:3]
    if float(np.linalg.norm(eye)) == 0.0:
        raise ValueError("a view direction of zero length has no eye to look from")
    facing = normals @ eye

    silhouette: List[Edge] = []
    undecided: List[Edge] = []
    notes: Dict[Edge, str] = {}
    for edge, users in sorted(edge_face_counts(tris).items()):
        if len(users) < 2:
            undecided.append(edge)
            notes[edge] = ("single_face: no neighbour to compare against, so this "
                           "is neither a silhouette nor a ruled-out edge")
            continue
        first, second = (float(facing[users[0]]), float(facing[users[1]]))
        if first * second < 0.0:
            silhouette.append(edge)
            notes[edge] = ("faces_face_opposite_ways: silhouette candidate, "
                           "occlusion unverified")
    return ContourProposal(silhouette, undecided, notes)


def runs_of(edges: Sequence[Edge]) -> List[List[Edge]]:
    """Split a loose set of edges into connected runs, for display and for apply.

    A user marking several contours should get several seams, not one seam that
    teleports across the mesh between them.
    """
    links: Dict[int, List[int]] = {}
    for left, right in edges:
        links.setdefault(left, []).append(right)
        links.setdefault(right, []).append(left)

    unused = {(int(a), int(b)) for a, b in edges}
    runs: List[List[Edge]] = []
    while unused:
        seed = min(unused)
        stack = [seed[0]]
        component: List[Edge] = []
        while stack:
            vertex = stack.pop()
            touching = [e for e in unused if vertex in e]
            for edge in touching:
                unused.discard(edge)
                component.append(edge)
                stack.append(edge[0] if edge[1] == vertex else edge[1])
        runs.append(sorted(component))
    return runs
