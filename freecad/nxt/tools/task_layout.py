"""Pad and Pocket's task dialogs, laid out by the inspector's template.

FreeCAD opens its own dialog whenever a feature is edited. The dialog
stays, for its preview and its OK and Cancel; its parameters box is
swapped, as it is filled, for the template's cards (TaskLayout.qml): the
Data tab only, with no "Everything else". Edits reach the dialog's fields
(task_sync.py), which OK writes back as usual.
"""

from __future__ import annotations

import traceback
from typing import Any

import FreeCAD as App
import FreeCADGui as Gui

from ..core import widgets
from ..core.qt import QtCore, QtGui, QtWidgets
from ..inspector import bridge as inspector_bridge
from ..ui import quick_host
from ..ui import theme as theme_mod
from . import expressions
from .task_sync import SWAPPED

#: The dialog boxes replaced: FreeCAD's class for each feature's box.
REPLACED = frozenset({"TaskPadParameters", "TaskPocketParameters"})
#: FreeCAD's task panel exists from startup, but is looked for until found.
FIND_MS = 500
#: After the swap: the dialog settles, then the view is drawn afresh.
RENEW_MS = (0, 120, 400)
#: What a dialog does on its way to being shown.
_FILLING = (QtCore.QEvent.Type.ChildAdded, QtCore.QEvent.Type.LayoutRequest,
            QtCore.QEvent.Type.Show, QtCore.QEvent.Type.Polish)


def _short(widget: Any) -> str:
    return widget.metaObject().className().split("::")[-1]


def _task_view() -> Any:
    main = Gui.getMainWindow()
    if main is None:
        return None
    for widget in main.findChildren(QtWidgets.QWidget):
        if widget.metaObject().className() == "Gui::TaskView::TaskView":
            return widget
    return None


class _OnShow(QtCore.QObject):
    """Calls `shown` after the watched widget is shown or reparented."""

    def __init__(self, widget: Any, shown: Any) -> None:
        super().__init__(widget)
        self._shown = shown
        widget.installEventFilter(self)

    def eventFilter(self, _obj: Any, event: Any) -> bool:  # noqa: N802
        if event.type() in (QtCore.QEvent.Type.Show,
                            QtCore.QEvent.Type.ParentChange):
            QtCore.QTimer.singleShot(0, self._shown)
        return False


def _discard(cards: Any, bridge: Any) -> None:
    try:
        bridge.stop()
    except RuntimeError:
        pass
    if widgets.alive(cards):
        cards.hide()
        cards.setParent(None)
        cards.deleteLater()


class TaskLayout(QtCore.QObject):
    """Watches FreeCAD's task panel and swaps the boxes it can lay out."""

    def __init__(self, parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        self._view: Any = None
        self._busy = False
        self._find = QtCore.QTimer(self)
        self._find.setInterval(FIND_MS)
        self._find.timeout.connect(self._watch)

    def install(self) -> None:
        self._find.start()
        self._watch()

    def remove(self) -> None:
        self._find.stop()
        if widgets.alive(self._view):
            self._view.removeEventFilter(self)
        self._view = None

    def _watch(self) -> None:
        if widgets.alive(self._view):
            return
        view = _task_view()
        if view is self._view:
            return
        if widgets.alive(self._view):
            self._view.removeEventFilter(self)
        self._view = view
        if view is not None:
            view.installEventFilter(self)
            self._swap()

    def eventFilter(self, watched: Any, event: Any) -> bool:  # noqa: N802
        if watched is self._view and event.type() in _FILLING \
                and not self._busy:
            self._swap()
        return False

    def _swap(self) -> None:
        """Each replaceable box, hidden, with the cards in its place."""
        view = self._view
        if not widgets.alive(view):
            return
        self._busy = True
        try:
            for widget in view.findChildren(QtWidgets.QWidget):
                if _short(widget) not in REPLACED:
                    continue
                # The parameters class is the dialog's box itself (a
                # TaskBox): only it is hidden, never what holds it.
                box = widget
                if box.property(SWAPPED):
                    if box.isVisible():
                        box.hide()      # the dialog may show it again
                    continue
                box.setProperty(SWAPPED, True)
                self._replace(box)
        except Exception:
            App.Console.PrintError("Nxt: could not lay out the task\n")
            App.Console.PrintError(traceback.format_exc())
        finally:
            self._busy = False

    def _replace(self, box: Any) -> None:
        holder = box.parentWidget()
        layout = holder.layout() if holder is not None else None
        if layout is None:
            return
        from ..app import services
        theme = services.theme() or theme_mod.Theme(
            holder, theme_mod.find_reference_widget(holder))
        bridge = inspector_bridge.InspectorBridge(task=True)
        cards = quick_host.make_view(
            holder, "TaskLayout.qml",
            {"expressions": expressions.helper(), "inspector": bridge,
             "theme": theme})
        bridge.setParent(cards)
        cards.setClearColor(QtGui.QColor(theme.background))
        root = cards.rootObject()

        def fit() -> None:
            if widgets.alive(cards) and root is not None:
                cards.setFixedHeight(
                    max(1, int(root.property("implicitHeight"))))

        def renew() -> None:
            """Resize the view once on screen, so it draws at its size.

            Made while the dialog is still being filled, the view keeps
            showing its first, half-sized frame (though it takes clicks)
            until it is resized, as a change of Sides does.
            """
            if not widgets.alive(cards) or root is None:
                return
            height = max(1, int(root.property("implicitHeight")))
            cards.setFixedHeight(height + 1)
            QtCore.QTimer.singleShot(0, cards, fit)

        root.implicitHeightChanged.connect(fit)
        fit()
        cards.nxt_shown = _OnShow(cards, renew)  # type: ignore[attr-defined]
        for delay in RENEW_MS:
            QtCore.QTimer.singleShot(delay, cards, renew)
        cards.setSizePolicy(QtWidgets.QSizePolicy.Policy.Preferred,
                            QtWidgets.QSizePolicy.Policy.Fixed)
        if isinstance(layout, QtWidgets.QBoxLayout):
            layout.insertWidget(layout.indexOf(box), cards)
        else:
            layout.addWidget(cards)
        box.hide()
        bridge.start()
        # The box goes with its dialog; what holds it stays for the next.
        box.destroyed.connect(lambda *_: _discard(cards, bridge))
