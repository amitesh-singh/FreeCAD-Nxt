"""The isolate mode's notice at the top centre of the 3D view."""

from __future__ import annotations

import contextlib
from typing import Any

import FreeCAD as App
import FreeCADGui as Gui

from ..core.events import ApplicationEventFilter
from ..core.qt import QtCore, QtWidgets
from ..core.view3d import active_viewport
from .view_notice import TopNotice


class ViewNotice(TopNotice):
    """Keeps the notice over the active 3D view while isolating."""

    SOURCE = "IsolationBanner.qml"

    def __init__(self, isolation: Any, theme: Any,
                 parent: QtCore.QObject | None = None) -> None:
        super().__init__(theme, parent)
        self._isolation = isolation
        isolation.changed.connect(self._sync)

    def remove(self) -> None:
        with contextlib.suppress(RuntimeError, TypeError):
            self._isolation.changed.disconnect(self._sync)
        super().remove()

    def _context(self) -> dict[str, Any]:
        return {"isolation": self._isolation}

    def _wanted_host(self) -> Any:
        if not self._isolation.active():
            return None
        gui_doc = Gui.ActiveDocument
        if gui_doc is None \
                or gui_doc.Document.Name != self._isolation.document():
            return None
        return active_viewport()


class EscapeToExit(ApplicationEventFilter):
    """Escape leaves the isolate mode from anywhere it means nothing else.

    Stands aside for task panels, edits, dialogs/popups, text fields and
    the model panel, which handle Escape themselves.
    """

    def __init__(self, isolation: Any,
                 parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        self._isolation = isolation

    def eventFilter(self, watched: Any, event: Any) -> bool:  # noqa: N802
        # Every application event passes here: cheap tests first.
        if event.type() != QtCore.QEvent.Type.KeyPress \
                or event.key() != QtCore.Qt.Key.Key_Escape:
            return False
        try:
            if not self._isolation.active() or not self._free():
                return False
            return bool(self._isolation.exit())
        except Exception as exc:
            App.Console.PrintLog("Nxt isolate Escape: %s\n" % exc)
            return False

    @staticmethod
    def _free() -> bool:
        """Whether Escape means nothing else right now."""
        app = QtWidgets.QApplication
        if app.instance() is None:
            return False
        if app.activeModalWidget() is not None \
                or app.activePopupWidget() is not None:
            return False
        with contextlib.suppress(Exception):
            if Gui.Control.activeDialog():
                return False
        gui_doc = Gui.ActiveDocument
        if gui_doc is not None and gui_doc.getInEdit() is not None:
            return False
        focus = app.focusWidget()
        if isinstance(focus, (QtWidgets.QLineEdit, QtWidgets.QTextEdit,
                              QtWidgets.QPlainTextEdit,
                              QtWidgets.QAbstractSpinBox)):
            return False
        widget = focus
        while widget is not None:
            if widget.objectName() == "NxtModelPanel":
                return False
            widget = widget.parentWidget()
        return True
