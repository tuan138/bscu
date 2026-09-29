"""Measure the preview pipeline on the 200k-triangle acceptance case.

UIUX 3.7 asks for 10 Hz preview on that case, so this prints the real numbers
for the two stages a preview needs: capture the snapshot, then measure it.
Run with:
    blender/blender.exe -b --python scripts/bench_200k.py
"""

import os
import sys
import time

import bpy

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

# The add-on is auto-enabled from the installed copy at startup, so the
# benchmark has to drop it or it measures whatever was last packaged.
for _name in [m for m in sys.modules if m == "bscu" or m.startswith("bscu.")]:
    del sys.modules[_name]

from bscu.bridge.snapshot import take_snapshot
from bscu.core.uv_islands import check_topology
from bscu.core.uv_metrics import compute_face_metrics, summarise, with_scores

BSCU_UV = "BSCU_UV_Active"
GRID = int(os.environ.get("BSCU_BENCH_GRID", "320"))
REPEATS = 3


def build_workpiece():
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    bpy.ops.mesh.primitive_grid_add(x_subdivisions=GRID, y_subdivisions=GRID, size=1.0)
    obj = bpy.context.active_object
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=1.15192, island_margin=0.02)
    bpy.ops.object.mode_set(mode="OBJECT")
    mesh = obj.data
    if BSCU_UV in mesh.uv_layers:
        mesh.uv_layers.remove(mesh.uv_layers[BSCU_UV])
    mesh.uv_layers.new(name=BSCU_UV)
    return obj


def time_it(label, fn):
    fn()
    start = time.perf_counter()
    for _ in range(REPEATS):
        out = fn()
    return (label, (time.perf_counter() - start) * 1000.0 / REPEATS), out


def main():
    obj = build_workpiece()
    rows = []

    (name, snapshot_ms), snap = time_it(
        "take_snapshot", lambda: take_snapshot(obj, BSCU_UV)
    )
    rows.append((name, snapshot_ms))

    (name, metrics_ms), metrics = time_it(
        "compute_face_metrics",
        lambda: compute_face_metrics(snap.verts_mm, snap.uv, snap.faces),
    )
    rows.append((name, metrics_ms))

    (name, topology_ms), _ = time_it(
        "check_topology", lambda: check_topology(snap.source_faces)
    )
    rows.append((name, topology_ms))

    total = snapshot_ms + metrics_ms + topology_ms
    summary = summarise(with_scores(metrics))

    print("=" * 62)
    print(f"200k acceptance case: {len(snap.faces)} triangles, {len(snap.uv)} split UV rows")
    print("=" * 62)
    for name, ms in rows:
        print(f"  {name:<22} {ms:8.1f} ms")
    print(f"  {'TOTAL':<22} {total:8.1f} ms  ->  {1000.0 / total:5.2f} Hz")
    print(f"  budget for 10 Hz is 100.0 ms -> {'PASS' if total < 100.0 else 'FAIL'}")
    print(f"  rms_D={summary.rms:.4f} flipped={summary.flipped_count}")
    print("=" * 62)


if __name__ == "__main__":
    main()
