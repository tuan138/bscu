"""
Viewport drawing for BSCU. Handlers attach on install and come off on shutdown.
"""

from . import seam_overlay  # noqa: F401

__all__ = ["seam_overlay"]


def install():
    """Attach the viewport handlers."""
    seam_overlay.install()


def shutdown():
    """Detach them again, so a reload does not stack handlers."""
    seam_overlay.shutdown()
