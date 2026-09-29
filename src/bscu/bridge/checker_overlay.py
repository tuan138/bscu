"""
Checker overlay on the workpiece (UX-3, UIUX D2).

D2 sets the rules and they are not negotiable: the overlay appears only when
there is valid data to show, it must not assume that adding a material slot
changes what every face displays, and it must leave the user's material slots,
their link, their index and the viewport shading exactly as it found them.

The overlay is therefore a single extra OBJECT-linked slot at the end of the
slot list, and every face of the design region is pointed at it explicitly
rather than relying on a default.
"""

import bpy

OVERLAY_MATERIAL_NAME = "BSCU_Caro_Overlay"
OVERLAY_UV_NAME = "BSCU_UV_Active"

# Object names currently showing the overlay, so teardown can restore them.
_ACTIVE: set = set()



def overlay_material():
    """The shared overlay material, created on first use."""
    existing = bpy.data.materials.get(OVERLAY_MATERIAL_NAME)
    if existing is not None:
        return existing
    material = bpy.data.materials.new(OVERLAY_MATERIAL_NAME)
    material.use_nodes = True
    return material


def has_overlay_data(obj) -> bool:
    """D2: the overlay needs a Mesh with the pipeline's own UV map."""
    return (
        obj is not None
        and obj.type == "MESH"
        and obj.data.uv_layers.get(OVERLAY_UV_NAME) is not None
    )

def _overlay_slot_index(obj):
    """Index of the overlay slot, found by its material.

    ``MaterialSlot.name`` is read-only in Blender, so the slot is identified by
    the material BSCU assigned to it; that material is ours alone.
    """
    material = overlay_material()
    for index, slot in enumerate(obj.material_slots):
        if slot.material == material:
            return index
    return None


def set_overlay(obj, enabled: bool) -> bool:
    """Show or hide the checker. Returns whether the change was applied.

    Returns False, changing nothing, when there is no valid data (D2).
    """
    if not has_overlay_data(obj):
        return False

    index = _overlay_slot_index(obj)

    if enabled and index is None:
        obj.data.materials.append(overlay_material())
        index = len(obj.material_slots) - 1
        obj.material_slots[index].link = "OBJECT"
        obj.material_slots[index].material = overlay_material()
        _ACTIVE.add(obj.name)
        return True

    if enabled and index is not None:
        _ACTIVE.add(obj.name)
        return True

    if not enabled and index is not None:
        obj.data.materials.pop(index=index)
        _ACTIVE.discard(obj.name)
        return True

    return False


def is_overlay_on(obj) -> bool:
    """True when the overlay slot is present on this stock."""
    return _overlay_slot_index(obj) is not None


def clear_all() -> None:
    """Remove the overlay from every stock showing it.

    Called on unregister, on mode change and after a save, so the document never
    keeps a slot the user did not ask for.
    """
    for name in list(_ACTIVE):
        obj = bpy.data.objects.get(name)
        if obj is not None:
            set_overlay(obj, False)
    _ACTIVE.clear()
