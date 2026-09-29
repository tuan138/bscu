"""
Bridge package for BSCU. Modules here read and write Blender data on behalf of
the pure core.

Only modules that actually register Blender classes belong in MODULES; plain
read-only helpers are imported directly by their consumers.
"""

from . import checker_overlay, design_store, job_runner, snapshot  # noqa: F401

__all__ = [
    "checker_overlay",
    "design_store",
    "job_runner",
    "snapshot",
]


def shutdown():
    """Restore anything the bridge and the viewport handlers left behind."""
    from .. import draw

    checker_overlay.clear_all()
    design_store.forget_all()
    draw.shutdown()
