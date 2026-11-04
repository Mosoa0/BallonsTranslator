import json
import unittest

from ballontranslator.utils.fontformat import FontFormat


class WordWrapFormatTest(unittest.TestCase):
    def test_off_by_default(self) -> None:
        self.assertFalse(FontFormat().wrap_at_word_boundary)

    def test_older_projects_without_the_field_load_unchanged(self) -> None:
        saved = FontFormat().to_serializable_dict()
        saved.pop('wrap_at_word_boundary', None)
        restored = FontFormat(**json.loads(json.dumps(saved)))
        self.assertFalse(restored.wrap_at_word_boundary)

    def test_enabled_state_survives_save_and_reload(self) -> None:
        saved = FontFormat(wrap_at_word_boundary=True).to_serializable_dict()
        restored = FontFormat(**json.loads(json.dumps(saved)))
        self.assertTrue(restored.wrap_at_word_boundary)


if __name__ == '__main__':
    unittest.main()
