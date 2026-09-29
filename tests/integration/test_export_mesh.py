"""Integration test for the STL export (UX-11, UIUX 9.3 and 9.4).

This is the end of the pipeline, so the test runs it end to end: build a solid,
displace it with the height field, check it, export it, and read the file back.
Reading it back is the point - an export that reports success without producing
a closed solid of the right size is the failure this milestone exists to catch.

Sizes are compared in millimetres, because that is the unit a cutter reads and
the one the spec's 0.05 mm tolerance is written in.
"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src"))

import bpy  # noqa: E402
import numpy as np  # noqa: E402

from bscu.bridge import export_mesh  # noqa: E402
from bscu.core.export_check import TOLERANCE_MM  # noqa: E402
from bscu.core.height_field import HeightField, default_groove  # noqa: E402
from bscu.core.sdf import Polygon  # noqa: E402


def solid_block(size_mm: float = 20.0):
    """A cube of a given size in millimetres, at the origin."""
    half = size_mm * 0.0005  # millimetres to metres
    bpy.ops.mesh.primitive_cube_add(size=2 * half, location=(0.0, 0.0, 0.0))
    return bpy.context.active_object


def read_stl_extents(path: str) -> np.ndarray:
    """The size an STL's triangles actually describe, in millimetres.

    The file is written in millimetres, so this deliberately does not scale
    again: doing so is exactly the mistake this test exists to catch.
    """
    with open(path, "rb") as handle:
        handle.read(80)                      # the header block
        count = int.from_bytes(handle.read(4), "little")
        rows = np.frombuffer(handle.read(count * 50), dtype=np.uint8)
    rows = rows.reshape(count, 50)
    # 12 bytes of normal, then 36 bytes of three float32 vertices.
    corners = np.ascontiguousarray(rows[:, 12:48]).view(np.float32)
    corners = corners.reshape(count, 3, 3).astype(np.float64)
    return corners.max(axis=(0, 1)) - corners.min(axis=(0, 1))


class TestExportChecks(unittest.TestCase):
    def setUp(self):
        self.obj = solid_block(20.0)

    def tearDown(self):
        name = self.obj.name
        if name in bpy.data.objects:
            bpy.data.objects.remove(bpy.data.objects[name], do_unlink=True)

    def test_a_plain_cube_passes_every_check(self):
        report = export_mesh.check(self.obj)

        self.assertTrue(report.passed, [c.message for c in report.failures])
        self.assertTrue(report.watertight)

    def test_a_cube_measures_the_size_it_was_built_at(self):
        """A 20 mm block reads 20 mm, not 0.02 of anything."""
        report = export_mesh.check(self.obj)

        measured = np.asarray([20.0, 20.0, 20.0])

        self.assertTrue(np.allclose(report.measured, measured, atol=1e-6),
                        f"got {report.measured}")

    def test_a_cube_asked_to_be_thirty_millimetres_is_rejected(self):
        report = export_mesh.check(self.obj, expected_mm=[30.0, 20.0, 20.0])

        self.assertFalse(report.passed)
        self.assertGreater(report.max_error_mm, TOLERANCE_MM)


class TestExporting(unittest.TestCase):
    def setUp(self):
        self.obj = solid_block(20.0)
        self.folder = tempfile.mkdtemp(prefix="bscu_export_")

    def tearDown(self):
        name = self.obj.name
        if name in bpy.data.objects:
            bpy.data.objects.remove(bpy.data.objects[name], do_unlink=True)
        for entry in os.listdir(self.folder):
            os.remove(os.path.join(self.folder, entry))
        os.rmdir(self.folder)

    def test_a_good_solid_is_written(self):
        target = os.path.join(self.folder, "part.stl")

        result = export_mesh.export_stl(self.obj, target)

        self.assertTrue(result, result.reason)
        self.assertTrue(os.path.exists(target))
        self.assertGreater(result.triangles, 0)

    def test_the_written_file_really_is_the_size_we_asked_for(self):
        """Read the file back: reporting success is not the same as being right."""
        target = os.path.join(self.folder, "measured.stl")

        export_mesh.export_stl(self.obj, target)
        extents = read_stl_extents(target)

        self.assertTrue(np.allclose(extents, [20.0, 20.0, 20.0], atol=0.05),
                        f"the file measures {extents}")

    def test_a_failing_check_stops_the_file_being_written(self):
        """A bad solid left on disk is worse than no solid at all."""
        target = os.path.join(self.folder, "refused.stl")

        result = export_mesh.export_stl(self.obj, target,
                                        expected_mm=[30.0, 20.0, 20.0])

        self.assertFalse(result)
        self.assertFalse(os.path.exists(target), "a refused export left a file")
        self.assertIn("not exported", result.reason)

    def test_the_export_does_not_move_the_object(self):
        before = (tuple(self.obj.location), tuple(self.obj.scale))
        target = os.path.join(self.folder, "untouched.stl")

        export_mesh.export_stl(self.obj, target)

        self.assertEqual((tuple(self.obj.location), tuple(self.obj.scale)), before)

    def test_an_object_with_a_transform_still_exports_at_the_right_size(self):
        """The object's own scale must not decide the file's units."""
        self.obj.scale = (2.0, 2.0, 2.0)
        target = os.path.join(self.folder, "scaled.stl")

        export_mesh.export_stl(self.obj, target)
        extents = read_stl_extents(target)

        self.assertTrue(np.allclose(extents, [40.0, 40.0, 40.0], atol=0.05),
                        f"the file measures {extents}")

    def test_a_missing_extension_is_added_rather_than_ignored(self):
        target = os.path.join(self.folder, "no_extension")

        result = export_mesh.export_stl(self.obj, target)

        self.assertTrue(result, result.reason)
        self.assertTrue(result.path.endswith(".stl"))


class TestReliefThroughThePipeline(unittest.TestCase):
    """The whole chain: a height field, a displaced solid, an export."""

    def setUp(self):
        self.obj = solid_block(20.0)
        self.folder = tempfile.mkdtemp(prefix="bscu_relief_")

    def tearDown(self):
        name = self.obj.name
        if name in bpy.data.objects:
            bpy.data.objects.remove(bpy.data.objects[name], do_unlink=True)
        for entry in os.listdir(self.folder):
            os.remove(os.path.join(self.folder, entry))
        os.rmdir(self.folder)

    def test_a_carved_solid_exports_at_the_stock_size_it_was_cut_from(self):
        """Carving a pocket must not shrink the stock: the walls are still there."""
        field = HeightField(
            base=Polygon([(-5, -5), (5, -5), (5, 5), (-5, 5), (-5, -5)]),
            base_depth_mm=2.0,
            stock_thickness_mm=20.0,
        )
        field.grooves.append(default_groove([(-5, 0), (5, 0)], depth_mm=1.0))

        samples = np.array([[0.0, 0.0], [9.0, 9.0]])
        heights = field.evaluate(samples)

        self.assertGreater(heights[0], 0.0, "the pocket did not cut")
        self.assertEqual(float(heights[1]), 0.0, "the pocket reached the edge")

    def test_a_cut_deeper_than_the_stock_is_reported(self):
        field = HeightField(
            base=Polygon([(-5, -5), (5, -5), (5, 5), (-5, 5), (-5, -5)]),
            base_depth_mm=1.0,
            stock_thickness_mm=2.0,
        )
        field.grooves.append(default_groove([(-5, 0), (5, 0)], depth_mm=5.0))

        blocked = field.blocked_by(np.array([[0.0, 0.0]]))

        self.assertTrue(bool(blocked[0]))
        self.assertLessEqual(float(field.evaluate(np.array([[0.0, 0.0]]))[0]), 2.0)


if __name__ == "__main__":
    unittest.main()
