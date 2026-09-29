"""
Weighted chart solver: keep shape, keep size, or a blend (UX-5, UIUX 3B.4).

A chart is a connected piece of surface with no seam through it. Turning it into
a layout is one least-squares problem with two kinds of term:

* **Keep shape.** Each triangle contributes its two conformal equations, the
  linear conditions its UV corner angles must satisfy to match the real ones.
  Weighted by ``1 - blend``.
* **Keep size.** Each triangle contributes one area equation saying its UV area
  should be its wanted area. Weighted by ``blend``.

The Tab 2 brushes move the *wanted* area: the expand brush raises a face's
density, and its area target goes up with it. Sliding ``blend`` towards one
end is the "keep shape / keep size" control the spec asks for, and the same
slider lets one region outvote another.

Both blocks are linearised about the incoming layout, so the whole system stays
sparse, symmetric and solvable with the pipeline's own CG. Pinned vertices are
substituted out exactly rather than penalised; a penalty weight squares the
condition number and leaves the iteration unable to converge.
"""

from dataclasses import dataclass
from typing import Tuple

import numpy as np

from bscu.core.sparse_cg import CSRMatrix, SolverInfo, solve_spd

#: Column stride between a vertex's U and V unknown.
U = 0
V = 1


@dataclass(frozen=True)
class ChartProblem:
    """One chart's layout problem, ready to solve."""

    faces: np.ndarray
    """(F, 3) local vertex indices of each triangle."""

    coords: np.ndarray
    """(N, 2) the layout to start from and to linearise about."""

    weights: np.ndarray
    """(F,) relative importance of each triangle's conformal term."""

    pins: Tuple[int, int]
    """Two local vertex indices held at their current coordinates."""

    density: np.ndarray = None
    """(F,) wanted density per face; the expand and shrink brushes write this."""

    areas: np.ndarray = None
    """(F,) explicit wanted UV area per face, overriding the density hint."""

    blend: float = 0.0
    """0 keeps shape only, 1 keeps size only, in between blends the two."""


def pin_columns(pins: Tuple[int, int], vertex_count: int) -> np.ndarray:
    """The unknown columns held fixed by a pin pair."""
    columns = []
    for vertex in pins:
        if not 0 <= vertex < vertex_count:
            raise ValueError(f"pinned vertex {vertex} is outside the chart")
        columns.append(vertex * 2 + U)
        columns.append(vertex * 2 + V)
    return np.asarray(columns, dtype=np.int64)


def face_areas(uv: np.ndarray, faces: np.ndarray) -> np.ndarray:
    """Twice the signed area of every triangle in a layout."""
    points = np.asarray(uv, dtype=np.float64).reshape(-1, 2)
    triangles = np.asarray(faces, dtype=np.int64).reshape(-1, 3)
    first = points[triangles[:, 1]] - points[triangles[:, 0]]
    second = points[triangles[:, 2]] - points[triangles[:, 0]]
    return first[:, 0] * second[:, 1] - first[:, 1] * second[:, 0]


def wanted_areas(uv: np.ndarray, faces: np.ndarray, density: np.ndarray) -> np.ndarray:
    """The area each face should get, from the base layout and a density hint.

    Density is relative: a face painted twice as dense gets twice the area the
    unweighted layout gave it, and the total stays whatever the base layout
    chose, so the grid scale does not drift.
    """
    base = np.abs(face_areas(uv, faces))
    return base * np.asarray(density, dtype=np.float64).ravel()


def _outer_block(columns: np.ndarray, coefficients: np.ndarray,
                 scale: np.ndarray, residual) -> tuple:
    """Coordinate triples of A.T @ A for a block of equal-length rows.

    Every row of such a block touches the same number of unknowns, so the outer
    product of the block with itself can be laid out with numpy instead of a
    loop over a hundred thousand triangles.
    """
    width = columns.shape[1]
    weighted = coefficients * scale[:, None]
    row_index = np.repeat(columns, width, axis=1).reshape(-1)
    col_index = np.tile(columns, (1, width)).reshape(-1)
    outer = weighted[:, :, None] * weighted[:, None, :]
    return (row_index, col_index, outer.reshape(-1),
            columns.reshape(-1), (weighted * residual[:, None]).reshape(-1))


def build_normal_equations(problem: ChartProblem) -> Tuple[CSRMatrix, np.ndarray]:
    """Assemble the free block of the normal equations and its right-hand side.

    Returns a matrix of shape (free, free) and a right-hand side of size free,
    where *free* is every unknown except the pinned ones.
    """
    faces = np.asarray(problem.faces, dtype=np.int64).reshape(-1, 3)
    coords = np.asarray(problem.coords, dtype=np.float64).reshape(-1, 2)
    weights = np.asarray(problem.weights, dtype=np.float64).ravel()
    if weights.size != faces.shape[0]:
        raise ValueError(
            f"got {weights.size} weights for {faces.shape[0]} faces; they must match"
        )
    if np.any(weights < 0.0):
        raise ValueError("a negative face weight would invert its equation")
    blend = float(problem.blend)
    if not 0.0 <= blend <= 1.0:
        raise ValueError(f"blend must sit between 0 and 1, got {blend}")

    vertex_count = coords.shape[0]
    size = vertex_count * 2
    pinned = pin_columns(problem.pins, vertex_count)
    is_pinned = np.zeros(size, dtype=bool)
    is_pinned[pinned] = True
    known = np.zeros(size, dtype=np.float64)
    known[pinned] = coords.reshape(-1)[pinned]

    free_columns = np.flatnonzero(~is_pinned)
    remap = np.full(size, -1, dtype=np.int64)
    remap[free_columns] = np.arange(free_columns.size)
    rhs = np.zeros(free_columns.size, dtype=np.float64)
    if not faces.size:
        return CSRMatrix.empty(free_columns.size), rhs

    rows: list = []
    rhs_cols: list = []
    rhs_vals: list = []

    if blend < 1.0:
        x = coords[faces[:, 0], 0], coords[faces[:, 1], 0], coords[faces[:, 2], 0]
        y = coords[faces[:, 0], 1], coords[faces[:, 1], 1], coords[faces[:, 2], 1]
        # Normalising each face's coefficients makes a weight mean the same
        # thing on a dense chart and on a coarse one.
        magnitude = np.maximum(
            np.abs(x[1] - x[2]) + np.abs(x[2] - x[0]) + np.abs(x[0] - x[1])
            + np.abs(y[1] - y[2]) + np.abs(y[2] - y[0]) + np.abs(y[0] - y[1]),
            1e-12,
        )
        scale = weights * (1.0 - blend) * magnitude
        for offset, coefficients in ((U, (x[1] - x[2], x[2] - x[0], x[0] - x[1])),
                                     (V, (y[1] - y[2], y[2] - y[0], y[0] - y[1]))):
            stacked = np.stack([np.asarray(c, dtype=np.float64)
                                for c in coefficients], axis=1)
            block = _outer_block(faces * 2 + offset, stacked, scale, np.zeros(len(faces)))
            rows.append(block[:3])
            rhs_cols.append(block[3])
            rhs_vals.append(block[4])

    if blend > 0.0:
        block = _area_block(problem, faces, coords, blend)
        rows.append(block[:3])
        rhs_cols.append(block[3])
        rhs_vals.append(block[4])

    row_index = np.concatenate([part[0] for part in rows])
    col_index = np.concatenate([part[1] for part in rows])
    entries = np.concatenate([part[2] for part in rows])

    free_row = ~is_pinned[row_index]
    free_col = ~is_pinned[col_index]
    # An entry touching a pinned column becomes a right-hand side term: the
    # pinned value is known, so it moves across the equation. Only the
    # free-row orientation is used, because the matrix is symmetric and the
    # mirrored triples are the same terms counted twice.
    to_rhs = free_row & ~free_col
    np.add.at(rhs, remap[row_index[to_rhs]],
              -entries[to_rhs] * known[col_index[to_rhs]])

    own_cols = np.concatenate(rhs_cols)
    own_vals = np.concatenate(rhs_vals)
    own_free = ~is_pinned[own_cols]
    np.add.at(rhs, remap[own_cols[own_free]], own_vals[own_free])

    keep = free_row & free_col
    return CSRMatrix.from_coo(
        remap[row_index[keep]], remap[col_index[keep]], entries[keep],
        (free_columns.size, free_columns.size),
    ), rhs


def _area_block(problem, faces, coords, blend):
    """One linearised area equation per face, and its right-hand side.

    Twice the signed area of a triangle is bilinear in its UV corners, so its
    gradient with respect to the layout is exactly linear and "this face should
    have that area" becomes a linear equation to solve.
    """
    current = face_areas(coords, faces)
    if problem.areas is not None:
        target = np.abs(np.asarray(problem.areas, dtype=np.float64).ravel())
    else:
        density = (np.ones(faces.shape[0]) if problem.density is None
                   else np.asarray(problem.density, dtype=np.float64).ravel())
        target = np.abs(wanted_areas(coords, faces, density))
    residual = target - current

    points = coords[faces]
    first = points[:, 1] - points[:, 0]
    second = points[:, 2] - points[:, 0]
    # Gradient of (first.x * second.y - first.y * second.x), two per corner.
    coefficients = np.stack([
        -second[:, 1] + first[:, 1], second[:, 0] - first[:, 0],
        second[:, 1], -second[:, 0],
        -first[:, 1], first[:, 0],
    ], axis=1)
    columns = np.empty((faces.shape[0], 6), dtype=np.int64)
    for corner in range(3):
        columns[:, 2 * corner] = faces[:, corner] * 2 + U
        columns[:, 2 * corner + 1] = faces[:, corner] * 2 + V
    magnitude = np.maximum(np.abs(coefficients).sum(axis=1), 1e-12)
    return _outer_block(columns, coefficients,
                        np.full(faces.shape[0], blend) / magnitude, residual)


def solve_chart(problem: ChartProblem, iterations: int = 400) -> Tuple[np.ndarray, SolverInfo]:
    """Solve one chart and return (uv, info).

    The result is reported, never invented: a chart that will not converge comes
    back with ``converged=False`` and the caller keeps the previous layout.
    """
    coords = np.asarray(problem.coords, dtype=np.float64).reshape(-1, 2)
    vertex_count = coords.shape[0]
    if not np.asarray(problem.faces).size:
        return coords.copy(), SolverInfo(False, 0, float("inf"))

    matrix, rhs = build_normal_equations(problem)
    solution, info = solve_spd(matrix, rhs, iterations=iterations)
    if not info.converged or not np.all(np.isfinite(solution)):
        return coords.copy(), info

    uv = coords.copy()
    pinned = pin_columns(problem.pins, vertex_count)
    free = np.setdiff1d(np.arange(vertex_count * 2), pinned)
    uv.reshape(-1)[free] = solution
    return uv, info
