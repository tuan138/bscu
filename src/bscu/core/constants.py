"""
System constants and default values for BSCU CNC sculpting pipeline.
Pure Python module (NO bpy dependencies).
"""

# Default Dimensions (in Millimeters)
DEFAULT_BASE_HEIGHT_MM = 10.0
DEFAULT_BEVEL_ANGLE_DEG = 45.0
DEFAULT_BEVEL_DEPTH_MM = 5.0
DEFAULT_STOCK_LENGTH_MM = 200.0
DEFAULT_STOCK_WIDTH_MM = 300.0
DEFAULT_STOCK_THICKNESS_MM = 50.0

# Tolerance limits
TOLERANCE_MANIFOLD_MM = 0.001
TOLERANCE_DIMENSION_MM = 0.001

# Custom Property Keys
PROP_BASE_HEIGHT = "cnc_base_height"
PROP_BEVEL_ANGLE = "cnc_bevel_angle"
PROP_BEVEL_DEPTH = "cnc_bevel_depth"
PROP_PROFILE_SHAPE = "cnc_profile_shape"
PROP_BLEND_MODE = "cnc_blend_mode"
PROP_TOOL_RADIUS = "cnc_tool_radius"
PROP_TOOL_PROFILE = "cnc_tool_profile"

# Geometry Node Group Names
GN_SDF_RELIEF_TREE = "BSCU_SDF_Procedural_Relief"
GN_SURFACE_DISPLACE_TREE = "BSCU_Surface_Displacement"
