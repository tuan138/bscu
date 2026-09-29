"""
Mathematical and morphological calculations for SDF relief generation.
Pure Python module (NO bpy dependencies).
"""

import math
from dataclasses import dataclass
from typing import Tuple

import numpy as np


def mm_to_meters(val_mm: float) -> float:
    """Convert millimeter value to meters for Blender internal units."""
    return val_mm * 0.001


def meters_to_mm(val_m: float) -> float:
    """Convert meter value from Blender internal units to millimeters."""
    return val_m * 1000.0


def calculate_bevel_slope_height(
    dist_mm: float, bevel_angle_deg: float, base_height_mm: float
) -> float:
    """
    Calculate relief height from SDF boundary distance and bevel slope angle.
    Clamps maximum height to base_height to prevent geometric piercing.
    """
    if dist_mm <= 0.0:
        return 0.0

    angle_rad = math.radians(min(max(bevel_angle_deg, 0.0), 89.99))
    raw_height = dist_mm * math.tan(angle_rad)
    return min(raw_height, base_height_mm)


def compute_stock_bounding_box(
    length_mm: float, width_mm: float, thickness_mm: float
) -> Tuple[Tuple[float, float, float], Tuple[float, float, float]]:
    """Compute local bounding box coordinates for stock block."""
    half_x = length_mm / 2.0
    half_y = width_mm / 2.0
    min_pt = (-half_x, -half_y, 0.0)
    max_pt = (half_x, half_y, thickness_mm)
    return min_pt, max_pt


@dataclass(frozen=True)
class Similarity:
    """A 2D similarity: one uniform scale, one rotation, one translation."""

    scale: float
    angle: float
    offset: np.ndarray

    def apply(self, points: np.ndarray) -> np.ndarray:
        """Move points through the transform."""
        data = np.asarray(points, dtype=np.float64).reshape(-1, 2)
        cos, sin = math.cos(self.angle), math.sin(self.angle)
        rotation = np.array([[cos, -sin], [sin, cos]], dtype=np.float64)
        return data @ (rotation * self.scale).T + self.offset


def similarity_fit(source: np.ndarray, target: np.ndarray) -> Similarity:
    """The scale, rotation and translation that best map source onto target.

    An unwrap that matches its target up to a rigid motion is a correct unwrap,
    and this fit is how a test says so without pinning down the motion itself.
    """
    src = np.asarray(source, dtype=np.float64).reshape(-1, 2)
    dst = np.asarray(target, dtype=np.float64).reshape(-1, 2)
    if src.shape != dst.shape:
        raise ValueError(f"need matching point sets, got {src.shape} and {dst.shape}")
    if src.shape[0] == 0:
        raise ValueError("cannot fit a transform through no points")

    centred_src = src - src.mean(axis=0)
    centred_dst = dst - dst.mean(axis=0)
    denominator = float((centred_src * centred_src).sum())
    if denominator == 0.0:
        raise ValueError("cannot fit a transform through coincident points")

    # Complex form: the best multiplier is sum(conj(a) * b) / sum(|a|^2).
    real = float((centred_src * centred_dst).sum())
    imag = float(
        (centred_src[:, 0] * centred_dst[:, 1]).sum()
        - (centred_src[:, 1] * centred_dst[:, 0]).sum()
    )
    scale = math.hypot(real, imag) / denominator
    angle = math.atan2(imag, real)
    rotation = np.array(
        [[math.cos(angle), -math.sin(angle)], [math.sin(angle), math.cos(angle)]],
        dtype=np.float64,
    ) * scale
    return Similarity(scale, angle, dst.mean(axis=0) - src.mean(axis=0) @ rotation)


def plane_frame(points3d: np.ndarray) -> np.ndarray:
    """Flatten points onto the plane that best fits them, keeping two axes.

    A chart has to start from somewhere, and a degenerate starting frame gives
    the conformal solver nothing to work with. Projecting onto the best-fit
    plane is the standard opening move, and it is also the honest way to ask
    "how much would this chart distort if it were flattened", since that is
    exactly what the projection produces.
    """
    points = np.asarray(points3d, dtype=np.float64).reshape(-1, 3)
    if len(points) == 0:
        return np.zeros((0, 2), dtype=np.float64)
    centred = points - points.mean(axis=0)
    if not np.any(centred):
        return np.zeros((len(points), 2), dtype=np.float64)
    values, vectors = np.linalg.eigh(centred.T @ centred)
    axes = vectors[:, np.argsort(values)[::-1][:2]]
    return centred @ axes
