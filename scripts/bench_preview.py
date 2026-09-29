"""
Measure the two-tier unwrap on the published 200k case (UX-7, UIUX 3.4).

Two numbers decide whether the pipeline is usable: how often a preview can be
produced while a seam is being dragged, and how long the full solve takes.
The budget is 100 ms, because that is a 10 Hz interaction.
"""

import os
import sys
import time

import bpy
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

# The add-on is auto-enabled from the installed copy at startup, so the
# benchmark has to drop it or it measures whatever was last packaged.
for _name in [m for m in sys.modules if m == "bscu" or m.startswith("bscu.")]:
    del sys.modules[_name]

from bscu.core.seam_tools import edge_face_counts  # noqa: E402
from bscu.core.unwrap_solver import SolverSettings, UnwrapSolver  # noqa: E402

BSCU_UV = "BSCU_UV_Active"
TARGET_HZ = 10.0
BUDGET_S = 0.1


def build_workpiece(grid: int):
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    bpy.ops.mesh.primitive_grid_add(x_subdivisions=grid, y_subdivisions=grid,
                                    size=0.2)
    obj = bpy.context.active_object
    obj.data.uv_layers.new(name=BSCU_UV)
    return obj


def read_state(obj, seam_moved: bool):
    mesh = obj.data
    mesh.calc_loop_triangles()
    faces = np.asarray([tuple(t.vertices) for t in mesh.loop_triangles], dtype=np.int64)
    points = np.empty((len(mesh.vertices), 3), dtype=np.float64)
    mesh.vertices.foreach_get("co", points.ravel())

    # Two charts split down the middle: a seam, then a change to one side.
    middle = (points[:, 0] < points[:, 0].mean()).astype(np.int64)
    islands = middle[faces[:, 0]]

    seam = [(index, index + 1) for index in range(0, len(mesh.vertices) - 1, 7)]
    if seam_moved:
        seam = seam[:-1]
        points[0, 2] += 0.001

    return {
        "points": points,
        "faces": faces,
        "islands": islands,
        "geometry": float(np.abs(points).sum()),
        "topology": int(faces.size),
        "transform": 1.0,
        "region": "all",
        "seam": tuple(seam),
        "uv_revision": 0,
    }


def main() -> int:
    grid = int(os.environ.get("BSCU_BENCH_GRID", "320"))
    obj = build_workpiece(grid)
    state = read_state(obj, seam_moved=False)
    solver = UnwrapSolver(SolverSettings(blend=0.5), budget=BUDGET_S)

    cold = time.perf_counter()
    solver.preview(state)
    cold_ms = (time.perf_counter() - cold) * 1000.0

    print(f"triangles: {len(state['faces'])}  edges: {len(edge_face_counts(state['faces']))}")
    print(f"  cold preview (solves every chart) {cold_ms:8.1f} ms")

    warm = time.perf_counter()
    solver.preview(state)
    warm_ms = (time.perf_counter() - warm) * 1000.0
    print(f"  warm preview (cache hit)          {warm_ms:8.1f} ms")

    # A drag: only one chart's input moves, so only one chart should be solved.
    drag_times = []
    for step in range(1, 6):
        moved = read_state(obj, seam_moved=True)
        moved["points"] = state["points"].copy()
        moved["points"][0, 2] += step * 0.0005
        moved["geometry"] = float(np.abs(moved["points"]).sum())
        started = time.perf_counter()
        result = solver.preview(moved)
        drag_times.append((time.perf_counter() - started) * 1000.0)
        del result

    average = sum(drag_times) / len(drag_times)
    hz = 1000.0 / average if average else float("inf")
    print(f"  drag preview, one chart solved    {average:8.1f} ms -> {hz:5.2f} Hz")
    print(f"  budget for {TARGET_HZ:.0f} Hz is {BUDGET_S * 1000:.0f} ms "
          f"-> {'PASS' if hz >= TARGET_HZ else 'FAIL'}")
    return 0 if hz >= TARGET_HZ else 1


if __name__ == "__main__":
    raise SystemExit(main())
