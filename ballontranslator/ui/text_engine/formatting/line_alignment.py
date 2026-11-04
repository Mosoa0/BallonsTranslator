"""Per-paragraph text alignment.

Alignment is a block-level property in Qt, so a paragraph can carry its own
value that overrides the item's. While a block is being edited the alignment
buttons act on the paragraphs the caret or selection touches; everywhere else
they keep acting on the whole item, as before.
"""

from typing import Optional

from qtpy.QtCore import Qt
from qtpy.QtGui import (
    QTextBlock,
    QTextBlockFormat,
    QTextCursor,
    QTextFormat,
)


#: Panel values index this tuple, matching ``TextBlkItem.setAlignment``.
ALIGNMENT_FLAGS = (
    Qt.AlignmentFlag.AlignLeft,
    Qt.AlignmentFlag.AlignCenter,
    Qt.AlignmentFlag.AlignRight,
)


def block_alignment_flag(block: QTextBlock) -> Optional[Qt.AlignmentFlag]:
    """Return a paragraph's own alignment, or ``None`` when it has none.

    Only an explicitly set property counts. Without a property the item's
    document-wide alignment still applies.
    """
    block_format = block.blockFormat()
    if not block_format.hasProperty(QTextFormat.Property.BlockAlignment):
        return None
    return block_format.alignment()


def clear_block_alignments(document) -> bool:
    """Drop every paragraph override so the item's alignment applies again.

    A paragraph's own alignment outranks the document default, so an item
    wide change has no visible effect until the overrides are removed.
    """
    cleared = False
    block = document.firstBlock()
    while block.isValid():
        block_format = block.blockFormat()
        if block_format.hasProperty(QTextFormat.Property.BlockAlignment):
            block_format.clearProperty(QTextFormat.Property.BlockAlignment)
            QTextCursor(block).setBlockFormat(block_format)
            cleared = True
        block = block.next()
    return cleared


def apply_block_alignment(cursor: QTextCursor, value: int) -> None:
    """Align the paragraphs the cursor touches.

    ``mergeBlockFormat`` covers every block in a selection, or just the
    caret's block when nothing is selected, which is the behaviour wanted
    here.
    """
    block_format = QTextBlockFormat()
    block_format.setAlignment(ALIGNMENT_FLAGS[value])
    cursor.mergeBlockFormat(block_format)


def _whole_document_selected(item) -> bool:
    """Report whether the selection covers the entire item."""
    cursor = item.textCursor()
    if cursor is None or not cursor.hasSelection():
        return False
    end = item.document().characterCount() - 1
    return cursor.selectionStart() <= 0 and cursor.selectionEnd() >= end


def _paragraph_target(panel):
    """Return the item taking per-paragraph alignment, else ``None``."""
    item = getattr(panel, 'textblk_item', None)
    if item is None or not item.isEditing():
        return None
    # Vertical layout positions columns itself and ignores block alignment.
    if item.fontformat.vertical:
        return None
    if _whole_document_selected(item):
        # Selecting everything means the whole item, keeping the item's
        # stored alignment and the panel's buttons in agreement.
        return None
    return item


def _whole_item_targets(panel):
    """Return the items an item wide alignment change applies to."""
    # Imported late: shared_widget reaches the canvas, which imports the
    # text item and its layouts, so a module-level import would be circular.
    from ... import shared_widget as SW

    item = getattr(panel, 'textblk_item', None)
    if item is not None:
        return [item]
    if SW.canvas is None:
        return []
    return SW.canvas.selected_text_items()


def apply_alignment(panel, param_name: str, value: int) -> None:
    """Route an alignment click to a paragraph or to the whole item."""
    item = _paragraph_target(panel)
    if item is None:
        for target in _whole_item_targets(panel):
            target._apply_text_format(
                lambda _cursor, target=target: clear_block_alignments(
                    target.document()
                ),
                select_document=True,
            )
        panel.on_param_changed(param_name, value)
        return

    # Alignment moves ink, so warn the scene before the layout changes.
    item.prepareGeometryChange()
    item._apply_text_format(
        lambda cursor: apply_block_alignment(cursor, value)
    )
    item.geometry_controller.invalidate_surface_cache()
    item.repaint_background()
    item.update()
