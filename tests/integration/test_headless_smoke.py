"""
Headless smoke test for Level 2 debugging.
Verifies Curve creation, Custom Properties assignment, and Geometry Nodes socket inspection.
"""

import bpy


def run_test():
    print("[Level 2 Test] Initializing clean scene...")
    bpy.ops.wm.read_factory_settings(use_empty=True)

    print("[Level 2 Test] Creating Closed Bezier Curve...")
    bpy.ops.curve.primitive_bezier_circle_add(radius=2.0, location=(0, 0, 0))
    curve_obj = bpy.context.active_object
    assert curve_obj is not None, "Failed to create curve object"
    assert curve_obj.type == "CURVE", f"Object type is {curve_obj.type}, expected CURVE"

    print("[Level 2 Test] Assigning CNC Metadata Properties...")
    curve_obj["cnc_base_height"] = 10.0
    curve_obj["cnc_bevel_angle"] = 45.0
    curve_obj["cnc_profile_shape"] = 1  # Dome

    assert curve_obj["cnc_base_height"] == 10.0
    assert curve_obj["cnc_bevel_angle"] == 45.0
    assert curve_obj["cnc_profile_shape"] == 1
    print("[Level 2 Test] Custom Properties successfully validated.")

    print("[Level 2 Test] Creating Geometry Nodes modifier...")
    mod = curve_obj.modifiers.new(name="BSCUGN", type="NODES")
    node_group = bpy.data.node_groups.new(name="BSCU_SDF_Test", type="GeometryNodeTree")
    mod.node_group = node_group

    # In Blender 4.x/5.x, sockets are added via interface
    node_group.interface.new_socket(
        name="Geometry", in_out="INPUT", socket_type="NodeSocketGeometry"
    )
    node_group.interface.new_socket(
        name="Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry"
    )
    in_height = node_group.interface.new_socket(
        name="Base Height", in_out="INPUT", socket_type="NodeSocketFloat"
    )
    in_height.default_value = 10.0

    print(
        f"[Level 2 Test] Node Group interface sockets count: {len(node_group.interface.items_tree)}"
    )
    assert len(node_group.interface.items_tree) == 3, "Failed to create required node sockets"

    print("[Level 2 Test] Evaluating Dependency Graph...")
    depsgraph = bpy.context.evaluated_depsgraph_get()
    eval_obj = curve_obj.evaluated_get(depsgraph)
    assert eval_obj is not None, "Failed to evaluate object in depsgraph"

    print("[Level 2 Test] ALL ASSERTIONS PASSED SUCCESSFULLY!")


if __name__ == "__main__":
    run_test()
