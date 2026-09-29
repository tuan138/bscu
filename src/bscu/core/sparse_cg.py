"""
Sparse matrix storage and a conjugate gradient solver (UX-5, UIUX K4).

Blender ships numpy but not scipy, so the unwrap pipeline carries its own CSR
matrix and CG. The solver exists for one job: solve the symmetric positive
semi-definite systems that come out of the least-squares conformal map, and
report honestly when it did not converge.

Conjugate gradients need a positive definite matrix. A chart with a degenerate
corner configuration only produces a semi-definite one, so :func:`solve_spd`
adds a Tikhonov term, which turns "indefinite" into "small but positive" and
keeps the iteration defined. The term is scaled to the matrix and escalated
until the iteration actually converges.
"""

from dataclasses import dataclass
from typing import Callable, Optional

import numpy as np


@dataclass
class CSRMatrix:
    """Compressed sparse row: indices, indptr and data, all numpy arrays.

    Mutable only for one reason: the row index used by the transpose is
    derived data that would otherwise be rebuilt on every iteration. Nothing
    that changes the matrix's contents is allowed to go through here.
    """

    data: np.ndarray
    indices: np.ndarray
    indptr: np.ndarray
    shape: tuple
    _row_index: Optional[np.ndarray] = None

    @classmethod
    def from_dense(cls, matrix: np.ndarray) -> "CSRMatrix":
        """Build from a dense array; for tests and small systems only."""
        dense = np.asarray(matrix, dtype=np.float64)
        rows, cols = np.nonzero(dense)
        order = np.argsort(rows, kind="stable")
        rows, cols = rows[order], cols[order]
        counts = np.bincount(rows, minlength=dense.shape[0])
        indptr = np.r_[0, np.cumsum(counts)]
        return cls(
            data=dense[rows, cols].copy(),
            indices=cols.astype(np.int64),
            indptr=indptr.astype(np.int64),
            shape=dense.shape,
        )

    @classmethod
    def from_coo(cls, rows, cols, values, shape) -> "CSRMatrix":
        """Build from coordinate triples, summing entries at the same position.

        Summing by row would be wrong: one row of a normal-equation matrix holds
        several columns, and folding them together destroys the matrix.
        """
        rows = np.asarray(rows, dtype=np.int64).ravel()
        cols = np.asarray(cols, dtype=np.int64).ravel()
        values = np.asarray(values, dtype=np.float64).ravel()
        if not rows.size:
            return cls.empty(shape[1] if len(shape) > 1 else 0)

        key = rows * max(int(cols.max(initial=0)) + 1, 1) + cols
        order = np.argsort(key, kind="stable")
        key, cols, values = key[order], cols[order], values[order]
        rows = rows[order]

        boundary = np.r_[True, key[1:] != key[:-1]]
        starts = np.flatnonzero(boundary)
        summed = np.add.reduceat(values, starts) if starts.size else values
        rows, cols = rows[starts], cols[starts]

        indptr = np.zeros(shape[0] + 1, dtype=np.int64)
        np.cumsum(np.bincount(rows, minlength=shape[0]), out=indptr[1:])
        return cls(summed, cols.astype(np.int64), indptr, shape)

    @classmethod
    def empty(cls, columns: int = 0) -> "CSRMatrix":
        return cls(
            data=np.zeros(0),
            indices=np.zeros(0, dtype=np.int64),
            indptr=np.zeros(1, dtype=np.int64),
            shape=(0, columns),
        )

    def diagonal(self) -> np.ndarray:
        """Diagonal entries, zero where a row has no entry on itself."""
        out = np.zeros(self.shape[0], dtype=np.float64)
        for row in range(self.shape[0]):
            start, stop = self.indptr[row], self.indptr[row + 1]
            cols = self.indices[start:stop]
            hit = cols == row
            if hit.any():
                out[row] = self.data[start:stop][hit][0]
        return out

    def rows(self):
        """Yield (indices, data) for every row, in order."""
        for row in range(self.shape[0]):
            start, stop = self.indptr[row], self.indptr[row + 1]
            yield self.indices[start:stop], self.data[start:stop]

    def _row_counts(self) -> np.ndarray:
        return np.diff(self.indptr)

    def _row_of_entry(self) -> np.ndarray:
        """Which row each stored entry belongs to, built once and kept.

        The transpose needs it every iteration, and rebuilding it each time
        costs more than the multiplication it feeds.
        """
        if self._row_index is None or len(self._row_index) != len(self.data):
            self._row_index = np.repeat(np.arange(self.shape[0]),
                                        self._row_counts())
        return self._row_index

    def dot(self, vector: np.ndarray) -> np.ndarray:
        """Matrix times vector, in one pass over the stored values.

        Written with ``reduceat`` rather than a loop because the whole point of
        carrying our own sparse matrix is systems far too large to iterate in
        Python: a chart of a hundred thousand triangles has millions of stored
        entries, and a Python loop over them costs more than the entire solve.
        """
        data = np.asarray(vector, dtype=np.float64).ravel()[self.indices]
        out = np.zeros(self.shape[0], dtype=np.float64)
        counts = self._row_counts()
        filled = counts > 0
        if filled.any():
            out[filled] = np.add.reduceat(self.data * data, self.indptr[:-1][filled])
        return out

    def transpose_dot(self, vector: np.ndarray) -> np.ndarray:
        """Transpose times vector, by scattering each entry onto its column."""
        scaled = self.data * np.asarray(vector, dtype=np.float64).ravel()[
            self._row_of_entry()]
        out = np.zeros(self.shape[1], dtype=np.float64)
        np.add.at(out, self.indices, scaled)
        return out

    def __matmul__(self, vector: np.ndarray) -> np.ndarray:
        return self.dot(np.asarray(vector, dtype=np.float64).ravel())

    @property
    def T(self) -> "_TransposeView":
        """Transpose as a view, so ``A.T @ v`` costs no extra storage."""
        return _TransposeView(self)


class _TransposeView:
    """Applies A.T without materialising the transpose."""

    def __init__(self, matrix: CSRMatrix) -> None:
        self._matrix = matrix

    def dot(self, vector: np.ndarray) -> np.ndarray:
        return self._matrix.transpose_dot(np.asarray(vector, dtype=np.float64).ravel())

    def __matmul__(self, vector: np.ndarray) -> np.ndarray:
        return self.dot(vector)


@dataclass(frozen=True)
class SolverInfo:
    """What the solver achieved, so callers never have to guess."""

    converged: bool
    iterations: int
    residual: float


def conjugate_gradient(
    matrix: CSRMatrix,
    rhs: np.ndarray,
    iterations: int = 200,
    tolerance: float = 1e-10,
    preconditioner: Optional[Callable] = None,
) -> tuple:
    """Solve ``matrix @ x = rhs`` by conjugate gradients.

    Returns ``(x, SolverInfo)``. A run that does not converge is returned as-is
    with ``converged=False``; the caller decides whether to keep the old answer
    rather than silently using a half-solved one.
    """
    rhs = np.asarray(rhs, dtype=np.float64).ravel()
    size = rhs.size
    if size == 0:
        return np.zeros(0), SolverInfo(True, 0, 0.0)

    x = np.zeros(size, dtype=np.float64)
    residual = rhs.copy()
    initial = float(np.linalg.norm(residual))
    if initial <= tolerance:
        return x, SolverInfo(True, 0, initial)

    z = preconditioner(residual) if preconditioner else residual.copy()
    direction = z.copy()
    rz = float(residual @ z)
    used = 0

    for used in range(1, iterations + 1):
        applied = matrix.dot(direction)
        denominator = float(direction @ applied)
        if denominator <= 0.0 or not np.isfinite(denominator):
            break
        step = rz / denominator
        x += step * direction
        residual -= step * applied
        if float(np.linalg.norm(residual)) <= tolerance * max(initial, 1.0):
            break
        z = preconditioner(residual) if preconditioner else residual.copy()
        next_rz = float(residual @ z)
        if rz == 0.0:
            break
        direction = z + (next_rz / rz) * direction
        rz = next_rz

    norm = float(np.linalg.norm(residual))
    return x, SolverInfo(norm <= tolerance * max(initial, 1.0), used, norm)


def _add_diagonal(matrix: CSRMatrix, amount: float) -> CSRMatrix:
    """A copy of the matrix with ``amount`` added to its diagonal."""
    size = matrix.shape[0]
    rows: list = []
    cols: list = []
    values: list = []
    for row in range(size):
        index_cols, data = matrix._row(row) if hasattr(matrix, "_row") else (None, None)
        del index_cols, data
        break
    # Walk the stored rows directly; CSRMatrix.rows() is the public accessor.
    for row, (row_cols, row_data) in enumerate(matrix.rows()):
        seen = False
        for col, value in zip(row_cols, row_data):
            rows.append(row)
            cols.append(col)
            values.append(value + amount if col == row else value)
            seen = seen or col == row
        if not seen:
            rows.append(row)
            cols.append(row)
            values.append(amount)

    indptr = np.zeros(size + 1, dtype=np.int64)
    np.cumsum(np.bincount(np.asarray(rows, dtype=np.int64), minlength=size), out=indptr[1:])
    return CSRMatrix(
        data=np.asarray(values, dtype=np.float64),
        indices=np.asarray(cols, dtype=np.int64),
        indptr=indptr,
        shape=(size, size),
    )


def solve_spd(
    matrix: CSRMatrix,
    rhs: np.ndarray,
    iterations: int = 500,
    tolerance: float = 1e-10,
    ridge: float = 1e-10,
    growth_limit: float = 1e3,
) -> tuple:
    """Solve a symmetric semi-definite system, regularising until it converges.

    The ridge starts far below the matrix scale: a Tikhonov term comparable to
    the smallest eigenvalue stops being a regulariser and becomes part of the
    answer, which is how a regularised solve ends up quietly wrong.

    A rank-deficient matrix has arbitrarily large solutions along its near-null
    direction, and a small residual says nothing about those. Escalating the
    ridge fixes some of those; anything that still needs a solution orders of
    magnitude larger than the right-hand side is reported as *not* converged, so
    the caller keeps the previous chart rather than applying a meaningless one.
    """
    diagonal = matrix.diagonal()
    scale = max(float(np.abs(diagonal).max(initial=0.0)), 1.0)
    bound = growth_limit * max(float(np.linalg.norm(rhs)), 1.0)
    current = ridge
    info = SolverInfo(False, 0, float("inf"))

    for _ in range(8):
        shifted = _add_diagonal(matrix, current * scale)
        entries = shifted.diagonal()

        def precondition(vector, d=entries):
            return np.divide(vector, d, out=np.zeros_like(vector), where=d > 0)

        x, info = conjugate_gradient(
            shifted, rhs, iterations=iterations, tolerance=tolerance,
            preconditioner=precondition,
        )
        if not info.converged:
            current *= 100.0
            continue
        if not np.all(np.isfinite(x)) or float(np.linalg.norm(x)) > bound:
            return x, SolverInfo(False, info.iterations, info.residual)
        return x, info

    return x, info
