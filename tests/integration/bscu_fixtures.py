"""Shared fixtures for the BSCU integration suites.

Kept in one place because every suite that touches the canvas needs the same
three things: a clean scene, an empty canvas, and a layout that records what a
panel drew. Duplicating them is how two suites end up disagreeing about what a
"blank" scene is.
"""

import os
import sys

import bpy

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src"))


def run_suite(module_name: str) -> None:
    """Run this module's tests the way tests/run_tests.py expects.

    The add-on is registered, not re-imported. Purging ``bscu`` and importing it
    again builds a *second* copy of every module: the operators would be
    registered from the new copy and write to that copy's state, while the suite
    still holds the old one, and everything would look empty for reasons that
    have nothing to do with the code under test.
    """
    import unittest

    import bscu

    bscu.register()
    try:
        result = unittest.TextTestRunner(verbosity=1).run(
            unittest.defaultTestLoader.loadTestsFromModule(sys.modules[module_name])
        )
    finally:
        bscu.unregister()
    if not result.wasSuccessful():
        raise AssertionError(
            f"{result.testsRun} test(s) ran, {len(result.failures)} failed "
            f"and {len(result.errors)} errored")
    print(f"[OK] {result.testsRun} test(s) passed in {module_name}")


def fresh_scene():
    """An empty scene with one grid to be active."""
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    bpy.ops.mesh.primitive_grid_add(x_subdivisions=2, y_subdivisions=2)
    return bpy.context.active_object


def blank_canvas():
    """Start with no drawing.

    The canvas is stored on the scene on purpose, so saving the file saves the
    drawing. That is right for the product and wrong for tests, which share one
    scene: each has to clear both the cached copy and the stored one.
    """
    from bscu.operators import op_draw

    op_draw.forget(bpy.context.scene.name)
    # Written empty rather than deleted: a leftover stroke would be picked up
    # as a snap target by the next test.
    for key in ("bscu_strokes", "bscu_hidden", "bscu_selection"):
        bpy.context.scene[key] = "{}"


class RecordingLayout:
    """Stands in for a UILayout and remembers what was asked of it.

    Not a pixel test. The point is that drawing a panel runs every line of it,
    which is where a wrong import shows up.
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
