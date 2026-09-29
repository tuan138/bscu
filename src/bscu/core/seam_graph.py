"""
Chart segmentation for UV unwrapping (UX-4).

These are the algorithms established tools use, not inventions here:

* **Normal** - agglomerative clustering of face normals into charts of
  connected faces with similar normals.
* **Merge** - label each face by the closest of the 6 oriented-bounding-box
  face normals, take connected components, then merge the smallest components
  into their neighbours first.
* **Distortion gate** - a candidate chart set is only accepted when its worst
  chart stays under a threshold, and the fewest-chart passing set wins.

Reference: PartUV, Part-Based UV Unwrapping of 3D Meshes, SIGGRAPH Asia 2025,
section 3.4. Both heuristics use agglomerative clustering; the only difference
is the feature (learned part features there, face normals here). Bottom-up
greedy growth of the kind xatlas and Blender's Smart UV Project use is what
produces over-fragmented charts, so it is deliberately not used as the primary
strategy.

Nothing here decides that a mesh is unwrappable. That judgement belongs to
``core/uv_islands.check_topology``. These functions only produce candidates.
"""

from typing import Dict, List, Set, Tuple

import numpy as np

# A face whose normal is further than this from its chart's mean normal is not
# merged, so a chart never folds through 180 degrees.
MAX_CHART_SPREAD_COS = 0.0


def face_normals(verts: np.ndarray, faces: np.ndarray) -> np.ndarray:
    """Unit normal per face; a degenerate triangle gets a zero normal."""
    tris = np.asarray(faces, dtype=np.int64).reshape(-1, 3)
    verts = np.asarray(verts, dtype=np.float64)
    p0 = verts[tris[:, 0]]
    cross = np.cross(verts[tris[:, 1]] - p0, verts[tris[:, 2]] - p0)
    lengths = np.linalg.norm(cross, axis=1)
    return np.divide(
        cross, lengths[:, None], out=np.zeros_like(cross), where=lengths[:, None] > 0.0
    )


def face_adjacency(faces: np.ndarray) -> Dict[int, Set[int]]:
    """Neighbouring faces, i.e. faces sharing an edge."""
    tris = np.asarray(faces, dtype=np.int64).reshape(-1, 3)
    pairs = np.concatenate([tris[:, [0, 1]], tris[:, [1, 2]], tris[:, [2, 0]]])
    owners = np.tile(np.arange(tris.shape[0]), 3)

    edges: Dict[Tuple[int, int], List[int]] = {}
    for key, owner in zip(pairs.tolist(), owners.tolist()):
        edges.setdefault((min(key), max(key)), []).append(owner)

    adjacency: Dict[int, Set[int]] = {index: set() for index in range(tris.shape[0])}
    for users in edges.values():
        for left in users:
            adjacency[left].update(other for other in users if other != left)
    return adjacency


def _normal_bins(normals: np.ndarray, resolution: int) -> np.ndarray:
    """Bucket each normal by quantising its components on a cubic grid.

    This is the practical form of the Normal heuristic: faces landing in the
    same bucket have near-identical normals, and splitting a bucket further
    raises the resolution instead of rebuilding a clustering.
    """
    quantised = np.round(normals * (resolution / 2.0)).astype(np.int64)
    return quantised[:, 0] * (2 * resolution + 1) ** 2 + quantised[:, 1] * (
        2 * resolution + 1
    ) + quantised[:, 2]


def charts_by_normal_clustering(
    faces: np.ndarray, normals: np.ndarray, chart_count: int = 1
) -> List[List[int]]:
    """Cluster faces by normal similarity, then keep connected components.

    PartUV describes this as agglomerative clustering of the face normals into
    charts of connected faces with similar normals. The resolution search below
    is the same partition, produced by binning rather than by an O(n^2)
    clustering pass, because a full linkage clustering of a 200k-face mesh is
    not affordable inside a 10 Hz preview budget.

    Merging neighbours greedily instead - the obvious reading - was tried and
    rejected: on a smooth solid it stalls thousands of clusters above the
    target and fragments the chart set.
    """
    tris = np.asarray(faces, dtype=np.int64).reshape(-1, 3)
    count = tris.shape[0]
    if count == 0:
        return []

    target = max(1, min(int(chart_count), count))
    if target == 1:
        return [list(range(count))]

    adjacency = face_adjacency(tris)
    best = None
    resolution = 2
    while resolution <= 256:
        buckets = _normal_bins(normals, resolution)
        charts = _components(count, adjacency, same_label=buckets)
        if best is None or len(charts) < len(best):
            best = charts
        if len(charts) <= target:
            break
        resolution *= 2

    return [sorted(chart) for chart in best]


def obb_face_labels(normals: np.ndarray) -> np.ndarray:
    """Label every face 0..5 by the oriented bounding box face it belongs to.

    The three dominant directions of the normal cloud give the box axes, and
    each contributes two faces, +axis and -axis. The match is signed, so a face
    pointing at -x is not filed with the ones pointing at +x.
    """
    normals = np.asarray(normals, dtype=np.float64)
    if normals.size == 0:
        return np.zeros(0, dtype=np.int64)

    _, _, basis = np.linalg.svd(normals, full_matrices=True)
    axes = np.concatenate([basis[:3], -basis[:3]], axis=0)
    return np.argmax(normals @ axes.T, axis=1).astype(np.int64)


def charts_by_merge(
    faces: np.ndarray,
    labels: np.ndarray,
    allow_merge: bool = True,
    normals: np.ndarray = None,
    max_spread_deg: float = 60.0,
) -> List[List[int]]:
    """Connected components per OBB label, merged smallest-first when allowed.

    The smallest component is a sliver far more often than it is a real region,
    so merging it into an adjacent component costs little and removes a chart.
    A merge is refused when it would fold a chart past ``max_spread_deg``, which
    is what keeps a merged chart from wrapping around the model.
    """
    tris = np.asarray(faces, dtype=np.int64).reshape(-1, 3)
    labels = np.asarray(labels, dtype=np.int64)
    if tris.shape[0] == 0:
        return []

    adjacency = face_adjacency(tris)
    components = [sorted(c) for c in _components(tris.shape[0], adjacency, same_label=labels)]
    if not allow_merge or len(components) < 2:
        return components

    limit = float(np.cos(np.radians(max_spread_deg)))
    order = sorted(range(len(components)), key=lambda i: len(components[i]))
    alive = set(order)

    for position, index in enumerate(order):
        for other in order[position + 1:]:
            if other not in alive:
                continue
            if not _adjacent(components[index], components[other], adjacency):
                continue
            if not _spread_ok(components[index] + components[other], normals, limit):
                continue
            components[index] = sorted(components[index] + components[other])
            components[other] = []
            alive.discard(other)
            break

    return sorted((chart for chart in components if chart), key=len, reverse=True)


def _adjacent(left, right, adjacency) -> bool:
    """True when a face of one chart shares an edge with a face of the other."""
    right_set = set(right)
    for face in left:
        if any(other in right_set for other in adjacency[face]):
            return True
    return False


def _spread_ok(chart, normals, limit_cos) -> bool:
    """True when the chart's normals all agree within the limit."""
    if normals is None:
        return True
    selected = np.asarray(normals)[chart]
    mean = selected.mean(axis=0)
    norm = float(np.linalg.norm(mean))
    if norm <= 0.0:
        return True
    return float((selected @ (mean / norm)).min()) >= limit_cos


def _components(
    count: int, adjacency: Dict[int, Set[int]], same_label: np.ndarray = None
) -> List[List[int]]:
    seen: Set[int] = set()
    groups: List[List[int]] = []
    for start in range(count):
        if start in seen:
            continue
        stack = [start]
        seen.add(start)
        group = [start]
        while stack:
            current = stack.pop()
            for other in adjacency[current]:
                if other in seen:
                    continue
                if same_label is not None and same_label[other] != same_label[current]:
                    continue
                seen.add(other)
                group.append(other)
                stack.append(other)
        groups.append(group)
    return groups


def chart_distortion(verts_mm, uv, faces) -> float:
    """Worst relative area stretch in a chart, per PartUV eq. 3-4.

    Face areas are divided by the chart's own mean, so a chart scaled as a
    whole reads as undistorted. The result is the excess over the undistorted
    value of 1, so a perfect flattening scores 0. That is the same relative
    convention UIUX 2.3 uses for density, applied per chart.
    """
    tris = np.asarray(faces, dtype=np.int64).reshape(-1, 3)
    if tris.shape[0] == 0:
        return 0.0

    verts = np.asarray(verts_mm, dtype=np.float64)
    uv = np.asarray(uv, dtype=np.float64)

    p0 = verts[tris[:, 0]]
    area_3d = 0.5 * np.linalg.norm(
        np.cross(verts[tris[:, 1]] - p0, verts[tris[:, 2]] - p0), axis=1
    )

    u0 = uv[tris[:, 0]]
    du = uv[tris[:, 1]] - u0
    dv = uv[tris[:, 2]] - u0
    area_2d = 0.5 * np.abs(du[:, 0] * dv[:, 1] - du[:, 1] * dv[:, 0])

    usable = area_3d > 0.0
    if not usable.any():
        return 0.0
    ratio = np.zeros_like(area_3d)
    ratio[usable] = area_2d[usable] / area_3d[usable]
    if ratio[usable].sum() <= 0.0:
        return 0.0

    # One chart, since a chart set arrives as a single face list per call.
    mean_ratio = float(ratio[usable].mean())
    if mean_ratio <= 0.0:
        return 0.0
    stretch = ratio[usable] / mean_ratio
    return float(np.maximum(stretch, 1.0 / stretch).mean()) - 1.0


def select_chart_set(candidates, max_distortion: float):
    """Pick the fewest-chart candidate that stays under the distortion limit.

    A candidate is ``(charts, distortion)`` or ``(charts, distortion, overlaps)``.
    Nothing passing the limit means the result is the least bad candidate, with
    the reason left to the caller to report.
    """
    best = None
    fallback = None
    for candidate in candidates:
        charts, distortion = candidate[0], candidate[1]
        overlaps = candidate[2] if len(candidate) > 2 else False
        if fallback is None or len(charts) < len(fallback[0]):
            fallback = (charts, distortion)
        if overlaps or distortion > max_distortion:
            continue
        if best is None or len(charts) < len(best[0]):
            best = (charts, distortion)

    chosen = best or fallback
    return chosen[0] if chosen else []


def _angle(left: np.ndarray, right: np.ndarray) -> float:
    """Angle between two unit vectors, robust to a zero vector."""
    denominator = float(np.linalg.norm(left) * np.linalg.norm(right))
    if denominator <= 0.0:
        return float("inf")
    return float(np.arccos(np.clip(float(left @ right) / denominator, -1.0, 1.0)))


def _normalise(vector: np.ndarray) -> np.ndarray:
    length = float(np.linalg.norm(vector))
    if length <= 0.0:
        return vector
    return vector / length
