import unittest

from bscu.core.math_utils import (
    calculate_bevel_slope_height,
    compute_stock_bounding_box,
    meters_to_mm,
    mm_to_meters,
)
from bscu.core.types import CNCBlendMode, CNCCurveMetadata, CNCProfileShape


class TestCoreMathUtils(unittest.TestCase):
    def test_unit_conversions(self):
        self.assertAlmostEqual(mm_to_meters(1000.0), 1.0)
        self.assertAlmostEqual(mm_to_meters(250.0), 0.25)
        self.assertAlmostEqual(meters_to_mm(1.5), 1500.0)

    def test_bevel_slope_calculations(self):
        # Angle 45 deg, tan(45) = 1.0
        self.assertAlmostEqual(calculate_bevel_slope_height(5.0, 45.0, 10.0), 5.0)
        # Clamped to base height 10.0
        self.assertAlmostEqual(calculate_bevel_slope_height(15.0, 45.0, 10.0), 10.0)
        # Zero distance
        self.assertEqual(calculate_bevel_slope_height(0.0, 45.0, 10.0), 0.0)

    def test_stock_bounding_box(self):
        min_pt, max_pt = compute_stock_bounding_box(200.0, 300.0, 50.0)
        self.assertEqual(min_pt, (-100.0, -150.0, 0.0))
        self.assertEqual(max_pt, (100.0, 150.0, 50.0))

    def test_curve_metadata_dataclass(self):
        meta = CNCCurveMetadata(
            base_height=10.0,
            bevel_angle=45.0,
            bevel_depth=5.0,
            profile_shape=CNCProfileShape.DOME,
            blend_mode=CNCBlendMode.ADD,
        )
        self.assertEqual(meta.base_height, 10.0)
        self.assertEqual(meta.profile_shape, CNCProfileShape.DOME)


if __name__ == "__main__":
    unittest.main()
