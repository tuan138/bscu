"""Integration test for the canvas inspector panel (UX-9a).

The panel has to *draw*, not merely register. A wrong relative import in a
panel is invisible to every other test and crashes the first time a user
opens the tab, so the real draw body is run here against a recorder.
"""

import os
import sys
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "src"))
sys.path.insert(0, HERE)

import bpy  # noqa: E402
from bscu_fixtures import RecordingLayout, blank_canvas, fresh_scene, run_suite  # noqa: E402

from bscu.operators import op_canvas_mode, op_draw  # noqa: E402
from bscu.ui import panel_inspector  # noqa: E402
from bscu.ui.panel_inspector import BSCU_PT_CanvasInspector  # noqa: E402


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


class _FakeRegion:
    def __init__(self, space):
        self.active = space


class _FakeSpace:
    def __init__(self):
        self.region_3d = _FakeRegion3D()


class _FakeRegion3D:
    def __init__(self):
        self.view_perspective = "PERSP"
        self.view_rotation = (0.0, 0.0, 0.0, 1.0)


class _FakeArea:
    def __init__(self, space):
        self.spaces = _FakeRegion(space)
        self.type = "VIEW_3D"


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

    def test_the_mode_is_kept_on_the_window_not_the_document(self):
        """A view state is not an edit, and must not become an undo step."""
        bpy.ops.bscu.canvas_mode(active=False)

        self.assertNotIn("bscu_canvas_mode", bpy.context.scene.keys())
        self.assertFalse(op_canvas_mode.is_on(bpy.context))

    def test_turning_the_canvas_on_asks_for_top_orthographic(self):
        """Drawing in perspective puts a stroke where the cursor is."""
        space = _FakeSpace()
        area = _FakeArea(space)

        moved = op_canvas_mode.enter_canvas_view(area)

        self.assertTrue(moved)
        self.assertEqual(space.region_3d.view_perspective, "ORTHO")

    def test_entering_the_view_says_so_when_there_is_no_view(self):
        """A background run has no region; saying so beats pretending."""
        self.assertFalse(op_canvas_mode.enter_canvas_view(_FakeArea(None)))

    def test_turning_it_off_does_not_delete_the_drawing(self):
        """Hiding is a viewing act, and must not cost the user an Undo step."""
        bpy.ops.bscu.draw_line(start_mm=(0.0, 0.0), to_mm=(10.0, 0.0))
        before = len(op_draw.canvas_for(bpy.context).strokes)

        bpy.ops.bscu.canvas_mode(active=False)

        self.assertEqual(len(op_draw.canvas_for(bpy.context).strokes), before)


def run_test():
    """Run this suite the way tests/run_tests.py expects."""
    run_suite(__name__)


if __name__ == "__main__":
    unittest.main()
