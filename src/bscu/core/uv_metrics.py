"""
UV distortion metrics (UX-1, UIUX mục 2.3).

Pure numpy, no bpy and no mathutils. All 3D coordinates are millimetres, so the
density comes out in UV per millimetre.

    rho_f   = sqrt(A_uv,f / A_3d,f)          density
    rho*    = median(rho_f)                  relative benchmark
    delta_f = rho_f / rho* - 1              relative density
    s_f     = sigma_2 / sigma_1              anisotropy of the tangent->UV Jacobian
    D_f     = sqrt(delta_f^2 + (1 - s_f)^2)  composite, never a length error percent

The Jacobian is taken against an orthonormal tangent basis of the 3D triangle,
so shear introduced by the surface curvature does not leak into s_f: s_f
measures pure anisotropy of the map, as the spec requires.

Everything is vectorised over all faces at once. A per-face Python loop with
``np.linalg.svd`` cost 68 seconds on a 200k-triangle mesh, which is the whole
10 Hz preview budget burned on the measurement alone.
"""

from dataclasses import dataclass, field, replace
from typing import Optional

import numpy as np

# Areas below this count as zero, in the units of the input (mm^2 for 3D,
# UV^2 for UV). Deliberately generous so a 1 mm part is not treated as flat.
AREA_EPS = 1e-12
# Singular values at or below this mean the map has collapsed in one direction.
SIGMA_EPS = 1e-12

DEGENERATE_NONE = None
DEGENERATE_ZERO_3D = "ZERO_3D_AREA"
DEGENERATE_ZERO_UV = "ZERO_UV_AREA"


@dataclass(frozen=True)
class FaceMetrics:
    """Per-face measurements, parallel arrays in face order.

    ``degenerate`` holds None for a usable face and a reason string otherwise.
    """

    density: np.ndarray
    anisotropy: np.ndarray
    sigma_max: np.ndarray
    sigma_min: np.ndarray
    area_3d: np.ndarray
    area_uv: np.ndarray
    score: np.ndarray
    flipped: np.ndarray
    degenerate: np.ndarray = field(default=None)

    def __len__(self) -> int:
        return int(self.density.shape[0])

    def valid_mask(self) -> np.ndarray:
        """Boolean mask of faces that carry a usable measurement."""
        return np.array([reason is None for reason in self.degenerate], dtype=bool)


@dataclass(frozen=True)
class MetricSummary:
    """Aggregate view over one surface."""

    rho_star: Optional[float] = None
    rms: float = 0.0
    worst: float = 0.0
    worst_face: Optional[int] = None
    density_min: float = 0.0
    density_max: float = 0.0
    flipped_count: int = 0
    degenerate_count: int = 0


def _svd_2x2(matrix: np.ndarray):
    """Singular values of a stack of 2x2 matrices, largest first.

    Closed form instead of ``np.linalg.svd``: on 200k faces the LAPACK call was
    the single most expensive step in the whole pipeline.
    """
    a, b, c, d = matrix[..., 0, 0], matrix[..., 0, 1], matrix[..., 1, 0], matrix[..., 1, 1]
    e = 0.5 * (a + d)
    f = 0.5 * (d - a)
    g = 0.5 * (c + b)
    h = 0.5 * (c - b)
    q = np.hypot(e, h)
    r = np.hypot(f, g)
    return q + r, np.abs(q - r)


def _compose_scores(metrics: FaceMetrics, rho_star: float, valid: np.ndarray):
    """D_f for every face, leaving degenerate faces at zero."""
    scores = np.zeros(len(metrics))
    if not valid.any():
        return scores
    delta = metrics.density[valid] / rho_star - 1.0
    scores[valid] = np.sqrt(delta**2 + (1.0 - metrics.anisotropy[valid]) ** 2)
    return scores


def compute_face_metrics(verts_mm, uv_coords, faces) -> FaceMetrics:
    """Measure every face of a triangulated surface.

    ``verts_mm``  (V, 3) millimetre positions
    ``uv_coords`` (V, 2) UV coordinates, one row per vertex
    ``faces``     (F, 3) vertex indices, triangles only

    ``score`` is left at zero because D_f needs the density benchmark, which is
    only defined across a whole surface; call :func:`with_scores` for that.
    """
    verts = np.asarray(verts_mm, dtype=np.float64)
    uvs = np.asarray(uv_coords, dtype=np.float64)
    tris = np.asarray(faces, dtype=np.int64).reshape(-1, 3)
    count = tris.shape[0]

    zeros = np.zeros(count)
    degenerate = np.full(count, DEGENERATE_NONE, dtype=object)
    if count == 0:
        return FaceMetrics(
            density=zeros, anisotropy=zeros, sigma_max=zeros, sigma_min=zeros,
            area_3d=zeros, area_uv=zeros, score=zeros,
            flipped=np.zeros(0, dtype=bool), degenerate=degenerate,
        )

    p0 = verts[tris[:, 0]]
    p1 = verts[tris[:, 1]]
    p2 = verts[tris[:, 2]]
    u0 = uvs[tris[:, 0]]
    u1 = uvs[tris[:, 1]]
    u2 = uvs[tris[:, 2]]

    edge1 = p1 - p0
    edge2 = p2 - p0
    cross = np.cross(edge1, edge2)
    twice_area_3d = np.linalg.norm(cross, axis=1)
    area_3d = twice_area_3d / 2.0

    du = u1 - u0
    dv = u2 - u0
    signed_area_uv = du[:, 0] * dv[:, 1] - du[:, 1] * dv[:, 0]
    area_uv = np.abs(signed_area_uv) / 2.0

    flat_3d = twice_area_3d <= AREA_EPS
    flat_uv = area_uv <= AREA_EPS
    degenerate[flat_3d] = DEGENERATE_ZERO_3D
    degenerate[flat_uv & ~flat_3d] = DEGENERATE_ZERO_UV
    usable = ~(flat_3d | flat_uv)

    # Orthonormal tangent basis of each triangle. The basis lives in the
    # triangle's own plane, so |det(B)| equals twice the 3D area and B is
    # invertible for every face that passed the area test.
    length1 = np.linalg.norm(edge1, axis=1)
    e1 = np.divide(edge1, length1[:, None], out=np.zeros_like(edge1),
                   where=length1[:, None] > 0.0)
    normal = np.divide(cross, twice_area_3d[:, None], out=np.zeros_like(cross),
                       where=twice_area_3d[:, None] > 0.0)
    e2 = np.cross(normal, e1)

    b_matrix = np.empty((count, 2, 2))
    b_matrix[:, 0, 0] = np.einsum("ij,ij->i", edge1, e1)
    b_matrix[:, 0, 1] = np.einsum("ij,ij->i", edge2, e1)
    b_matrix[:, 1, 0] = np.einsum("ij,ij->i", edge1, e2)
    b_matrix[:, 1, 1] = np.einsum("ij,ij->i", edge2, e2)

    u_matrix = np.empty((count, 2, 2))
    u_matrix[:, 0, 0] = du[:, 0]
    u_matrix[:, 0, 1] = dv[:, 0]
    u_matrix[:, 1, 0] = du[:, 1]
    u_matrix[:, 1, 1] = dv[:, 1]

    determinant = b_matrix[:, 0, 0] * b_matrix[:, 1, 1] - b_matrix[:, 0, 1] * b_matrix[:, 1, 0]
    inverse = np.empty_like(b_matrix)
    safe = np.abs(determinant) > 0.0
    inverse[:, 0, 0] = np.where(safe, b_matrix[:, 1, 1] / np.where(safe, determinant, 1.0), 0.0)
    inverse[:, 1, 1] = np.where(safe, b_matrix[:, 0, 0] / np.where(safe, determinant, 1.0), 0.0)
    inverse[:, 0, 1] = np.where(safe, -b_matrix[:, 0, 1] / np.where(safe, determinant, 1.0), 0.0)
    inverse[:, 1, 0] = np.where(safe, -b_matrix[:, 1, 0] / np.where(safe, determinant, 1.0), 0.0)

    jacobian = u_matrix @ inverse
    s_max, s_min = _svd_2x2(jacobian)

    anisotropy = np.where(s_max > SIGMA_EPS, s_min / np.where(s_max > SIGMA_EPS, s_max, 1.0), 0.0)
    density = np.sqrt(area_uv / np.where(area_3d > AREA_EPS, area_3d, 1.0))

    return FaceMetrics(
        density=np.where(usable, density, 0.0),
        anisotropy=np.where(usable, anisotropy, 0.0),
        sigma_max=np.where(usable, s_max, 0.0),
        sigma_min=np.where(usable, s_min, 0.0),
        area_3d=area_3d,
        area_uv=area_uv,
        score=np.zeros(count),
        flipped=(signed_area_uv < 0.0) & usable,
        degenerate=degenerate,
    )


def benchmark_density(metrics: FaceMetrics) -> Optional[float]:
    """rho* = median density over usable faces, or None if there are none."""
    valid = metrics.valid_mask()
    if not valid.any():
        return None
    return float(np.median(metrics.density[valid]))


def with_scores(metrics: FaceMetrics) -> FaceMetrics:
    """Return a copy with D_f filled in, using the surface's own benchmark."""
    valid = metrics.valid_mask()
    rho_star = benchmark_density(metrics)
    if rho_star is None:
        return replace(metrics, score=np.zeros(len(metrics)))
    return replace(metrics, score=_compose_scores(metrics, rho_star, valid))


def summarise(metrics: FaceMetrics) -> MetricSummary:
    """Reduce per-face metrics to the numbers the panels report.

    Degenerate faces are excluded from the benchmark: they have no meaningful
    density, and letting them into the median would shift every other face.
    """
    valid = metrics.valid_mask()
    degenerate_count = int((~valid).sum())
    flipped_count = int(metrics.flipped.sum())

    rho_star = benchmark_density(metrics)
    if rho_star is None:
        return MetricSummary(
            rho_star=None,
            rms=0.0,
            worst=0.0,
            worst_face=None,
            flipped_count=flipped_count,
            degenerate_count=degenerate_count,
        )

    scores = _compose_scores(metrics, rho_star, valid)
    areas = metrics.area_3d[valid]
    total_area = float(areas.sum())
    rms = float(np.sqrt((areas * scores[valid] ** 2).sum() / total_area))

    valid_indices = np.flatnonzero(valid)
    worst_local = int(np.argmax(scores[valid]))
    return MetricSummary(
        rho_star=rho_star,
        rms=rms,
        worst=float(scores[valid][worst_local]),
        worst_face=int(valid_indices[worst_local]),
        density_min=float(metrics.density[valid].min()),
        density_max=float(metrics.density[valid].max()),
        flipped_count=flipped_count,
        degenerate_count=degenerate_count,
    )
