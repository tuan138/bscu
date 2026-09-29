"""Measure how much Blender's own unwrap blocks the UI (UX-2 gate, D1).

D1 refuses to call a C-level Blender API "a background task" without measuring
it. This suite times the main-thread unwrap at several mesh sizes and reports
the blocking time, so the build order can justify a solver on a snapshot instead
of Blender's operator if the numbers demand it.

It is a measurement, not a pass/fail gate: the printed numbers are the evidence.
"""

import time

import bpy

from bscu.bridge.snapshot import take_snapshot

BSCU_UV = "BSCU_UV_Active"

# Target mesh sizes for the measurement.
SIZES = [(8, 8), (32, 16), (96, 48), (192, 96)]


def _clear():
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)


def _grid(segments, rings):
    bpy.ops.mesh.primitive_grid_add(x_subdivisions=segments, y_subdivisions=rings, size=0.1)
    return bpy.context.active_object


def _unwrap(obj):
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=1.15192, island_margin=0.02)
    bpy.ops.object.mode_set(mode="OBJECT")


def measure_unwrap(segments, rings):
    _clear()
    obj = _grid(segments, rings)
    triangles = len(obj.data.polygons) * 2

    start = time.perf_counter()
    _unwrap(obj)
    blocked_ms = (time.perf_counter() - start) * 1000.0

    if BSCU_UV in obj.data.uv_layers:
        obj.data.uv_layers.remove(obj.data.uv_layers[BSCU_UV])
    obj.data.uv_layers.new(name=BSCU_UV)
    snapshot = take_snapshot(obj, BSCU_UV)
    return triangles, blocked_ms, len(snapshot.faces)


def test_measured_blocking_grows_with_the_mesh():
    """The measurement itself: unwrap cost must rise with triangle count."""
    rows = []
    for segments, rings in SIZES:
        triangles, blocked_ms, measured = measure_unwrap(segments, rings)
        rows.append((triangles, blocked_ms))
        print(
            f"[MEASURE] {triangles:>8} triangles -> unwrap blocked the main thread "
            f"{blocked_ms:8.1f} ms ({measured} measured triangles)"
        )

    assert len(rows) == len(SIZES)
    smallest, largest = rows[0], rows[-1]
    assert largest[0] > smallest[0], rows
    assert largest[1] > smallest[1], (
        f"unwrap of {largest[0]} triangles was not slower than {smallest[0]}: {rows}"
    )

    per_triangle_us = largest[1] * 1000.0 / largest[0]
    print(
        f"[MEASURE] {per_triangle_us:.2f} us per triangle at the largest size; "
        "a 16 ms frame budget is blown above roughly "
        f"{int(16000 / per_triangle_us) if per_triangle_us else 0} triangles"
    )


def test_snapshot_capture_fits_the_preview_budget():
    """UIUX 3.7 asks for 10 Hz preview, so a snapshot has a 100 ms budget."""
    _clear()
    obj = _grid(96, 48)
    _unwrap(obj)
    if BSCU_UV in obj.data.uv_layers:
        obj.data.uv_layers.remove(obj.data.uv_layers[BSCU_UV])
    obj.data.uv_layers.new(name=BSCU_UV)

    triangles = len(obj.data.polygons) * 2
    start = time.perf_counter()
    for _ in range(5):
        take_snapshot(obj, BSCU_UV)
    snapshot_ms = (time.perf_counter() - start) * 1000.0 / 5

    start = time.perf_counter()
    _unwrap(obj)
    unwrap_ms = (time.perf_counter() - start) * 1000.0

    per_triangle_us = snapshot_ms * 1000.0 / triangles
    print(
        f"[MEASURE] snapshot {snapshot_ms:.1f} ms for {triangles} triangles "
        f"({per_triangle_us:.2f} us/tri) vs unwrap {unwrap_ms:.1f} ms"
    )
    print(
        f"[MEASURE] extrapolated to the 200k-triangle acceptance case: "
        f"{per_triangle_us * 200000 / 1000.0:.0f} ms per snapshot, "
        f"{per_triangle_us * 200000 / 100000:.1f} Hz"
    )

    # Reading the data must not dominate the work it feeds; being on the same
    # order as the unwrap is the expected relationship.
    assert snapshot_ms < 4.0 * unwrap_ms, (snapshot_ms, unwrap_ms)
    assert snapshot_ms < 100.0, f"one snapshot already blows the 10 Hz budget: {snapshot_ms}"


def run_test():
    test_measured_blocking_grows_with_the_mesh()
    test_snapshot_capture_fits_the_preview_budget()
    print("\nBlender unwrap blocking time measured on the real main thread!")
