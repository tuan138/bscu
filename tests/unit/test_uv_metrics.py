"""Unit tests for the UV distortion metrics (UX-1, UIUX mục 2.3).

Definitions under test, verbatim from the spec:
    rho_f = sqrt(A_uv,f / A_3d,f)          density in UV per mm
    rho*   = median(rho_f)                 relative benchmark
    delta_f = rho_f / rho* - 1             relative density
    s_f    = sigma_2 / sigma_1             anisotropy of the tangent->UV Jacobian
    D_f    = sqrt(delta_f^2 + (1 - s_f)^2) composite, NOT a length error percent
"""

import math
import unittest

import numpy as np

from bscu.core.uv_metrics import (
    MetricSummary,
    compute_face_metrics,
    summarise,
    with_scores,
)

# A 1 mm right triangle lying in the XY plane, so its tangent basis is the
# identity frame and the Jacobian is exactly the UV change of basis.
V0 = np.array([0.0, 0.0, 0.0])
V1 = np.array([1.0, 0.0, 0.0])
V2 = np.array([0.0, 1.0, 0.0])


def triangle(uv1, uv2):
    verts = np.array([V0, V1, V2])
    uvs = np.array([[0.0, 0.0], uv1, uv2])
    faces = np.array([[0, 1, 2]])
    return verts, uvs, faces


def one_face_summary(uv1, uv2):
    metrics = compute_face_metrics(*triangle(uv1, uv2))
    return metrics, summarise(metrics)


class TestFaceGeometry(unittest.TestCase):
    def test_identity_mapping_has_unit_density(self):
        metrics, _ = one_face_summary((1.0, 0.0), (0.0, 1.0))
        self.assertAlmostEqual(metrics.density[0], 1.0, places=9)
        self.assertAlmostEqual(metrics.area_3d[0], 0.5, places=9)
        self.assertAlmostEqual(metrics.area_uv[0], 0.5, places=9)

    def test_orthonormal_tangent_basis_gives_unit_singular_values(self):
        metrics, _ = one_face_summary((1.0, 0.0), (0.0, 1.0))
        self.assertAlmostEqual(metrics.anisotropy[0], 1.0, places=9)
        self.assertAlmostEqual(metrics.sigma_max[0], 1.0, places=9)
        self.assertAlmostEqual(metrics.sigma_min[0], 1.0, places=9)

    def test_density_is_the_square_root_of_the_area_ratio(self):
        # UV quad 2x2 over a 0.5 mm^2 triangle -> 4x area, so rho doubles.
        metrics, _ = one_face_summary((2.0, 0.0), (0.0, 2.0))
        self.assertAlmostEqual(metrics.density[0], 2.0, places=9)

    def test_triangle_orientation_does_not_change_density(self):
        rotated, _ = one_face_summary((0.0, 2.0), (2.0, 0.0))
        plain, _ = one_face_summary((2.0, 0.0), (0.0, 2.0))
        self.assertAlmostEqual(rotated.density[0], plain.density[0], places=9)

    def test_sliver_triangle_reports_anisotropy_below_one(self):
        metrics, _ = one_face_summary((10.0, 0.0), (0.0, 0.1))
        self.assertLess(metrics.anisotropy[0], 1.0)
        self.assertGreater(metrics.anisotropy[0], 0.0)


class TestDegeneracyAndFlips(unittest.TestCase):
    def test_zero_3d_area_is_degenerate(self):
        verts = np.array([V0, V1, V1])
        uvs = np.array([[0.0, 0.0], [1.0, 0.0], [0.0, 1.0]])
        metrics = compute_face_metrics(verts, uvs, np.array([[0, 1, 2]]))
        self.assertEqual(metrics.degenerate[0], "ZERO_3D_AREA")
        self.assertAlmostEqual(metrics.density[0], 0.0)

    def test_zero_uv_area_is_degenerate(self):
        metrics, _ = one_face_summary((1.0, 0.0), (2.0, 0.0))
        self.assertEqual(metrics.degenerate[0], "ZERO_UV_AREA")


    def test_mirrored_uv_is_flagged_flipped(self):
        metrics, _ = one_face_summary((0.0, 1.0), (1.0, 0.0))
        self.assertTrue(metrics.flipped[0])
        self.assertIsNone(metrics.degenerate[0])

    def test_valid_uv_is_not_flagged_flipped(self):
        metrics, _ = one_face_summary((1.0, 0.0), (0.0, 1.0))
        self.assertFalse(metrics.flipped[0])


class TestCompositeScore(unittest.TestCase):
    def test_uniform_stretch_reports_fifty_percent_not_a_hundred(self):
        """UIUX 2.7: stretching U by 2 must not read as D_f = 100%."""
        _, summary = one_face_summary((2.0, 0.0), (0.0, 1.0))
        self.assertAlmostEqual(summary.worst, 0.5, places=9)

    def test_uniform_scale_of_the_whole_unwrap_is_invisible_to_the_median(self):
        """UIUX 2.3: median density cannot catch a global scale error."""
        _, doubled = one_face_summary((2.0, 0.0), (0.0, 2.0))
        _, plain = one_face_summary((1.0, 0.0), (0.0, 1.0))
        self.assertAlmostEqual(doubled.worst, 0.0, places=9)
        self.assertAlmostEqual(plain.worst, 0.0, places=9)
        self.assertAlmostEqual(doubled.rho_star, 2.0 * plain.rho_star, places=9)

    def test_single_face_summary_uses_itself_as_the_benchmark(self):
        _, summary = one_face_summary((1.0, 0.0), (0.0, 1.0))
        self.assertAlmostEqual(summary.rho_star, 1.0, places=9)
        self.assertAlmostEqual(summary.rms, 0.0, places=9)


class TestAggregate(unittest.TestCase):
    """Three co-planar triangles: two undistorted, one with U stretched 3x."""

    def _three_faces(self, bad_edge_mm=1.0):
        verts = np.array(
            [
                V0, V1, V2,
                [1.0, 1.0, 0.0], [2.0, 1.0, 0.0], [1.0, 2.0, 0.0],
                [0.0, 0.0, 1.0], [bad_edge_mm, 0.0, 1.0], [0.0, bad_edge_mm, 1.0],
            ]
        )
        uvs = np.array(
            [
                [0.0, 0.0], [1.0, 0.0], [0.0, 1.0],
                [0.0, 0.0], [1.0, 0.0], [0.0, 1.0],
                [0.0, 0.0], [3.0 * bad_edge_mm, 0.0], [0.0, 3.0 * bad_edge_mm],
            ]
        )
        faces = np.array([[0, 1, 2], [3, 4, 5], [6, 7, 8]])
        return compute_face_metrics(verts, uvs, faces)

    def test_median_benchmark_ignores_a_single_outlier_face(self):
        summary = summarise(self._three_faces())
        self.assertAlmostEqual(summary.rho_star, 1.0, places=6)
        self.assertGreater(summary.worst, 0.0)

    def test_good_faces_score_zero(self):
        summary = summarise(self._three_faces())
        self.assertAlmostEqual(summary.worst, summary.worst)
        scored = with_scores(self._three_faces())
        self.assertAlmostEqual(scored.score[0], 0.0, places=9)
        self.assertAlmostEqual(scored.score[1], 0.0, places=9)
        self.assertGreater(scored.score[2], 0.0)

    def test_rms_is_weighted_by_3d_area(self):
        metrics = with_scores(self._three_faces())
        expected = math.sqrt(
            float((metrics.area_3d * metrics.score**2).sum())
            / float(metrics.area_3d.sum())
        )
        self.assertAlmostEqual(summarise(self._three_faces()).rms, expected, places=9)

    def test_a_larger_bad_face_dominates_the_rms(self):
        small = summarise(self._three_faces(bad_edge_mm=1.0)).rms
        large = summarise(self._three_faces(bad_edge_mm=10.0)).rms
        self.assertGreater(large, small)

    def test_summary_reports_worst_face_index(self):
        self.assertEqual(summarise(self._three_faces()).worst_face, 2)

    def test_summary_counts_flipped_and_degenerate_faces(self):
        uvs = np.array([[0.0, 0.0], [0.0, 1.0], [1.0, 0.0]])
        metrics = compute_face_metrics(
            np.array([V0, V1, V2]), uvs, np.array([[0, 1, 2]])
        )
        summary = summarise(metrics)
        self.assertEqual(summary.flipped_count, 1)
        self.assertEqual(summary.degenerate_count, 0)

    def test_degenerate_faces_are_excluded_from_the_benchmark(self):
        verts = np.array(
            [V0, V1, V2, [3.0, 0.0, 0.0], [4.0, 0.0, 0.0], [3.0, 1.0, 0.0]]
        )
        uvs = np.array(
            [
                [0.0, 0.0], [1.0, 0.0], [0.0, 1.0],
                [0.0, 0.0], [1.0, 0.0], [2.0, 0.0],
            ]
        )
        faces = np.array([[0, 1, 2], [3, 4, 5]])
        summary = summarise(compute_face_metrics(verts, uvs, faces))
        self.assertEqual(summary.degenerate_count, 1)
        self.assertAlmostEqual(summary.rho_star, 1.0, places=6)

    def test_all_degenerate_input_reports_no_benchmark(self):
        verts = np.array([V0, V1, V1])
        uvs = np.array([[0.0, 0.0], [1.0, 0.0], [0.0, 1.0]])
        summary = summarise(compute_face_metrics(verts, uvs, np.array([[0, 1, 2]])))
        self.assertIsNone(summary.rho_star)
        self.assertEqual(summary.rms, 0.0)
        self.assertIsNone(summary.worst_face)

    def test_empty_input_is_handled(self):
        empty = compute_face_metrics(
            np.zeros((0, 3)), np.zeros((0, 2)), np.zeros((0, 3), dtype=int)
        )
        self.assertEqual(len(empty), 0)
        self.assertIsNone(summarise(empty).rho_star)



class TestSummaryShape(unittest.TestCase):
    def test_summary_is_a_frozen_record(self):
        summary = MetricSummary()
        with self.assertRaises(Exception):
            summary.rms = 1.0


if __name__ == "__main__":
    unittest.main()
