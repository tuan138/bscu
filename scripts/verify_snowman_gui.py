"""Run the BSCU pipeline on the snowman fixture, in the GUI, and measure it.

This is the real-model check the synthetic grids cannot answer: a metaball
isosurface has curvature that varies from face to face, so a chart that is
flat on a grid is not flat here. The numbers it writes are the ones the
performance claims have to survive.

Run with:
    blender/blender.exe tests/fixtures/snowman.blend --python scripts/verify_snowman_gui.py

Blender stays open afterwards so the result can be looked at.
"""

import json
import os
import sys
import time

import bpy

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "src"))

RESULT_PATH = os.path.join(REPO_ROOT, "tests", "fixtures", "snowman_verify.json")


def timed(label, function, *args, **kwargs):
    """Run a step, and return its result with the milliseconds it took."""
    started = time.perf_counter()
    result = function(*args, **kwargs)
    return result, (time.perf_counter() - started) * 1000.0


def main():
    for module in [k for k in list(sys.modules)
                   if k == "bscu" or k.startswith("bscu.")]:
        del sys.modules[module]
    import bscu

    _registered, register_ms = timed("register", bscu.register)

    obj = bpy.data.objects.get("Snowman")
    if obj is None:
        raise RuntimeError("the snowman fixture is missing")

    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj

    mesh = obj.data
    before = {
        "vertices": len(mesh.vertices),
        "faces": len(mesh.polygons),
        "dimensions_mm": [round(float(d), 3) for d in obj.dimensions],
    }

    report = {"model": "snowman", "before": before, "steps": {}}

    def propose():
        return bpy.ops.bscu.auto_seam(max_charts=8, apply_now=True)

    proposal, report["steps"]["auto_seam_ms"] = timed("auto_seam", propose)
    report["auto_seam"] = str(proposal)
    report["seams_marked"] = sum(1 for e in mesh.edges if e.use_seam)

    def unwrap():
        from bscu.core.unwrap_solver import UnwrapSolver
        from bscu.operators import op_uv_apply

        mesh = obj.data
        faces = [tuple(p.vertices) for p in mesh.polygons]
        points = [tuple(v.co) for v in mesh.vertices]
        from bscu.bridge import seam_bridge
        from bscu.core import uv_islands

        labels = uv_islands.extract_islands(faces, seam_bridge.seam_edges(mesh))
        state = {"points": points, "faces": faces, "islands": labels,
                 "weights": [1.0] * len(faces)}
        solver = UnwrapSolver()
        islands, layout = solver.solve(state)
        op_uv_apply.stage(obj, layout, None)
        return bpy.ops.bscu.apply_layout()

    layout, report["steps"]["apply_layout_ms"] = timed("apply_layout", unwrap)
    report["apply_layout"] = str(layout)

    uv = mesh.uv_layers.get("BSCU_UV_Active")
    report["uv"] = {
        "layer": uv.name if uv else None,
        "coordinates": len(uv.data) if uv else 0,
    }

    # The distortion the whole exercise exists to keep small.
    from bscu.core import uv_metrics

    try:
        summary = uv_metrics.summarise(uv_metrics.compute_face_metrics(
            [tuple(v.co) for v in mesh.vertices],
            [tuple(loop.uv) for loop in mesh.uv_layers["BSCU_UV_Active"].data],
            [tuple(p.vertices) for p in mesh.polygons]))
        report["distortion"] = {
            "worst": round(float(summary.worst), 4),
            "rms": round(float(summary.rms), 4),
            "flipped": int(summary.flipped_count),
            "degenerate": int(summary.degenerate_count),
        }
    except Exception as error:  # noqa: BLE001 - report, do not abort the GUI
        report["distortion"] = {"error": str(error)}

    report["total_ms"] = round(sum(report["steps"].values()), 1)
    with open(RESULT_PATH, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)

    print("=" * 60)
    print("SNOWMAN VERIFICATION")
    print("=" * 60)
    for key, value in report["steps"].items():
        print(f"  {key:24s} {value:9.1f} ms")
    print(f"  {'total':24s} {report['total_ms']:9.1f} ms")
    print(f"  seams marked            {report['seams_marked']}")
    print(f"  uv coordinates          {report['uv']['coordinates']}")
    print(f"  distortion              {report.get('distortion')}")
    print(f"  written to {RESULT_PATH}")
    print("Blender stays open.")
    # Quit after a short pause so the result can be read from the console.
    import threading
    threading.Timer(3.0, lambda: bpy.ops.wm.quit_blender()).start()


main()
