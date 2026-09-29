"""Build the snowman verification model: four spheres genuinely united.

This is the standing verification asset for the project. A snowman is a good
adversarial case for a 2.5D relief pipeline:

* closed and manifold, so it is a valid design base;
* four strong convex lobes, so seam placement has somewhere obvious to cut;
* four curvature maxima, which is exactly what shreds a greedy chart grower;
* no flat area at all, so a bad flattening shows up immediately.

The spheres are unioned through a metaball rather than joined, so the result is
one watertight shell. Joining would leave four overlapping shells, which is a
different and less useful test.

Units: the scene is set to millimetres, where one Blender unit is one
millimetre, so every dimension below is authored as a plain number.

Run with:
    blender/blender.exe -b --python scripts/make_snowman.py
It writes tests/fixtures/snowman.blend and fails if the result is not watertight.
"""

import os

import bpy

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(REPO_ROOT, "tests", "fixtures")
OUT_PATH = os.path.join(OUT_DIR, "snowman.blend")

# (height_mm, radius_mm) from the ground up: body, middle, head, hat knob.
# The balls overlap vertically, which is what makes the metaball union a single
# connected body rather than a stack of separate lumps.
BALLS = (
    (28.0, 42.0),
    (76.0, 34.0),
    (118.0, 26.0),
    (150.0, 12.0),
)
METABALL_RESOLUTION = 2.5
METABALL_RENDER_RESOLUTION = 1.5


def clear_scene():
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)


def set_units():
    """Millimetre scene units, so dimensions are authored as plain numbers."""
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.length_unit = "MILLIMETERS"
    scene.unit_settings.scale_length = 0.001


def add_balls(metaball):
    """Place the four balls. Default stiffness (2.0) uses the radius as given;
    lowering it shrinks a ball's effective radius and the upper balls stop
    merging into the body."""
    for height_mm, radius_mm in BALLS:
        element = metaball.elements.new(type="BALL")
        element.co = (0.0, 0.0, height_mm)
        element.radius = radius_mm


def build_snowman():
    clear_scene()
    set_units()

    metaball = bpy.data.metaballs.new("SnowmanBalls")
    metaball.resolution = METABALL_RESOLUTION
    metaball.render_resolution = METABALL_RENDER_RESOLUTION
    add_balls(metaball)

    obj = bpy.data.objects.new("Snowman", metaball)
    bpy.context.collection.objects.link(obj)
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj

    bpy.ops.object.convert(target="MESH")
    obj = bpy.context.view_layer.objects.active
    obj.name = "Snowman"

    # No decimate: collapsing triangles tears holes in the isosurface, and the
    # fixture has to stay watertight. The metaball resolution alone gives an
    # even enough tessellation.
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.remove_doubles(threshold=1e-4)
    bpy.ops.mesh.fill_holes()
    bpy.ops.mesh.normals_make_consistent(inside=False)
    bpy.ops.object.mode_set(mode="OBJECT")

    # The core works on triangles, so the fixture stores triangles too.
    bpy.ops.object.modifier_add(type="TRIANGULATE")
    bpy.ops.object.modifier_apply(modifier="Triangulate")
    bpy.ops.object.shade_smooth()

    if "BSCU_UV_Active" in obj.data.uv_layers:
        obj.data.uv_layers.remove(obj.data.uv_layers["BSCU_UV_Active"])
    obj.data.uv_layers.new(name="BSCU_UV_Active")
    return obj


def check_watertight(mesh) -> tuple:
    """Count triangle edges used once (boundary) or more than twice (non-manifold).

    Counted over triangles on purpose: a metaball stores n-gons, and the edges
    of those n-gons say nothing about whether the surface is closed.
    """
    mesh.calc_loop_triangles()
    usage = {}
    for tri in mesh.loop_triangles:
        a, b, c = tri.vertices
        for left, right in ((a, b), (b, c), (c, a)):
            key = (min(left, right), max(left, right))
            usage[key] = usage.get(key, 0) + 1
    boundary = sum(1 for count in usage.values() if count == 1)
    non_manifold = sum(1 for count in usage.values() if count > 2)
    return boundary, non_manifold


def report(obj) -> tuple:
    mesh = obj.data
    boundary, non_manifold = check_watertight(mesh)
    print("=" * 62)
    print("Snowman verification model")
    print("=" * 62)
    print(f"  name           {obj.name}")
    print(f"  vertices       {len(mesh.vertices)}")
    print(f"  triangles      {len(mesh.loop_triangles)}")
    print(f"  size (mm)      {[round(d, 1) for d in obj.dimensions]}")
    print(f"  unit scale     {bpy.context.scene.unit_settings.scale_length}")
    print(f"  boundary edges {boundary}")
    print(f"  non-manifold   {non_manifold}")
    print("=" * 62)
    return boundary, non_manifold


def main():
    obj = build_snowman()
    boundary, non_manifold = report(obj)
    if boundary or non_manifold:
        raise SystemExit("[FAIL] the snowman fixture must be watertight")
    os.makedirs(OUT_DIR, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=OUT_PATH)
    print(f"[OK] saved {OUT_PATH}")


if __name__ == "__main__":
    main()
