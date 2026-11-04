"""Per-block word-wrap toggle for horizontal text layout.

Horizontal layout may break a word at any character when it does not fit the
text box. Checking the toggle restricts a block's visual wrapping to word
boundaries, letting an over-wide word overflow instead of splitting. Only the
visual line breaks change; the document text is never touched.

The state lives on the block's own ``FontFormat``, so it saves with the
project, travels with a duplicated block, and is stored and applied along with
a global font format.
"""

from qtpy.QtCore import QCoreApplication, Qt
from qtpy.QtGui import QTextOption
from qtpy.QtWidgets import QToolButton


#: Name of the ``FontFormat`` field holding the per-block state.
PARAM_NAME = 'wrap_at_word_boundary'

#: Room for the button frame around the label.
LABEL_PADDING = 10

#: Geometry copied from the neighbouring toggles: square corners, a 2px
#: outline, and a 26px box.
ACCENT_COLOR = '#1e93e5'
CORNER_RADIUS = 0
BORDER_WIDTH = 2
BUTTON_HEIGHT = 26

#: The panel stylesheet gives tool buttons no hover or checked state, so the
#: button carries its own rules. A widget stylesheet outranks the application
#: one. The transparent border in the normal state reserves the hover
#: outline's space, so the label never shifts.
BUTTON_STYLE = (
    'QToolButton#WordWrapChecker {{'
    ' background-color: transparent;'
    ' border: {width}px solid transparent;'
    ' border-radius: {radius}px;'
    '}}'
    'QToolButton#WordWrapChecker:hover {{'
    ' background-color: transparent;'
    ' border: {width}px solid {color};'
    '}}'
    'QToolButton#WordWrapChecker:checked,'
    'QToolButton#WordWrapChecker:checked:hover {{'
    ' background-color: {color};'
    ' border: {width}px solid {color};'
    ' color: white;'
    '}}'
)


def wrap_mode(fontformat=None) -> QTextOption.WrapMode:
    """Return the wrap mode for one block's format.

    Qt spells word-boundary-only wrapping ``WordWrap``; there is no
    ``WrapAtWordBoundary`` member.

    >>> wrap_mode() == QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere
    True
    """
    if fontformat is not None and getattr(fontformat, PARAM_NAME, False):
        return QTextOption.WrapMode.WordWrap
    return QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere


def set_word_wrap(blkitem, value: bool) -> None:
    """Store the state on one block and re-wrap it."""
    if blkitem.fontformat is not None:
        setattr(blkitem.fontformat, PARAM_NAME, value)
    layout = blkitem.layout
    if layout is None or not hasattr(layout, 'reLayout'):
        return
    # Imported late: this module is imported by the layout it inspects.
    from ..horizontal_layout import HorizontalTextDocumentLayout

    if not isinstance(layout, HorizontalTextDocumentLayout):
        return
    # Re-wrapping moves ink, so the scene needs the geometry warning.
    blkitem.prepareGeometryChange()
    layout.reLayout()
    blkitem.geometry_controller.flush_deferred_compilation()
    blkitem.repaint_background()
    blkitem.update()
    blkitem.visual_geometry_changed.emit()


def create_word_wrap_checker(panel) -> QToolButton:
    """Build the toggle driving the wrap state of the selected blocks.

    A tool button is used rather than a checkbox because the panel
    stylesheet renders checkboxes as icon-only indicators, which drops the
    label. Unchecked keeps the long-standing behaviour, so existing blocks
    are unaffected until the user opts one in.
    """
    button = QToolButton(panel)
    button.setObjectName('WordWrapChecker')
    # A single letter keeps the button close to the square shape of the
    # neighbouring toggles.
    button.setText(QCoreApplication.translate('FontFormatPanel', 'W'))
    button.setToolTip(
        QCoreApplication.translate(
            'FontFormatPanel',
            'Wrap at word boundaries\n'
            'Check to keep words whole in this text block: lines break only '
            'between words, and a word wider than the box overflows instead '
            'of splitting. The text itself is never modified.'
        )
    )
    button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
    button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    button.setCheckable(True)
    button.setStyleSheet(
        BUTTON_STYLE.format(
            color=ACCENT_COLOR,
            radius=CORNER_RADIUS,
            width=BORDER_WIDTH,
        )
    )
    width = button.fontMetrics().horizontalAdvance(button.text())
    width += LABEL_PADDING + 2 * BORDER_WIDTH
    button.setFixedSize(max(width, BUTTON_HEIGHT), BUTTON_HEIGHT)
    button.clicked.connect(
        lambda checked: panel.on_param_changed(PARAM_NAME, checked)
    )
    return button
