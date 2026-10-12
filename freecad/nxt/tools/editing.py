"""Opening a feature for editing, the way FreeCAD's own tree does."""

from __future__ import annotations

import traceback
from typing import Any

import FreeCAD as App
import FreeCADGui as Gui

ORIGIN = "App::Origin"
ORIGIN_FEATURE = "App::OriginFeature"
#: Datum types; origin features are DatumElements too, so are excluded.
DATUMS = ("Part::Datum", "App::DatumElement")


def object_in(doc_name: str, name: str) -> Any:
    """The named object of an open document, or None."""
    try:
        return Gui.getDocument(doc_name).Document.getObject(name)
    except Exception:
        return None


def is_datum(obj: Any) -> bool:
    """A datum plane, line or point that can be attached."""
    try:
        return (any(obj.isDerivedFrom(t) for t in DATUMS)
                and not obj.isDerivedFrom(ORIGIN_FEATURE)
                and hasattr(obj, "MapMode"))
    except Exception:
        return False


def edit_attachment(doc_name: str, name: str) -> None:
    """Open the attachment dialog for a datum.

    AttachmentEditor opens its own undo step. Call deferred, as enter_edit.
    """
    gui_doc = Gui.getDocument(doc_name)
    obj = gui_doc.Document.getObject(name) if gui_doc else None
    if obj is None:
        return
    if gui_doc.getInEdit() is not None:
        gui_doc.resetEdit()
    try:
        from AttachmentEditor import Commands
        Commands.editAttachment(obj, take_selection=False,
                                create_transaction=True)
        return
    except Exception:
        App.Console.PrintLog("Nxt: AttachmentEditor not usable: %s\n"
                             % traceback.format_exc())
    try:
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(doc_name, name)
        Gui.runCommand("Part_EditAttachment", 0)
    except Exception:
        App.Console.PrintError("Nxt: could not open the attachment of %s\n"
                               % name)
        App.Console.PrintError(traceback.format_exc())


def is_reference_pick(obj: Any) -> bool:
    """An origin feature clicked while a task panel is open (a reference)."""
    try:
        if obj is None or not Gui.Control.activeDialog():
            return False
        return bool(obj.isDerivedFrom(ORIGIN_FEATURE)) or any(
            parent.isDerivedFrom(ORIGIN) for parent in obj.InList)
    except Exception:
        return False


def open_edit_transaction(obj: Any) -> bool:
    """Open the undo step for an edit of `obj`, unless one is active."""
    try:
        if App.getActiveTransaction():
            return False
        # persist: the task panel closes it on OK or Cancel.
        App.setActiveTransaction("Edit %s" % obj.Label, True)
        return True
    except Exception:
        return False


def open_for_edit(doc_name: str, name: str, handles: bool = True) -> None:
    """A double-click's edit: a datum's attachment, else enter_edit."""
    if is_datum(object_in(doc_name, name)):
        edit_attachment(doc_name, name)
    elif handles:
        enter_edit(doc_name, name)
    else:
        enter_edit(doc_name, name, handles=False)


def enter_edit(doc_name: str, name: str, handles: bool = True) -> None:
    """Edit an object, inside an undo step of its own.

    setEdit opens no transaction, so Cancel/undo would not work without
    one. Call deferred: setEdit nests an event loop.
    """
    opened = False
    try:
        gui_doc = Gui.getDocument(doc_name)
        obj = gui_doc.Document.getObject(name)
        if obj is None:
            return
        if gui_doc.getInEdit() is not None:
            gui_doc.resetEdit()
        opened = open_edit_transaction(obj)
        if handles:
            gui_doc.setEdit(obj)
        else:
            from . import gizmos
            with gizmos.hidden():
                gui_doc.setEdit(obj)
        if gui_doc.getInEdit() is None and opened:
            App.closeActiveTransaction(True)    # nothing was edited
    except Exception:
        if opened:
            App.closeActiveTransaction(True)
        App.Console.PrintError("Nxt: could not open %s for editing\n" % name)
        App.Console.PrintError(traceback.format_exc())
