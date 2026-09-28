import math
import unittest


def calculate_bevel_height(dist: float, bevel_angle_deg: float, base_height: float) -> float:
    """Calculate bevel height from SDF distance, angle and clamp limit."""
    if dist <= 0:
        return 0.0
    angle_rad = math.radians(bevel_angle_deg)
    slope_h = dist * math.tan(angle_rad)
    return min(slope_h, base_height)


class TestBevelSlopeMath(unittest.TestCase):
    def test_zero_distance(self):
        self.assertEqual(calculate_bevel_height(0.0, 45.0, 10.0), 0.0)

    def test_slope_45_deg(self):
        # tan(45 deg) = 1.0 -> height = dist
        self.assertAlmostEqual(calculate_bevel_height(5.0, 45.0, 10.0), 5.0)

    def test_height_clamp(self):
        # 15.0 * tan(45) = 15.0, but clamped to base_height = 10.0
        self.assertEqual(calculate_bevel_height(15.0, 45.0, 10.0), 10.0)


if __name__ == "__main__":
    unittest.main()
