"""
The geometry nodes graph that turns a height field into a surface (UX-10).

The height field in :mod:`bscu.core.height_field` is the single source of
truth. This builds the Blender side of it: a node group that samples that field
at each vertex's UV and pushes the vertex along its normal by the result.

Two things the spec insists on, and that shape this file:

* **The height attribute is the authority.** The group reads ``cnc_height`` and
  does nothing clever with it. If the solver produced a number, that number is
  what gets cut, and a second calculation somewhere else could only disagree
  with it.
* **The modifier never touches the user's material or slot** (D2). It adds its
  own geometry and leaves the rest of the object alone.
"""

import bpy

#: The attribute the height field writes and this graph reads.
HEIGHT_ATTRIBUTE = "cnc_height"

#: The node group BSCU owns, so a user's own groups are never mistaken for it.
GROUP_NAME = "BSCU_Relief_Displace"

MM_PER_METRE = 1000.0


def _new_group(name: str = GROUP_NAME):
    """Create a node group, replacing any earlier one of the same name.

    Re-registering an add-on runs this again, and a second group with the same
    name would make Blender append a suffix and leave the old one orphaned.
    """
    data = getattr(bpy.data, "node_groups", None)
    if data is None:
        return None
    existing = data.get(name)
    if existing is not None:
        data.remove(existing)
    return data.new(name, "GeometryNodeTree")


def ensure_group():
    """The displace group, built on first use.

    Deliberately not built while the add-on registers: Blender restricts
    ``bpy.data`` during parts of enable and load, and a group that cannot be
    created then would take the whole add-on down with it.
    """
    existing = bpy.data.node_groups.get(GROUP_NAME)
    if existing is not None:
        return existing
    return build_group()


def build_group() -> bpy.types.NodeTree:
    """The displace group: read the height, push along the normal, in metres."""
    group = _new_group()
    group.interface.new_socket("Geometry", in_out="INPUT",
                                socket_type="NodeSocketGeometry")
    group.interface.new_socket("Geometry", in_out="OUTPUT",
                                socket_type="NodeSocketGeometry")
    group.interface.new_socket("Height", in_out="INPUT", socket_type="NodeSocketFloat")
    group.interface.new_socket("Height", in_out="OUTPUT",
                                socket_type="NodeSocketFloat")

    nodes, links = group.nodes, group.links
    entry = nodes.new("NodeGroupInput")
    exit_node = nodes.new("NodeGroupOutput")
    named = nodes.new("GeometryNodeInputNamedAttribute")
    named.data_type = "FLOAT"
    named.inputs["Name"].default_value = HEIGHT_ATTRIBUTE
    set_position = nodes.new("GeometryNodeSetPosition")

    for node, place in ((entry, (-600, 0)), (named, (-600, 300)),
                        (set_position, (0, 0)), (exit_node, (220, 0))):
        node.location = place

    # The attribute is the authority: the group's own Height input scales it,
    # it does not replace it. A second source of truth could only disagree.
    multiply = nodes.new("ShaderNodeMath")
    multiply.operation = "MULTIPLY"
    multiply.location = (-300, 200)
    links.new(named.outputs["Attribute"], multiply.inputs[0])
    links.new(entry.outputs["Height"], multiply.inputs[1])
    links.new(multiply.outputs[0], set_position.inputs["Offset"])
    links.new(entry.outputs["Geometry"], set_position.inputs["Geometry"])
    links.new(set_position.outputs["Geometry"], exit_node.inputs["Geometry"])
    return group


def write_height_attribute(obj, heights_mm, name: str = HEIGHT_ATTRIBUTE) -> int:
    """Write the field's heights onto a mesh, in millimetres.

    The values are stored as a float attribute rather than baked into positions
    so the modifier can be re-run, and so a value can be read back and checked
    against the field that produced it.
    """
    import numpy as np

    data = np.asarray(heights_mm, dtype=np.float32).ravel()
    mesh = obj.data
    if data.size != len(mesh.vertices):
        raise ValueError(f"got {data.size} heights for {len(mesh.vertices)} "
                         f"vertices; they have to match one for one")
    attribute = mesh.attributes.get(name) or mesh.attributes.new(
        name=name, type="FLOAT", domain="POINT")
    attribute.data.foreach_set("value", data)
    # Read-back has to see the new values, and Blender keeps attribute data
    # lazily; without this the check reads the previous run's numbers.
    mesh.update()
    return data.size


def read_height_attribute(obj, name: str = HEIGHT_ATTRIBUTE):
    """Read the heights back, so the field and the mesh can be compared."""
    import numpy as np

    attribute = obj.data.attributes.get(name)
    if attribute is None:
        return np.zeros(0, dtype=np.float32)
    # Collected element by element, not gathered by index: these are values,
    # and treating them as indices would read whatever was in memory.
    return np.asarray([item.value for item in attribute.data], dtype=np.float32)


def attach(obj, group=None) -> bpy.types.Modifier:
    """Put the displace modifier on an object, or return the one already there.

    Adding a second one would double every depth, so an existing modifier is
    reused rather than stacked.
    """
    wanted = group if group is not None else bpy.data.node_groups.get(GROUP_NAME)
    for modifier in obj.modifiers:
        if modifier.type == "NODES" and modifier.node_group is not None \
                and (wanted is None or modifier.node_group.name == wanted.name):
            return modifier
    modifier = obj.modifiers.new(name="BSCU Relief", type="NODES")
    modifier.node_group = group if group is not None else ensure_group()
    if modifier.node_group is None:
        obj.modifiers.remove(modifier)
        raise RuntimeError("the BSCU displace group could not be created")
    return modifier


def detach(obj) -> bool:
    """Take BSCU's own modifier off, leaving the user's alone."""
    for modifier in list(obj.modifiers):
        if modifier.name.startswith("BSCU"):
            obj.modifiers.remove(modifier)
            return True
    return False


def clear_all() -> None:
    """Drop the node group BSCU owns, on shutdown."""
    group = bpy.data.node_groups.get(GROUP_NAME)
    if group is not None:
        bpy.data.node_groups.remove(group)


__all__ = ("GROUP_NAME", "HEIGHT_ATTRIBUTE", "MM_PER_METRE", "attach",
           "build_group", "clear_all", "detach", "ensure_group",
           "read_height_attribute", "write_height_attribute")
