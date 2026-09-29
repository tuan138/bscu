"""Headless integration test for the UX-0 add-on skeleton.

Verifies the real Blender-side contract: registration is clean and repeatable,
the 4 step tabs exist in the View3D N-panel, and the step facts reflect the
actual scene.
"""

import bpy

_registered = False


def _ensure_registered():
    """Register BSCU once; later tests reuse the same registration."""
    global _registered
    if _registered:
        return
    import bscu

    bscu.register()
    _registered = True


def _bscu_panels() -> dict:
    found = {}
    for attr in dir(bpy.types):
        obj = getattr(bpy.types, attr)
        if not isinstance(obj, type) or not issubclass(obj, bpy.types.Panel):
            continue
        if obj.__module__.startswith("bscu"):
            found[obj.bl_idname] = obj
    return found


def _statuses(facts) -> dict:
    from bscu.core.workflow import STEP_ORDER, derive_step_status

    return dict(zip(STEP_ORDER, [s.value for s in derive_step_status(facts)]))


def test_register_unregister_cycle_is_clean():
    """Full teardown must leave no BSCU class or WindowManager pointer behind."""
    import bscu

    _ensure_registered()
    bscu.unregister()

    leaked = _bscu_panels()
    assert not leaked, f"Panels still registered after unregister: {sorted(leaked)}"
    assert not hasattr(bpy.types.WindowManager, "bscu_ui"), "bscu_ui pointer survived"

    bscu.register()
    globals()["_registered"] = True
    print("[OK] register/unregister cycle leaves nothing behind")


def test_all_step_panels_exist():
    _ensure_registered()
    expected = {
        "BSCU_PT_steps",
        "BSCU_PT_stock",
        "BSCU_PT_caro",
        "BSCU_PT_layout",
        "BSCU_PT_relief",
    }
    missing = expected - set(_bscu_panels())
    assert not missing, f"Missing panels: {sorted(missing)}"
    print(f"[OK] panels present: {sorted(_bscu_panels())}")


def test_panels_live_in_view3d_sidebar():
    _ensure_registered()
    for name, cls in _bscu_panels().items():
        assert cls.bl_space_type == "VIEW_3D", f"{name}: {cls.bl_space_type}"
        assert cls.bl_category == "BSCU", f"{name}: {cls.bl_category}"
    print("[OK] every BSCU panel is in View3D > Sidebar > BSCU")

def test_active_tab_defaults_to_stock():
    _ensure_registered()
    active = bpy.context.window_manager.bscu_ui.active_tab
    assert active == "STOCK", active
    print("[OK] active_tab defaults to STOCK")



def test_set_step_operator_switches_tab():
    _ensure_registered()
    wm = bpy.context.window_manager
    original = wm.bscu_ui.active_tab
    try:
        result = bpy.ops.bscu.set_step(step="LAYOUT")
        assert "FINISHED" in result, result
        assert wm.bscu_ui.active_tab == "LAYOUT", wm.bscu_ui.active_tab
    finally:
        wm.bscu_ui.active_tab = original
    print("[OK] bscu.set_step switches the active tab")


def test_empty_scene_reports_nothing_done():
    from bscu.ui.context import collect_step_facts

    _ensure_registered()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    _ensure_registered()
    statuses = _statuses(collect_step_facts())
    assert set(statuses.values()) == {"NOT_DONE"}, statuses
    print("[OK] empty scene -> every step NOT_DONE")


def test_selected_mesh_completes_stock_step():
    from bscu.ui.context import collect_step_facts

    _ensure_registered()
    bpy.ops.mesh.primitive_cube_add()
    statuses = _statuses(collect_step_facts())
    assert statuses["STOCK"] == "DONE", statuses
    assert statuses["SEAM"] == "NOT_DONE", statuses
    print("[OK] selected Mesh -> STOCK DONE, later steps untouched")


def test_non_mesh_selection_is_not_an_accepted_stock():
    from bscu.ui.context import collect_step_facts

    _ensure_registered()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    _ensure_registered()
    bpy.ops.object.camera_add()
    bpy.context.view_layer.objects.active = bpy.data.objects["Camera"]
    statuses = _statuses(collect_step_facts())
    assert statuses["STOCK"] == "NOT_DONE", statuses
    print("[OK] Camera selection -> STOCK not accepted")


def run_test():
    test_register_unregister_cycle_is_clean()
    test_all_step_panels_exist()
    test_panels_live_in_view3d_sidebar()
    test_active_tab_defaults_to_stock()
    test_set_step_operator_switches_tab()
    test_empty_scene_reports_nothing_done()
    test_selected_mesh_completes_stock_step()
    test_non_mesh_selection_is_not_an_accepted_stock()
    print("\nAll UX-0 skeleton integration tests passed!")
