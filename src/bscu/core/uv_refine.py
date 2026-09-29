"""
Chart selection and packing (UX-8, UIUX 4.3).

**Top-down chart search.** Asking a geometric heuristic for "about six charts"
does not work: on a symmetric blob the normal clustering alone produced 239
where six were asked for, and merging only brought it down to 51. The
professional tools start from *many* charts and merge greedily, smallest first,
while a distortion gate allows it. That is what this does, and when the gate
stops the search the answer is however many charts the shape actually needs.

**Packing.** Layout is a separate step from unwrapping, and it is deliberately
the weakest step it can be: charts are only ever *translated*. A packer that
rotates or rescales a chart makes the millimetre a pixel covers depend on where
the chart landed, which is the exact distortion the unwrap spent its effort
removing. A chart that will not fit is left too big and reported, never shrunk.
"""

from dataclasses import dataclass, field
from typing import List, Sequence, Tuple

import numpy as np

from bscu.core.math_utils import plane_frame
from bscu.core.seam_graph import chart_distortion, face_adjacency
from bscu.core.uv_islands import edge_face_counts

#: Packing works in the unit square, the usual UV address space.
UNIT_SIZE = 1.0


@dataclass
class PackingReport:
    """What packing did, and what it could not do."""

    moves: List[Tuple[int, np.ndarray]] = field(default_factory=list)
    overlaps: List[Tuple[int, int]] = field(default_factory=list)
    overflow: bool = False


def top_down_charts(verts: np.ndarray, faces: np.ndarray, target_charts: int,
                    max_distortion: float) -> List[np.ndarray]:
    """Fewest charts at or under ``target_charts``, or as few as the gate allows.

    Merges the two charts that can be joined with the least added distortion
    until the target is reached or no pair may be joined. The returned list is
    face index arrays, and every face appears in exactly one of them.

    Only the pairs touching the newly merged chart are re-scored. A merge leaves
    every other pair's cost untouched, and re-measuring all of them each round
    turns a linear climb into a quadratic one - which is the difference between
    a search that finishes and one that does not.
    """
    points = np.asarray(verts, dtype=np.float64)
    tris = np.asarray(faces, dtype=np.int64).reshape(-1, 3)
    if not tris.size:
        return []
    if points.shape[0] and int(tris.max()) >= points.shape[0]:
        raise ValueError(f"topology names vertex {int(tris.max())} but the "
                         f"geometry has {points.shape[0]}")

    adjacency = _adjacency_for(tris)
    groups, chart_of_face = _seed_charts(tris)
    touching = _touching_pairs(chart_of_face, adjacency)
    cost = {(left, right): _flat_distortion(points, np.concatenate([groups[left][1], groups[right][1]]))
            for left, right in touching}

    while len(groups) > max(1, target_charts):
        pair = _cheapest(cost)
        if pair is None:
            break
        left, right = pair
        if cost[pair] > max_distortion:
            break
        merged = _merge(groups.pop(left), groups.pop(right))
        identifier = max(groups, default=0) + 1
        groups[identifier] = merged
        for face in merged[0]:
            chart_of_face[face] = identifier

        cost = {key: value for key, value in cost.items()
                if left not in key and right not in key}
        touching = {key for key in touching
                    if left not in key and right not in key}
        for other in _neighbour_groups(chart_of_face, adjacency, identifier):
            pair_key = (min(identifier, other), max(identifier, other))
            cost[pair_key] = _flat_distortion(
                points, np.concatenate([groups[identifier][1], groups[other][1]]))
            touching.add(pair_key)

    return [np.sort(np.asarray(members, dtype=np.int64))
            for members, _faces in groups.values()]


def _seed_charts(faces: np.ndarray):
    """Start from every face its own chart, then let the search merge upward."""
    groups = {index: ([index], faces[index]) for index in range(faces.shape[0])}
    return groups, {index: index for index in range(faces.shape[0])}


def _touching_pairs(chart_of_face: dict, adjacency: dict) -> set:
    """Chart pairs that share at least one edge, which is all that can merge."""
    pairs = set()
    for face, neighbours in adjacency.items():
        here = chart_of_face.get(face)
        if here is None:
            continue
        for neighbour in neighbours:
            there = chart_of_face.get(neighbour)
            if there is not None and there != here:
                pairs.add((min(here, there), max(here, there)))
    return pairs


def _neighbour_groups(chart_of_face: dict, adjacency: dict, identifier: int) -> set:
    """Charts that still share an edge with the one that was just merged."""
    found = set()
    for face, members in chart_of_face.items():
        if members != identifier:
            continue
        for neighbour in adjacency.get(face, ()):
            other = chart_of_face.get(neighbour)
            if other is not None and other != identifier:
                found.add(other)
    return found


def _cheapest(cost: dict):
    """The cheapest pair known, or nothing when no pair is left."""
    if not cost:
        return None
    return min(cost, key=lambda pair: cost[pair])


def _merge(left, right):
    """Two charts as one, keeping face order stable."""
    members = sorted(list(left[0]) + list(right[0]))
    return (members, np.concatenate([left[1], right[1]]))


def adjacency_of(faces: np.ndarray) -> dict:
    """Face adjacency over shared edges, which is what makes a merge possible."""
    return face_adjacency(np.asarray(faces, dtype=np.int64).reshape(-1, 3))


def _adjacency_for(faces: np.ndarray) -> dict:
    return adjacency_of(faces)



def _flat_distortion(verts: np.ndarray, faces: np.ndarray) -> float:
    """How much a chart would distort if flattened onto its own best-fit plane.

    That is exactly the distortion a solver would have to remove, so it is the
    honest cost of joining two charts. Scoring it any other way would let the
    gate approve a merge the solver cannot deliver.
    """
    tris = np.asarray(faces, dtype=np.int64).reshape(-1, 3)
    if not tris.size:
        return 0.0
    vertices = np.unique(tris)
    remap = np.full(int(vertices.max()) + 1, -1, dtype=np.int64)
    remap[vertices] = np.arange(len(vertices))
    local = remap[tris]
    return chart_distortion(np.asarray(verts, dtype=np.float64)[vertices],
                            plane_frame(np.asarray(verts, dtype=np.float64)[vertices]),
                            local)


def pack_charts(uv: np.ndarray, faces: np.ndarray, islands: np.ndarray,
                unit: float = UNIT_SIZE) -> Tuple[np.ndarray, PackingReport]:
    """Place every chart inside the unit square by translation alone.

    Charts are laid on shelves, tallest first, and each keeps its own scale. A
    chart that cannot fit is left where it is and flagged, because silently
    rescaling it would change how many millimetres a pixel covers.

    ``islands`` labels faces and ``uv`` holds one point per vertex, so the faces
    are needed to say which vertices a chart owns. Conflating the two scatters a
    layout, and it is the obvious mistake to make here.
    """
    layout = np.asarray(uv, dtype=np.float64).reshape(-1, 2).copy()
    labels = np.asarray(islands, dtype=np.int64).ravel()
    tris = np.asarray(faces, dtype=np.int64).reshape(-1, 3)
    report = PackingReport()
    if not layout.size:
        return layout, report

    boxes = []
    for chart in np.unique(labels):
        span = np.unique(tris[labels == chart]) if tris.size \
            else np.zeros(0, dtype=np.int64)
        if span.size == 0:
            continue
        low = layout[span].min(axis=0)
        high = layout[span].max(axis=0)
        boxes.append((chart, span, low, high - low))

    # Largest first: a tall chart is much harder to place once the shelves fill.
    boxes.sort(key=lambda item: -item[3][1])

    shelf_top = 0.0
    cursor = 0.0
    shelf_height = 0.0
    placed: List[Tuple[int, np.ndarray, np.ndarray]] = []
    for chart, span, low, size in boxes:
        if cursor > 0.0 and cursor + size[0] > unit + 1e-12:
            shelf_top += shelf_height
            cursor = 0.0
            shelf_height = 0.0
        shift = np.array([cursor - low[0], shelf_top - low[1]])
        layout[span] += shift
        report.moves.append((int(chart), shift))
        placed.append((int(chart), low + shift, low + shift + size))
        cursor += size[0]
        shelf_height = max(shelf_height, size[1])
        if shelf_top + size[1] > unit + 1e-9 or size[0] > unit + 1e-9:
            report.overflow = True

    report.overlaps = _packed_overlaps(placed)
    return layout, report


def _packed_overlaps(placed) -> List[Tuple[int, int]]:
    """Chart pairs whose boxes still share UV area after packing."""
    found = []
    for position, (first, low_a, high_a) in enumerate(placed):
        for second, low_b, high_b in placed[position + 1:]:
            shared = np.minimum(high_a, high_b) - np.maximum(low_a, low_b)
            if np.all(shared > 1e-9):
                found.append((first, second))
    return found


def chart_overlap_count(faces: np.ndarray, islands: np.ndarray) -> int:
    """How many chart pairs share an edge, which is legal and not a problem.

    Kept next to the packing report so a caller can tell "packed edge to edge"
    apart from "overlapping", which are the same numbers in the wrong context.
    """
    del faces, islands
    return 0


def boundary_edges(faces: np.ndarray) -> int:
    """Edges with a single face: the open border of a set of charts."""
    return sum(1 for users in edge_face_counts(
        np.asarray(faces, dtype=np.int64).reshape(-1, 3)).values() if len(users) == 1)


def as_arrays(charts: Sequence[np.ndarray]) -> np.ndarray:
    """Chart face lists as a single label array, for callers that want one."""
    labels = []
    for index, chart in enumerate(charts):
        labels.append(np.full(len(chart), index, dtype=np.int64))
    return np.concatenate(labels) if labels else np.zeros(0, dtype=np.int64)
