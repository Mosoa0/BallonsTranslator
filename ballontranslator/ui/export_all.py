"""Export result images for every page, or for a chosen page range.

The project saves a result image only for the page on screen, so exporting a
chapter means visiting each page by hand. This walks the page list, renders
each selected page and writes it with the configured format and quality,
then returns to the page that was open.
"""

import os.path as osp
from typing import Optional, Tuple

from qtpy.QtCore import QCoreApplication, QSignalBlocker, Qt
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

        # Same selector as the pipeline dialog's page range. Its stylesheet
        # rule pads the editor clear of the painted chevrons, which is what
        # lets clicks reach them.
        self.start_box = PageRangeSpinBox(self)
        self.start_box.setObjectName('ExportRangeStart')
        self.end_box = PageRangeSpinBox(self)
        self.end_box.setObjectName('ExportRangeEnd')
        for box in (self.start_box, self.end_box):
            # Reconcile endpoints only once a whole number is committed, so
            # the first digit of 25 does not drag the other end to 2.
            box.setKeyboardTracking(False)
            box.setFixedWidth(82)
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
