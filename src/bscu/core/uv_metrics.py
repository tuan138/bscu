"""
UV distortion metrics (UX-1, UIUX mục 2.3).

Pure numpy; no bpy and no mathutils. All 3D coordinates are millimetres, so the
density comes out in UV per millimetre.

    rho_f   = sqrt(A_uv,f / A_3d,f)          density
    rho*    = median(rho_f)                  relative benchmark
    delta_f = rho_f / rho* - 1              relative density
    s_f     = sigma_2 / sigma_1              anisotropy of the tangent->UV Jacobian
    D_f     = sqrt(delta_f^2 + (1 - s_f)^2)  composite, never a length error percent

The Jacobian is taken against an orthonormal tangent basis of the 3D triangle,
so shear introduced by the surface curvature does not leak into s_f: s_f
measures pure anisotropy of the map, as the spec requires.
"""

from dataclasses import dataclass, field, replace
from typing import Optional

import numpy as np

# Areas at or below this count as zero, in the units of the input (mm^2 for 3D,
# UV^2 for UV). Deliberately generous so a 1 mm part is not treated as flat.
AREA_EPS = 1e-12
# Singular values at or below this mean the map has collapsed in one direction.
SIGMA_EPS = 1e-12


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


def _tangent_frame(p0, p1, p2):
    """Orthonormal 2x3 tangent basis of the triangle, or None if it is flat."""
    cross = np.cross(p1 - p0, p2 - p0)
    twice_area = float(np.linalg.norm(cross))
    if twice_area <= 0.0:
        return None
    e1 = p1 - p0
    e1 = e1 / np.linalg.norm(e1)
    e2 = np.cross(cross / twice_area, e1)
    return np.stack([e1, e2])


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
    tris = np.asarray(faces, dtype=np.int64)
    count = tris.shape[0]

    density = np.zeros(count)
    anisotropy = np.zeros(count)
    sigma_max = np.zeros(count)
    sigma_min = np.zeros(count)
    area_3d = np.zeros(count)
    area_uv = np.zeros(count)
    flipped = np.zeros(count, dtype=bool)
    degenerate = np.full(count, None, dtype=object)

    for index in range(count):
        i0, i1, i2 = tris[index]
        p0, p1, p2 = verts[i0], verts[i1], verts[i2]
        u0, u1, u2 = uvs[i0], uvs[i1], uvs[i2]

        basis = _tangent_frame(p0, p1, p2)
        if basis is None:
            degenerate[index] = "ZERO_3D_AREA"
            continue
        tri_area_3d = float(np.linalg.norm(np.cross(p1 - p0, p2 - p0))) / 2.0
        area_3d[index] = tri_area_3d
        if tri_area_3d <= AREA_EPS:
            degenerate[index] = "ZERO_3D_AREA"
            continue

        du = u1 - u0
        dv = u2 - u0
        signed_area_uv = du[0] * dv[1] - du[1] * dv[0]
        area_uv[index] = abs(signed_area_uv) / 2.0
        if area_uv[index] <= AREA_EPS:
            degenerate[index] = "ZERO_UV_AREA"
            continue

        flipped[index] = signed_area_uv < 0.0

        # B holds the triangle edges in the orthonormal tangent frame, U holds
        # the same edges in UV; J = U @ inv(B) maps tangent coords to UV coords.
        # The basis is orthonormal inside the triangle plane, so |det(B)| is
        # twice the 3D area and B is invertible for every non-flat face.
        edge1 = p1 - p0
        edge2 = p2 - p0
        b_matrix = np.array(
            [
                [edge1 @ basis[0], edge2 @ basis[0]],
                [edge1 @ basis[1], edge2 @ basis[1]],
            ]
        )
        u_matrix = np.array([[du[0], dv[0]], [du[1], dv[1]]])

        sigma = np.linalg.svd(u_matrix @ np.linalg.inv(b_matrix), compute_uv=False)
        s_max, s_min = float(sigma[0]), float(sigma[1])

        sigma_max[index] = s_max
        sigma_min[index] = s_min
        anisotropy[index] = s_min / s_max if s_max > SIGMA_EPS else 0.0
        density[index] = np.sqrt(area_uv[index] / tri_area_3d)

    return FaceMetrics(
        density=density,
        anisotropy=anisotropy,
        sigma_max=sigma_max,
        sigma_min=sigma_min,
        area_3d=area_3d,
        area_uv=area_uv,
        score=np.zeros(count),
        flipped=flipped,
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
