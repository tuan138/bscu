"""Unit tests for the DXF reader (UX-13, UIUX 10.6).

DXF is a tagged text format: every value is a group code on one line and its
value on the next. That makes it easy to parse and easy to get quietly wrong,
so the tests here are mostly about refusing clearly rather than accepting
something that would become bad geometry later:

* units come from ``$INSUNITS`` and a file without one is a question, not a
  guess;
* an entity the reader does not understand is named, not dropped;
* a bulge on a polyline really does produce an arc, because that is the whole
  reason bulges exist.
"""

import unittest

import numpy as np

from bscu.core.dxf_import import (
    DxfError,
    parse_dxf,
    scale_to_mm,
)


def tag(code: int, value) -> str:
    return f"{code}\n{value}\n"


def entities(*body: str) -> str:
    return tag(0, "SECTION") + tag(2, "ENTITIES") + "".join(body) + \
        tag(0, "ENDSEC") + tag(0, "EOF")


def header(*values) -> str:
    """Group codes in the HEADER section; $INSUNITS is code 70."""
    body = "".join(tag(code, value) for code, value in values)
    return tag(0, "SECTION") + tag(2, "HEADER") + body + tag(0, "ENDSEC")


def insunits(value: int) -> str:
    return header((70, value))


class TestGroupCodes(unittest.TestCase):
    def test_a_line_becomes_a_segment_in_millimetres(self):
        text = entities(tag(0, "LINE") + tag(8, "0")
                        + tag(10, 0.0) + tag(20, 0.0)
                        + tag(11, 25.4) + tag(21, 0.0))

        result = parse_dxf(text)

        segment = result.shapes[0]
        self.assertAlmostEqual(segment["length_mm"], 25.4)
        self.assertAlmostEqual(segment["points"][0][0], 0.0)
        self.assertAlmostEqual(segment["points"][-1][0], 25.4)

    def test_a_circle_carries_its_centre_and_radius(self):
        text = entities(tag(0, "CIRCLE") + tag(10, 5.0) + tag(20, 5.0)
                        + tag(40, 2.5))

        result = parse_dxf(text)

        self.assertEqual(result.shapes[0]["kind"], "arc")
        self.assertAlmostEqual(result.shapes[0]["radius_mm"], 2.5)

    def test_an_arc_keeps_its_start_and_end_angles(self):
        text = entities(tag(0, "ARC") + tag(10, 0.0) + tag(20, 0.0)
                        + tag(40, 10.0) + tag(50, 0.0) + tag(51, 90.0))

        result = parse_dxf(text)

        arc = result.shapes[0]
        self.assertAlmostEqual(arc["start_deg"], 0.0)
        self.assertAlmostEqual(arc["end_deg"], 90.0)

    def test_a_lwpolyline_becomes_an_open_run(self):
        text = entities(tag(0, "LWPOLYLINE") + tag(8, "cut")
                        + tag(90, 3)
                        + tag(10, 0.0) + tag(20, 0.0)
                        + tag(10, 10.0) + tag(20, 0.0)
                        + tag(10, 10.0) + tag(20, 5.0))

        result = parse_dxf(text)

        self.assertEqual(result.shapes[0]["kind"], "polyline")
        self.assertEqual(len(result.shapes[0]["points"]), 3)
        self.assertFalse(result.shapes[0]["closed"])

    def test_a_closed_lwpolyline_is_marked_closed(self):
        text = entities(tag(0, "LWPOLYLINE") + tag(90, 2)
                        + tag(70, 1)
                        + tag(10, 0.0) + tag(20, 0.0)
                        + tag(10, 10.0) + tag(20, 0.0))

        result = parse_dxf(text)

        self.assertTrue(result.shapes[0]["closed"])

    def test_a_bulge_turns_a_straight_run_into_an_arc(self):
        """A bulge is the tangent of a quarter of the included angle."""
        text = entities(tag(0, "LWPOLYLINE") + tag(90, 2)
                        + tag(10, 0.0) + tag(20, 0.0) + tag(42, 1.0)
                        + tag(10, 10.0) + tag(20, 0.0))

        result = parse_dxf(text)

        polyline = result.shapes[0]
        self.assertTrue(polyline["has_arcs"],
                        "a bulge of 1 is a 90 degree arc, not a straight line")

    def test_the_layer_name_is_kept(self):
        text = entities(tag(0, "LINE") + tag(8, "engraving")
                        + tag(10, 0.0) + tag(20, 0.0)
                        + tag(11, 1.0) + tag(21, 0.0))

        result = parse_dxf(text)

        self.assertEqual(result.shapes[0]["layer"], "engraving")

    def test_splines_and_ellipses_are_sampled_rather_than_skipped(self):
        """Neither has a shape the rest of the pipeline knows, so each becomes
        a run of points rather than being quietly left out."""
        text = entities(
            tag(0, "SPLINE") + tag(10, 0.0) + tag(20, 0.0)
            + tag(10, 5.0) + tag(20, 5.0),
            tag(0, "ELLIPSE") + tag(10, 0.0) + tag(20, 0.0)
            + tag(11, 4.0) + tag(21, 0.0)
            + tag(40, 0.5) + tag(41, 0.0) + tag(42, 6.283),
        )

        result = parse_dxf(text)

        self.assertEqual(len(result.shapes), 2)
        for shape in result.shapes:
            self.assertEqual(shape["kind"], "polyline")
            self.assertGreaterEqual(len(shape["points"]), 2)


class TestUnits(unittest.TestCase):
    def test_inches_are_converted_to_millimetres(self):
        text = insunits(1) + entities(
            tag(0, "LINE") + tag(10, 0.0) + tag(20, 0.0)
            + tag(11, 1.0) + tag(21, 0.0))

        result = parse_dxf(text)

        self.assertAlmostEqual(result.shapes[0]["length_mm"], 25.4)

    def test_millimetres_are_left_alone(self):
        text = insunits(4) + entities(
            tag(0, "LINE") + tag(10, 0.0) + tag(20, 0.0)
            + tag(11, 7.0) + tag(21, 0.0))

        result = parse_dxf(text)

        self.assertAlmostEqual(result.shapes[0]["length_mm"], 7.0)

    def test_metres_are_converted(self):
        text = insunits(6) + entities(
            tag(0, "LINE") + tag(10, 0.0) + tag(20, 0.0)
            + tag(11, 0.5) + tag(21, 0.0))

        result = parse_dxf(text)

        self.assertAlmostEqual(result.shapes[0]["length_mm"], 500.0)

    def test_a_file_with_no_units_says_so_rather_than_guessing(self):
        text = entities(tag(0, "LINE") + tag(10, 0.0) + tag(20, 0.0)
                        + tag(11, 1.0) + tag(21, 0.0))

        result = parse_dxf(text)

        self.assertTrue(any("UNITS_MISSING" in issue for issue in result.issues),
                        result.issues)

    def test_the_scale_factor_is_reported(self):
        self.assertAlmostEqual(scale_to_mm(1), 25.4)
        self.assertAlmostEqual(scale_to_mm(4), 1.0)
        self.assertAlmostEqual(scale_to_mm(0), 1.0)


class TestBadInput(unittest.TestCase):
    def test_a_file_without_eof_is_refused(self):
        with self.assertRaises(DxfError) as caught:
            parse_dxf(tag(0, "SECTION") + tag(2, "ENTITIES"))

        self.assertIn("EOF", str(caught.exception))

    def test_an_odd_number_of_tag_lines_is_refused(self):
        with self.assertRaises(DxfError):
            parse_dxf("0\nLINE\n10\n")

    def test_a_non_numeric_coordinate_is_refused_by_name(self):
        text = entities(tag(0, "LINE") + tag(10, "left") + tag(20, 0.0)
                        + tag(11, 1.0) + tag(21, 0.0))

        with self.assertRaises(DxfError) as caught:
            parse_dxf(text)

        self.assertIn("10", str(caught.exception))

    def test_an_entity_the_reader_does_not_know_is_named_not_dropped(self):
        text = entities(tag(0, "XLINE") + tag(10, 0.0) + tag(20, 0.0)
                        + tag(11, 1.0) + tag(21, 1.0))

        result = parse_dxf(text)

        self.assertIn("XLINE", " ".join(result.issues))
        self.assertEqual(len(result.shapes), 0)

    def test_a_file_with_no_entities_is_empty_not_broken(self):
        result = parse_dxf(tag(0, "SECTION") + tag(2, "ENTITIES")
                           + tag(0, "ENDSEC") + tag(0, "EOF"))

        self.assertEqual(result.shapes, [])

    def test_an_empty_file_is_refused(self):
        with self.assertRaises(DxfError):
            parse_dxf("")


class TestScale(unittest.TestCase):
    def test_every_shape_is_reported_in_millimetres(self):
        text = insunits(1) + entities(
            tag(0, "CIRCLE") + tag(10, 0.0) + tag(20, 0.0) + tag(40, 1.0),
            tag(0, "LWPOLYLINE") + tag(90, 2)
            + tag(10, 0.0) + tag(20, 0.0) + tag(10, 2.0) + tag(20, 0.0),
        )

        result = parse_dxf(text)

        for shape in result.shapes:
            self.assertEqual(shape["units"], "mm")
        self.assertAlmostEqual(result.shapes[0]["radius_mm"], 25.4)
        self.assertAlmostEqual(result.shapes[1]["length_mm"], 50.8)

    def test_the_parsed_points_are_arrays(self):
        text = entities(tag(0, "LWPOLYLINE") + tag(90, 2)
                        + tag(10, 0.0) + tag(20, 0.0)
                        + tag(10, 1.0) + tag(20, 0.0))

        result = parse_dxf(text)

        self.assertIsInstance(result.shapes[0]["points"], np.ndarray)


if __name__ == "__main__":
    unittest.main()
