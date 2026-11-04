import os
import unittest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from ballontranslator.ui.text_engine.formatting.letter_case import (
    LOWERCASE,
    SENTENCE_CASE,
    UPPERCASE,
    transform_span,
)


class TransformSpanTest(unittest.TestCase):
    def test_upper_and_lower(self) -> None:
        self.assertEqual(transform_span(UPPERCASE, 'one two', 4, 7), 'TWO')
        self.assertEqual(transform_span(LOWERCASE, 'ONE TWO', 0, 3), 'one')

    def test_sentence_case_on_whole_text(self) -> None:
        text = 'hELLO THERE. nEXT ONE!'
        self.assertEqual(
            transform_span(SENTENCE_CASE, text, 0, len(text)),
            'Hello there. Next one!',
        )

    def test_sentence_case_capitalizes_a_span_that_opens_a_sentence(self) -> None:
        self.assertEqual(
            transform_span(SENTENCE_CASE, 'one. TWO', 5, 8), 'Two'
        )

    def test_sentence_case_mid_sentence_stays_lowercase(self) -> None:
        self.assertEqual(
            transform_span(SENTENCE_CASE, 'one TWO three', 4, 7), 'two'
        )

    def test_unknown_mode_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            transform_span('title', 'abc', 0, 3)


if __name__ == '__main__':
    unittest.main()
