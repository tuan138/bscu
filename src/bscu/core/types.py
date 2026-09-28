"""
Data types, Enums, and Dataclasses for CNC relief sculpting.
Pure Python module (NO bpy dependencies).
"""

from dataclasses import dataclass
from enum import IntEnum


class CNCProfileShape(IntEnum):
    """Profile cross-section shape for closed curve bevels."""

    FLAT = 0
    DOME = 1
    PYRAMID = 2


class CNCBlendMode(IntEnum):
    """Relief blend operation mode."""

    ADD = 1  # Positive relief (đắp dương)
    SUBTRACT = -1  # Carved recess (khoét âm)


class CNCToolProfile(IntEnum):
    """Tool bit geometry for open-curve carving."""

    V_BIT = 0
    BALL_NOSE = 1
    END_MILL = 2


@dataclass(frozen=True)
class CNCCurveMetadata:
    """Immutable data record holding CNC carving parameters for a curve."""

    base_height: float
    bevel_angle: float
    bevel_depth: float
    profile_shape: CNCProfileShape = CNCProfileShape.FLAT
    blend_mode: CNCBlendMode = CNCBlendMode.ADD
