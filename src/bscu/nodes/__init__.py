"""
Blender-side construction: the geometry node groups BSCU owns.

The groups are built on first use rather than at register time, because
Blender restricts ``bpy.data`` during parts of enable and load.
"""

from . import relief_displace  # noqa: F401

MODULES = (relief_displace,)


def register():
    """Nothing to register: the groups are built on first use."""


def unregister():
    relief_displace.clear_all()


def shutdown():
    """Called by the bridge on undo, redo and file load."""
    relief_displace.clear_all()
