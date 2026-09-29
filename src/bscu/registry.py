"""
Registering Blender classes, exactly once.

Blender raises when a class is registered twice, and an add-on gets asked to
register twice in ordinary use: a hot reload, enabling the installed copy while
the source tree is already loaded, or a packaging test that does both. Handling
that by catching the error and carrying on leaves the module half registered,
which fails later and further away.

So the check happens before the call, per class, and both directions are
symmetrical. This is the same discipline the document handlers already follow
for the same reason.
"""

import bpy

#: What this copy of the add-on has registered. Blender's own check is on the
#: RNA name, which a PropertyGroup does not always carry, so the record is ours.
_registered: set = set()


def register_classes(classes) -> int:
    """Register the classes this copy has not registered yet."""
    added = 0
    for cls in classes:
        if cls.__name__ in _registered:
            continue
        bpy.utils.register_class(cls)
        _registered.add(cls.__name__)
        added += 1
    return added


def unregister_classes(classes) -> int:
    """Unregister what this copy registered, newest first."""
    removed = 0
    for cls in reversed(tuple(classes)):
        if cls.__name__ not in _registered:
            continue
        bpy.utils.unregister_class(cls)
        _registered.discard(cls.__name__)
        removed += 1
    return removed


def forget() -> None:
    """Drop the record, for a reload that replaced every class object."""
    _registered.clear()


__all__ = ("forget", "register_classes", "unregister_classes")
