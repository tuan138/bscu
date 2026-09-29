"""Unit tests for the four seam tools (UX-6, UIUX 3.2).

Each tool is a proposal, not a promise: the user previews the exact chain, and
that same chain is what gets applied. These tests pin the parts where a wrong
answer would be invisible in the viewport but wrong on the mesh - a boundary
that only counts the whole mesh, a "shortest path" that walks off the surface,
a contour that claims to know what is visible.
"""

import unittest

import numpy as np

from bscu.core.seam_tools import (
    ChainError,
    chain_between,
    edge_face_counts,
    nearest_plane_chain,
    plane_offset,
    selection_boundary,
    view_contour,
)


def grid_faces(columns: int, rows: int) -> np.ndarray:
    """Triangles over a columns x rows vertex grid, indexed row-major."""
    quads = []
    for row in range(rows - 1):
        for column in range(columns - 1):
            top_left = row * columns + column
            top_right = top_left + 1
            bottom_left = top_left + columns
            bottom_right = bottom_left + 1
            quads.append([top_left, bottom_left, top_right])
            quads.append([top_right, bottom_left, bottom_right])
    return np.asarray(quads, dtype=np.int64)


class TestChainBetween(unittest.TestCase):
    def test_the_chain_walks_existing_edges_only(self):
        faces = grid_faces(4, 4)

        chain = chain_between(faces, 0, 3)

        self.assertGreater(len(chain), 0)
        walked = {vertex for edge in chain for vertex in edge}
        self.assertTrue(walked.issubset(set(range(16))),
                        "the chain invented a vertex that is not on the mesh")

    def test_a_chain_is_a_connected_path_from_start_to_goal(self):
        """Vertex 0 and vertex 24 are opposite corners of a 5 x 5 grid."""
        faces = grid_faces(5, 5)

        chain = chain_between(faces, 0, 24)

        self.assertEqual(len(chain), 8, f"expected eight steps, got {chain}")
        ends = [chain[0][0], chain[-1][1]]
        self.assertEqual(sorted(ends), [0, 24])
        for before, after in zip(chain, chain[1:]):
            self.assertIn(after[0], before, f"{before} does not meet {after}")

    def test_the_shortest_of_two_routes_is_the_one_returned(self):
        """A grid offers a long way round; the tool must not take it."""
        faces = grid_faces(5, 5)

        chain = chain_between(faces, 0, 4)

        self.assertEqual(len(chain), 4, f"expected four steps across, got {chain}")

    def test_the_same_vertex_gives_an_empty_chain(self):
        faces = grid_faces(3, 3)

        self.assertEqual(chain_between(faces, 4, 4), [])

    def test_asking_for_two_islands_apart_is_refused(self):
        """No chain across a seam exists, and inventing one would be worse."""
        # Two quads that share no vertex at all.
        faces = np.array([[0, 4, 1], [1, 4, 5],
                          [100, 104, 101], [101, 104, 105]], dtype=np.int64)

        with self.assertRaises(ChainError):
            chain_between(faces, 0, 105)

    def test_a_vertex_that_does_not_exist_is_refused(self):
        faces = grid_faces(3, 3)

        with self.assertRaises(ChainError):
            chain_between(faces, 0, 999)


class TestSelectionBoundary(unittest.TestCase):
    def test_edges_with_exactly_one_selected_face_are_the_boundary(self):
        """The first two triangles of a 3 x 3 grid share the edge (1, 3)."""
        faces = grid_faces(3, 3)
        selected = np.zeros(len(faces), dtype=bool)
        selected[:2] = True

        boundary = selection_boundary(faces, selected)

        self.assertIn((0, 1), boundary)
        self.assertIn((0, 3), boundary)
        self.assertNotIn((1, 3), boundary, "an edge with two selected faces is inside")

    def test_the_open_border_of_the_mesh_counts_when_it_is_selected(self):
        """The whole-mesh border is not the selection border, but it is one here."""
        faces = grid_faces(3, 3)
        selected = np.zeros(len(faces), dtype=bool)
        selected[0] = True  # the first triangle, which touches the mesh border

        boundary = selection_boundary(faces, selected)

        self.assertIn((0, 3), boundary)

    def test_selecting_everything_leaves_the_mesh_border(self):
        """A whole mesh still has an outline, and that outline is the answer.

        This is exactly the case the spec means by counting the mesh border as
        well: the open border of a closed selection is still a seam the user
        may want, and reading the mesh's own border flag would not find it.
        """
        faces = grid_faces(3, 3)
        selected = np.ones(len(faces), dtype=bool)

        boundary = selection_boundary(faces, selected)

        self.assertTrue(boundary)
        mesh_border = {edge for edge, users in edge_face_counts(faces).items()
                       if len(users) == 1}
        self.assertEqual(set(boundary), mesh_border)

    def test_selecting_nothing_leaves_no_border(self):
        faces = grid_faces(3, 3)

        self.assertEqual(selection_boundary(faces, np.zeros(len(faces), dtype=bool)), [])

    def test_a_lone_face_border_is_its_three_edges(self):
        faces = grid_faces(3, 3)
        selected = np.zeros(len(faces), dtype=bool)
        selected[0] = True

        boundary = selection_boundary(faces, selected)

        self.assertEqual(len(boundary), 3, boundary)

    def test_a_selection_longer_than_the_mesh_is_refused(self):
        faces = grid_faces(3, 3)

        with self.assertRaises(ValueError):
            selection_boundary(faces, np.ones(len(faces) + 3, dtype=bool))


class TestNearestPlaneChain(unittest.TestCase):
    def test_the_chain_follows_the_edges_closest_to_the_plane(self):
        """A cutting gizmo suggests a path; it does not cut the mesh."""
        faces = grid_faces(5, 5)
        positions = np.stack(
            np.meshgrid(np.arange(5.0), np.arange(5.0), indexing="xy"), axis=-1
        ).reshape(-1, 2)

        chain = nearest_plane_chain(faces, positions, origin=np.array([0.0, 2.0]),
                                    normal=np.array([0.0, 1.0]), tolerance=0.6)

        self.assertTrue(chain, "a plane across the middle should find edges")
        for edge in chain:
            midpoint = positions[list(edge)].mean(axis=0)
            self.assertLess(abs(float(midpoint[1]) - 2.0), 0.6, f"{edge} is off the plane")

    def test_a_plane_far_from_the_mesh_finds_nothing(self):
        faces = grid_faces(3, 3)
        positions = np.stack(
            np.meshgrid(np.arange(3.0), np.arange(3.0), indexing="xy"), axis=-1
        ).reshape(-1, 2)

        chain = nearest_plane_chain(faces, positions, origin=np.array([0.0, 50.0]),
                                    normal=np.array([0.0, 1.0]), tolerance=0.5)

        self.assertEqual(chain, [])

    def test_a_zero_normal_is_refused(self):
        faces = grid_faces(3, 3)
        positions = np.zeros((9, 2))

        with self.assertRaises(ValueError):
            nearest_plane_chain(faces, positions, np.zeros(2), np.zeros(2), 0.5)


class TestViewContour(unittest.TestCase):
    def setUp(self):
        # Two triangles sharing the edge (1, 2), so a comparison is possible.
        self.faces = np.array([[0, 1, 2], [1, 3, 2]], dtype=np.int64)
        self.flat = np.tile(np.array([[0.0, 0.0, 1.0]]), (len(self.faces), 1))

    def test_an_edge_where_the_faces_flip_away_from_the_eye_is_a_contour(self):
        """The silhouette is where one face turns away and the other does not."""
        # The eye looks along +Z, so a silhouette is one face turned towards it
        # and its neighbour turned away.
        tilted = self.flat.copy()
        tilted[0] = [0.0, 0.0, 0.95]
        tilted[1] = [0.0, 0.0, -0.95]

        proposal = view_contour(self.faces, tilted, np.array([0.0, 0.0, 1.0]))

        self.assertIn((1, 2), proposal.silhouette)
        self.assertIn("faces_face_opposite_ways", proposal.notes[(1, 2)])

    def test_two_faces_pointing_the_same_way_are_not_a_contour(self):
        proposal = view_contour(self.faces, self.flat, np.array([0.0, 0.0, 1.0]))

        self.assertEqual(proposal.silhouette, [])

    def test_the_open_border_is_undecided_rather_than_a_silhouette(self):
        """One face cannot tell you what is behind it, so it is neither."""
        tilted = self.flat.copy()
        tilted[0] = [0.0, 0.0, 0.95]
        tilted[1] = [0.0, 0.0, -0.95]

        proposal = view_contour(self.faces, tilted, np.array([0.0, 0.0, 1.0]))

        self.assertIn((0, 1), proposal.undecided)
        self.assertNotIn((0, 1), proposal.silhouette)
        self.assertIn("single_face", proposal.notes[(0, 1)])

    def test_every_candidate_says_it_is_unverified(self):
        """The tool proposes; it must not imply it has checked visibility."""
        tilted = self.flat.copy()
        tilted[0] = [0.0, 0.0, 0.95]
        tilted[1] = [0.0, 0.0, -0.95]

        proposal = view_contour(self.faces, tilted, np.array([0.0, 0.0, 1.0]))

        self.assertTrue(proposal.notes)
        for edge, reason in proposal.notes.items():
            self.assertTrue("unverified" in reason or "neither" in reason,
                            f"{edge} is presented as settled: {reason}")

    def test_mismatched_normals_are_refused(self):
        with self.assertRaises(ValueError):
            view_contour(self.faces, self.flat[:1], np.array([0.0, 0.0, -1.0]))

    def test_a_view_direction_of_zero_length_is_refused(self):
        with self.assertRaises(ValueError):
            view_contour(self.faces, self.flat, np.zeros(3))


class TestPlaneOffset(unittest.TestCase):
    def test_offset_is_signed_by_which_side_of_the_plane_a_point_falls(self):
        signed = plane_offset(np.array([[0.0, 1.0], [0.0, -1.0]]), np.array([0.0, 0.0]),
                              np.array([0.0, 1.0]))

        self.assertAlmostEqual(float(signed[0]), 1.0)
        self.assertAlmostEqual(float(signed[1]), -1.0)

    def test_a_point_on_the_plane_has_no_offset(self):
        signed = plane_offset(np.array([[3.0, 0.0]]), np.array([3.0, 0.0]),
                              np.array([0.0, 1.0]))

        self.assertAlmostEqual(float(signed[0]), 0.0)


if __name__ == "__main__":
    unittest.main()
