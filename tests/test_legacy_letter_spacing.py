import json
import unittest

from ballontranslator.utils.fontformat import FontFormat


def reload(font_format: FontFormat) -> FontFormat:
    """Round-trip through the JSON a project file stores."""
    return FontFormat(**json.loads(json.dumps(
        font_format.to_serializable_dict()
    )))


class LegacyLetterSpacingTest(unittest.TestCase):
    def test_legacy_zero_reads_as_no_extra_spacing(self) -> None:
        # Older projects stored extra spacing, where 0 meant none.
        self.assertEqual(FontFormat(letter_spacing=0).letter_spacing, 1.0)
        self.assertEqual(FontFormat(letter_spacing=0.0).letter_spacing, 1.0)

    def test_real_multipliers_are_kept(self) -> None:
        self.assertEqual(FontFormat(letter_spacing=1.2).letter_spacing, 1.2)
        self.assertEqual(reload(FontFormat(letter_spacing=0.8)).letter_spacing, 0.8)


if __name__ == '__main__':
    unittest.main()
