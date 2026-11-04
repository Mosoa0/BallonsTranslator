import os
import unittest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from ballontranslator.ui.zoom_control import (
    ZOOM_MAX_PERCENT,
    ZOOM_MIN_PERCENT,
    clamp_percent,
    scaled_percent,
)


class ZoomMathTest(unittest.TestCase):
    def test_clamps_to_canvas_range(self) -> None:
        self.assertEqual(clamp_percent(0), ZOOM_MIN_PERCENT)
        self.assertEqual(clamp_percent(5000), ZOOM_MAX_PERCENT)
        self.assertEqual(clamp_percent(150), 150.0)

    def test_drag_is_proportional_at_every_level(self) -> None:
        # The same pointer distance gives the same ratio, low or high.
        low = scaled_percent(40.0, 50.0) / 40.0
        high = scaled_percent(400.0, 50.0) / 400.0
        self.assertAlmostEqual(low, high)

    def test_drag_back_returns_to_the_start(self) -> None:
        there = scaled_percent(100.0, 120.0)
        self.assertAlmostEqual(scaled_percent(there, -120.0), 100.0)


if __name__ == '__main__':
    unittest.main()
