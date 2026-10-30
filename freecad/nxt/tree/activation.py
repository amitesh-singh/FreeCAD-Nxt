"""Double-click in the tree: activate a container or open an edit."""

from __future__ import annotations

from typing import Any

import FreeCAD as App

from ..core import fc, log, settings
from ..tools import editing

#: Types whose task opens through FreeCAD's double-click, not an edit.
DOUBLE_CLICKED = frozenset({"Image::ImagePlane"})


class Activation:
    """Double-click handling for the tree; TreeBridge's slot calls this."""

    def __init__(self, bridge: Any) -> None:
        self._bridge = bridge
        self._pending_active = ""
        self._pending_edit: tuple[str, str] | None = None
        self._activate_timer = bridge._deferral(self._activate_pending)
        self._edit_timer = bridge._deferral(self._enter_pending_edit)
        self._pending_inspect = ""
        self._pending_native = ""
        self._native_timer = bridge._deferral(self._native_pending)
        self._inspect_timer = bridge._deferral(self._inspect_pending)

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
            key = self._active_key(doc.getObject(name))
            current = (self._bridge._active_part if key == "part"
                       else self._bridge._active)
            if key and name != current:
                # Deferred: activating can switch workbench or open a task.
                self._pending_active = name
                self._activate_timer.start()
                return
            self._bridge.toggleExpanded(name)
            return
        obj = doc.getObject(name)
        if obj is None:
            return
        if getattr(obj, "TypeId", "") in DOUBLE_CLICKED:
            # Their view provider's own double-click opens their task;
            # editing them instead opens a bare transform.
            self._pending_native = name
            self._native_timer.start()
            return
        if getattr(obj, "TypeId", "") == "App::VarSet":
            # Its variables are its content: show them in the inspector.
            self._pending_inspect = name
            self._inspect_timer.start()
            return
        # Deferred: setEdit nests an event loop and can destroy the
        # delegate inside its own onDoubleClicked, which aborts QML.
        self._pending_edit = (doc.Name, name)
        self._edit_timer.start()

    def _native_pending(self) -> None:
        """Run FreeCAD's own double-click on the object."""
        name, self._pending_native = self._pending_native, ""
        doc = App.ActiveDocument
        obj = doc.getObject(name) if doc is not None and name else None
        view = getattr(obj, "ViewObject", None)
        if view is None:
            return
        try:
            view.doubleClicked()
        except Exception:
            log.error("could not open %s" % name)

    def _inspect_pending(self) -> None:
        """Open the Property Inspector on the double-clicked VarSet."""
        name, self._pending_inspect = self._pending_inspect, ""
        if not name:
            return
        self._bridge._push_selection([name], False)
        self._bridge.request_property_inspector()

    @staticmethod
    def _active_key(obj: Any) -> str:
        """The key FreeCAD keeps this kind of active container under."""
        type_id = str(getattr(obj, "TypeId", ""))
        if type_id == "PartDesign::Body":
            return "pdbody"
        if type_id.startswith("Assembly::Assembly"):
            return "assembly"
        try:
            if obj.isDerivedFrom("App::Part"):
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
            if self._bridge._read_active((key,)) != name \
                    and view is not None:
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
