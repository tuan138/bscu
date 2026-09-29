"""Unit tests for island extraction and seam topology checks (UX-1, UIUX 2.4/3.7).

The spec is explicit that open boundaries and a valid seam endpoint are not the
same thing: an open mesh is a legitimate design base, and a seam ending on a
valence-1 vertex must not be reported as an error.
"""

import unittest

import numpy as np

from bscu.core.uv_islands import (
    TopologyReport,
    build_edge_faces,
    check_topology,
    extract_islands,
    island_face_counts,
    seam_endpoint_vertices,
)

# A strip of four triangles sharing edges through vertex 1.
STRIP_FACES = np.array([[0, 1, 2], [1, 3, 2], [1, 4, 3], [1, 5, 4]])


def quad_faces():
    """Two disjoint quads: verts 0-3 and 4-7."""
    return np.array([[0, 1, 2], [0, 2, 3], [4, 5, 6], [4, 6, 7]])


def cube_faces():
    """Closed cube as 12 triangles."""
    quads = [
        (0, 1, 2, 3), (4, 5, 6, 7), (0, 1, 5, 4),
        (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7),
    ]
    faces = []
    for a, b, c, d in quads:
        faces.append([a, b, c])
        faces.append([a, c, d])
    return np.array(faces)


class TestIslandExtraction(unittest.TestCase):
    def test_disconnected_quads_are_two_islands(self):
        islands = extract_islands(quad_faces(), [])
        self.assertEqual(sorted(set(islands.tolist())), [0, 1])
        self.assertEqual(island_face_counts(islands), [2, 2])

    def test_no_seams_means_one_island(self):
        islands = extract_islands(np.array([[0, 1, 2], [0, 2, 3]]), [])
        self.assertEqual(sorted(set(islands.tolist())), [0])

    def test_a_single_seam_cuts_a_strip_in_two(self):
        islands = extract_islands(STRIP_FACES, [(1, 3)])
        self.assertEqual(sorted(set(islands.tolist())), [0, 1])

    def test_two_seams_cut_a_strip_in_three(self):
        islands = extract_islands(STRIP_FACES, [(1, 3), (1, 4)])
        self.assertEqual(sorted(set(islands.tolist())), [0, 1, 2])

    def test_island_ids_are_dense_in_first_seen_order(self):
        islands = extract_islands(np.array([[0, 1, 2], [5, 6, 7], [8, 9, 10]]), [])
        self.assertEqual(sorted(set(islands.tolist())), [0, 1, 2])
        self.assertEqual(island_face_counts(islands), [1, 1, 1])

    def test_empty_input_gives_no_islands(self):
        islands = extract_islands(np.zeros((0, 3), dtype=int), [])
        self.assertEqual(len(islands), 0)
        self.assertEqual(island_face_counts(islands), [])

    def test_seam_edge_matching_a_pair_of_faces_splits_them(self):
        faces = np.array([[0, 1, 2], [1, 0, 5]])
        joined = extract_islands(faces, [])
        cut = extract_islands(faces, [(0, 1)])
        self.assertEqual(len(set(joined.tolist())), 1)
        self.assertEqual(len(set(cut.tolist())), 2)

    def test_a_seam_no_face_uses_does_not_invent_islands(self):
        islands = extract_islands(np.array([[0, 1, 2], [0, 2, 3]]), [(0, 9)])
        self.assertEqual(sorted(set(islands.tolist())), [0])


class TestSeamEndpoints(unittest.TestCase):
    def test_open_seam_path_has_two_endpoints(self):
        path = np.array([[0, 1], [1, 2]])
        self.assertEqual(sorted(seam_endpoint_vertices(path, path, 3).tolist()), [0, 2])

    def test_closed_seam_loop_has_no_endpoints(self):
        loop = np.array([[0, 1], [1, 2], [2, 3], [3, 0]])
        self.assertEqual(seam_endpoint_vertices(loop, loop, 4).size, 0)

    def test_no_seams_means_no_endpoints(self):
        loop = np.array([[0, 1], [1, 2]])
        self.assertEqual(seam_endpoint_vertices(loop, np.zeros((0, 2), int), 3).size, 0)

    def test_junctions_are_not_endpoints(self):
        # A closed loop plus a chord: vertices 0 and 1 reach valence 4 and 3,
        # yet no seam edge dangles.
        seam = np.array([[0, 1], [1, 2], [2, 0], [0, 3], [3, 1]])
        self.assertEqual(seam_endpoint_vertices(seam, seam, 4).size, 0)

    def test_t_shape_keeps_its_three_free_ends(self):
        seam = np.array([[0, 1], [0, 2], [0, 3]])
        self.assertEqual(sorted(seam_endpoint_vertices(seam, seam, 4).tolist()), [1, 2, 3])


class TestTopologyReport(unittest.TestCase):
    def test_open_quad_is_a_valid_design_base(self):
        faces = quad_faces()
        report = check_topology(faces, build_edge_faces(faces))
        assert isinstance(report, TopologyReport)
        self.assertEqual(report.blocking_codes, ())
        self.assertTrue(report.has_open_boundary)
        self.assertTrue(report.is_mappable)

    def test_closed_cube_reports_no_boundary(self):
        faces = cube_faces()
        report = check_topology(faces, build_edge_faces(faces))
        self.assertEqual(report.blocking_codes, ())
        self.assertFalse(report.has_open_boundary)
        self.assertEqual(report.boundary_edges, 0)

    def test_non_manifold_edge_blocks(self):
        faces = np.array([[0, 1, 2], [0, 1, 3], [0, 1, 4]])
        report = check_topology(faces, build_edge_faces(faces))
        self.assertIn("NON_MANIFOLD_EDGE", report.blocking_codes)
        self.assertEqual(report.non_manifold_edges, 1)
        self.assertFalse(report.is_mappable)

    def test_duplicate_face_blocks(self):
        faces = np.array([[0, 1, 2], [2, 1, 0]])
        report = check_topology(faces, build_edge_faces(faces))
        self.assertIn("DUPLICATE_FACE", report.blocking_codes)

    def test_repeated_vertex_in_a_face_blocks(self):
        faces = np.array([[0, 1, 1]])
        report = check_topology(faces, build_edge_faces(faces))
        self.assertIn("REPEATED_VERTEX", report.blocking_codes)

    def test_boundary_edges_are_counted_but_not_blocking(self):
        faces = np.array([[0, 1, 2], [0, 2, 3]])
        report = check_topology(faces, build_edge_faces(faces))
        self.assertTrue(report.has_open_boundary)
        self.assertEqual(report.boundary_edges, 4)
        self.assertEqual(report.blocking_codes, ())

    def test_a_valence_one_vertex_alone_is_never_an_error(self):
        """UIUX 3.7: vertex valence 1 alone must not raise an error."""
        faces = np.array([[0, 1, 2], [0, 2, 3], [0, 4, 5]])
        report = check_topology(faces, build_edge_faces(faces))
        self.assertEqual(report.blocking_codes, ())

    def test_blocking_codes_are_reported_once_each(self):
        faces = np.array([[0, 1, 1], [0, 1, 2], [0, 1, 3], [2, 1, 0]])
        report = check_topology(faces, build_edge_faces(faces))
        self.assertEqual(len(report.blocking_codes), len(set(report.blocking_codes)))


if __name__ == "__main__":
    unittest.main()
