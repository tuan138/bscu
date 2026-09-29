"""Guard the panel drawing code against UILayout API misuse.

Blender's ``layout.operator()`` returns a properties struct with no ``enabled``
attribute; assigning one only fails while a real UI is drawing, which no
headless test would catch. These fakes reject unknown attributes exactly like
the real API so the mistake surfaces here instead. That crash was found by
drawing the panel in a live Blender GUI.
"""

import unittest

from bscu.core.draw_downstream import draw_gated_tab
from bscu.core.draw_steps import STATUS_ICONS, draw_step_row
from bscu.core.draw_stock import draw_no_stock, draw_stock_summary
from bscu.core.workflow import STEP_ORDER, StepFacts, StepStatus


class FakeOperatorProperties:
    """Mimics the struct returned by layout.operator(): declared props only."""

    ALLOWED = {"step"}

    def __setattr__(self, name, value):
        if name not in self.ALLOWED:
            raise AttributeError(f"operator properties struct has no {name!r}")
        object.__setattr__(self, name, value)


class FakeLayout:
    """Minimal UILayout stand-in that records the widgets a panel creates."""

    def __init__(self, recorder):
        object.__setattr__(self, "_recorder", recorder)

    def row(self, **kwargs):
        self._recorder.containers.append("row")
        return FakeLayout(self._recorder)

    def box(self):
        self._recorder.containers.append("box")
        return FakeLayout(self._recorder)

    def separator(self, **kwargs):
        self._recorder.containers.append("separator")

    def label(self, text="", icon=""):
        self._recorder.labels.append((text, icon))

    def operator(self, idname, text="", depress=False, icon=""):
        self._recorder.operators.append((idname, text, depress))
        return FakeOperatorProperties()

    def __setattr__(self, name, value):
        if name.startswith("_"):
            object.__setattr__(self, name, value)
            return
        self._recorder.layout_flags.append((name, value))


class Recorder:
    def __init__(self):
        self.containers = []
        self.labels = []
        self.operators = []
        self.layout_flags = []

    @property
    def texts(self):
        return [t for t, _ in self.labels]

    @property
    def icons(self):
        return [i for _, i in self.labels if i]


def _stock_only_facts() -> StepFacts:
    return StepFacts(has_stock=True, stock_is_mesh=True)


def _through_caro() -> StepFacts:
    return StepFacts(has_stock=True, stock_is_mesh=True, has_uv_active=True)


def _draw_step_bar(facts, active_step="STOCK") -> Recorder:
    recorder = Recorder()
    layout = FakeLayout(recorder)
    for step in STEP_ORDER:
        draw_step_row(layout, facts, step, StepStatus.NOT_DONE, active_step)
    return recorder


class TestStepRowDrawing(unittest.TestCase):
    def test_draws_one_button_per_step(self):
        recorder = _draw_step_bar(_stock_only_facts())
        self.assertEqual(
            [op[0] for op in recorder.operators], ["bscu.set_step"] * len(STEP_ORDER)
        )

    def test_never_assigns_enabled_on_the_operator(self):
        """Regresses the live-GUI crash: op.enabled raises in the real API."""
        _draw_step_bar(_stock_only_facts())

    def test_locked_step_disables_its_row_instead(self):
        recorder = _draw_step_bar(_stock_only_facts())
        self.assertIn(("enabled", False), recorder.layout_flags)

    def test_unlocked_step_keeps_its_row_enabled(self):
        recorder = _draw_step_bar(_through_caro())
        self.assertIn(("enabled", True), recorder.layout_flags)

    def test_active_step_is_pressed(self):
        recorder = _draw_step_bar(_stock_only_facts(), active_step="SEAM")
        self.assertEqual(
            [op[2] for op in recorder.operators],
            [step == "SEAM" for step in STEP_ORDER],
        )

    def test_locked_row_states_which_step_blocks_it(self):
        recorder = _draw_step_bar(_stock_only_facts())
        self.assertTrue(
            any("Hoàn thành" in t and "Caro" in t for t in recorder.texts),
            recorder.texts,
        )

    def test_every_status_has_an_icon(self):
        icons = set()
        for status in StepStatus:
            recorder = Recorder()
            draw_step_row(FakeLayout(recorder), _stock_only_facts(), "STOCK", status, "STOCK")
            icons.update(recorder.icons)
        for status in StepStatus:
            self.assertIn(STATUS_ICONS[status], icons, f"no icon for {status}")


class TestStockDrawing(unittest.TestCase):
    def test_missing_stock_prompts_a_selection(self):
        recorder = Recorder()
        draw_no_stock(FakeLayout(recorder))
        self.assertTrue(any("Chưa chọn phôi" in t for t in recorder.texts))

    def test_mesh_summary_reports_size_and_topology(self):
        recorder = Recorder()
        draw_stock_summary(
            FakeLayout(recorder),
            name="PhoiDe",
            obj_type="MESH",
            dims_mm=(50.0, 50.0, 50.0),
            vert_count=152,
            face_count=150,
            has_uv=False,
        )
        joined = " | ".join(recorder.texts)
        self.assertIn("PhoiDe", joined)
        self.assertIn("50.0 × 50.0 × 50.0 mm", joined)
        self.assertIn("152", joined)
        self.assertIn("150", joined)
        self.assertIn("Chưa có bản trải BSCU", joined)

    def test_non_mesh_is_rejected_without_topology_numbers(self):
        recorder = Recorder()
        draw_stock_summary(
            FakeLayout(recorder),
            name="Camera",
            obj_type="CAMERA",
            dims_mm=(0.0, 0.0, 0.0),
            vert_count=0,
            face_count=0,
            has_uv=False,
        )
        self.assertTrue(any("Chỉ Mesh" in t for t in recorder.texts), recorder.texts)
        self.assertFalse(any("Số đỉnh" in t for t in recorder.texts))


class TestGatedTabDrawing(unittest.TestCase):
    def test_locked_tab_names_the_blocker_and_hides_the_roadmap(self):
        recorder = Recorder()
        draw_gated_tab(FakeLayout(recorder), _stock_only_facts(), "LAYOUT")
        self.assertTrue(any("Caro" in t for t in recorder.texts), recorder.texts)
        self.assertFalse(any("UX-" in t for t in recorder.texts), recorder.texts)

    def test_unlocked_tab_lists_its_roadmap(self):
        recorder = Recorder()
        draw_gated_tab(FakeLayout(recorder), _through_caro(), "LAYOUT")
        self.assertTrue(any("UX-" in t for t in recorder.texts), recorder.texts)


if __name__ == "__main__":
    unittest.main()
