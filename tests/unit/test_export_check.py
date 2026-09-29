"""Unit tests for the pre-export checks (UX-11, UIUX 9.3 and 9.4).

A closed mesh and a correctly sized one are different promises, and the second
is the one that silently goes wrong: a cage can measure right while the relief
comes out the wrong size. The dimensional check here is fed measured surface
extents rather than design points for that reason.
"""

import unittest

import numpy as np

from bscu.core.export_check import (
    TOLERANCE_MM,
    build_report,
    check_degenerate,
    check_dimensions,
    check_walls,
    check_watertight,
)


def cube() -> tuple:
    """A unit cube as eight corners and twelve triangles, correctly wound."""
    verts = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
                      [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1]], dtype=np.float64)
    quads = [
        (0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4),
        (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7),
    ]
    faces = []
    for a, b, c, d in quads:
        faces.append([a, b, c])
        faces.append([a, c, d])
    return verts, np.asarray(faces, dtype=np.int64)


class TestWatertight(unittest.TestCase):
    def test_a_closed_cube_is_watertight(self):
        _verts, faces = cube()

        check = check_watertight(faces)

        self.assertTrue(check.ok, check.message)

    def test_a_cube_with_a_face_removed_is_not(self):
        _verts, faces = cube()

        check = check_watertight(faces[:-1])

        self.assertFalse(check.ok)
        self.assertIn("open", check.message)

    def test_a_flipped_face_breaks_the_winding_consistency(self):
        """A naive edge count would call this closed; it is inside out."""
        _verts, faces = cube()
        wound = faces.copy()
        wound[0] = wound[0][::-1]

        check = check_watertight(wound)

        self.assertFalse(check.ok)
        self.assertIn("same way", check.message)

    def test_a_mesh_with_no_faces_is_not_exported_as_watertight(self):
        check = check_watertight(np.zeros((0, 3), dtype=np.int64))

        self.assertFalse(check.ok)

    def test_a_non_manifold_edge_is_caught(self):
        faces = np.array([[0, 1, 2], [0, 1, 2], [0, 1, 3], [0, 1, 4]], dtype=np.int64)

        check = check_watertight(faces)

        self.assertFalse(check.ok)


class TestDimensions(unittest.TestCase):
    def test_a_part_within_tolerance_passes(self):
        check, error = check_dimensions([100.0, 50.0], [100.02, 49.99])

        self.assertTrue(check.ok)
        self.assertLessEqual(error, TOLERANCE_MM)

    def test_a_part_outside_tolerance_is_reported_with_the_size_of_the_error(self):
        check, error = check_dimensions([100.0, 50.0], [100.0, 50.2])

        self.assertFalse(check.ok)
        self.assertAlmostEqual(error, 0.2)
        self.assertIn("0.2", check.message)

    def test_the_tolerance_is_fifty_microns(self):
        self.assertAlmostEqual(TOLERANCE_MM, 0.05)

    def test_the_worst_axis_decides(self):
        """One axis out by a hair must not be averaged away by the others."""
        check, error = check_dimensions([100.0, 50.0, 5.0], [100.0, 50.0, 4.9])

        self.assertFalse(check.ok, "the third axis is the one that matters")
        self.assertAlmostEqual(error, 0.1)

    def test_mismatched_lengths_are_refused(self):
        with self.assertRaises(ValueError):
            check_dimensions([1.0, 2.0], [1.0])

    def test_nothing_to_compare_is_not_a_failure(self):
        check, error = check_dimensions([], [])

        self.assertTrue(check.ok)
        self.assertEqual(error, 0.0)


class TestWalls(unittest.TestCase):
    def test_a_thick_enough_part_passes(self):
        check, thinnest = check_walls([5.0, 8.0, 3.0], minimum_mm=1.0)

        self.assertTrue(check.ok)
        self.assertAlmostEqual(thinnest, 3.0)

    def test_a_thin_wall_is_reported_with_its_thickness(self):
        check, thinnest = check_walls([5.0, 0.2], minimum_mm=1.0)

        self.assertFalse(check.ok)
        self.assertAlmostEqual(thinnest, 0.2)
        self.assertIn("0.200", check.message)

    def test_nothing_to_measure_is_not_a_failure(self):
        check, thinnest = check_walls([], minimum_mm=1.0)

        self.assertTrue(check.ok)
        self.assertEqual(thinnest, float("inf"))


class TestDegenerateFaces(unittest.TestCase):
    def test_a_cube_has_no_degenerate_faces(self):
        verts, faces = cube()

        check = check_degenerate(verts, faces)

        self.assertTrue(check.ok, check.message)

    def test_a_collapsed_face_is_caught(self):
        verts, faces = cube()
        verts[2] = verts[1]

        check = check_degenerate(verts, faces)

        self.assertFalse(check.ok)

    def test_a_zero_area_face_is_caught(self):
        """Collinear corners with no short edge, so only the area test can see it."""
        verts, faces = cube()
        verts[2] = (verts[0] + verts[1]) * 0.5

        check = check_degenerate(verts, faces)

        self.assertFalse(check.ok)
        self.assertIn("no area", check.message)


class TestTheWholeReport(unittest.TestCase):
    def test_a_good_part_passes_every_check(self):
        verts, faces = cube()

        report = build_report(verts, faces, [1.0, 1.0, 1.0], [1.0, 1.0, 1.0],
                              remaining_mm=[5.0, 5.0])

        self.assertTrue(report.passed, [c.message for c in report.failures])
        self.assertTrue(report.watertight)

    def test_one_bad_thing_fails_the_report(self):
        verts, faces = cube()

        report = build_report(verts, faces, [1.0, 1.0, 1.0], [1.0, 1.0, 1.3],
                              remaining_mm=[5.0])

        self.assertFalse(report.passed)
        self.assertEqual(len(report.failures), 1)
        self.assertAlmostEqual(report.max_error_mm, 0.3)

    def test_every_failure_carries_a_way_forward(self):
        verts, faces = cube()

        report = build_report(verts, faces, [1.0], [2.0], remaining_mm=[0.1])

        for check in report.failures:
            self.assertTrue(check.detail, f"{check.code} offers no way forward")

    def test_walls_are_left_out_when_no_thickness_was_given(self):
        verts, faces = cube()

        report = build_report(verts, faces, [1.0], [1.0])

        self.assertNotIn("WALLS", {check.code for check in report.checks})
        self.assertTrue(report.passed)


if __name__ == "__main__":
    unittest.main()
