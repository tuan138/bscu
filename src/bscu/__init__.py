"""
BSCU - Parametric 2.5D CNC Sculpting Workflow in Blender.

Entry point only: import the sub-packages and let each one register itself.
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

    from . import operators, properties, ui

    MODULES = (properties, ui, operators)
except ImportError:
    bpy = None
    MODULES = ()


def register():
    for module in MODULES:
        module.register()
    print("[BSCU] Addon successfully registered.")


def unregister():
    for module in reversed(MODULES):
        module.unregister()
    print("[BSCU] Addon successfully unregistered.")


if __name__ == "__main__":
    register()
