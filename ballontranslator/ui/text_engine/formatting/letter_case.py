"""Letter-case buttons for the font format panel.

The buttons rewrite the selected span of a text item, or the whole item when
nothing is selected, while every character format is preserved. Editing goes
through the same synchronized undo command used by the capitalize shortcut, so
the item document and its paired translation editor stay in step.
"""

from functools import partial
from typing import List, Optional, Tuple

from qtpy.QtCore import QTimer, Signal, Qt
from qtpy.QtWidgets import QFrame, QHBoxLayout, QToolButton

from ballontranslator.utils.text_processing import (
    SENTENCE_TERMINATORS,
    capitalize_sentences,
)

from ..editing.commands import CapitalizeTextItemsCommand
from ..item import TextBlkItem
from .commands import restore_canvas_view_focus
from ... import shared_widget as SW


UPPERCASE = 'uppercase'
LOWERCASE = 'lowercase'
SENTENCE_CASE = 'sentence_case'


def _text_index(text: str, document_position: int) -> int:
    """Convert one UTF-16 document position into a Python string index.

    >>> _text_index('abc', 2)
    2
    >>> _text_index('\U0001f600abc', 3)
    2
    """
    if document_position <= 0:
        return 0
    units = 0
    for index, character in enumerate(text):
        if units >= document_position:
            return index
        units += 2 if ord(character) > 0xFFFF else 1
    return len(text)


def _starts_sentence(text: str, start: int) -> bool:
    """Report whether a span beginning at ``start`` opens a sentence.

    >>> _starts_sentence('one. two', 5)
    True
    >>> _starts_sentence('one two', 4)
    False
    """
    for character in reversed(text[:start]):
        if character.isspace():
            continue
        return character in SENTENCE_TERMINATORS
    return True


def _sentence_case(span: str, capitalize_first: bool) -> str:
    """Apply sentence case, respecting a span that continues a sentence.

    >>> _sentence_case('hELLO. nEXT!', True)
    'Hello. Next!'
    >>> _sentence_case('hELLO world', False)
    'hello world'
    """
    result = capitalize_sentences(span)
    if capitalize_first:
        return result
    for index, character in enumerate(result):
        if character.isalpha():
            return result[:index] + character.lower() + result[index + 1:]
        if character in SENTENCE_TERMINATORS:
            break
    return result


def transform_span(mode: str, text: str, start: int, end: int) -> str:
    """Return ``text[start:end]`` converted to ``mode``.

    >>> transform_span(UPPERCASE, 'one two', 4, 7)
    'TWO'
    >>> transform_span(SENTENCE_CASE, 'one. TWO', 5, 8)
    'Two'
    """
    span = text[start:end]
    if mode == UPPERCASE:
        return span.upper()
    if mode == LOWERCASE:
        return span.lower()
    if mode == SENTENCE_CASE:
        return _sentence_case(span, _starts_sentence(text, start))
    raise ValueError(f'unsupported letter case mode {mode}')


def _selection_span(item: TextBlkItem, text: str) -> Optional[Tuple[int, int]]:
    """Return the edited span, or ``None`` when there is nothing to convert.

    A block selected on the canvas converts as a whole. Once the block is
    being edited the caret drives the conversion, so an empty selection
    converts nothing.
    """
    if not item.isEditing():
        return 0, len(text)
    cursor = item.textCursor()
    if cursor is None or not cursor.hasSelection():
        return None
    return (
        _text_index(text, cursor.selectionStart()),
        _text_index(text, cursor.selectionEnd()),
    )


def _target_pairs(panel) -> List[Tuple[TextBlkItem, object]]:
    """Pair every targeted item with its translation editor."""
    manager = SW.st_manager
    if manager is None or SW.canvas is None:
        return []
    item = getattr(panel, 'textblk_item', None)
    items = [item] if item is not None else SW.canvas.selected_text_items()
    pairs = []
    for blk_item in items:
        if blk_item is None:
            continue
        widgets = manager.pairwidget_list
        if blk_item.idx >= len(widgets):
            continue
        pairs.append((blk_item, widgets[blk_item.idx].e_trans))
    return pairs


def apply_letter_case(panel, mode: str) -> None:
    """Convert the targeted text and push one undoable command."""
    changes = []
    for item, edit in _target_pairs(panel):
        before = item.toPlainText()
        if edit.toPlainText() != before:
            # The pair is mid-sync; skip it rather than desynchronize further.
            continue
        span = _selection_span(item, before)
        if span is None:
            continue
        start, end = span
        after = before[:start] + transform_span(mode, before, start, end) \
            + before[end:]
        if after != before:
            changes.append((item, edit, before, after))
    if not changes:
        return
    SW.canvas.push_undo_command(CapitalizeTextItemsCommand(changes))
    restore_canvas_view_focus()


class LetterCaseBtnGroup(QFrame):
    """Three click-only buttons requesting a letter-case conversion.

    >>> LetterCaseBtnGroup.__name__
    'LetterCaseBtnGroup'
    """

    case_requested = Signal(str)

    BUTTON_LABELS = (
        (UPPERCASE, 'AA'),
        (LOWERCASE, 'aa'),
        (SENTENCE_CASE, 'Aa'),
    )

    # Room for the button's own frame around the widest label.
    LABEL_PADDING = 10

    # Geometry and accent shared with the neighbouring toggles.
    ACCENT_COLOR = '#1e93e5'
    BORDER_WIDTH = 2
    CORNER_RADIUS = 0

    # The click fill would otherwise vanish with the mouse release, too
    # briefly to register as confirmation.
    FLASH_MS = 180

    # These are actions rather than toggles, so nothing stays lit. The
    # transparent border reserves the hover outline's space, keeping the
    # label from shifting.
    BUTTON_STYLE = (
        'QToolButton#LetterCaseButton {{'
        ' background-color: transparent;'
        ' border: {width}px solid transparent;'
        ' border-radius: {radius}px;'
        '}}'
        'QToolButton#LetterCaseButton:hover {{'
        ' border: {width}px solid {color};'
        '}}'
        'QToolButton#LetterCaseButton:pressed,'
        'QToolButton#LetterCaseButton[flashing="true"] {{'
        ' background-color: {color};'
        ' border: {width}px solid {color};'
        ' color: white;'
        '}}'
    )

    def __init__(
        self,
        *args,
        button_size: Tuple[int, int] = (26, 26),
        margins: Tuple[int, int, int, int] = (0, 0, 0, 0),
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.setObjectName('LetterCaseBtnGroup')
        self.setStyleSheet(
            self.BUTTON_STYLE.format(
                color=self.ACCENT_COLOR,
                width=self.BORDER_WIDTH,
                radius=self.CORNER_RADIUS,
            )
        )
        hlayout = QHBoxLayout(self)
        hlayout.setSpacing(0)
        hlayout.setContentsMargins(*margins)
        tooltip_suffix = self.tr(
            'Applies to the selected text, or to the whole text block '
            'when nothing is selected'
        )
        # Spelled out as literals so Qt's translation scanner can find them.
        names = {
            UPPERCASE: self.tr('UPPERCASE'),
            LOWERCASE: self.tr('lowercase'),
            SENTENCE_CASE: self.tr('Sentence case'),
        }
        buttons = []
        for mode, label in self.BUTTON_LABELS:
            button = QToolButton(self)
            button.setObjectName('LetterCaseButton')
            button.setText(label)
            button.setToolTip(f'{names[mode]}\n{tooltip_suffix}')
            button.setAccessibleName(names[mode])
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
            # Click-only controls must not steal the caret from the scene.
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            button.clicked.connect(
                partial(self._request_case, mode, button)
            )
            setattr(self, f'{mode}Btn', button)
            buttons.append(button)
            hlayout.addWidget(button)

        # Uniform buttons wide enough for the widest label; a fixed width
        # narrower than the text makes Qt elide it to an ellipsis.
        width = max(
            button.fontMetrics().horizontalAdvance(button.text())
            for button in buttons
        ) + self.LABEL_PADDING + 2 * self.BORDER_WIDTH
        for button in buttons:
            button.setFixedSize(max(width, button_size[0]), button_size[1])

    def _request_case(self, mode: str, button: QToolButton) -> None:
        self._flash(button)
        self.case_requested.emit(mode)

    def _flash(self, button: QToolButton) -> None:
        """Hold the pressed fill briefly so the click is visible."""
        self._set_flashing(button, True)
        QTimer.singleShot(
            self.FLASH_MS,
            lambda: self._set_flashing(button, False),
        )

    @staticmethod
    def _set_flashing(button: QToolButton, flashing: bool) -> None:
        button.setProperty('flashing', flashing)
        # Property selectors only re-evaluate when the style is refreshed.
        button.style().unpolish(button)
        button.style().polish(button)
