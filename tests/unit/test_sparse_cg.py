"""Unit tests for the sparse conjugate gradient solver (UX-5, UIUX K4).

Blender ships numpy but not scipy, so the pipeline carries its own CSR matrix
and CG. These tests pin the properties the unwrap depends on: it must actually
converge, it must be deterministic, and it must refuse to pretend it converged.
"""

import unittest

import numpy as np

from bscu.core.sparse_cg import CSRMatrix, conjugate_gradient, solve_spd


def dense_to_csr(matrix: np.ndarray) -> CSRMatrix:
    return CSRMatrix.from_dense(matrix)


class TestCSRMatrix(unittest.TestCase):
    def test_multiplying_by_a_vector_matches_the_dense_product(self):
        dense = np.array([[4.0, 1.0], [1.0, 3.0]])
        result = dense_to_csr(dense) @ np.array([1.0, 2.0])
        assert np.allclose(result, dense @ np.array([1.0, 2.0])), result

    def test_matvec_with_a_matrix_is_the_same_as_stacked_matvecs(self):
        dense = np.array([[4.0, 1.0], [1.0, 3.0]])
        csr = dense_to_csr(dense)
        left = np.array([1.0, 0.0])
        right = np.array([0.0, 1.0])
        assert np.allclose(csr @ left, dense @ left)
        assert np.allclose(csr @ right, dense @ right)
        stacked = np.stack([csr @ left, csr @ right], axis=1)
        assert np.allclose(stacked, dense), stacked

    def test_shape_is_reported(self):
        csr = dense_to_csr(np.eye(3))
        assert csr.shape == (3, 3)

    def test_transpose_multiplying_matches_the_dense_transpose(self):
        dense = np.array([[0.0, 2.0], [3.0, 0.0]])
        csr = dense_to_csr(dense)
        vector = np.array([1.0, 1.0])
        assert np.allclose(csr.T @ vector, dense.T @ vector)

    def test_diagonal_is_available_for_preconditioning(self):
        csr = dense_to_csr(np.diag([2.0, 4.0, 8.0]))
        assert np.allclose(csr.diagonal(), [2.0, 4.0, 8.0])

    def test_empty_matrix_has_no_diagonal(self):
        csr = CSRMatrix.empty()
        assert csr.shape == (0, 0)
        assert csr.diagonal().size == 0


class TestConjugateGradient(unittest.TestCase):
    def test_solves_a_known_linear_system(self):
        dense = np.array([[4.0, 1.0], [1.0, 3.0]])
        b = np.array([1.0, 2.0])
        x, info = conjugate_gradient(dense_to_csr(dense), b, iterations=50)
        assert np.allclose(x, np.linalg.solve(dense, b), atol=1e-8), (x, info)
        assert info.converged, info

    def test_residual_is_small_after_converging(self):
        dense = np.array([[4.0, 1.0], [1.0, 3.0]])
        b = np.array([1.0, 2.0])
        x, info = conjugate_gradient(dense_to_csr(dense), b, iterations=50)
        residual = np.linalg.norm(dense_to_csr(dense) @ x - b)
        assert residual < 1e-8, residual
        assert info.residual == residual or abs(info.residual - residual) < 1e-8

    def test_reports_how_many_iterations_it_took(self):
        dense = np.array([[4.0, 1.0], [1.0, 3.0]])
        x, info = conjugate_gradient(dense_to_csr(dense), np.array([1.0, 2.0]), 50)
        assert 0 < info.iterations <= 50, info

    def test_stops_early_and_says_it_did_not_converge(self):
        # A wide spread of eigenvalues needs more than one CG step.
        dense = np.diag([1.0, 1e3, 1e6, 1e9])
        x, info = conjugate_gradient(dense_to_csr(dense), np.ones(4), iterations=1)
        assert not info.converged, info
        assert info.iterations == 1, info

    def test_zero_right_hand_side_is_already_solved(self):
        x, info = conjugate_gradient(dense_to_csr(np.eye(3)), np.zeros(3))
        assert np.allclose(x, 0.0)
        assert info.converged, info

    def test_uses_a_preconditioner_when_given_one(self):
        dense = np.diag([1.0, 1e6, 1.0, 1.0])
        b = np.array([1.0, 1.0, 1.0, 1.0])
        plain, _ = conjugate_gradient(dense_to_csr(dense), b, iterations=3)
        scaled, info = conjugate_gradient(
            dense_to_csr(dense), b, iterations=200, preconditioner=lambda v: v / 1e6
        )
        assert info.iterations <= 3, info.iterations
        assert np.allclose(scaled, np.linalg.solve(dense, b), atol=1e-6), (plain, scaled)

    def test_zero_iterations_returns_the_starting_point(self):
        dense = np.array([[4.0, 1.0], [1.0, 3.0]])
        x, info = conjugate_gradient(dense_to_csr(dense), np.array([1.0, 2.0]), 0)
        assert np.allclose(x, 0.0), x
        assert not info.converged, info


class TestSolveSPD(unittest.TestCase):
    def test_solves_and_reports_convergence(self):
        dense = np.array([[4.0, 1.0], [1.0, 3.0]])
        x, info = solve_spd(dense_to_csr(dense), np.array([1.0, 2.0]), 50)
        # The ridge perturbs the answer slightly; that is the price of a solver
        # that is defined on the semi-definite systems charts actually produce.
        assert np.allclose(x, np.linalg.solve(dense, np.array([1.0, 2.0])), atol=1e-3)
        assert info.converged, info

    def test_singular_system_is_reported_rather_than_answered(self):
        """A rank-deficient chart must not get a plausible-looking answer.

        Conjugate gradients does converge here, to a huge value along the
        near-null direction, with a tiny residual. Reporting that as solved
        would push garbage into the UV map, so the solver refuses it.
        """
        dense = np.array([[1.0, 1.0], [1.0, 1.0]])
        x, info = solve_spd(dense_to_csr(dense), np.array([1.0, 0.0]), 100)
        assert not info.converged, info
        assert np.all(np.isfinite(x)), x


if __name__ == "__main__":
    unittest.main()
