"""
Run the UV metrics on meshes that really come out of Blender (UX-1).

The pure maths is unit tested; this proves the bridge hands it the right arrays:
world-space millimetres, one UV row per mesh vertex, triangles only, and the
seam set the user actually marked.
"""

import math

import bpy

from bscu.bridge.snapshot import take_snapshot
from bscu.core.uv_islands import check_topology, extract_islands, island_face_counts
from bscu.core.uv_metrics import summarise, with_scores

BSCU_UV = "BSCU_UV_Active"


def _clear():
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)


def _prepare(obj, uv_name):
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=1.15192, island_margin=0.02)
    bpy.ops.object.mode_set(mode="OBJECT")
    mesh = obj.data
    if uv_name in mesh.uv_layers:
        mesh.uv_layers.remove(mesh.uv_layers[uv_name])
    mesh.uv_layers.new(name=uv_name)
    return obj


def _make_cube():
    bpy.ops.mesh.primitive_cube_add(size=0.1)
    return bpy.context.active_object


def _make_uv_sphere():
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.05, segments=32, ring_count=16)
    return bpy.context.active_object


def _make_torus():
    bpy.ops.mesh.primitive_torus_add(
        major_radius=0.05, minor_radius=0.015, major_segments=32, minor_segments=16
    )
    return bpy.context.active_object


def test_snapshot_reports_millimetres_not_metres():
    _clear()
    cube = _prepare(_make_cube(), BSCU_UV)
    snap = take_snapshot(cube, BSCU_UV)
    expected_mm = max(d for d in cube.dimensions) * 1000.0
    span = snap.verts_mm[:, 0].max() - snap.verts_mm[:, 0].min()
    assert abs(span - expected_mm) < 0.5, (span, expected_mm)
    print(f"[OK] snapshot spans {span:.2f} mm for a {expected_mm:.2f} mm cube")


def test_snapshot_uses_the_requested_uv_layer():
    # uv_layers.new() clones the active layer, so the two start identical; move
    # BSCU_UV_Active and the snapshot must follow that layer, not UVMap.
    _clear()
    cube = _prepare(_make_cube(), BSCU_UV)
    before_other = take_snapshot(cube, "UVMap").uv.copy()
    before_named = take_snapshot(cube, BSCU_UV).uv.copy()
    assert (before_other == before_named).all()

    for loop in cube.data.uv_layers[BSCU_UV].data:
        loop.uv = (loop.uv[0] * 0.5, loop.uv[1] * 0.25)

    after_named = take_snapshot(cube, BSCU_UV).uv
    after_other = take_snapshot(cube, "UVMap").uv
    assert not (after_named == before_named).all(), "BSCU_UV_Active edit was ignored"
    assert (after_other == before_other).all(), "UVMap must not be affected"
    print("[OK] each UV layer is read from the layer that was asked for")


def test_snapshot_is_triangles_only_and_splits_at_seams():
    _clear()
    cube = _prepare(_make_cube(), BSCU_UV)
    snap = take_snapshot(cube, BSCU_UV)
    assert snap.faces.shape[1] == 3, snap.faces.shape
    assert snap.uv.shape[0] == snap.verts_mm.shape[0], (snap.uv.shape, snap.verts_mm.shape)
    assert len(snap.faces) == 12, len(snap.faces)
    # A cube unwrap splits every corner across its charts, so the measured
    # surface has more vertices than the mesh does.
    assert len(snap.uv) > len(cube.data.vertices), (len(snap.uv), len(cube.data.vertices))
    print(
        f"[OK] {len(snap.faces)} triangles over {len(snap.uv)} split UV rows "
        f"(mesh has {len(cube.data.vertices)} vertices)"
    )


def _metrics(snap):
    from bscu.core.uv_metrics import compute_face_metrics

    return compute_face_metrics(snap.verts_mm, snap.uv, snap.faces)


def _scored_snapshot(obj):
    return with_scores(_metrics(take_snapshot(obj, BSCU_UV)))




def test_cube_unwrap_is_perfectly_uniform():
    """A cube unwrap maps every face to the same area: the metrics must say zero."""
    _clear()
    cube = _prepare(_make_cube(), BSCU_UV)
    summary = summarise(_scored_snapshot(cube))
    assert summary.rho_star is not None
    # Blender stores UVs as float32, so a perfect cube lands near zero, not on it.
    assert summary.rms < 1e-5, summary.rms
    assert abs(summary.density_max - summary.density_min) < 1e-5
    print(
        f"[OK] cube unwrap is uniform: rho*={summary.rho_star:.6f} UV/mm, "
        f"rms={summary.rms:.2e}"
    )


def test_sphere_density_matches_its_surface_size():
    """rho must be UV per mm: a 50 mm sphere cannot have rho near 1."""
    _clear()
    sphere = _prepare(_make_uv_sphere(), BSCU_UV)
    snap = take_snapshot(sphere, BSCU_UV)
    metrics = with_scores(_metrics(snap))
    total_area_mm2 = float(metrics.area_3d.sum())
    uv_area = float(metrics.area_uv.sum())
    # Uniform density over the whole surface: rho* = sqrt(uv_area / 3d_area).
    expected = (uv_area / total_area_mm2) ** 0.5
    summary = summarise(metrics)
    assert abs(summary.rho_star - expected) / expected < 0.5, (
        summary.rho_star,
        expected,
    )
    assert 0.001 < summary.rho_star < 0.05, summary.rho_star
    print(
        f"[OK] sphere rho*={summary.rho_star:.5f} UV/mm over {total_area_mm2:.0f} mm^2 "
        f"and {uv_area:.3f} UV^2, rms={summary.rms:.4f}"
    )


def test_smart_projected_cube_keeps_orientation_and_area():
    _clear()
    cube = _prepare(_make_cube(), BSCU_UV)
    summary = summarise(_scored_snapshot(cube))
    assert summary.flipped_count == 0, summary.flipped_count
    assert summary.degenerate_count == 0, summary.degenerate_count
    assert math.isfinite(summary.rms)
    print(
        f"[OK] cube unwrap: flipped={summary.flipped_count} "
        f"degenerate={summary.degenerate_count} rms={summary.rms:.6f}"
    )




def test_sphere_unwrap_has_real_variation():
    """A sphere cannot unwrap uniformly, so the metrics must say so."""
    _clear()
    sphere = _prepare(_make_uv_sphere(), BSCU_UV)
    summary = summarise(_scored_snapshot(sphere))
    assert summary.rho_star and summary.rho_star > 0
    assert summary.density_max > summary.density_min, (
        summary.density_min,
        summary.density_max,
    )
    assert summary.rms > 0.0, summary.rms
    print(
        f"[OK] sphere: rho*={summary.rho_star:.5f} rms={summary.rms:.4f} "
        f"density {summary.density_min:.5f}..{summary.density_max:.5f}"
    )


def test_torus_mesh_topology_is_fully_closed():
    """Topology is judged on the mesh, not on the UV-split surface."""
    _clear()
    torus = _prepare(_make_torus(), BSCU_UV)
    snap = take_snapshot(torus, BSCU_UV)
    report = check_topology(snap.source_faces, snap.source_edge_faces)
    assert report.blocking_codes == (), report.blocking_codes
    assert report.boundary_edges == 0, report.boundary_edges
    print("[OK] torus mesh is closed and mappable")


def test_unwrapped_surface_is_open_even_without_marked_seams():
    """smart_project cuts via UV only; it never sets use_seam.

    The marked seam set stays the user's decision (UIUX 6), so it is empty
    here even though the measured surface is already cut open.
    """
    _clear()
    torus = _prepare(_make_torus(), BSCU_UV)
    snap = take_snapshot(torus, BSCU_UV)
    split = check_topology(snap.faces, snap.edge_faces)
    assert split.has_open_boundary, "an unwrapped torus must have cut edges"
    assert snap.seam_edges.size == 0, "smart_project must not invent seams"
    print(
        f"[OK] unwrapped torus: {split.boundary_edges} boundary edges on the cut "
        "surface, 0 marked seams (UV cut only)"
    )


def test_marked_seams_are_reported_and_cut_islands():
    """The marked seam set is the user's, and it is what cuts islands apart."""
    _clear()
    cube = _prepare(_make_cube(), BSCU_UV)
    snap = take_snapshot(cube, BSCU_UV)
    assert snap.seam_edges.size == 0, "smart_project must not mark seams"

    mesh = cube.data
    mesh.edges.foreach_set("use_seam", [True] * len(mesh.edges))
    mesh.update()

    cut = take_snapshot(cube, BSCU_UV)
    # Only real mesh edges can carry a seam, so the triangle diagonals inside
    # each face stay connected: 6 faces of 2 triangles, not 12 singletons.
    marked = {tuple(pair) for pair in cut.seam_edges.tolist()}
    assert marked, "marking every edge must produce seams"
    assert len(marked) > len(mesh.edges), "each mesh edge splits into chart copies"
    assert island_face_counts(extract_islands(cut.faces, cut.seam_edges)) == [2] * 6
    print(
        f"[OK] {len(marked)} seam edges cut the unwrap into 6 islands of 2 "
        "triangles (diagonals are not mesh edges, so they stay joined)"
    )


def test_scaled_object_does_not_change_reported_size():
    """Object scale must be honoured, or the density would be a lie."""
    _clear()
    cube = _prepare(_make_cube(), BSCU_UV)
    base = take_snapshot(cube, BSCU_UV)
    cube.scale = (2.0, 2.0, 2.0)
    bpy.context.view_layer.update()
    doubled = take_snapshot(cube, BSCU_UV)
    base_span = base.verts_mm[:, 0].max() - base.verts_mm[:, 0].min()
    doubled_span = doubled.verts_mm[:, 0].max() - doubled.verts_mm[:, 0].min()
    assert abs(doubled_span - 2.0 * base_span) < 0.5, (base_span, doubled_span)
    cube.scale = (1.0, 1.0, 1.0)
    print("[OK] object scale is reflected in the millimetre snapshot")


def test_non_mesh_object_is_rejected(self=None):
    _clear()
    bpy.ops.object.camera_add()
    camera = bpy.context.active_object
    try:
        take_snapshot(camera, BSCU_UV)
    except ValueError as error:
        assert "Mesh" in str(error), error
        print("[OK] a Camera is refused with a clear reason")
        return
    raise AssertionError("expected ValueError for a non-mesh object")


def test_missing_uv_layer_is_reported_clearly(self=None):
    _clear()
    cube = _make_cube()
    try:
        take_snapshot(cube, BSCU_UV)
    except ValueError as error:
        assert BSCU_UV in str(error), error
        print("[OK] a missing UV layer is reported by name")
        return
    raise AssertionError("expected ValueError for a missing UV layer")


def run_test():
    test_snapshot_reports_millimetres_not_metres()
    test_snapshot_uses_the_requested_uv_layer()
    test_snapshot_is_triangles_only_and_splits_at_seams()
    test_smart_projected_cube_keeps_orientation_and_area()
    test_cube_unwrap_is_perfectly_uniform()
    test_sphere_unwrap_has_real_variation()
    test_sphere_density_matches_its_surface_size()
    test_torus_mesh_topology_is_fully_closed()
    test_unwrapped_surface_is_open_even_without_marked_seams()
    test_marked_seams_are_reported_and_cut_islands()
    test_scaled_object_does_not_change_reported_size()
    test_non_mesh_object_is_rejected()
    test_missing_uv_layer_is_reported_clearly()
    print("\nUV metrics verified against real Blender meshes!")
