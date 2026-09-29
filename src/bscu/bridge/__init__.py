"""
Bridge package. Modules here read and write Blender data on behalf of
the pure core.

Imports are lazy. A good deal of what lives here is plain numpy that happens to
produce something a Blender material will read later, and dragging ``bpy`` in
through a package import would make that untestable outside Blender for no
reason. Only the modules that register classes need Blender at import time, and
they are reached through their own name.
"""

from typing import Any

__all__ = [
    "checker_overlay",
    "design_store",
    "export_mesh",
    "job_runner",
    "material_builder",
    "preview_image",
    "seam_bridge",
    "snapshot",
    "uv_bridge",
]


def __getattr__(name: str) -> Any:
    """Import a bridge module the first time it is asked for by name."""
    if name in __all__:
        import importlib

        return importlib.import_module(f".{name}", __name__)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list:
    return sorted(__all__)


def shutdown() -> None:
    """Restore anything the bridge and the viewport handlers left behind."""
    from .. import draw

    checker_overlay = __getattr__("checker_overlay")
    design_store = __getattr__("design_store")
    checker_overlay.clear_all()
    design_store.forget_all()
    draw.shutdown()
