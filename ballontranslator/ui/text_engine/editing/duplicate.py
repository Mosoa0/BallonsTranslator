"""Duplicate the selected text blocks.

A duplicate is a deep copy of the block's data, offset slightly so it does not
hide under the original. Copying the block rather than the item carries the
translation, rich text, font format, effects and angle across untouched, and
reuses the paste command so one undo removes the copies.
"""

import copy
from typing import List

#: Image-space offset of a duplicate from its original, in pixels.
DUPLICATE_OFFSET = 20

#: Unused elsewhere in the application; Ctrl+D is already Delete here.
DUPLICATE_SHORTCUT = 'Ctrl+J'


def duplicate_selected_blocks() -> None:
    """Copy every selected block in place, selecting the new items."""
    # Imported late: canvas imports this module, and both the manager and the
    # shared widgets reach back to the canvas.
    from ... import shared_widget as SW
    from .manager import PasteBlkItemsCommand

    manager = SW.st_manager
    canvas = SW.canvas
    if manager is None or canvas is None or not canvas.textEditMode():
        return

    items = canvas.selected_text_items()
    if not items and manager.txtblkShapeControl.blk_item is not None:
        items = [manager.txtblkShapeControl.blk_item]
    if not items:
        return

    # Edits live in the items until they are written back to the blocks.
    if canvas.text_change_unsaved():
        manager.updateTextBlkList()

    blkitem_list, pair_widget_list = [], []
    # A duplicate reproduces its original exactly; re-running auto layout
    # would reflow it instead.
    auto_textlayout = manager.auto_textlayout_flag
    manager.auto_textlayout_flag = False
    try:
        for item in items:
            blk = copy.deepcopy(item.blk)
            blk.adjust_pos(DUPLICATE_OFFSET, DUPLICATE_OFFSET)
            blkitem_list.append(manager.addTextBlock(blk))
            pair_widget_list.append(manager.pairwidget_list[-1])
    finally:
        manager.auto_textlayout_flag = auto_textlayout

    canvas.clearSelection()
    canvas.push_undo_command(
        PasteBlkItemsCommand(blkitem_list, pair_widget_list, manager)
    )
    if len(blkitem_list) == 1:
        manager.formatpanel.set_textblk_item(blkitem_list[0])
    else:
        manager.formatpanel.set_textblk_item(multi_select=True)
