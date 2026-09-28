"""
BSCU - Parametric 2.5D CNC Sculpting Workflow in Blender.
"""

bl_info = {
    "name": "BSCU - Parametric 2.5D CNC Sculptor",
    "author": "BSCU Team",
    "version": (1, 0, 0),
    "blender": (4, 2, 0),
    "location": "View3D > Sidebar > BSCU",
    "description": "Parametric 2.5D CNC sculpting and relief generator using procedural SDF",
    "category": "3D View",
}

try:
    import bpy

    from . import operators
except ImportError:
    bpy = None
    operators = None


def register():
    if operators:
        operators.register()
        print("[BSCU] Addon successfully registered.")


def unregister():
    if operators:
        operators.unregister()
        print("[BSCU] Addon successfully unregistered.")


if __name__ == "__main__":
    register()
