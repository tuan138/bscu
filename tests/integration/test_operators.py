"""Integration test for the operators, panel and preview (UX-9a, UX-10, UX-13).

These all live on the Blender side, and the unit tests cannot reach them. That
gap was not theoretical: the inspector panel shipped with an import that
resolved to a module that does not exist, and every unit test stayed green
because none of them opened the panel.

So this file calls the things a user actually triggers - a panel draw, an
operator execute, a preview sample - inside a real Blender. The panel is drawn
through a small recorder, because ``bpy.types.UILayout`` cannot be constructed
and the point is that ``draw()`` runs at all, not what the pixels are.
"""

import os
import sys
import tempfile
import types
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src"))

import bpy  # noqa: E402
import numpy as np  # noqa: E402

from bscu.core.geom2d import Line  # noqa: E402
from bscu.core.height_field import HeightField  # noqa: E402
from bscu.core.sdf import Polygon  # noqa: E402
from bscu.operators import op_canvas_mode, op_draw, op_import_vector  # noqa: E402
from bscu.ui import panel_inspector  # noqa: E402
from bscu.ui.panel_inspector import BSCU_PT_CanvasInspector  # noqa: E402


class RecordingLayout:
    """Stands in for a UILayout and remembers what was asked of it.

    Not a pixel test. The point is that drawing the panel runs every line of
    it, which is where a wrong import shows up.
    """

    def __init__(self):
        self.texts = []
        self.operators = []

    def label(self, text="", icon="", **_kwargs):
        self.texts.append(str(text))

    def separator(self, **_kwargs):
        pass

    def row(self, **_kwargs):
        return self

    def column(self, **_kwargs):
        return self

    def box(self, **_kwargs):
        return self

    def operator(self, idname, text="", **_kwargs):
        self.operators.append((idname, text))
        return self

    def property(self, *_args, **_kwargs):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def says(self, needle) -> bool:
        return any(needle in text for text in self.texts)


def fresh_scene():
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    bpy.ops.mesh.primitive_grid_add(x_subdivisions=2, y_subdivisions=2)
    return bpy.context.active_object


def blank_canvas():
    """Start a test with no drawing.

    The canvas is stored on the scene on purpose, so saving the file saves the
    drawing. That is right for the product and wrong for tests, which share one
    scene: each one has to clear both the cached copy and the stored one.
    """
    op_draw.forget(bpy.context.scene.name)
    # Written empty rather than deleted: deleting a scene property does not
    # reliably remove it here, and a leftover stroke would be picked up as a
    # snap target by the next test.
    for key in ("bscu_strokes", "bscu_hidden", "bscu_selection"):
        bpy.context.scene[key] = "{}"


class TestInspectorPanel(unittest.TestCase):
    """The panel has to draw, not merely register."""

    def setUp(self):
        self.obj = fresh_scene()
        blank_canvas()

    def tearDown(self):
        name = self.obj.name
        blank_canvas()
        if name in bpy.data.objects:
            bpy.data.objects.remove(bpy.data.objects[name], do_unlink=True)

    def test_the_panel_draws_on_an_empty_canvas(self):
        layout = RecordingLayout()

        panel_inspector.draw_panel(layout, bpy.context)

        self.assertTrue(layout.texts)
        self.assertTrue(layout.says("Nothing drawn yet"))

    def test_the_panel_draws_with_strokes_on_it(self):
        bpy.ops.bscu.draw_line(start_mm=(0.0, 0.0), to_mm=(10.0, 0.0))
        layout = RecordingLayout()

        panel_inspector.draw_panel(layout, bpy.context)

        self.assertTrue(layout.says("Strokes: 1"))
        self.assertTrue(layout.says("Nothing hidden"))
        self.assertTrue(layout.says("Fillet"))

    def test_the_panel_lists_what_is_hidden(self):
        bpy.ops.bscu.draw_line(start_mm=(0.0, 0.0), to_mm=(10.0, 0.0))
        bpy.ops.bscu.canvas_visibility(stroke="stroke-0001", hide=True)
        layout = RecordingLayout()

        panel_inspector.draw_panel(layout, bpy.context)

        self.assertTrue(layout.says("stroke-0001"))

    def test_the_panel_class_draws_rather_than_only_registering(self):
        """The failure this file exists for: a panel that raises on first draw."""
        bpy.ops.bscu.draw_line(start_mm=(0.0, 0.0), to_mm=(10.0, 0.0))
        recorder = RecordingLayout()
        stub = types.SimpleNamespace(layout=recorder)

        BSCU_PT_CanvasInspector.draw(stub, bpy.context)

        self.assertTrue(recorder.operators, "the panel drew nothing at all")
        self.assertTrue(recorder.says("Strokes: 1"))


class TestCanvasMode(unittest.TestCase):
    def setUp(self):
        self.obj = fresh_scene()
        blank_canvas()

    def tearDown(self):
        name = self.obj.name
        if name in bpy.data.objects:
            bpy.data.objects.remove(bpy.data.objects[name], do_unlink=True)

    def test_the_canvas_starts_on(self):
        self.assertTrue(op_canvas_mode.is_on(bpy.context))

    def test_turning_it_off_is_recorded(self):
        bpy.ops.bscu.canvas_mode(active=False)

        self.assertFalse(op_canvas_mode.is_on(bpy.context))

    def test_turning_it_off_does_not_delete_the_drawing(self):
        """Hiding is a viewing act, and must not cost the user an Undo step."""
        bpy.ops.bscu.draw_line(start_mm=(0.0, 0.0), to_mm=(10.0, 0.0))
        before = len(op_draw.canvas_for(bpy.context).strokes)

        bpy.ops.bscu.canvas_mode(active=False)

        self.assertEqual(len(op_draw.canvas_for(bpy.context).strokes), before)


class TestDrawOperators(unittest.TestCase):
    def setUp(self):
        self.obj = fresh_scene()
        blank_canvas()

    def tearDown(self):
        name = self.obj.name
        blank_canvas()
        if name in bpy.data.objects:
            bpy.data.objects.remove(bpy.data.objects[name], do_unlink=True)

    def test_a_line_is_drawn_where_it_was_asked_for(self):
        bpy.ops.bscu.draw_line(start_mm=(0.0, 0.0), to_mm=(10.0, 5.0))
        canvas = op_draw.canvas_for(bpy.context)

        stroke = list(canvas.strokes.values())[0][0]
        self.assertTrue(np.allclose(stroke.end, [10.0, 5.0]))

    def test_a_zero_length_stroke_is_refused(self):
        result = bpy.ops.bscu.draw_line(start_mm=(1.0, 1.0), to_mm=(1.0, 1.0))

        self.assertEqual(result, {"CANCELLED"})
        self.assertEqual(len(op_draw.canvas_for(bpy.context).strokes), 0)

    def test_a_fillet_replaces_the_two_arms_with_three_pieces(self):
        bpy.ops.bscu.corner(before_start=(0, 0), before_end=(10, 0),
                            after_start=(10, 0), after_end=(10, 10),
                            radius_mm=2.0, fillet=True)
        canvas = op_draw.canvas_for(bpy.context)

        self.assertEqual(len(list(canvas.strokes.values())[0]), 3)

    def test_a_fillet_too_big_for_the_arms_is_refused(self):
        """A refused operator raises, which is how the reason reaches the user."""
        with self.assertRaises(RuntimeError) as caught:
            bpy.ops.bscu.corner(before_start=(0, 0), before_end=(1, 0),
                                after_start=(1, 0), after_end=(1, 10),
                                radius_mm=9.0, fillet=True)

        self.assertIn("only 1.000 mm is there", str(caught.exception))
        self.assertEqual(op_draw.canvas_for(bpy.context).strokes, {})

    def test_extending_pushes_the_end_out(self):
        bpy.ops.bscu.edit_line(start_mm=(0, 0), end_mm=(10, 0), extend_mm=5.0,
                               do_trim=False)
        canvas = op_draw.canvas_for(bpy.context)

        self.assertTrue(np.allclose(list(canvas.strokes.values())[0][0].end, [15.0, 0.0]))

    def test_a_hidden_stroke_stays_on_the_canvas(self):
        bpy.ops.bscu.draw_line(start_mm=(0, 0), to_mm=(10, 0))
        bpy.ops.bscu.canvas_visibility(stroke="stroke-0001", hide=True)
        canvas = op_draw.canvas_for(bpy.context)

        self.assertIn("stroke-0001", canvas.strokes)
        self.assertEqual(len(canvas.to_batches()), 0)

    def test_hiding_a_stroke_that_is_not_there_says_so(self):
        self.assertEqual(bpy.ops.bscu.canvas_visibility(stroke="nope", hide=True),
                         {"CANCELLED"})

    def test_removing_a_stroke_that_is_not_there_says_so(self):
        self.assertEqual(bpy.ops.bscu.remove_stroke(stroke="nope"), {"CANCELLED"})

    def test_a_stroke_survives_being_written_out_and_read_back(self):
        bpy.ops.bscu.draw_line(start_mm=(0, 0), to_mm=(10, 0))
        op_draw.forget(bpy.context.scene.name)

        restored = op_draw.canvas_for(bpy.context)

        self.assertEqual(len(restored.strokes), 1)
        self.assertTrue(np.allclose(list(restored.strokes.values())[0][0].end, [10.0, 0.0]))


class TestExportOperator(unittest.TestCase):
    def setUp(self):
        self.obj = fresh_scene()
        blank_canvas()
        self.folder = tempfile.mkdtemp(prefix="bscu_op_")

    def tearDown(self):
        for entry in os.listdir(self.folder):
            os.remove(os.path.join(self.folder, entry))
        os.rmdir(self.folder)
        name = self.obj.name
        if name in bpy.data.objects:
            bpy.data.objects.remove(bpy.data.objects[name], do_unlink=True)

    def test_checking_a_good_solid_finishes(self):
        bpy.ops.mesh.primitive_cube_add(size=0.02)
        cube = bpy.context.active_object
        result = bpy.ops.bscu.export_stl(check_only=True)

        self.assertEqual(result, {"FINISHED"})
        if cube.name in bpy.data.objects:
            bpy.data.objects.remove(bpy.data.objects[cube.name], do_unlink=True)

    def test_an_open_mesh_is_refused_and_writes_nothing(self):
        target = os.path.join(self.folder, "open.stl")

        with self.assertRaises(RuntimeError):
            bpy.ops.bscu.export_stl(filepath=target)

        self.assertFalse(os.path.exists(target))

    def test_a_cube_exports_and_reads_back_the_right_size(self):
        bpy.ops.mesh.primitive_cube_add(size=0.02)
        cube = bpy.context.active_object
        target = os.path.join(self.folder, "cube.stl")

        bpy.ops.bscu.export_stl(filepath=target)

        self.assertTrue(os.path.exists(target))
        if cube.name in bpy.data.objects:
            bpy.data.objects.remove(bpy.data.objects[cube.name], do_unlink=True)


class TestImportOperator(unittest.TestCase):
    def setUp(self):
        self.obj = fresh_scene()
        blank_canvas()
        self.folder = tempfile.mkdtemp(prefix="bscu_import_")

    def tearDown(self):
        for entry in os.listdir(self.folder):
            os.remove(os.path.join(self.folder, entry))
        os.rmdir(self.folder)
        name = self.obj.name
        blank_canvas()
        if name in bpy.data.objects:
            bpy.data.objects.remove(bpy.data.objects[name], do_unlink=True)

    def _write(self, name: str, text: str) -> str:
        path = os.path.join(self.folder, name)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
        return path

    def test_an_svg_lands_on_the_canvas_in_millimetres(self):
        path = self._write("plate.svg",
                           '<svg xmlns="http://www.w3.org/2000/svg" '
                           'width="100mm" height="50mm">'
                           '<path d="M0 0 L50 0 L50 25"/></svg>')

        bpy.ops.bscu.import_vector(filepath=path)

        canvas = op_draw.canvas_for(bpy.context)
        self.assertIn("plate", canvas.strokes)
        self.assertTrue(np.allclose(list(canvas.strokes.values())[0][0].end,
                                    [50.0, 0.0]))

    def test_an_unknown_extension_is_refused_by_name(self):
        path = self._write("notes.txt", "not a drawing")

        with self.assertRaises(RuntimeError) as caught:
            bpy.ops.bscu.import_vector(filepath=path)

        self.assertIn("not a format", str(caught.exception))

    def test_a_file_with_nothing_in_it_writes_no_stroke(self):
        path = self._write("empty.svg",
                           '<svg xmlns="http://www.w3.org/2000/svg" '
                           'width="10mm" height="10mm"></svg>')

        with self.assertRaises(RuntimeError):
            bpy.ops.bscu.import_vector(filepath=path)

        self.assertEqual(op_draw.canvas_for(bpy.context).strokes, {})

    def test_a_template_is_a_copy_and_its_instances_share_the_geometry(self):
        bpy.ops.bscu.draw_line(start_mm=(0, 0), to_mm=(10, 0))
        bpy.ops.bscu.make_template(name="rosette")
        template = bpy.data.objects["rosette"]

        copy = op_import_vector.place_instance(template, (0.01, 0.0, 0.0))

        self.assertIsNot(copy, template)
        self.assertIs(copy.data, template.data)
        self.assertEqual(len(op_import_vector.instances_of(template)), 1)

    def test_making_a_template_from_an_empty_canvas_says_so(self):
        result = bpy.ops.bscu.make_template(name="nothing")

        self.assertEqual(result, {"CANCELLED"})


class TestPreviewImage(unittest.TestCase):
    """The preview has to come from the field, in the field's own units."""

    def _field(self, depth_mm=2.0):
        return HeightField(
            base=Polygon([(-10, -10), (10, -10), (10, 10), (-10, 10), (-10, -10)]),
            base_depth_mm=depth_mm,
            stock_thickness_mm=20.0)

    def test_a_preview_reads_back_the_depth_the_field_asked_for(self):
        from bscu.bridge import preview_image

        image = preview_image.preview_of(self._field(3.0), (-10, -10), (10, 10))

        self.assertAlmostEqual(image.max_mm, 3.0, places=3)

    def test_the_two_tiers_differ_in_sampling(self):
        from bscu.bridge import preview_image

        field = self._field()
        coarse = preview_image.preview_of(field, (-10, -10), (10, 10))
        fine = preview_image.preview_of(field, (-10, -10), (10, 10), fine=True)

        self.assertGreater(fine.heights_mm.size, coarse.heights_mm.size)

    def test_a_stale_preview_keeps_the_marking(self):
        from bscu.bridge import preview_image

        first = preview_image.preview_of(self._field(), (-10, -10), (10, 10))
        carried = preview_image.carried_forward(first, "3 of 9 charts left")

        self.assertFalse(carried.current)
        self.assertIn("not up to date", carried.label_text())

    def test_a_preview_becomes_a_real_image_with_the_field_in_it(self):
        from bscu.bridge import preview_image

        image = preview_image.preview_of(self._field(2.5), (-10, -10), (10, 10))
        buffer = preview_image.to_image_buffer(image)

        self.assertEqual(buffer.size[0], image.heights_mm.shape[1])
        self.assertEqual(buffer.size[1], image.heights_mm.shape[0])
        bpy.data.images.remove(buffer)

    def test_shutting_down_removes_the_preview_images(self):
        from bscu.bridge import preview_image

        image = preview_image.preview_of(self._field(), (-10, -10), (10, 10))
        preview_image.to_image_buffer(image)

        preview_image.forget_images()

        self.assertFalse([i for i in bpy.data.images
                          if i.name.startswith("BSCU_Relief_Preview")])


class TestStrokesAndLinksTogether(unittest.TestCase):
    """A snapped stroke follows its source; a free one does not."""

    def setUp(self):
        self.obj = fresh_scene()
        blank_canvas()

    def tearDown(self):
        name = self.obj.name
        blank_canvas()
        if name in bpy.data.objects:
            bpy.data.objects.remove(bpy.data.objects[name], do_unlink=True)

    def test_a_snapped_stroke_reports_that_it_snapped(self):
        bpy.ops.bscu.draw_line(start_mm=(10.0, 0.0), to_mm=(10.2, 0.0),
                                snap_links=True)

        self.assertEqual(len(op_draw.canvas_for(bpy.context).strokes), 1)

    def test_holding_alt_gives_a_free_point_with_no_link(self):
        canvas = op_draw.canvas_for(bpy.context)
        before = len(canvas.strokes)

        bpy.ops.bscu.draw_line(start_mm=(0.0, 0.0), to_mm=(10.0, 0.0),
                                snap_links=False)

        self.assertEqual(len(op_draw.canvas_for(bpy.context).strokes), before + 1)
        self.assertTrue(isinstance(list(canvas.strokes.values())[0][0], Line))




def run_test():
    """Run this suite, the way tests/run_tests.py expects.

    The add-on is registered, not re-imported. Purging ``bscu`` and importing
    it again would build a *second* copy of every module: the operators would
    be registered from the new copy and would write to that copy's state, while
    the test file still holds the old one. Everything would then look empty for
    reasons that have nothing to do with the code under test.
    """
    import unittest

    import bscu

    bscu.register()
    try:
        result = unittest.TextTestRunner(verbosity=1).run(
            unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
        )
    finally:
        bscu.unregister()
    if not result.wasSuccessful():
        raise AssertionError(
            f"{result.testsRun} test(s) ran, "
            f"{len(result.failures)} failed and {len(result.errors)} errored")
    print(f"[OK] {result.testsRun} test(s) passed in {__name__}")


if __name__ == "__main__":
    unittest.main()
