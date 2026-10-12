"""The QObject the Property Inspector's QML talks to."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import FreeCAD as App
import FreeCADGui as Gui

from ..core.qt import QtCore, QtWidgets
from ..tools import task_sync
from . import layout as inspector
from . import templates as inspector_templates

#: Selection and undo counts are polled; both are cheap to read.
POLL_MS = 250


class InspectorBridge(QtCore.QObject):
    """Serves `inspector.describe` for the selection, and applies edits."""

    changed = QtCore.Signal()
    nativeRequested = QtCore.Signal(str)

    def __init__(self, parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        self._groups: list[dict[str, Any]] = []
        self._title = ""
        self._tab = inspector.DATA
        self._filter = ""
        self._opened: dict[str, bool] = {}
        self._signature: tuple[Any, ...] = ()
        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(POLL_MS)
        self._timer.timeout.connect(self._poll)
        self._edits: list[Callable[[], None]] = []
        # Edits run on the next event-loop turn: applying one recomputes
        # and rebuilds the cards, which must not destroy the field whose
        # QML handler is still running (QML aborts).
        self._edit_timer = QtCore.QTimer(self)
        self._edit_timer.setSingleShot(True)
        self._edit_timer.setInterval(0)
        self._edit_timer.timeout.connect(self._apply_edits)

    # -- lifetime --

    def start(self) -> None:
        self._signature = ()
        self._poll()
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()

    def _objects(self) -> list[Any]:
        try:
            return list(Gui.Selection.getSelection())
        except Exception:
            return []

    def _poll(self) -> None:
        objects = self._objects()
        doc = App.ActiveDocument
        signature = (tuple(o.Name for o in objects),
                     getattr(doc, "UndoCount", 0),
                     getattr(doc, "RedoCount", 0))
        if signature != self._signature:
            self._signature = signature
            self.refresh(objects)

    def refresh(self, objects: list[Any] | None = None) -> None:
        objects = self._objects() if objects is None else objects
        self._groups = inspector.describe(objects, self._tab, self._filter)
        for group in self._groups:
            if group["name"] in self._opened and not self._filter:
                group["open"] = self._opened[group["name"]]
        names = [o.Label for o in objects]
        if not names:
            self._title = ""
        elif len(names) == 1:
            self._title = names[0]
        else:
            shown = ", ".join(names[:2])
            self._title = "%s · %d selected" % (shown, len(names))
        self.changed.emit()

    # -- what QML reads --

    @QtCore.Property(list, notify=changed)
    def groups(self) -> list[dict[str, Any]]:
        return self._groups

    @QtCore.Property(str, notify=changed)
    def title(self) -> str:
        return self._title

    @QtCore.Property(str, notify=changed)
    def tab(self) -> str:
        return self._tab

    @QtCore.Property(str, notify=changed)
    def owner(self) -> str:
        """Expression owner "Document#Name"; empty on the View tab."""
        objects = self._objects()
        if not objects or self._tab != inspector.DATA:
            return ""
        obj = objects[0]
        return "%s#%s" % (obj.Document.Name, obj.Name)

    @QtCore.Property(bool, notify=changed)
    def several(self) -> bool:
        return len(self._objects()) > 1

    # -- what QML does --

    @QtCore.Slot(str)
    def setTab(self, tab: str) -> None:
        self._tab = tab
        self.refresh()

    @QtCore.Slot(str)
    def setFilter(self, text: str) -> None:
        self._filter = text
        self.refresh()

    @QtCore.Slot(str, bool)
    def setGroupOpen(self, name: str, opened: bool) -> None:
        # Keyed by name so a group stays open across selections.
        self._opened[name] = opened

    def _defer(self, edit: Callable[[], None]) -> None:
        self._edits.append(edit)
        self._edit_timer.start()

    def _apply_edits(self) -> None:
        edits, self._edits = self._edits, []
        for edit in edits:
            edit()

    @QtCore.Slot(str, "QVariant", str)
    def setValue(self, prop: str, value: Any, unit: str) -> None:
        self._defer(lambda: self._set_value(prop, value, unit))

    def _set_value(self, prop: str, value: Any, unit: str) -> None:
        objects = self._objects()
        edits: list[tuple[str, Any]] = [(prop, value)]
        if self._tab == inspector.DATA:
            coupled = inspector_templates.coupled(
                inspector_templates.for_objects(objects), objects, prop,
                value)
            if coupled is not None:
                edits = coupled
            if not edits:
                return
            # Open task panels take the edit so previews follow.
            rest = [(p, v) for p, v in edits
                    if not task_sync.set_in_task(
                        objects, p, v, unit if p == prop else "")]
            if not rest:
                self.refresh()
                return
            edits = rest
        if inspector.apply_many(
                objects, [(p, v, unit if p == prop else "")
                          for p, v in edits], self._tab):
            self.refresh()

    @QtCore.Slot(str, str, str)
    def setPart(self, prop: str, part: str, text: str) -> None:
        self._defer(lambda: self._set_part(prop, part, text))

    def _set_part(self, prop: str, part: str, text: str) -> None:
        if inspector.apply(self._objects(), prop, text, self._tab,
                           part=part):
            self.refresh()

    @QtCore.Slot(str, str)
    def pickColour(self, prop: str, current: str) -> None:
        from ..core.qt import QtGui
        colour = QtWidgets.QColorDialog.getColor(
            QtGui.QColor(current or "#808080"),
            Gui.getMainWindow(), inspector.label_for(prop))
        if colour.isValid():
            self.setValue(prop, colour.name(), "")

    @QtCore.Slot(str)
    def editNative(self, prop: str) -> None:
        """Hand one property to FreeCAD's own editor."""
        self.nativeRequested.emit(prop)
