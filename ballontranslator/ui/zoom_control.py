"""Mouse-driven canvas zoom control for the bottom bar.

Zoom otherwise needs Ctrl+wheel or a keyboard shortcut. This adds a percent
field next to the opacity sliders that can be scrolled over, dragged, or
typed into.

The canvas range is 1% to 1000%, so steps are proportional rather than
linear: the same pointer distance changes the zoom by the same ratio at any
level, which keeps 40% to 50% feeling like 400% to 500%.
"""

from qtpy.QtCore import QSignalBlocker, Qt, Signal
from qtpy.QtGui import QDoubleValidator, QMouseEvent, QWheelEvent
from qtpy.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QWidget,
)

#: Percent bounds, matching CANVAS_SCALE_MIN/MAX on the canvas.
ZOOM_MIN_PERCENT = 1.0
ZOOM_MAX_PERCENT = 1000.0

#: Zoom levels offered in the dropdown.
ZOOM_PRESETS = (25, 50, 75, 100, 150, 200, 400)

#: One wheel notch multiplies the zoom by this, matching Ctrl+wheel.
WHEEL_STEP = 1.1

#: Pointer travel, in pixels, that doubles or halves the zoom.
DRAG_DOUBLING_DISTANCE = 180.0

#: The bottom bar is 32px; leave the field short of filling it.
BOX_HEIGHT = 22


def clamp_percent(value: float) -> float:
    """Clamp a percent value to the canvas range.

    >>> clamp_percent(5000.0)
    1000.0
    >>> clamp_percent(100.0)
    100.0
    """
    return max(ZOOM_MIN_PERCENT, min(ZOOM_MAX_PERCENT, float(value)))


def scaled_percent(percent: float, pixels: float) -> float:
    """Return the percent reached by dragging ``pixels`` from ``percent``.

    >>> round(scaled_percent(100.0, 180.0))
    200
    >>> round(scaled_percent(100.0, -180.0))
    50
    """
    return clamp_percent(percent * 2.0 ** (pixels / DRAG_DOUBLING_DISTANCE))


class ZoomDragLabel(QLabel):
    """Click-drag handle. Right zooms in, left zooms out."""

    drag_delta = Signal(float)
    drag_finished = Signal()

    def __init__(self, text: str, parent: QWidget = None) -> None:
        super().__init__(text, parent)
        self.setObjectName('ZoomDragLabel')
        self.setCursor(Qt.CursorShape.SizeHorCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._pressed = False
        self._origin = None

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._pressed = True
            self._origin = event.globalPosition().toPoint()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if not self._pressed:
            return super().mouseMoveEvent(event)
        position = event.globalPosition().toPoint()
        delta = position.x() - self._origin.x()
        if delta:
            self._origin = position
            self.drag_delta.emit(float(delta))
        event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._pressed:
            self._pressed = False
            self._origin = None
            self.drag_finished.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)


class ZoomBox(QComboBox):
    """Editable percent field that commits once, not per keystroke."""

    zoom_requested = Signal(float)

    def __init__(self, parent: QWidget = None) -> None:
        super().__init__(parent)
        self.setObjectName('ZoomBox')
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.addItems([str(preset) for preset in ZOOM_PRESETS])
        validator = QDoubleValidator(ZOOM_MIN_PERCENT, ZOOM_MAX_PERCENT, 0)
        validator.setNotation(QDoubleValidator.Notation.StandardNotation)
        self.setValidator(validator)
        # Committing per keystroke would apply 5% on the way to typing 50.
        self.lineEdit().editingFinished.connect(self._commit_text)
        self.activated.connect(self._commit_text)

    def percent(self) -> float:
        try:
            return clamp_percent(float(self.currentText()))
        except ValueError:
            return ZOOM_MIN_PERCENT

    def show_percent(self, percent: float) -> None:
        with QSignalBlocker(self):
            self.setCurrentText(f'{round(percent):d}')

    def _commit_text(self, *_args: object) -> None:
        self.zoom_requested.emit(self.percent())

    def wheelEvent(self, event: QWheelEvent) -> None:
        # QComboBox would otherwise walk the preset list.
        notches = event.angleDelta().y()
        if not notches:
            return event.ignore()
        factor = WHEEL_STEP if notches > 0 else 1.0 / WHEEL_STEP
        self.zoom_requested.emit(clamp_percent(self.percent() * factor))
        event.accept()


class ZoomControl(QWidget):
    """Percent field plus drag handle, bound to one canvas.

    >>> ZoomControl.__name__
    'ZoomControl'
    """

    def __init__(self, parent: QWidget = None) -> None:
        super().__init__(parent)
        self.setObjectName('ZoomControl')
        self.canvas = None
        self._drag_percent = None

        self.label = ZoomDragLabel(self.tr('Zoom'), self)
        self.label.setToolTip(
            self.tr(
                'Canvas zoom\n'
                'Drag, scroll over the value, or type a percentage.'
            )
        )
        self.box = ZoomBox(self)
        self.box.setFixedSize(68, BOX_HEIGHT)
        self.box.setToolTip(self.label.toolTip())
        self.suffix = QLabel('%', self)
        self.suffix.setObjectName('ZoomSuffix')

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        # Centred, so the short field sits in the middle of the bar rather
        # than being stretched to its full height.
        layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self.label, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self.box, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self.suffix, 0, Qt.AlignmentFlag.AlignVCenter)

        self.box.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed
        )
        self.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred
        )

        self.box.zoom_requested.connect(self.apply_percent)
        self.label.drag_delta.connect(self._on_drag_delta)
        self.label.drag_finished.connect(self._on_drag_finished)

    def bind_canvas(self, canvas) -> None:
        """Attach the canvas whose zoom this control drives."""
        self.canvas = canvas
        canvas.scalefactor_changed.connect(self.sync)
        self.sync()

    def current_percent(self) -> float:
        if self.canvas is None:
            return 100.0
        return clamp_percent(self.canvas.scale_factor * 100.0)

    def sync(self) -> None:
        """Show the canvas's own zoom, whatever changed it."""
        self.box.show_percent(self.current_percent())

    def apply_percent(self, percent: float) -> None:
        """Zoom the canvas to ``percent``, then show what it settled on."""
        if self.canvas is None:
            return
        target = clamp_percent(percent) / 100.0
        current = self.canvas.scale_factor
        if current > 0 and abs(target - current) > 1e-9:
            # The canvas scales by a factor and clamps the result itself.
            self.canvas.scaleImage(target / current)
        self.sync()

    def _on_drag_delta(self, pixels: float) -> None:
        # Accumulate against the drag's own running value so rounding in
        # the display cannot make the gesture drift.
        if self._drag_percent is None:
            self._drag_percent = self.current_percent()
        self._drag_percent = scaled_percent(self._drag_percent, pixels)
        self.apply_percent(self._drag_percent)

    def _on_drag_finished(self) -> None:
        self._drag_percent = None
