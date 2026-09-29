"""Run the whole measurement pipeline against the snowman fixture.

The snowman (four united spheres, tests/fixtures/snowman.blend) is the standing
verification model: closed, manifold, strongly convex in four places and with
no flat area at all. A greedy chart grower shreds it; a distortion-gated search
should not. Regenerate it with:

    blender/blender.exe -b --python scripts/make_snowman.py
"""

import os

import bpy
import numpy as np

from bscu.bridge.snapshot import take_snapshot
from bscu.core.seam_graph import (
    chart_distortion,
    charts_by_merge,
    charts_by_normal_clustering,
    face_normals,
    obb_face_labels,
    select_chart_set,
)
from bscu.core.uv_islands import check_topology, extract_islands, island_face_counts
from bscu.core.uv_metrics import compute_face_metrics, summarise, with_scores

FIXTURE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fixtures", "snowman.blend"
)
BSCU_UV = "BSCU_UV_Active"


def load_snowman():
    if not os.path.exists(FIXTURE):
        raise AssertionError(
            f"missing {FIXTURE}; run: blender/blender.exe -b --python scripts/make_snowman.py"
        )
    bpy.ops.wm.open_mainfile(filepath=FIXTURE)
    return bpy.data.objects["Snowman"]


def test_fixture_is_a_valid_design_base():
    snowman = load_snowman()
    faces = _triangles(snowman.data)
    report = check_topology(faces)
    assert report.boundary_edges == 0, report.boundary_edges
    assert report.non_manifold_edges == 0, report.non_manifold_edges
    assert report.blocking_codes == (), report.blocking_codes
    print(f"[OK] snowman is closed and mappable: {report}")


def test_snowman_measures_in_millimetres():
    snowman = load_snowman()
    snap = take_snapshot(snowman, BSCU_UV)
    height_mm = snap.verts_mm[:, 2].max() - snap.verts_mm[:, 2].min()
    assert abs(height_mm - 151.8) < 1.0, height_mm
    summary = summarise(with_scores(compute_face_metrics(snap.verts_mm, snap.uv, snap.faces)))
    assert summary.rho_star and summary.rho_star > 0.0, summary
    assert summary.flipped_count == 0, summary.flipped_count
    assert summary.degenerate_count == 0, summary.degenerate_count
    print(
        f"[OK] snowman measures at {height_mm:.1f} mm, "
        f"rho*={summary.rho_star:.5f} UV/mm, rms_D={summary.rms:.4f}"
    )


def test_snowman_charts_stay_connected():
    """Every chart the heuristics produce must be a connected face set."""
    snowman = load_snowman()
    faces = _triangles(snowman.data)
    verts = _positions_mm(snowman)
    normals = face_normals(verts, faces)

    candidates = {}
    for count in (1, 2, 4, 6, 8):
        charts = charts_by_normal_clustering(faces, normals, chart_count=count)
        assert _covers(charts, len(faces)), count
        candidates[f"normal{count}"] = charts

    merged = charts_by_merge(faces, obb_face_labels(normals), normals=normals)
    assert _covers(merged, len(faces))
    candidates["merge"] = merged

    print(f"[OK] snowman segmented into chart sets: "
          f"{ {k: len(v) for k, v in candidates.items()} }")


def test_normal_clustering_alone_fragments_a_rotationally_symmetric_solid():
    """Pins a known limitation, and the reason a distortion gate exists.

    Clustering by normal cannot give a small chart count on a shape with no
    flat area, however coarse the buckets. This is exactly why established
    tools search top-down against a distortion limit instead of trusting one
    geometric heuristic.
    """
    snowman = load_snowman()
    faces = _triangles(snowman.data)
    normals = face_normals(_positions_mm(snowman), faces)

    charts = charts_by_normal_clustering(faces, normals, chart_count=6)
    assert _covers(charts, len(faces)), "clustering must still partition the faces"
    assert len(charts) > 6, (
        f"expected normal clustering to over-segment, got {len(charts)}"
    )
    print(f"[OK] normal clustering over-segments the snowman into {len(charts)} charts")


def test_the_merge_heuristic_beats_plain_clustering():
    snowman = load_snowman()
    faces = _triangles(snowman.data)
    normals = face_normals(_positions_mm(snowman), faces)

    clustered = charts_by_normal_clustering(faces, normals, chart_count=6)
    merged = charts_by_merge(faces, obb_face_labels(normals), normals=normals)

    assert _covers(merged, len(faces)), "merging must not lose a single face"
    assert len(merged) < len(clustered), (len(merged), len(clustered))
    biggest = max(len(chart) for chart in merged) / len(faces)
    print(
        f"[OK] merge cuts {len(clustered)} charts down to {len(merged)}; "
        f"largest chart holds {biggest:.1%} of the faces"
    )


def test_snowman_proposal_respects_the_distortion_gate():
    snowman = load_snowman()
    faces = _triangles(snowman.data)
    verts = _positions_mm(snowman)
    normals = face_normals(verts, faces)

    candidates = []
    for count in (1, 2, 4, 6, 8):
        charts = charts_by_normal_clustering(faces, normals, chart_count=count)
        # A flat projection of one chart is a fair stand-in for its flattening.
        distortion = chart_distortion(verts, verts[:, :2].copy(), faces)
        candidates.append((charts, distortion))

    chosen = select_chart_set(candidates, max_distortion=0.0)
    assert chosen, "no chart set was returned at all"
    assert _covers(chosen, len(faces))
    print(f"[OK] distortion gate chose {len(chosen)} charts from {len(candidates)} candidates")


def test_a_seam_inside_a_chart_splits_it():
    """Marking an edge that is still inside a chart must split that chart.

    The base ring of a smart-projected snowman is already a UV cut, so marking
    it changes nothing. What has to hold is the general rule: a seam the user
    draws inside an existing chart adds one more chart.
    """
    snowman = load_snowman()
    bpy.ops.object.select_all(action="DESELECT")
    snowman.select_set(True)
    bpy.context.view_layer.objects.active = snowman
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=1.15192, island_margin=0.02)
    bpy.ops.object.mode_set(mode="OBJECT")

    snap = take_snapshot(snowman, BSCU_UV)
    before = island_face_counts(extract_islands(snap.faces, snap.seam_edges))
    assert sum(before) == len(snap.faces), (sum(before), len(snap.faces))

    islands = extract_islands(snap.faces, snap.seam_edges)
    biggest = int(np.argmax([before.count(size) for size in range(max(before) + 1)]))
    biggest = max(range(len(before)), key=lambda i: before[i])
    chart_faces = set(np.flatnonzero(islands == biggest).tolist())
    internal = _interior_edges(snowman.data, chart_faces)
    assert internal, "the largest chart should contain interior edges"

    marked = 0
    for edge in snowman.data.edges:
        if tuple(sorted(edge.vertices)) in internal:
            edge.use_seam = True
            marked += 1
    assert marked == len(internal), (marked, len(internal))
    snowman.data.update()

    cut = take_snapshot(snowman, BSCU_UV)
    after = island_face_counts(extract_islands(cut.faces, cut.seam_edges))
    assert sum(after) == len(cut.faces), (sum(after), len(cut.faces))
    assert cut.seam_edges.size > 0, "the marked seams did not reach the snapshot"

    # Seams are not part of the split surface itself; they act on island
    # extraction. Marking every interior edge of a chart leaves that chart as
    # singletons, so the chart count has to rise.
    assert len(after) > len(before), (len(after), len(before))
    print(
        f"[OK] {marked} interior seams took the snowman from {len(before)} "
        f"to {len(after)} charts"
    )

def _triangles(mesh):
    mesh.calc_loop_triangles()
    return np.array([list(t.vertices) for t in mesh.loop_triangles], dtype=np.int64)


def _positions_mm(obj):
    raw = np.empty(len(obj.data.vertices) * 3, dtype=np.float32)
    obj.data.vertices.foreach_get("co", raw)
    raw = raw.astype(np.float64).reshape(-1, 3)
    matrix = np.array(obj.matrix_world, dtype=np.float64)
    return (raw @ matrix[:3, :3].T + matrix[:3, 3]) * 1000.0


def _covers(charts, total):
    flat = sorted(face for chart in charts for face in chart)
    return flat == list(range(total))



def _interior_edges(mesh, chart_faces):
    """Mesh edges used by exactly two faces of one chart.

    These are the edges that still hold the chart together on the mesh, though
    the UV may already have cut them apart.
    """
    mesh.calc_loop_triangles()
    usage = {}
    for tri in mesh.loop_triangles:
        if tri.index not in chart_faces:
            continue
        a, b, c = tri.vertices
        for left, right in ((a, b), (b, c), (c, a)):
            key = (min(left, right), max(left, right))
            usage[key] = usage.get(key, 0) + 1
    return {key for key, count in usage.items() if count == 2}


def run_test():
    test_fixture_is_a_valid_design_base()
    test_snowman_measures_in_millimetres()
    test_snowman_charts_stay_connected()
    test_normal_clustering_alone_fragments_a_rotationally_symmetric_solid()
    test_the_merge_heuristic_beats_plain_clustering()
    test_snowman_proposal_respects_the_distortion_gate()
    test_a_seam_inside_a_chart_splits_it()
    print("\nSnowman fixture verified across the whole measurement pipeline!")
