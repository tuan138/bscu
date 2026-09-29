"""
Measure both preview tiers on a growing chart (UX-7, UIUX 3B.4).

Two numbers decide whether the pipeline is usable:

* the **local** solve, which runs while a stroke is being dragged and has to
  keep up with the cursor;
* the **full** solve, which runs when the stroke ends.

The structural point being checked is that the local solve's cost follows the
size of the stroke, not the size of the chart. A local solve that scaled with
the chart would be the same operation wearing a different name.
"""

import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

# The add-on is auto-enabled from the installed copy at startup, so the
# benchmark has to drop it or it measures whatever was last packaged.
for _name in [m for m in sys.modules if m == "bscu" or m.startswith("bscu.")]:
    del sys.modules[_name]

from bscu.core.local_solve import full_solve, solve_locally  # noqa: E402
from bscu.core.math_utils import plane_frame  # noqa: E402
from bscu.core.unwrap_solver import SolverSettings, UnwrapSolver  # noqa: E402

TARGET_HZ = 10.0
RADIUS_MM = 6.0


def build_chart(side: int, size_mm: float = 40.0):
    """A domed chart, as a flat grid lifted onto a shallow bowl."""
    top_left = []
    for row in range(side - 1):
        for column in range(side - 1):
            corner = row * side + column
            top_left.append([corner, corner + side, corner + 1])
            top_left.append([corner + 1, corner + side, corner + side + 1])
    faces = np.asarray(top_left, dtype=np.int64)

    axis = np.linspace(0.0, size_mm, side)
    grid = np.stack(np.meshgrid(axis, axis, indexing="xy"), axis=-1).reshape(-1, 2)
    points = np.column_stack([
        grid, 0.4 * (grid[:, 0] ** 2 + grid[:, 1] ** 2) / (size_mm * size_mm)
    ])
    return {
        "points": points,
        "faces": faces,
        "islands": np.zeros(len(faces), dtype=np.int64),
        "geometry": float(np.abs(points).sum()),
        "topology": int(faces.size),
        "transform": 1.0,
        "region": "all",
        "seam": (),
        "uv_revision": 0,
    }


def main() -> int:
    solver = UnwrapSolver(SolverSettings(blend=0.0), budget=1e9)
    centre = (20.0, 20.0)
    worst = 0.0

    print(f"{'faces':>9} {'full solve':>12} {'local solve':>13} {'rate':>9} {'patch':>7}")
    for side in (60, 120, 240, 340):
        state = build_chart(side)
        state["layout"] = plane_frame(state["points"])

        started = time.perf_counter()
        full = full_solve(solver, state)
        full_ms = (time.perf_counter() - started) * 1000.0
        state["layout"] = full.layout

        local_ms = []
        for step in range(1, 4):
            started = time.perf_counter()
            result = solve_locally(solver, state, centre_mm=centre,
                                   radius_mm=RADIUS_MM)
            local_ms.append((time.perf_counter() - started) * 1000.0)
            del step
        average = sum(local_ms) / len(local_ms)
        rate = 1000.0 / average if average else float("inf")
        worst = max(worst, average)

        print(f"{len(state['faces']):9d} {full_ms:10.0f} ms {average:11.1f} ms "
              f"{rate:7.1f} Hz {len(result.vertices):7d}")

    rate = 1000.0 / worst if worst else float("inf")
    verdict = "PASS" if rate >= TARGET_HZ else "FAIL"
    print(f"\nslowest local solve {worst:.1f} ms -> {rate:.1f} Hz; "
          f"target {TARGET_HZ:.0f} Hz -> {verdict}")
    return 0 if rate >= TARGET_HZ else 1


if __name__ == "__main__":
    raise SystemExit(main())
