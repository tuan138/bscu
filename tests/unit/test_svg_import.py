"""Unit tests for the SVG reader (UX-13, UIUX 10.6).

The conversion is the thing worth testing. A drawing is right or wrong by
millimetres, and a file that is 25.4 times out will look fine in the viewport
and cut a plate the wrong size. So the numbers here are the ones the format
itself is defined against: 96 pixels per inch, and the document's own width
taking priority over any assumption.
"""

import unittest

from bscu.core.svg_import import PX_PER_MM, parse_svg


def svg(body: str, **attributes) -> str:
    head = " ".join(f'{name.replace("_", "-")}="{value}"'
                    for name, value in attributes.items())
    return f'<svg xmlns="http://www.w3.org/2000/svg" {head}>{body}</svg>'


class TestUnits(unittest.TestCase):
    def test_pixels_become_millimetres_at_the_formats_own_rate(self):
        """SVG's units are defined at 96 px per inch, and so are ours."""
        result = parse_svg(svg("", width="96", height="96"))

        self.assertAlmostEqual(result.width_mm, 25.4)
        self.assertAlmostEqual(PX_PER_MM, 96.0 / 25.4)

    def test_millimetres_in_the_file_are_left_alone(self):
        result = parse_svg(svg("", width="300mm", height="200mm"))

        self.assertAlmostEqual(result.width_mm, 300.0)
        self.assertAlmostEqual(result.height_mm, 200.0)

    def test_inches_in_the_file_are_converted(self):
        result = parse_svg(svg("", width="2in", height="1in"))

        self.assertAlmostEqual(result.width_mm, 50.8)

    def test_a_file_with_no_size_is_reported_rather_than_guessed(self):
        result = parse_svg(svg('<path d="M0 0 L10 0"/>'))

        self.assertTrue(any("UNITS_MISSING" in issue for issue in result.issues),
                        result.issues)

    def test_a_view_box_scales_the_drawing_to_the_stated_size(self):
        """A CAD export sized in different pixels still has to land right."""
        result = parse_svg(svg('<path d="M0 0 L100 0"/>', width="100mm",
                               height="50mm", viewBox="0 0 100 50"))

        self.assertAlmostEqual(result.width_mm, 100.0)
        self.assertAlmostEqual(result.shapes[0]["length_mm"], 100.0)

    def test_a_bare_size_means_pixels_as_the_format_says(self):
        result = parse_svg(svg('<path d="M0 0 L96 0"/>', width="200", height="50"))

        self.assertAlmostEqual(result.shapes[0]["length_mm"], 25.4)

    def test_an_absolute_size_is_taken_at_its_word_and_says_so(self):
        """A 100 mm plate read as pixels would be 26 mm with nothing to show it."""
        result = parse_svg(svg('<path d="M0 0 L50 0"/>', width="100mm",
                               height="50mm"))

        self.assertAlmostEqual(result.shapes[0]["length_mm"], 50.0)
        self.assertTrue(any("UNITS_INFERRED" in issue for issue in result.issues))

    def test_a_view_box_with_the_wrong_number_of_values_is_reported(self):
        result = parse_svg(svg("", viewBox="0 0 100"))

        self.assertTrue(any("viewBox" in issue for issue in result.issues))


class TestPaths(unittest.TestCase):
    def test_a_straight_path_becomes_a_run_of_points(self):
        result = parse_svg(svg('<path d="M0 0 L10 0 L10 10"/>', width="100", height="100"))

        self.assertEqual(len(result.shapes), 1)
        self.assertEqual(result.shapes[0]["points"].shape, (3, 2))

    def test_a_curve_contributes_its_far_point(self):
        result = parse_svg(svg('<path d="M0 0 C1 1 2 1 3 0"/>', width="100", height="100"))

        self.assertGreaterEqual(len(result.shapes[0]["points"]), 2)

    def test_an_arc_contributes_its_end_point(self):
        result = parse_svg(svg('<path d="M0 0 A5 5 0 0 1 10 0"/>', width="100",
                               height="100"))

        self.assertGreaterEqual(len(result.shapes[0]["points"]), 2)

    def test_a_path_with_no_data_is_reported(self):
        result = parse_svg(svg("<path/>", width="100", height="100"))

        self.assertTrue(any("no data" in issue for issue in result.issues))

    def test_path_data_starting_with_a_number_is_refused(self):
        with self.assertRaises(ValueError):
            parse_svg(svg('<path d="10 10 L20 0"/>', width="100", height="100"))

    def test_an_unknown_path_command_is_named(self):
        with self.assertRaises(ValueError) as caught:
            parse_svg(svg('<path d="M0 0 W5 5"/>', width="100", height="100"))
        self.assertIn("W", str(caught.exception))


class TestBasicShapes(unittest.TestCase):
    def test_a_rectangle_comes_back_as_four_points(self):
        result = parse_svg(svg('<rect x="0" y="0" width="10" height="20"/>',
                               width="100", height="100"))

        points = result.shapes[0]["points"]
        self.assertEqual(points.shape, (4, 2))
        self.assertTrue(result.shapes[0]["closed"])

    def test_a_circle_keeps_its_centre_and_radius(self):
        """A radius written in millimetres in the file is taken at its word."""
        result = parse_svg(svg('<circle cx="5mm" cy="5mm" r="3mm"/>', width="100mm",
                               height="100mm"))

        self.assertEqual(result.shapes[0]["kind"], "arc")
        self.assertAlmostEqual(result.shapes[0]["radius_mm"], 3.0)

    def test_a_line_is_open(self):
        result = parse_svg(svg('<line x1="0" y1="0" x2="10" y2="0"/>',
                               width="100", height="100"))

        self.assertFalse(result.shapes[0]["closed"])

    def test_a_polygon_is_closed_and_a_polyline_is_not(self):
        body = ('<polygon points="0,0 10,0 10,10"/><polyline points="0,0 5,5 10,0"/>')
        result = parse_svg(svg(body, width="100", height="100"))

        self.assertTrue(result.shapes[0]["closed"])
        self.assertFalse(result.shapes[1]["closed"])

    def test_a_polygon_with_an_odd_number_of_numbers_is_reported(self):
        result = parse_svg(svg('<polygon points="0,0 10,0 10"/>', width="100",
                               height="100"))

        self.assertTrue(any("whole number of points" in issue
                            for issue in result.issues))


class TestOneLayerRule(unittest.TestCase):
    def test_only_the_asked_for_layer_comes_in(self):
        body = ('<path id="keep" d="M0 0 L10 0"/>'
                '<path id="other" d="M0 5 L10 5"/>')
        result = parse_svg(svg(body, width="100", height="100"),
                           target_layer="keep")

        self.assertEqual(len(result.shapes), 1)
        self.assertEqual(result.shapes[0]["layer"], "keep")

    def test_the_layers_left_out_are_named(self):
        body = '<path id="other" d="M0 5 L10 5"/>'
        result = parse_svg(svg(body, width="100", height="100"),
                           target_layer="keep")

        self.assertTrue(any("other" in issue for issue in result.issues),
                        result.issues)

    def test_everything_shapes_says_what_it_is_in_millimetres(self):
        body = ('<rect x="0" y="0" width="10" height="20"/>'
                '<circle cx="5" cy="5" r="3"/>')
        result = parse_svg(svg(body, width="100", height="100"))

        for shape in result.shapes:
            self.assertEqual(shape["units"], "mm")


class TestBadInput(unittest.TestCase):
    def test_an_empty_file_is_refused(self):
        with self.assertRaises(ValueError):
            parse_svg("")

    def test_a_file_that_is_not_xml_is_refused(self):
        with self.assertRaises(ValueError) as caught:
            parse_svg("<svg><path")
        self.assertIn("XML", str(caught.exception))

    def test_an_element_the_reader_does_not_know_is_named(self):
        result = parse_svg(svg("<video/>", width="100", height="100"))

        self.assertTrue(any("video" in issue for issue in result.issues))

    def test_a_drawing_with_nothing_in_it_is_empty_not_broken(self):
        result = parse_svg(svg("", width="100", height="100"))

        self.assertEqual(result.shapes, [])
        self.assertTrue(result.ok)


if __name__ == "__main__":
    unittest.main()
