"""A section's task panel: the inspector's section cards.

Shown in FreeCAD's task view while a section is edited; Close finishes
editing, as the section command does. Dragging, tilting and the offset
stay on the frame in the 3D view.
"""

from __future__ import annotations

from typing import Any

import FreeCADGui as Gui

from ..core.qt import QtCore, QtWidgets
from ..inspector import bridge as inspector_bridge
from . import task_layout


class SectionTask:
    """The task dialog FreeCAD shows while `section` is edited."""

    def __init__(self, section: Any) -> None:
        self.section = section
        self.bridge = inspector_bridge.InspectorBridge(
            task=True, target=lambda: section.obj)
        self.form = task_layout.make_cards(None, self.bridge)
        self.form.setWindowTitle("Section")
        self.bridge.start()

    def getStandardButtons(self) -> int:  # noqa: N802 - FreeCAD API
        return int(QtWidgets.QDialogButtonBox.StandardButton.Close.value)

    def accept(self) -> bool:
        return self.reject()

    def reject(self) -> bool:
        self.bridge.stop()
        section = self.section
        if section.task is self:
            section.task = None
            # Not while FreeCAD is still closing this dialog.
            QtCore.QTimer.singleShot(0, lambda: section.set_editing(False))
        return True

    def close(self) -> None:
        """The section stopped editing: take the dialog away."""
        self.bridge.stop()
        try:
            if Gui.Control.activeDialog():
                Gui.Control.closeDialog()
        except Exception:  # noqa: BLE001 - FreeCAD closed it already
            pass


def open_for(section: Any) -> None:
    """Show the section's task, unless another dialog is open."""
    try:
        if section.task is not None or Gui.Control.activeDialog():
            return
    except Exception:  # noqa: BLE001
        return
    if section.obj is None:
        return
    task = SectionTask(section)
    section.task = task
    Gui.Control.showDialog(task)


def close_for(section: Any) -> None:
    task, section.task = section.task, None
    if task is not None:
        task.close()
