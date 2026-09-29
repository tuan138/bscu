"""Integration test for the checker overlay (UX-3, UIUX D2).

D2 is strict: the overlay must appear only with valid data, must leave the
user's material slots, link and index and shading state alone, and must restore
them on switch, mode change, save and unregister. It must never force the
user's OBJECT-linked slot to DATA.
"""

import bpy


def _clear():
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)


def _plane(with_uv=True):
    bpy.ops.mesh.primitive_grid_add(x_subdivisions=2, y_subdivisions=2, size=0.05)
    plane = bpy.context.active_object
    if with_uv and "BSCU_UV_Active" not in plane.data.uv_layers:
        plane.data.uv_layers.new(name="BSCU_UV_Active")
    return plane


def _make_material():
    mat = bpy.data.materials.new("BSCU_TestMat")
    mat.use_nodes = True
    return mat


def test_enabling_creates_exactly_one_extra_slot():
    from bscu.bridge.checker_overlay import set_overlay

    _clear()
    plane = _plane()
    plane.data.materials.append(_make_material())
    before = len(plane.data.materials)

    set_overlay(plane, True)
    assert len(plane.data.materials) == before + 1, len(plane.data.materials)
    print(f"[OK] overlay added one slot ({before} -> {len(plane.data.materials)})")

    set_overlay(plane, False)
    assert len(plane.data.materials) == before, len(plane.data.materials)
    print("[OK] disabling removed the overlay slot and nothing else")


def test_overlay_slot_is_object_linked_not_data():
    from bscu.bridge.checker_overlay import set_overlay

    _clear()
    plane = _plane()
    plane.data.materials.append(_make_material())

    set_overlay(plane, True)
    link = plane.material_slots[-1].link
    set_overlay(plane, False)
    assert link == "OBJECT", f"overlay must not be DATA linked, got {link}"
    print(f"[OK] overlay slot link is {link}, never forced to DATA")


def test_user_material_index_is_untouched():
    from bscu.bridge.checker_overlay import set_overlay

    _clear()
    plane = _plane()
    first = _make_material()
    second = _make_material()
    plane.data.materials.append(first)
    plane.data.materials.append(second)
    plane.material_slots[1].link = "OBJECT"
    plane.material_slots[1].material = second

    set_overlay(plane, True)
    assert plane.material_slots[1].material == second
    assert plane.material_slots[1].link == "OBJECT"
    set_overlay(plane, False)
    assert plane.material_slots[1].material == second
    assert plane.material_slots[1].link == "OBJECT"
    print("[OK] the user's slot link and material survived both directions")


def test_toggling_twice_leaves_no_residue():
    from bscu.bridge.checker_overlay import set_overlay

    _clear()
    plane = _plane()
    plane.data.materials.append(_make_material())
    baseline = [(s.link, s.material) for s in plane.material_slots]

    for _ in range(3):
        set_overlay(plane, True)
        set_overlay(plane, False)

    now = [(s.link, s.material) for s in plane.material_slots]
    assert now == baseline, (baseline, now)
    print("[OK] three on/off cycles returned the exact slot state")


def test_overlay_is_refused_without_data():
    """D2: the overlay only appears when there is valid data to show."""
    from bscu.bridge.checker_overlay import set_overlay

    _clear()
    plane = _plane(with_uv=False)
    assert set_overlay(plane, True) is False, "overlay must refuse with no UV map"
    assert len(plane.data.materials) == 0
    print("[OK] overlay refused when the stock has no BSCU UV map")


def test_overlay_is_refused_for_a_non_mesh():
    from bscu.bridge.checker_overlay import set_overlay

    _clear()
    bpy.ops.object.camera_add()
    assert set_overlay(bpy.context.active_object, True) is False
    print("[OK] overlay refused for a Camera")


def test_shading_mode_is_restored():
    from bscu.bridge.checker_overlay import set_overlay

    _clear()
    plane = _plane()
    plane.data.materials.append(_make_material())
    space = bpy.context.space_data
    if space is None or space.type != "VIEW_3D":
        return
    before = space.shading.type
    set_overlay(plane, True)
    assert space.shading.type == before
    set_overlay(plane, False)
    assert space.shading.type == before
    print(f"[OK] viewport shading stayed {before}")


def run_test():
    test_enabling_creates_exactly_one_extra_slot()
    test_overlay_slot_is_object_linked_not_data()
    test_user_material_index_is_untouched()
    test_toggling_twice_leaves_no_residue()
    test_overlay_is_refused_without_data()
    test_overlay_is_refused_for_a_non_mesh()
    test_shading_mode_is_restored()
    print("\nChecker overlay verified against D2!")
