"""Put a new sketch, container or feature straight into rename.

A container is renamed as soon as it is made. A sketch or feature is
renamed when the edit it was made in closes, unless that edit was
cancelled, which deletes it. Objects read from a file, or brought back
by undo, are not new.
"""

from __future__ import annotations

from typing import Any

import FreeCAD as App

from ..core import settings
from ..core.qt import QtCore

CONTAINERS = frozenset({"App::Part", "App::DocumentObjectGroup",
                        "PartDesign::Body", "Assembly::AssemblyObject"})
#: Lets a cancelled edit delete its object, and the tree rebuild, first.
SETTLE_MS = 150


def _key(obj: Any) -> tuple[str, str]:
    return obj.Document.Name, obj.Name


def _arriving(obj: Any) -> bool:
    doc = obj.Document
    return not (App.isRestoring() or getattr(doc, "Restoring", False)
                or getattr(doc, "Transacting", False))


class AutoRename:
    """Watches creation and editing; asks `rename(name)` when one is due."""

    def __init__(self, parent: QtCore.QObject, rename: Any) -> None:
        self._rename = rename
        self._made: tuple[str, str] | None = None
        self._editing: tuple[str, str] | None = None
        self._due: tuple[str, str] | None = None
        self._timer = QtCore.QTimer(parent)
        self._timer.setSingleShot(True)
        self._timer.setInterval(SETTLE_MS)
        self._timer.timeout.connect(self._fire)

    def created(self, obj: Any) -> None:
        if not settings.get("AutoRename") or not _arriving(obj):
            return
        if obj.TypeId in CONTAINERS:
            self._schedule(_key(obj))
        else:
            self._made = _key(obj)

    def edit_opened(self, obj: Any) -> None:
        key = _key(obj)
        self._editing = key if key == self._made else None
        self._made = None

    def edit_closed(self, obj: Any) -> None:
        key = _key(obj)
        if key == self._editing:
            self._schedule(key)
        self._editing = None

    def deleted(self, obj: Any) -> None:
        key = _key(obj)
        if key in (self._made, self._editing, self._due):
            self._made = self._editing = self._due = None

    def _schedule(self, key: tuple[str, str]) -> None:
        self._due = key
        self._timer.start()

    def _fire(self) -> None:
        key, self._due = self._due, None
        if key is None:
            return
        try:
            obj = App.getDocument(key[0]).getObject(key[1])
        except Exception:  # noqa: BLE001 - the document closed
            return
        if obj is not None:
            self._rename(obj.Name)
