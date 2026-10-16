"""Keeps the section view button in FreeCAD's View toolbar."""

from __future__ import annotations

import FreeCAD as App
import FreeCADGui as Gui

from .. import resources
from ..core.qt import QtCore, QtGui, QtWidgets

TOOLBAR = "View"
COMMAND = "Nxt_SectionView"
ICON = str(resources.ICONS / "nxt_section.svg")

_button: list[QtGui.QAction] = []


def _action(parent: QtWidgets.QWidget) -> QtGui.QAction:
    # FreeCAD makes a command's own action only when a workbench lists it.
    if not _button:
        action = QtGui.QAction(QtGui.QIcon(ICON), "Section view", parent)
        action.setObjectName(COMMAND)
        action.setToolTip(
            QtWidgets.QApplication.translate(COMMAND, "Section view"))
        action.triggered.connect(lambda: Gui.runCommand(COMMAND))
        _button.append(action)
    return _button[0]


def add_button() -> None:
    """Append the button unless the toolbar already has it."""
    window = Gui.getMainWindow()
    toolbar = window.findChild(QtWidgets.QToolBar, TOOLBAR)
    if toolbar is None:
        App.Console.PrintLog("Nxt: no View toolbar to add to\n")
        return
    action = _action(window)
    if action not in toolbar.actions():
        toolbar.addAction(action)


def _later(*_args: object) -> None:
    # FreeCAD rebuilds the toolbars after the signal fires.
    QtCore.QTimer.singleShot(0, add_button)


def install() -> None:
    Gui.getMainWindow().workbenchActivated.connect(_later)
    _later()
