"""
Mathematical and morphological calculations for SDF relief generation.
Pure Python module (NO bpy dependencies).
"""

import math
from typing import Tuple


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
