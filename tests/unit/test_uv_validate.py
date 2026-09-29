"""Unit tests for the chart validator (UX-6, UIUX 3.3).

The validator runs on the *opened* surface, not on the original face set, and
every finding has to name a place, a reason and a suggestion. Those two things
are the difference between a tool the user trusts and one they learn to ignore.

The cases below are built by hand so the answer is known in advance: a disc, an
annulus, a chart with a flipped face, a degenerate one, two charts laid on top
of each other, and a seam with a legitimate loose end.
"""

import unittest

import numpy as np

from bscu.core.uv_validate import (
    SEVERITIES,
    validate_chart,
)


def disc_faces() -> np.ndarray:
    """A hexagon fan: one centre vertex, six rim vertices, six triangles."""
    triangles = [[0, index + 1, (index + 1) % 6 + 1] for index in range(6)]
    return np.asarray(triangles, dtype=np.int64)


def annulus_faces() -> np.ndarray:
    """A ring of quads between a six-gon and a larger six-gon."""
    quads = []
    for index in range(6):
        inner = 1 + index
        inner_next = 1 + (index + 1) % 6
        outer = 7 + index
        outer_next = 7 + (index + 1) % 6
        quads.append([inner, outer, inner_next])
        quads.append([inner_next, outer, outer_next])
    return np.asarray(quads, dtype=np.int64)


def disc_uv() -> np.ndarray:
    """A centre and six rim points, wound so no triangle comes out flipped."""
    rim = [(1.0, 0.0), (0.5, 0.866), (-0.5, 0.866),
           (-1.0, 0.0), (-0.5, -0.866), (0.5, -0.866)]
    return np.asarray([(0.0, 0.0)] + rim, dtype=np.float64)


class TestWellFormedCharts(unittest.TestCase):
    def test_a_disc_passes_with_one_border_loop(self):
        faces = disc_faces()
        uv = disc_uv()

        report = validate_chart(faces, uv, np.zeros(len(faces), dtype=np.int64))

        self.assertEqual(report.errors, [], report.errors)
        self.assertEqual(report.charts[0].boundary_loops, 1)
        self.assertEqual(report.charts[0].euler, 1)

    def test_an_annulus_passes_with_two_border_loops(self):
        """Two loops is a ring, not a mistake."""
        faces = annulus_faces()
        inner = disc_uv()[1:] * 0.5   # six inner points
        outer = disc_uv()[1:]          # the same six, twice as far out
        uv = np.vstack([np.zeros((1, 2)), inner, outer])

        report = validate_chart(faces, uv, np.zeros(len(faces), dtype=np.int64))

        self.assertEqual(report.errors, [], report.errors)
        self.assertEqual(report.charts[0].boundary_loops, 2)

    def test_the_euler_number_matches_the_opened_surface_not_the_original(self):
        """Opening a seam adds vertices and edges; both sides have to follow."""
        faces = disc_faces()
        uv = disc_uv()

        report = validate_chart(faces, uv, np.zeros(len(faces), dtype=np.int64))
        chart = report.charts[0]

        self.assertEqual(chart.euler, chart.vertices - chart.edges + chart.faces)

    def test_a_chart_with_no_problems_still_says_it_looked(self):
        faces = disc_faces()
        report = validate_chart(faces, disc_uv(), np.zeros(len(faces), dtype=np.int64))

        self.assertEqual(report.checked_charts, 1)


class TestLooseSeamEnds(unittest.TestCase):
    def test_a_seam_with_a_loose_end_is_a_note_not_an_error(self):
        """Opening a closed surface legitimately leaves loose ends."""
        faces = disc_faces()
        uv = disc_uv()
        seam = [(0, 1), (1, 2)]

        report = validate_chart(faces, uv, np.zeros(len(faces), dtype=np.int64),
                                seam_edges=seam)

        self.assertEqual(report.errors, [], report.errors)
        notes = [f for f in report.findings if f.code == "LOOSE_SEAM_END"]
        self.assertTrue(notes, "the loose end has to be pointed out")
        self.assertIn(notes[0].severity, ("note", "warning"))
        self.assertTrue(notes[0].suggestion)

    def test_a_closed_seam_has_no_loose_end_to_report(self):
        faces = disc_faces()
        report = validate_chart(faces, disc_uv(), np.zeros(len(faces), dtype=np.int64),
                                seam_edges=[(1, 2), (2, 3), (3, 1)])

        self.assertEqual([f for f in report.findings if f.code == "LOOSE_SEAM_END"], [])


class TestBrokenCharts(unittest.TestCase):
    def test_a_duplicate_face_is_an_error(self):
        faces = np.vstack([disc_faces(), disc_faces()[:1]])
        uv = np.zeros((7, 2))

        report = validate_chart(faces, uv, np.zeros(len(faces), dtype=np.int64))

        self.assertIn("DUPLICATE_FACE", {f.code for f in report.errors})

    def test_an_edge_shared_by_three_faces_is_an_error(self):
        faces = np.array([[0, 1, 2], [0, 1, 3], [0, 1, 4], [2, 3, 4]], dtype=np.int64)
        uv = np.zeros((5, 2))

        report = validate_chart(faces, uv, np.zeros(len(faces), dtype=np.int64))

        self.assertIn("NON_MANIFOLD_EDGE", {f.code for f in report.errors})

    def test_a_flipped_face_is_an_error(self):
        faces = np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int64)
        uv = np.array([[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]])
        uv = uv.copy()
        uv[[0, 1, 2]] = uv[[1, 0, 2]]  # wind the first triangle the other way

        report = validate_chart(faces, uv, np.zeros(len(faces), dtype=np.int64))

        self.assertIn("FLIPPED_FACE", {f.code for f in report.errors})

    def test_a_collapsed_uv_triangle_is_an_error(self):
        faces = np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int64)
        uv = np.array([[0.0, 0.0], [1.0, 0.0], [0.0, 0.0], [0.0, 1.0]])

        report = validate_chart(faces, uv, np.zeros(len(faces), dtype=np.int64))

        self.assertIn("DEGENERATE_FACE", {f.code for f in report.errors})

    def test_two_charts_landed_on_top_of_each_other_are_an_error(self):
        """Sharing a UV area is what makes the displacement ambiguous."""
        faces = np.array([[0, 1, 2], [0, 2, 3], [4, 5, 6], [4, 6, 7]], dtype=np.int64)
        square = [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]]
        uv = np.asarray(square + square, dtype=np.float64)
        islands = np.array([0, 0, 1, 1], dtype=np.int64)

        report = validate_chart(faces, uv, islands)

        self.assertIn("UV_OVERLAP", {f.code for f in report.errors})

    def test_charts_that_touch_along_an_edge_are_not_an_overlap(self):
        """Charts packed side by side share a border; that is the whole point."""
        faces = np.array([[0, 1, 2], [0, 2, 3], [2, 1, 4]], dtype=np.int64)
        uv = np.array([[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0],
                       [2.0, 0.0]], dtype=np.float64)
        islands = np.array([0, 0, 1], dtype=np.int64)

        report = validate_chart(faces, uv, islands)

        self.assertNotIn("UV_OVERLAP", {f.code for f in report.errors})

    def test_a_mismatched_uv_length_is_refused(self):
        faces = disc_faces()

        with self.assertRaises(ValueError):
            validate_chart(faces, np.zeros((3, 2)), np.zeros(len(faces), dtype=np.int64))


class TestFindingsAreActionable(unittest.TestCase):
    def test_every_finding_names_a_place_a_reason_and_a_suggestion(self):
        faces = np.vstack([disc_faces(), disc_faces()[:1]])
        uv = np.zeros((7, 2))

        report = validate_chart(faces, uv, np.zeros(len(faces), dtype=np.int64))

        self.assertTrue(report.findings)
        for finding in report.findings:
            self.assertIn(finding.severity, SEVERITIES)
            self.assertTrue(finding.message)
            self.assertTrue(finding.suggestion, f"{finding.code} offers no way forward")
            self.assertIsNotNone(finding.faces, f"{finding.code} names no location")

    def test_an_error_names_the_face_that_caused_it(self):
        faces = np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int64)
        uv = np.array([[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]]).copy()
        uv[[0, 1, 2]] = uv[[1, 0, 2]]

        report = validate_chart(faces, uv, np.zeros(len(faces), dtype=np.int64))

        flipped = [f for f in report.errors if f.code == "FLIPPED_FACE"]
        self.assertEqual(list(flipped[0].faces), [0])

    def test_severities_are_ordered_so_the_worst_decides_the_state(self):
        self.assertLess(SEVERITIES.index("error"), SEVERITIES.index("warning"))
        self.assertLess(SEVERITIES.index("warning"), SEVERITIES.index("note"))


if __name__ == "__main__":
    unittest.main()
