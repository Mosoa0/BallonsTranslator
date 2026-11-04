"""Export result images for every page, or for a chosen page range.

The project saves a result image only for the page on screen, so exporting a
chapter means visiting each page by hand. This walks the page list, renders
each selected page and writes it with the configured format and quality,
then returns to the page that was open.
"""

import os.path as osp
from typing import Optional, Tuple

from qtpy.QtCore import QCoreApplication, QEvent, QObject, QSignalBlocker, Qt
from qtpy.QtGui import QMouseEvent, QResizeEvent
from qtpy.QtWidgets import (
    QApplication,
    QCheckBox,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QWidget,
)

from ballontranslator.utils.config import pcfg
from ballontranslator.utils.logger import logger as LOGGER
from ballontranslator.utils.shared import CONFIG_FONTSIZE_CONTENT

from .custom_widget import MessageBox, ProgressMessageBox
from .page_range_progress import PageRangeSpinBox


def export_all_result_images(
    window, page_range: Optional[Tuple[int, int]] = None
) -> None:
    """Render and save result images for a page range, or for every page.

    ``page_range`` is a 1-based inclusive ``(first, last)`` pair, or None
    for the whole project. It is clamped to the pages that exist, so a
    stale selection can never index past the end.
    """
    project = window.imgtrans_proj
    if not project.img_valid:
        return
    all_pages = list(project.pages.keys())
    if not all_pages:
        return

    first, last = clamp_range(page_range, len(all_pages))
    pages = all_pages[first - 1:last]
    if not pages:
        return
    offset = first - 1

    page_list = window.pageList
    start_row = page_list.currentRow()

    # The page on screen may hold edits that only exist in its editors.
    # Flush them before rendering anything.
    if window.canvas.projstate_unsaved:
        window.saveCurrentPage(restore_interface=True)

    state = _suspend_interface(window)
    dialog = ProgressMessageBox(
        QCoreApplication.translate('MainWindow', 'Exporting result images'),
        show_stop_btn=True,
        parent=window,
    )
    stopped = {'value': False}
    dialog.stop_clicked.connect(lambda: stopped.__setitem__('value', True))
    dialog.show()
    QApplication.processEvents()

    exported, failed = 0, []
    try:
        for index, page_name in enumerate(pages):
            if stopped['value']:
                break
            dialog.updateTaskProgress(
                int(index / len(pages) * 100), page_name
            )
            QApplication.processEvents()
            try:
                row = offset + index
                if row != page_list.currentRow():
                    # Switching rows loads the page synchronously, and saves
                    # the previous one if the user had left it dirty.
                    page_list.setCurrentRow(row)
                window.saveCurrentPage(
                    update_scene_text=False,
                    save_proj=False,
                    restore_interface=False,
                    save_rst_only=True,
                )
                exported += 1
            except Exception as error:
                LOGGER.error('Failed to export %s: %s', page_name, error)
                failed.append(page_name)
    finally:
        if (
            0 <= start_row < len(all_pages)
            and page_list.currentRow() != start_row
        ):
            page_list.setCurrentRow(start_row)
        _restore_interface(window, state)
        dialog.close()
        dialog.deleteLater()

    _report(window, exported, failed, stopped['value'], project)


def _suspend_interface(window) -> dict:
    """Turn off the per-page view state the renderer would otherwise toggle.

    saveCurrentPage only restores these when it is asked to restore the
    interface, which it cannot do per page without flickering the whole
    window once per image. Doing it once around the loop is both correct
    and far cheaper.
    """
    state = {'textblock': pcfg.imgtrans_textblock, 'shape_control': False}
    if state['textblock']:
        window.bottomBar.textblockChecker.click()
    shape_control = window.st_manager.txtblkShapeControl
    if shape_control.isVisible():
        state['shape_control'] = True
        shape_control.hide()
    return state


def _restore_interface(window, state: dict) -> None:
    if state.get('shape_control'):
        window.st_manager.txtblkShapeControl.show()
    if state.get('textblock') != pcfg.imgtrans_textblock:
        window.bottomBar.textblockChecker.click()


def _report(window, exported: int, failed: list, stopped: bool, project) -> None:
    """Say what was written, and where."""
    try:
        directory = project.result_dir()
    except Exception:
        directory = ''
    lines = []
    if stopped:
        lines.append(QCoreApplication.translate('MainWindow', 'Export stopped.'))
    lines.append(
        QCoreApplication.translate(
            'MainWindow', 'Saved {n} result image(s) as {ext}.'
        ).format(
            n=exported, ext=pcfg.imgsave_ext
        )
    )
    if directory and osp.exists(directory):
        lines.append(directory)
    if failed:
        lines.append(
            QCoreApplication.translate('MainWindow', 'Failed: {pages}').format(
                pages=', '.join(failed[:10]) + ('...' if len(failed) > 10 else '')
            )
        )
    message_box = MessageBox('\n'.join(lines), parent=window)
    try:
        message_box.exec()
    finally:
        message_box.deleteLater()


def clamp_range(
    page_range: Optional[Tuple[int, int]], page_count: int
) -> Tuple[int, int]:
    """Return a valid 1-based inclusive ``(first, last)`` pair.

    None means the whole project. A reversed or out-of-date pair is
    corrected rather than refused, so the export always has something
    sensible to do.

    >>> clamp_range(None, 12)
    (1, 12)
    >>> clamp_range((9, 3), 12)
    (3, 9)
    >>> clamp_range((0, 500), 12)
    (1, 12)
    """
    if page_count < 1:
        return (1, 0)
    if page_range is None:
        return (1, page_count)
    first, last = (int(page_range[0]), int(page_range[1]))
    if first > last:
        first, last = last, first
    first = max(1, min(first, page_count))
    last = max(first, min(last, page_count))
    return (first, last)


class RangeSpinBox(PageRangeSpinBox):
    """A page selector whose step chevrons respond to clicks.

    PageRangeSpinBox paints the chevrons itself and handles clicks in its
    own mousePressEvent, but a spin box with no native buttons lets its
    internal QLineEdit span the full width, so the editor receives those
    clicks first and the arrows look dead. The pipeline dialog avoids this
    through stylesheet padding tied to its object names; filtering the
    editor's own events works wherever this widget is used.

    >>> RangeSpinBox.__name__
    'RangeSpinBox'
    """

    #: Smallest page count the box is sized for, so a short project still
    #: leaves room to type a longer number.
    MIN_DIGITS = 3

    #: Width of the chevron area drawn by PageRangeSpinBox._button_rects:
    #: a 4px right margin, two 16px buttons and a 1px gap. Used before the
    #: box is wide enough for the real span to be measured.
    CHEVRON_SPAN = 37

    #: Breathing room between the last digit and the first chevron.
    TEXT_GAP = 3

    #: Frame, inner padding and caret the editor needs beyond the digits.
    #: A stylesheet can add padding the font metrics know nothing about,
    #: so this is deliberately generous: too wide only costs a few pixels,
    #: too narrow clips the number.
    EDITOR_PADDING = 20

    def __init__(self, parent: QWidget = None) -> None:
        super().__init__(parent)
        editor = self.lineEdit()
        editor.installEventFilter(self)
        editor.setMouseTracking(True)
        self._editor_cursor = editor.cursor().shape()
        self.refresh_width()

    # ---------------------------------------------------------- geometry

    def _chevron_span(self) -> int:
        """Width taken by the chevrons, measured from the right edge."""
        _up_rect, down_rect = self._button_rects()
        return max(0, self.width() - down_rect.left())

    def refresh_width(self) -> None:
        """Size the box to its largest value, never below MIN_DIGITS."""
        digits = max(self.MIN_DIGITS, len(str(max(1, self.maximum()))))
        # Measure the widest digit, not a nominal one: proportional fonts
        # give 1 a much narrower advance than 8.
        text_width = self.fontMetrics().horizontalAdvance('8') * digits
        # The chevron span is derived from the current width, so measure it
        # against a width wide enough for the buttons to be laid out.
        chevrons = self._chevron_span() or self.CHEVRON_SPAN
        self.setFixedWidth(
            chevrons + text_width + self.TEXT_GAP * 2 + self.EDITOR_PADDING
        )
        self._sync_text_margin()

    def _sync_text_margin(self) -> None:
        """Reserve exactly the chevrons' width, and no more.

        A fixed margin either overlaps the arrows or strands a gap in front
        of them, because the chevrons are positioned from the right edge.
        """
        editor = self.lineEdit()
        _up_rect, down_rect = self._button_rects()
        editor_right = editor.x() + editor.width()
        margin = editor_right - down_rect.left() + self.TEXT_GAP
        editor.setTextMargins(0, 0, max(0, margin), 0)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._sync_text_margin()

    def setRange(self, minimum: int, maximum: int) -> None:
        super().setRange(minimum, maximum)
        self.refresh_width()

    # ------------------------------------------------------------- input

    def stepBy(self, steps: int) -> None:
        """Change the value without selecting the text.

        QAbstractSpinBox selects the whole field after every step, which
        on a click reads as the caret jumping to the start and back before
        the number updates. Selecting stays the user's own gesture.
        """
        editor = self.lineEdit()
        position = editor.cursorPosition()
        super().stepBy(steps)
        editor.deselect()
        editor.setCursorPosition(min(position, len(editor.text())))

    def _button_at(self, event: QMouseEvent) -> str:
        """Return 'up', 'down' or '' for a position inside the editor."""
        position = self._event_pos(event)
        position = self.lineEdit().mapTo(self, position)
        up_rect, down_rect = self._button_rects()
        if up_rect.contains(position):
            return 'up'
        if down_rect.contains(position):
            return 'down'
        return ''

    def _set_editor_cursor(self, over_button: bool) -> None:
        # The editor owns an I-beam across its whole width, which misreads
        # the chevrons as text. Swap it while the pointer is over them.
        shape = (
            Qt.CursorShape.ArrowCursor if over_button else self._editor_cursor
        )
        editor = self.lineEdit()
        if editor.cursor().shape() != shape:
            editor.setCursor(shape)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if watched is self.lineEdit() and self.isEnabled():
            event_type = event.type()
            if event_type in (
                QEvent.Type.MouseButtonPress,
                # Clicking an arrow twice in quick succession arrives as a
                # double click, not a second press. Left to the editor it
                # selects a word instead of stepping, which is why a fast
                # second click appeared to do nothing.
                QEvent.Type.MouseButtonDblClick,
            ):
                button = self._button_at(event)
                if button == 'up':
                    self.stepUp()
                    return True
                if button == 'down':
                    self.stepDown()
                    return True
            elif event_type == QEvent.Type.MouseButtonRelease:
                # Swallow the matching release so the editor cannot place
                # its caret, or start a selection, under the arrows.
                if self._button_at(event):
                    return True
            elif event_type == QEvent.Type.MouseMove:
                # Keep the hover highlight and the cursor shape alive over
                # the editor, which would otherwise swallow both.
                button = self._button_at(event)
                self._set_editor_cursor(bool(button))
                if button != self._hover_button:
                    self._hover_button = button
                    self.update()
            elif event_type == QEvent.Type.Leave:
                self._set_editor_cursor(False)
                if self._hover_button:
                    self._hover_button = ''
                    self.update()
        return super().eventFilter(watched, event)


class ConfigRowLabel(QLabel):
    """Text that matches the settings panel's own labels.

    The panel builds its labels at CONFIG_FONTSIZE_CONTENT pixels with
    browser interaction, which is what makes them selectable and gives
    them a right-click menu. Reproduced here rather than imported, so this
    module stays independent of configpanel.

    >>> ConfigRowLabel.__name__
    'ConfigRowLabel'
    """

    def __init__(self, text: str, parent: QWidget = None) -> None:
        super().__init__(text, parent)
        font = self.font()
        font.setPixelSize(CONFIG_FONTSIZE_CONTENT)
        self.setFont(font)
        self.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextBrowserInteraction
        )


class ExportRangeSelector(QWidget):
    """Choose between every page and a page range.

    A divider separates the two choices, and the range selectors grey out
    while All pages is ticked, so the inactive side recedes.

    >>> ExportRangeSelector.__name__
    'ExportRangeSelector'
    """

    #: How far the range labels fade while All pages is ticked.
    INACTIVE_OPACITY = 0.45

    def __init__(self, parent: QWidget = None) -> None:
        super().__init__(parent)
        self.setObjectName('ExportRangeSelector')
        self.page_count = 0

        # The panel's own checkboxes carry no text: the caption is a
        # separate label, so only the box itself toggles the setting.
        self.all_checker = QCheckBox(self)
        self.all_checker.setObjectName('ConfigCheckBox')
        self.all_checker.setChecked(True)
        self.all_checker.setToolTip(
            self.tr('Export every page instead of a range.')
        )
        self.all_checker.toggled.connect(self._sync_enabled)
        self.all_label = ConfigRowLabel(self.tr('All pages'), self)
        self.all_label.setToolTip(self.all_checker.toolTip())

        self.divider = QFrame(self)
        self.divider.setObjectName('ExportRangeDivider')
        self.divider.setFrameShape(QFrame.Shape.VLine)
        self.divider.setFrameShadow(QFrame.Shadow.Sunken)

        self.from_label = ConfigRowLabel(self.tr('From'), self)
        self.to_label = ConfigRowLabel(self.tr('to'), self)
        self._fade_effects = []
        for label in (self.from_label, self.to_label):
            effect = QGraphicsOpacityEffect(label)
            label.setGraphicsEffect(effect)
            self._fade_effects.append(effect)

        self.start_box = RangeSpinBox(self)
        self.end_box = RangeSpinBox(self)
        for box in (self.start_box, self.end_box):
            # Reconcile endpoints only once a whole number is committed, so
            # the first digit of 25 does not drag the other end to 2.
            box.setKeyboardTracking(False)
            font = box.font()
            font.setPixelSize(CONFIG_FONTSIZE_CONTENT)
            box.setFont(font)
            # Width follows the page count, so the digits always fit.
            box.setRange(1, 1)
        self.start_box.valueChanged.connect(self._on_start_changed)
        self.end_box.valueChanged.connect(self._on_end_changed)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self.all_checker)
        layout.addWidget(self.all_label)
        layout.addSpacing(4)
        layout.addWidget(self.divider)
        layout.addSpacing(4)
        layout.addWidget(self.from_label)
        layout.addWidget(self.start_box)
        layout.addWidget(self.to_label)
        layout.addWidget(self.end_box)
        self._sync_enabled(True)

    def set_page_count(self, page_count: int) -> None:
        """Re-scale the selectors when a project is opened or changed."""
        page_count = max(0, int(page_count))
        self.page_count = page_count
        maximum = max(1, page_count)
        # Opening a project resets both ends to cover it. Keeping the old
        # start would silently carry one project's range into another.
        for box, value in (
            (self.start_box, 1),
            (self.end_box, maximum),
        ):
            with QSignalBlocker(box):
                box.setRange(1, maximum)
                box.setValue(value)
        self._sync_enabled(self.all_checker.isChecked())

    def page_range(self) -> Optional[Tuple[int, int]]:
        """Return the chosen 1-based range, or None for every page."""
        if self.all_checker.isChecked():
            return None
        return (self.start_box.value(), self.end_box.value())

    def _sync_enabled(self, export_all: bool) -> None:
        usable = self.page_count > 0 and not export_all
        self.start_box.setEnabled(usable)
        self.end_box.setEnabled(usable)
        # A disabled QLabel ignores mouse input, which would cost the text
        # its selection and context menu, so the labels stay enabled and
        # are faded instead. Opacity leaves the stylesheet's own colour in
        # place, so a light/dark switch is picked up with nothing to
        # recompute; hard-coding a colour here would outrank the reloaded
        # stylesheet and strand the old theme's value.
        for effect in self._fade_effects:
            effect.setOpacity(1.0 if usable else self.INACTIVE_OPACITY)

    def _on_start_changed(self, value: int) -> None:
        if value > self.end_box.value():
            self.end_box.setValue(value)

    def _on_end_changed(self, value: int) -> None:
        if value < self.start_box.value():
            self.start_box.setValue(value)
