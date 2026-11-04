import os
import unittest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from ballontranslator.ui.export_all import clamp_range


class ClampRangeTest(unittest.TestCase):
    def test_none_means_every_page(self) -> None:
        self.assertEqual(clamp_range(None, 12), (1, 12))

    def test_valid_range_is_kept(self) -> None:
        self.assertEqual(clamp_range((3, 5), 12), (3, 5))

    def test_reversed_range_is_swapped(self) -> None:
        self.assertEqual(clamp_range((9, 3), 12), (3, 9))

    def test_stale_range_is_clamped_to_the_project(self) -> None:
        # A range picked for a longer project must not index past the end.
        self.assertEqual(clamp_range((10, 40), 12), (10, 12))
        self.assertEqual(clamp_range((0, 500), 12), (1, 12))
        self.assertEqual(clamp_range((30, 40), 12), (12, 12))

    def test_empty_project_selects_nothing(self) -> None:
        first, last = clamp_range(None, 0)
        self.assertGreater(first, last)


if __name__ == '__main__':
    unittest.main()
