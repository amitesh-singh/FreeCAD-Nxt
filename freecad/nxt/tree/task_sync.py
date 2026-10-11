"""Edits to a feature whose task panel is open go through the panel.

While a Pad's task panel is open, the panel owns the feature: its fields
drive the preview and the 3D handles, and OK writes every field back to the
feature. A property set behind its back - by the Property Inspector, say -
moves neither the handles nor the panel, and OK then puts the panel's old
value back.

So an edit to a property the panel has a field for is made in that field,
as if typed there: the panel's own handler sets the property, updates the
preview and places the handles, and its OK keeps the value. Edits it has
no field for, and expressions, go to the property as before.

Field names are FreeCAD's (TaskExtrudeParameters.ui, FreeCAD 27).
"""

from __future__ import annotations

from typing import Any

import FreeCAD as App
import FreeCADGui as Gui

from ..qt import QtWidgets

#: How a field is set: a quantity spin box, a check box, a combo box by
#: the enumeration's index, or Type's combo box (see _mode_index).
QUANTITY, CHECK, INDEX, MODE = "quantity", "check", "index", "mode"

_EXTRUDE: dict[str, tuple[str, str]] = {
    "SideType": ("sidesMode", INDEX),
    "Type": ("changeMode", MODE),
    "Type2": ("changeMode2", MODE),
    "Length": ("lengthEdit", QUANTITY),
    "Length2": ("lengthEdit2", QUANTITY),
    "Offset": ("offsetEdit", QUANTITY),
    "Offset2": ("offsetEdit2", QUANTITY),
    "TaperAngle": ("taperEdit", QUANTITY),
    "TaperAngle2": ("taperEdit2", QUANTITY),
    "StartType": ("startMode", INDEX),
    "StartOffset": ("startOffsetEdit", QUANTITY),
    "Reversed": ("checkBoxReversed", CHECK),
    "AlongSketchNormal": ("checkBoxAlongDirection", CHECK),
}

#: Per feature type, property -> (task field, how it is set).
FIELDS: dict[str, dict[str, tuple[str, str]]] = {
    "PartDesign::Pad": _EXTRUDE,
    "PartDesign::Pocket": _EXTRUDE,
}

#: The enumeration value FreeCAD keeps for compatibility only: Type's
#: combo box has no entry for it (SideType "Two sides" replaced it).
DEPRECATED_MODE = "TwoLengths"


def _in_edit(obj: Any) -> bool:
    """`obj` is being edited, with a task panel open."""
    try:
        gui_doc = Gui.getDocument(obj.Document.Name)
        view: Any = gui_doc.getInEdit() if gui_doc is not None else None
        return (getattr(view, "Object", None) is obj
                and bool(Gui.Control.activeDialog()))
    except Exception:
        return False


def _field(name: str) -> Any:
    main = Gui.getMainWindow()
    return main.findChild(QtWidgets.QWidget, name) if main else None


def _mode_index(options: list[str], value: str) -> int:
    """Type's combo index: the enumeration's, without TwoLengths."""
    shown = [o for o in options if o != DEPRECATED_MODE]
    return shown.index(value) if value in shown else -1


def _quantity(text: str, unit: str) -> float | None:
    text = str(text).strip()
    if text and unit and text[-1].isdigit():
        text = "%s %s" % (text, unit)
    try:
        return float(App.Units.Quantity(text).Value)
    except Exception:
        return None


def set_in_task(objects: list[Any], prop: str, value: Any,
                unit: str = "") -> bool:
    """Make the edit in the open task panel's field; False if it has none.

    Only for a single object being edited; an expression ("=...") is
    never typed into a field, as the panel would take it literally.
    """
    if len(objects) != 1:
        return False
    obj = objects[0]
    fields = FIELDS.get(str(getattr(obj, "TypeId", "")), {})
    if prop not in fields or not _in_edit(obj):
        return False
    if isinstance(value, str) and value.strip().startswith("="):
        return False
    name, how = fields[prop]
    widget = _field(name)
    if widget is None:
        return False
    try:
        if how == CHECK:
            widget.setChecked(bool(value) if not isinstance(value, str)
                              else value.lower() in ("1", "true", "yes"))
        elif how in (INDEX, MODE):
            options = list(obj.getEnumerationsOfProperty(prop) or ())
            index = (_mode_index(options, str(value)) if how == MODE
                     else options.index(str(value))
                     if str(value) in options else -1)
            if index < 0 or index >= widget.count():
                return False
            widget.setCurrentIndex(index)
        else:
            number = _quantity(value, unit)
            if number is None:
                return False
            widget.setProperty("rawValue", number)
    except (RuntimeError, AttributeError, ValueError):
        return False
    return True


#: The start a new edit of an extrusion is given in place of FreeCAD's
#: "Profile plane": the same solid at zero, and its offset handle shown in
#: the 3D view, ready to drag.
START_PROFILE, START_OFFSET = "Profile plane", "Offset"


def start_with_offset(obj: Any) -> bool:
    """A Pad or Pocket opened for editing starts at an offset, not a plane.

    Made in the task panel's own field, so the offset handle appears and
    Cancel takes it back with the rest of the edit. True if it changed.
    """
    if not wants_offset_start(obj):
        return False
    return set_in_task([obj], "StartType", START_OFFSET)


def wants_offset_start(obj: Any) -> bool:
    """`obj` is an extrusion still starting at its profile plane."""
    return (str(getattr(obj, "TypeId", "")) in FIELDS
            and str(getattr(obj, "StartType", "")) == START_PROFILE)
