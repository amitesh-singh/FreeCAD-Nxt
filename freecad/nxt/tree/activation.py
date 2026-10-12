"""Double-click in the tree: activate a container or open an edit."""

from __future__ import annotations

from typing import Any

import FreeCAD as App

from ..core import fc, log, settings
from ..tools import editing


class Activation:
    """Double-click handling for the tree; TreeBridge's slot calls this."""

    def __init__(self, bridge: Any) -> None:
        self._bridge = bridge
        self._pending_active = ""
        self._pending_edit: tuple[str, str] | None = None
        self._activate_timer = bridge._deferral(self._activate_pending)
        self._edit_timer = bridge._deferral(self._enter_pending_edit)

    @property
    def _snapshot(self) -> Any:
        return self._bridge._snapshot

    def activate(self, name: str) -> None:
        """Double-click: activate or toggle a container, edit anything else."""
        doc = App.ActiveDocument
        if doc is None or editing.is_reference_pick(doc.getObject(name)):
            return
        node = self._snapshot.nodes.get(name)
        if node is not None and node.is_container and not node.is_lifted:
            if name != self._bridge._active and self._active_key(
                    doc.getObject(name)):
                # Deferred: activating can switch workbench or open a task.
                self._pending_active = name
                self._activate_timer.start()
                return
            self._bridge.toggleExpanded(name)
            return
        if doc.getObject(name) is None:
            return
        # Deferred: setEdit nests an event loop and can destroy the
        # delegate inside its own onDoubleClicked, which aborts QML.
        self._pending_edit = (doc.Name, name)
        self._edit_timer.start()

    @staticmethod
    def _active_key(obj: Any) -> str:
        """The key FreeCAD keeps this kind of active container under."""
        type_id = str(getattr(obj, "TypeId", ""))
        if type_id == "PartDesign::Body":
            return "pdbody"
        try:
            if type_id.startswith("Assembly::Assembly") \
                    or obj.isDerivedFrom("App::Part"):
                return "part"
        except Exception:
            pass
        return ""

    def _activate_pending(self) -> None:
        """Make the double-clicked container the active one."""
        name, self._pending_active = self._pending_active, ""
        doc = App.ActiveDocument
        obj = doc.getObject(name) if doc is not None and name else None
        key = self._active_key(obj)
        if obj is None or not key:
            return
        try:
            obj.ViewObject.doubleClicked()
        except Exception:
            pass
        try:
            view = fc.active_view()
            if self._bridge._read_active() != name and view is not None:
                view.setActiveObject(key, obj)
        except Exception:
            log.error("could not make %s active" % name)
        self._bridge._sync_active()

    def _enter_pending_edit(self) -> None:
        pending, self._pending_edit = self._pending_edit, None
        if pending is not None:
            self._enter_edit(*pending)

    def _enter_edit(self, doc_name: str, name: str) -> None:
        """Edit an object inside an undo step of its own (editing.py)."""
        editing.open_for_edit(
            doc_name, name,
            handles=not settings.get("TreeEditHidesHandles"))
