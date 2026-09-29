"""Integration test for the design store on the stock (UX-2, UIUX K2).

K2: the design lives in a Blender datablock, so Undo, Redo and saving use
Blender's own machinery, and one Undo step covers one operator. IDs must never
come back, not even when Undo rewinds the stored counter.
"""

import bpy

from bscu.bridge.design_store import (
    DESIGN_PROPERTY,
    DesignStore,
    forget_all,
)

_registered = False


def _ensure_registered():
    """The design property only exists once the add-on is registered."""
    global _registered
    if _registered:
        return
    import bscu

    bscu.register()
    _registered = True

def _clear():
    """Start from an empty scene with no leftover ID allocators."""
    forget_all()
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)

def _mesh():
    bpy.ops.mesh.primitive_cube_add(size=0.05)
    return bpy.context.active_object


def test_property_is_attached_to_the_stock():
    _ensure_registered()
    _clear()
    cube = _mesh()
    assert hasattr(cube, "bscu_design"), "stock object must carry the design"
    assert DESIGN_PROPERTY in cube.keys() or hasattr(cube, "bscu_design")
    print("[OK] design property is registered on Object")


def test_new_stock_starts_with_no_ids_used():
    _ensure_registered()
    _clear()
    cube = _mesh()
    store = DesignStore(cube)
    assert store.high_water == 0
    assert store.next_id() == 1
    print("[OK] a fresh stock starts allocating at 1")


def test_allocated_id_is_persisted_on_the_object():
    _ensure_registered()
    _clear()
    cube = _mesh()
    store = DesignStore(cube)
    allocated = store.next_id()
    assert cube["bscu_next_id"] == allocated
    assert DesignStore(cube).high_water == allocated
    print(f"[OK] allocated ID {allocated} survives a new store over the same stock")


def test_undo_does_not_hand_back_an_id():
    _ensure_registered()
    _clear()
    cube = _mesh()
    store = DesignStore(cube)
    first = store.next_id()
    second = store.next_id()

    # Simulate Undo rewinding the datablock to the state after `first`.
    cube["bscu_next_id"] = first
    reopened = DesignStore(cube)
    third = reopened.next_id()

    assert third > second, (first, second, third)
    print(f"[OK] after Undo rewound to {first}, the next ID was {third} (> {second})")


def test_redo_keeps_counting_up():
    _ensure_registered()
    _clear()
    cube = _mesh()
    store = DesignStore(cube)
    store.next_id()
    store.next_id()
    higher = store.next_id()
    cube["bscu_next_id"] = 1
    assert DesignStore(cube).next_id() > higher
    print(f"[OK] after Redo to {higher}, IDs keep increasing")


def test_saving_and_reloading_keeps_the_counter():
    _ensure_registered()
    _clear()
    cube = _mesh()
    cube.name = "PhoiID"
    store = DesignStore(cube)
    for _ in range(3):
        store.next_id()
    last = store.high_water
    bpy.ops.wm.save_as_mainfile(filepath=bpy.app.tempdir + "bscu_ids.blend")

    bpy.ops.wm.open_mainfile(filepath=bpy.app.tempdir + "bscu_ids.blend")
    reloaded = bpy.data.objects["PhoiID"]
    assert DesignStore(reloaded).high_water >= last, (last, reloaded["bscu_next_id"])
    assert DesignStore(reloaded).next_id() > last
    print(f"[OK] reload preserved the counter at {last} and moved past it")


def test_two_stocks_keep_independent_counters():
    _ensure_registered()
    _clear()
    first = _mesh()
    second = _mesh()
    a = DesignStore(first)
    a.next_id()
    a.next_id()
    assert DesignStore(second).next_id() == 1
    print("[OK] each stock carries its own design counter")


def run_test():
    test_property_is_attached_to_the_stock()
    test_new_stock_starts_with_no_ids_used()
    test_allocated_id_is_persisted_on_the_object()
    test_undo_does_not_hand_back_an_id()
    test_redo_keeps_counting_up()
    test_saving_and_reloading_keeps_the_counter()
    test_two_stocks_keep_independent_counters()
    print("\nDesign store verified on real Blender objects!")
