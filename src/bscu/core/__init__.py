"""
Core pure-python logic for BSCU.
"""

from .constants import (
    DEFAULT_BASE_HEIGHT_MM,
    DEFAULT_BEVEL_ANGLE_DEG,
    DEFAULT_BEVEL_DEPTH_MM,
    GN_SDF_RELIEF_TREE,
    PROP_BASE_HEIGHT,
    PROP_BEVEL_ANGLE,
)
from .math_utils import (
    calculate_bevel_slope_height,
    compute_stock_bounding_box,
    meters_to_mm,
    mm_to_meters,
)
from .reloader import reload_bscu_modules
from .types import CNCBlendMode, CNCCurveMetadata, CNCProfileShape, CNCToolProfile

__all__ = [
    "DEFAULT_BASE_HEIGHT_MM",
    "DEFAULT_BEVEL_ANGLE_DEG",
    "DEFAULT_BEVEL_DEPTH_MM",
    "GN_SDF_RELIEF_TREE",
    "PROP_BASE_HEIGHT",
    "PROP_BEVEL_ANGLE",
    "calculate_bevel_slope_height",
    "compute_stock_bounding_box",
    "meters_to_mm",
    "mm_to_meters",
    "reload_bscu_modules",
    "CNCBlendMode",
    "CNCCurveMetadata",
    "CNCProfileShape",
    "CNCToolProfile",
]
