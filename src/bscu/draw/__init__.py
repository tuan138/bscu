"""
Viewport drawing for BSCU. Handlers attach on register and come off on unregister.
"""

from . import seam_overlay


def register():
    """Attach the viewport handlers."""
    seam_overlay.install()


def unregister():
    """Detach them, so a reload does not stack handlers."""
    seam_overlay.shutdown()


def shutdown():
    """Called by the bridge on undo, redo and file load."""
    seam_overlay.shutdown()
