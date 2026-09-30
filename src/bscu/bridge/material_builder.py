"""
The material that paints a relief area with a colour (UX-12, UIUX 10.1).

One material per workpiece, named after it, holding the base shader and one
node group per overlay layer mixed by its mask. The user's own shading stays
where it was: the material is added as a new object slot and BSCU fills that
slot, so nothing about the original material or the original slot changes (D2).

The mask is sampled from ``BSCU_UV_Active``, with the padding across seams the
spec asks for. Padding matters more than it sounds: without it a band of
unpainted surface shows along every seam, and the user reads that as a mistake
in their overlay.
"""

from dataclasses import dataclass
from typing import Optional, Sequence, Tuple

import bpy

#: The material BSCU owns, found by name so it is never mistaken for a user's.
OVERLAY_MATERIAL_PREFIX = "BSCU_Relief_"

#: The image attribute the overlay masks are written to.
MASK_ATTRIBUTE = "bscu_overlay_mask"

#: How far a mask bleeds past a seam, in UV units. Too little and the seam shows
#: as an unpainted line; too much and one layer colours its neighbour.
DEFAULT_PADDING = 0.002


@dataclass
class LayerSpec:
    """One overlay layer, as the material builder needs it."""

    name: str
    colour: Tuple[float, float, float, float] = (1.0, 0.0, 0.0, 1.0)
    blend: str = "MIX"
    opacity: float = 1.0

    def __post_init__(self) -> None:
        if self.blend not in ("MIX", "ADD", "MULTIPLY", "SUBTRACT"):
            raise ValueError(f"{self.blend!r} is not a blend mode this "
                             f"material can do")
        if not 0.0 <= float(self.opacity) <= 1.0:
            raise ValueError(f"opacity runs from 0 to 1, got {self.opacity}")


def material_name(obj) -> str:
    """The material name BSCU owns for a workpiece."""
    return f"{OVERLAY_MATERIAL_PREFIX}{obj.name}"


def find_material(obj):
    """BSCU's material for this workpiece, or None when it has not been built."""
    return bpy.data.materials.get(material_name(obj))


def build_material(obj, layers: Sequence[LayerSpec] = ()) -> bpy.types.Material:
    """Build (or rebuild) the relief material for a workpiece.

    Rebuilding replaces BSCU's own material only. Anything the user made is
    left alone, and so is the slot it was in.
    """
    name = material_name(obj)
    existing = bpy.data.materials.get(name)
    if existing is not None:
        bpy.data.materials.remove(existing)

    material = bpy.data.materials.new(name)
    material.use_nodes = True
    tree = material.node_tree
    tree.nodes.clear()

    output = tree.nodes.new("ShaderNodeOutputMaterial")
    output.location = (400, 0)
    surface = tree.nodes.new("ShaderNodeBsdfPrincipled")
    surface.location = (100, 0)
    tree.links.new(surface.outputs["BSDF"], output.inputs["Surface"])

    # Layers blend the base colour rather than the shader itself: a coloured
    # overlay is paint on a surface, not a second surface. ShaderNodeMixShader
    # has no data_type and no inputs[6] - it is ShaderNodeMix, in RGBA mode.
    # The base colour is itself a node output, because a socket on the
    # Principled node is an *input* and cannot feed another input.
    base_colour = tree.nodes.new("ShaderNodeRGB")
    base_colour.location = (-100, -200)
    base_colour.outputs[0].default_value = surface.inputs["Base Color"].default_value
    previous = base_colour.outputs[0]
    for index, layer in enumerate(layers):
        place = (100 + index * 240, -200)
        mix = tree.nodes.new("ShaderNodeMix")
        mix.location = place
        mix.data_type = "RGBA"
        mix.blend_type = layer.blend
        mix.inputs["Factor"].default_value = float(layer.opacity)
        colour = tree.nodes.new("ShaderNodeRGB")
        colour.location = (place[0] - 180, place[1] - 120)
        colour.outputs[0].default_value = layer.colour
        # A and B are separate sockets; A carries what was already there and
        # B the layer's own colour, so the layers stack in the order given.
        tree.links.new(previous, mix.inputs[6])
        tree.links.new(colour.outputs[0], mix.inputs[7])
        previous = mix.outputs[2]
    tree.links.new(previous, surface.inputs["Base Color"])
    return material


def attach_slot(obj, material) -> int:
    """Add BSCU's material as an object slot and return the index.

    An object slot, always. D2 forbids forcing the user's own slot to be data
    linked, and a data slot here would replace every face on the object.
    """
    for index, slot in enumerate(obj.material_slots):
        if slot.material is material:
            return index
    obj.data.materials.append(material)
    index = len(obj.material_slots) - 1
    slot = obj.material_slots[index]
    # Switching a slot to OBJECT clears it: the object level override starts
    # empty and the mesh's material stops showing through. Assigning after the
    # switch is the only order that leaves the slot actually filled, and an
    # empty overlay slot is an object that renders unpainted with no warning.
    slot.link = "OBJECT"
    slot.material = material
    return index


def enable(obj, layers: Sequence[LayerSpec] = ()) -> bool:
    """Show the overlay, building whatever is missing.

    Refuses rather than raises when there is nothing to paint against: no active
    BSCU map, or not a mesh, is a reason to do nothing, not a crash.
    """
    if obj is None or obj.type != "MESH":
        return False
    if not obj.data.uv_layers.get("BSCU_UV_Active"):
        return False
    material = find_material(obj) or build_material(obj, layers)
    attach_slot(obj, material)
    return True


def disable(obj) -> bool:
    """Take BSCU's slot away and nothing else."""
    material = find_material(obj)
    if material is None:
        return False
    index = _overlay_slot(obj, material)
    if index is None:
        return False
    # The object-level override is cleared first. Popping only the mesh data
    # leaves the object slot holding the material, and a datablock with a user
    # is never collected - which is how BSCU's material ended up orphaned with
    # the user's still in place.
    obj.material_slots[index].material = None
    obj.data.materials.pop(index=index)
    # Removed on its own count, not on whether the mesh happens to have another
    # material: a user material on the object would otherwise leave BSCU's
    # datablock behind with no user, which is exactly what pack files warn about.
    if material.users == 0:
        bpy.data.materials.remove(material)
    return True


def _overlay_slot(obj, material) -> Optional[int]:
    """The index of BSCU's slot on this object, or None."""
    for index, slot in enumerate(obj.material_slots):
        if slot.material is material:
            return index
    return None


def write_mask_attribute(obj, values, name: str = MASK_ATTRIBUTE) -> int:
    """Write the overlay mask onto a mesh, one value per face."""
    import numpy as np

    data = np.asarray(values, dtype=np.float32).ravel()
    mesh = obj.data
    if data.size != len(mesh.polygons):
        raise ValueError(f"got {data.size} mask values for "
                         f"{len(mesh.polygons)} faces; they have to match")
    attribute = mesh.attributes.get(name) or mesh.attributes.new(
        name=name, type="FLOAT", domain="FACE")
    attribute.data.foreach_set("value", data)
    mesh.update()
    return data.size


def padding_for(px_per_mm: float, padding_mm: float = DEFAULT_PADDING) -> float:
    """Seam padding in UV units for a given image resolution.

    Expressed in pixels at the sampling rate the spec sets, so a mask does not
    shrink or grow with the export resolution.
    """
    if px_per_mm <= 0.0:
        raise ValueError("a sampling rate of zero pixels per millimetre gives "
                         "no padding to speak of")
    return max(0.0, padding_mm * px_per_mm)


__all__ = ("DEFAULT_PADDING", "MASK_ATTRIBUTE", "OVERLAY_MATERIAL_PREFIX",
           "LayerSpec", "attach_slot", "build_material", "disable", "enable",
           "find_material", "material_name", "padding_for",
           "write_mask_attribute")
