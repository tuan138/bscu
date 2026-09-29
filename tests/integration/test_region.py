"""Integration test for the design region (UX-3, UIUX 2.1/2.7).

The region is either the whole workpiece or the selected faces. It must not
default to reaching round to the back, must survive save/load, and must be
reported as a face count so the user can see what they picked.
"""

import bpy

from bscu.bridge.region import (
    RegionError,
    clear_region,
    read_region,
    region_face_count,
    select_whole_stock,
    set_region_from_selection,
)

_registered = False


def _ensure_registered():
    """Install the add-on so the document handlers exist and are current."""
    global _registered
    if _registered:
        return
    import bscu

    bscu.register()
    _registered = True



def _clear():
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)


def _solid():
    bpy.ops.mesh.primitive_cube_add(size=0.05)
    return bpy.context.active_object


def _uv_sphere():
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.03, segments=16, ring_count=8)
    return bpy.context.active_object


def test_whole_stock_covers_every_face():
    _clear()
    sphere = _uv_sphere()
    select_whole_stock(sphere)
    assert region_face_count(sphere) == len(sphere.data.polygons)
    print(f"[OK] whole stock covers all {len(sphere.data.polygons)} faces")


def test_selection_region_keeps_only_the_selected_faces():
    _clear()
    sphere = _uv_sphere()
    for face in sphere.data.polygons:
        face.select = face.index < 5
    picked = sum(1 for p in sphere.data.polygons if p.select)
    assert picked == 5, picked

    set_region_from_selection(sphere)
    assert region_face_count(sphere) == 5, region_face_count(sphere)
    print(f"[OK] selection region keeps exactly {picked} faces")



def test_empty_selection_is_reported_not_guessed():
    """UIUX 2.7: never silently widen the region to the whole mesh."""
    _ensure_registered()
    _clear()
    sphere = _uv_sphere()
    for face in sphere.data.polygons:
        face.select = False

    try:
        set_region_from_selection(sphere)
    except RegionError as error:
        assert "select" in str(error).lower(), error
        print(f"[OK] empty selection refused: {error}")
        return
    raise AssertionError("expected RegionError for an empty selection")


def test_a_stale_region_survives_object_mode_switches():
    _clear()
    cube = _solid()
    select_whole_stock(cube)
    before = read_region(cube)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.object.mode_set(mode="OBJECT")
    assert read_region(cube) == before
    print(f"[OK] region unchanged across mode switches: {before.mode}")


def test_region_survives_save_and_load():
    _clear()
    cube = _solid()
    cube.name = "PhoiRegion"
    select_whole_stock(cube)
    expected = read_region(cube)
    path = bpy.app.tempdir + "bscu_region.blend"
    bpy.ops.wm.save_as_mainfile(filepath=path)

    bpy.ops.wm.open_mainfile(filepath=path)
    reloaded = bpy.data.objects["PhoiRegion"]
    assert read_region(reloaded) == expected, (expected, read_region(reloaded))
    print(f"[OK] region survived save/load as {expected.mode}")


def test_cleared_region_falls_back_to_nothing():
    _clear()
    cube = _solid()
    select_whole_stock(cube)
    clear_region(cube)
    assert read_region(cube).mode == "NONE"
    assert region_face_count(cube) == 0
    print("[OK] a cleared region reports NONE rather than the whole stock")


def test_region_rejects_a_non_mesh():
    _clear()
    bpy.ops.object.camera_add()
    camera = bpy.context.active_object
    try:
        read_region(camera)
    except RegionError as error:
        assert "Mesh" in str(error), error
        print("[OK] a Camera is refused with a clear reason")
        return
    raise AssertionError("expected RegionError for a non-mesh")


def run_test():
    test_whole_stock_covers_every_face()
    test_selection_region_keeps_only_the_selected_faces()
    test_empty_selection_is_reported_not_guessed()
    test_a_stale_region_survives_object_mode_switches()
    test_region_survives_save_and_load()
    test_cleared_region_falls_back_to_nothing()
    test_region_rejects_a_non_mesh()
    print("\nDesign region verified on real Blender objects!")
