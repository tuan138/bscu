"""
The node group a colour overlay is drawn with (UX-12, UIUX 10.1).

Each overlay layer is one node group, so a user can open it and change how
their layer looks without touching the rest of the material. The group is
assigned to a material and never to the mesh: the workpiece keeps its own
material and slot (D2), and this only paints into the result.

The group reads a mask sampled from ``BSCU_UV_Active`` and mixes the layer's
colour over the surface by it. The mask bleeds past seams, because a band of
unpainted surface along every seam reads as a mistake in the overlay rather
than as a padding that was set too small.
"""

from typing import Tuple

import bpy

#: The node group BSCU owns for one layer.
GROUP_PREFIX = "BSCU_Overlay_"

#: The image attribute a layer's mask is written to.
MASK_ATTRIBUTE = "bscu_overlay_mask"

#: The UV map the masks are sampled through.
UV_MAP = "BSCU_UV_Active"

#: How far a mask bleeds past a seam, in millimetres. Too little and the seam
#: shows as an unpainted line; too much and a layer colours its neighbour.
DEFAULT_PADDING_MM = 0.25

MM_PER_METRE = 1000.0


def group_name(layer_name: str) -> str:
    """The node group name BSCU owns for a layer."""
    return f"{GROUP_PREFIX}{layer_name}"


def build_group(layer_name: str, colour: Tuple[float, float, float, float] = (1.0, 0.0, 0.0, 1.0),
                opacity: float = 1.0) -> bpy.types.NodeTree:
    """The node group one overlay layer is drawn with.

    Built per layer so the user can open it and change their own shading, which
    is the point of the group rather than a hard-wired material.
    """
    name = group_name(layer_name)
    stale = bpy.data.node_groups.get(name)
    if stale is not None:
        bpy.data.node_groups.remove(stale)
    group = bpy.data.node_groups.new(name, "ShaderNodeTree")

    group.interface.new_socket("Mask", in_out="INPUT",
                               socket_type="NodeSocketFloat")
    group.interface.new_socket("Mask", in_out="OUTPUT",
                               socket_type="NodeSocketFloat")
    strength_socket = group.interface.new_socket(
        "Strength", in_out="INPUT", socket_type="NodeSocketFloat")
    # Set on the item, not as a keyword: new_socket takes no default_value.
    strength_socket.default_value = float(opacity)

    nodes, links = group.nodes, group.links
    entry = nodes.new("NodeGroupInput")
    exit_node = nodes.new("NodeGroupOutput")
    strength = nodes.new("ShaderNodeMath")
    strength.operation = "MULTIPLY"
    entry.location = (-400, 0)
    strength.location = (-100, 0)
    exit_node.location = (200, 0)

    # The mask is baked with its seam padding already in it, so the group is
    # only a strength and a pass-through. The UV node is left in place because
    # the group is the user's to edit, and this is the map it would be sampled
    # through.
    uv = nodes.new("ShaderNodeUVMap")
    uv.location = (-400, 240)
    uv.uv_map = UV_MAP

    links.new(entry.outputs["Strength"], strength.inputs[0])
    links.new(entry.outputs["Mask"], strength.inputs[1])
    links.new(strength.outputs[0], exit_node.inputs["Mask"])
    return group


def ensure_group(layer_name: str, colour=(1.0, 0.0, 0.0, 1.0),
                 opacity: float = 1.0):
    """The layer's group, built on first use.

    Deliberately not built while the add-on registers: Blender restricts
    ``bpy.data`` during parts of enable and load, and a group that cannot be
    made then would take the whole add-on with it.
    """
    existing = bpy.data.node_groups.get(group_name(layer_name))
    if existing is not None:
        return existing
    return build_group(layer_name, colour, opacity)


def write_mask(obj, values, layer_name: str = "default") -> str:
    """Write a layer's mask onto a mesh and return the attribute name used.

    One attribute per layer, so two overlays do not paint over each other's
    bookkeeping.
    """
    import numpy as np

    data = np.asarray(values, dtype=np.float32).ravel()
    mesh = obj.data
    if data.size != len(mesh.polygons):
        raise ValueError(f"got {data.size} mask values for {len(mesh.polygons)} "
                         f"faces; they have to match")
    name = f"{MASK_ATTRIBUTE}_{layer_name}"
    attribute = mesh.attributes.get(name) or mesh.attributes.new(
        name=name, type="FLOAT", domain="FACE")
    attribute.data.foreach_set("value", data)
    mesh.update()
    return name


def read_mask(obj, layer_name: str = "default"):
    """A layer's mask, or nothing when the layer has never been painted."""
    import numpy as np

    attribute = obj.data.attributes.get(f"{MASK_ATTRIBUTE}_{layer_name}")
    if attribute is None:
        return np.zeros(0, dtype=np.float32)
    return np.asarray([item.value for item in attribute.data], dtype=np.float32)


def padding_in_uv(padding_mm: float, mm_across_uv: float) -> float:
    """Seam padding in UV units for a map that spans a known physical size.

    Expressed against the part's own size, so a mask does not shrink or grow
    with the export resolution: the same pad in millimetres is the same band of
    unpainted seam whichever resolution the image was made at.
    """
    if mm_across_uv <= 0.0:
        raise ValueError("a map of no size cannot have its padding worked out")
    return max(0.0, float(padding_mm) / mm_across_uv)


def clear_all() -> None:
    """Drop the overlay groups BSCU owns, on shutdown."""
    for group in list(bpy.data.node_groups):
        if group.name.startswith(GROUP_PREFIX):
            bpy.data.node_groups.remove(group)


__all__ = ("DEFAULT_PADDING_MM", "GROUP_PREFIX", "MASK_ATTRIBUTE",
           "MM_PER_METRE", "UV_MAP", "build_group", "clear_all", "ensure_group",
           "group_name", "padding_in_uv", "read_mask", "write_mask")
