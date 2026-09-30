"""Integration test for snapped strokes (UX-9a, UIUX 10.2).

A snapped stroke is a link, not a coordinate: it holds the thing it was snapped
to by ID and follows it when the source moves. That is what makes a stroke
survive an edit to the relief underneath it, and it is why a snapped stroke and
a free one are kept in separate tests rather than one test with a flag.
"""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "src"))
sys.path.insert(0, HERE)

import bpy  # noqa: E402
from bscu_fixtures import blank_canvas, fresh_scene  # noqa: E402

from bscu.core.geom2d import Line  # noqa: E402
from bscu.operators import op_draw  # noqa: E402


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




if __name__ == "__main__":
    unittest.main()


def run_test():
    """Run this suite, the way tests/run_tests.py expects.

    The add-on is registered, not re-imported: purging and re-importing builds
    a second copy of every module, and the operators would then write to that
    copy's state while this file still holds the old one.
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
