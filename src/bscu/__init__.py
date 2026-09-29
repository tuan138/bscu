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

    from . import bridge, operators, properties, ui

    MODULES = (properties, ui, operators)
except ImportError:
    bpy = None
    MODULES = ()


def _restore_document_state(*_args) -> None:
    """Undo everything the bridge left on the document (D2).

    Blender calls undo/redo/load handlers with varying arguments, so the
    signature has to absorb them.
    """
    if "bridge" in globals():
        bridge.shutdown()


_HANDLER_LISTS = ("undo_post", "redo_post", "load_post")


def _install_handlers() -> None:
    """Register the document handlers exactly once.

    A reloaded module is a different function object, so stale handlers from a
    previous load would otherwise pile up and be called many times per event.
    """
    for name in _HANDLER_LISTS:
        handlers = getattr(bpy.app.handlers, name)
        for stale in [h for h in handlers if getattr(h, "__name__", "") == _restore_document_state.__name__]:
            handlers.remove(stale)
        handlers.append(_restore_document_state)


def _remove_handlers() -> None:
    for name in _HANDLER_LISTS:
        handlers = getattr(bpy.app.handlers, name)
        for stale in [h for h in handlers if getattr(h, "__name__", "") == _restore_document_state.__name__]:
            handlers.remove(stale)


def register():
    for module in MODULES:
        module.register()
    _install_handlers()
    print("[BSCU] Addon successfully registered.")


def unregister():
    if bpy is None:
        return

    _remove_handlers()

    if "bridge" in globals():
        bridge.shutdown()

    for module in reversed(MODULES):
        module.unregister()
    print("[BSCU] Addon successfully unregistered.")


if __name__ == "__main__":
    register()
