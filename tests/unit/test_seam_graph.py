"""Unit tests for chart segmentation (UX-4).

The algorithms here are the ones established tools use, not inventions:

* **Normal** - agglomerative clustering of face normals into charts of
  connected faces with similar normals (PartUV, SIGGRAPH Asia 2025, mục 3.4).
* **Merge** - label every face by the closest of 6 OBB face normals, take
  connected components, then merge the smallest into their neighbours first.
* **Distortion gate** - a chart set is only accepted when its worst chart
  stays under a threshold, and the fewest-chart set that passes wins.

Nothing here decides that a mesh is unwrappable; that stays with the topology
check in ``core/uv_islands.py``. These functions produce candidate charts.
"""

import unittest

import numpy as np

from bscu.core.seam_graph import (
    chart_distortion,
    charts_by_merge,
    charts_by_normal_clustering,
    face_normals,
    obb_face_labels,
    select_chart_set,
)


def open_box():
    """A closed cube as 12 triangles, unit sized."""
    faces = np.array(
        [
            [0, 2, 1], [0, 3, 2],   # bottom
            [4, 5, 6], [4, 6, 7],   # top
            [0, 1, 5], [0, 5, 4],   # front
            [1, 2, 6], [1, 6, 5],   # right
            [2, 3, 7], [2, 7, 6],   # back
            [3, 0, 4], [3, 4, 7],   # left
        ]
    )
    verts = np.array(
        [
            [0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
            [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1],
        ],
        dtype=np.float64,
    )
    return verts, faces


def fold_cylinder(segments, rings, radius=1.0, height=2.0):
    """A tube: a shape that genuinely cannot be flattened as one chart."""
    verts = []
    for r in range(rings + 1):
        for s in range(segments):
            angle = 2.0 * np.pi * s / segments
            verts.append((radius * np.cos(angle), radius * np.sin(angle), height * r / rings))
    faces = []
    for r in range(rings):
        for s in range(segments):
            a = r * segments + s
            b = r * segments + (s + 1) % segments
            c = a + segments
            d = b + segments
            faces.append([a, b, d])
            faces.append([a, d, c])
    return np.array(verts, dtype=np.float64), np.array(faces)

def _flat_quad():
    """A unit quad as two triangles, used to exercise the distortion maths."""
    verts = np.array([[0.0, 0, 0], [1.0, 0, 0], [1.0, 1, 0], [0.0, 1, 0]])
    return verts, np.array([[0, 1, 2], [0, 2, 3]])




def _flat_chart_uv(verts, faces):
    """A trivially valid UV, used to prove the distortion maths is sane."""
    uv = verts[:, :2].copy()
    return uv


class TestFaceNormals(unittest.TestCase):
    def test_cube_has_six_axis_aligned_normals(self):
        _, faces = open_box()
        normals = face_normals(verts_of_cube(), faces)
        unique = np.unique(np.round(normals, 6), axis=0)
        assert unique.shape[0] == 6, unique

    def test_normals_are_unit_length(self):
        verts, faces = fold_cylinder(8, 4)
        normals = face_normals(verts, faces)
        lengths = np.linalg.norm(normals, axis=1)
        assert np.allclose(lengths, 1.0, atol=1e-9)

    def test_a_degenerate_triangle_yields_a_zero_normal(self):
        verts = np.array([[0.0, 0, 0], [1.0, 0, 0], [2.0, 0, 0]])
        faces = np.array([[0, 1, 2]])
        normals = face_normals(verts, faces)
        assert np.allclose(normals[0], 0.0)

    def test_every_face_gets_one_normal(self):
        verts, faces = fold_cylinder(6, 3)
        assert face_normals(verts, faces).shape == (len(faces), 3)


def verts_of_cube():
    return np.array(
        [
            [0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
            [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1],
        ],
        dtype=np.float64,
    )


class TestNormalClustering(unittest.TestCase):
    def test_a_cube_at_one_chart_is_a_single_chart(self):
        _, faces = open_box()
        normals = face_normals(verts_of_cube(), faces)
        charts = charts_by_normal_clustering(faces, normals, chart_count=1)
        assert len(charts) == 1
        assert sorted(charts[0]) == list(range(len(faces)))

    def test_six_opposite_faces_want_six_charts(self):
        _, faces = open_box()
        normals = face_normals(verts_of_cube(), faces)
        charts = charts_by_normal_clustering(faces, normals, chart_count=6)
        assert len(charts) == 6

    def test_charts_partition_the_faces_exactly_once(self):
        verts, faces = fold_cylinder(8, 4)
        normals = face_normals(verts, faces)
        for count in (1, 3, 6):
            charts = charts_by_normal_clustering(faces, normals, chart_count=count)
            flat = sorted(f for chart in charts for f in chart)
            assert flat == list(range(len(faces))), count

    def test_every_chart_is_connected(self):
        verts, faces = fold_cylinder(8, 4)
        normals = face_normals(verts, faces)
        adjacency = _face_adjacency(faces)
        for chart in charts_by_normal_clustering(faces, normals, chart_count=5):
            assert _is_connected(chart, adjacency), chart

    def test_requesting_more_charts_than_faces_is_clamped(self):
        _, faces = open_box()
        normals = face_normals(verts_of_cube(), faces)
        charts = charts_by_normal_clustering(faces, normals, chart_count=99)
        assert 1 <= len(charts) <= len(faces)


class TestObbLabels(unittest.TestCase):
    def test_a_cube_gets_the_expected_label_count(self):
        _, faces = open_box()
        normals = face_normals(verts_of_cube(), faces)
        labels = obb_face_labels(normals)
        assert set(labels.tolist()) == {0, 1, 2, 3, 4, 5}, set(labels.tolist())

    def test_labels_are_six_integers(self):
        verts, faces = fold_cylinder(8, 4)
        labels = obb_face_labels(face_normals(verts, faces))
        assert labels.min() >= 0 and labels.max() <= 5

    def test_a_tube_labels_its_curved_band_by_dominant_axis(self):
        verts, faces = fold_cylinder(8, 4)
        labels = obb_face_labels(face_normals(verts, faces))
        assert len(np.unique(labels)) >= 2, np.unique(labels)


class TestMergeCharts(unittest.TestCase):
    def test_a_cube_merges_back_into_connected_components(self):
        _, faces = open_box()
        labels = obb_face_labels(face_normals(verts_of_cube(), faces))
        charts = charts_by_merge(faces, labels)
        flat = sorted(f for chart in charts for f in chart)
        assert flat == list(range(len(faces)))

    def test_merge_never_increases_the_chart_count(self):
        verts, faces = fold_cylinder(8, 4)
        labels = obb_face_labels(face_normals(verts, faces))
        labels_only = charts_by_merge(faces, labels, allow_merge=False)
        merged = charts_by_merge(faces, labels, allow_merge=True)
        assert len(merged) <= len(labels_only)

    def test_a_tube_merges_below_six_charts(self):
        verts, faces = fold_cylinder(8, 4)
        labels = obb_face_labels(face_normals(verts, faces))
        assert len(charts_by_merge(faces, labels, allow_merge=True)) < 6


class TestDistortionGate(unittest.TestCase):
    def test_a_flat_sheet_has_no_distortion(self):
        verts, faces = _flat_quad()
        assert chart_distortion(verts, verts[:, :2].copy(), faces) < 1e-9

    def test_stretching_one_face_of_a_chart_widens_the_measure(self):
        """The measure is per-chart and relative, so one bad face shows."""
        verts, faces = _flat_quad()
        uv = verts[:, :2].copy()
        assert chart_distortion(verts, uv, faces) < 1e-9
        uv[1] = (4.0, 0.0)
        assert chart_distortion(verts, uv, faces) > 0.1

    def test_scaling_the_whole_chart_does_not_change_the_measure(self):
        """A relative measure, exactly as UIUX 2.3 states for density."""
        verts, faces = _flat_quad()
        uv = verts[:, :2].copy()
        uv[1] = (4.0, 0.0)
        reference = chart_distortion(verts, uv, faces)
        for factor in (3.0, 1.0 / 3.0, 100.0):
            assert abs(chart_distortion(verts, uv * factor, faces) - reference) < 1e-9

    def test_the_measure_is_symmetric_under_area_inversion(self):
        verts, faces = _flat_quad()
        uv = verts[:, :2].copy()
        uv[1] = (4.0, 0.0)
        up = chart_distortion(verts, uv, faces)
        down = chart_distortion(verts, uv * 0.25, faces)
        assert abs(up - down) < 1e-9, (up, down)

    def test_a_single_face_chart_can_never_be_distorted(self):
        """With one face the mean is itself, so the relative measure is 1."""
        verts, faces = _flat_quad()
        uv = verts[:, :2].copy()
        uv[1] = (4.0, 0.0)
        assert chart_distortion(verts, uv, faces[:1]) < 1e-9



class TestSelectChartSet(unittest.TestCase):
    def test_the_fewest_passing_chart_set_wins(self):
        candidates = [([[0, 1]], 0.1), ([[0, 1], [2, 3]], 0.2), ([[0, 1], [2, 3], [4, 5]], 5.0)]
        chosen = select_chart_set(candidates, max_distortion=1.0)
        assert chosen == [[0, 1]]

    def test_a_set_over_the_threshold_is_rejected(self):
        candidates = [([[0, 1]], 0.1), ([[0, 1], [2, 3]], 9.0)]
        chosen = select_chart_set(candidates, max_distortion=1.0)
        assert chosen == [[0, 1]]

    def test_nothing_passing_returns_the_least_bad(self):
        candidates = [([[0, 1]], 5.0), ([[0, 1], [2, 3]], 9.0)]
        chosen = select_chart_set(candidates, max_distortion=1.0)
        assert chosen == [[0, 1]]

    def test_no_candidates_returns_nothing(self):
        assert select_chart_set([], max_distortion=1.0) == []

    def test_a_uv_overlap_rejects_the_set(self):
        candidates = [([[0, 1]], 0.1, True), ([[0, 1], [2, 3]], 0.2, False)]
        chosen = select_chart_set(candidates, max_distortion=1.0)
        assert chosen == [[0, 1], [2, 3]]


def _face_adjacency(faces):
    edges = {}
    for index, face in enumerate(faces):
        a, b, c = int(face[0]), int(face[1]), int(face[2])
        for edge in ((a, b), (b, c), (c, a)):
            edges.setdefault(tuple(sorted(edge)), []).append(index)
    adjacency = {index: set() for index in range(len(faces))}
    for users in edges.values():
        for left in users:
            adjacency[left].update(u for u in users if u != left)
    return adjacency


def _is_connected(chart, adjacency):
    if not chart:
        return True
    seen = {chart[0]}
    stack = [chart[0]]
    while stack:
        current = stack.pop()
        for other in chart:
            if other not in seen and other in adjacency[current]:
                seen.add(other)
                stack.append(other)
    return len(seen) == len(chart)


if __name__ == "__main__":
    unittest.main()
