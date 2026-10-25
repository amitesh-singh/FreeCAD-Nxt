"""Edits to a feature whose task panel is open go through the panel.

The open panel owns the feature: OK writes its fields back, overwriting
a property set directly. Field names: TaskExtrudeParameters.ui.
"""

from __future__ import annotations

from typing import Any

import FreeCADGui as Gui

from ..core import units
from ..core.qt import QtWidgets

#: How a field is set.
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

#: Kept in the enumeration for compatibility; absent from the combo box.
DEPRECATED_MODE = "TwoLengths"


#: Set on a dialog box task_layout.py has swapped for the template's cards.
SWAPPED = "nxtSwapped"


def showing(widget: Any) -> bool:
    """A task field is in use: on screen, or in a box swapped for cards."""
    if widget.isVisible():
        return True
    box = widget.parentWidget()
    while box is not None:
        if box.property(SWAPPED):
            holder = box.parentWidget()
            return (widget.isVisibleTo(box) and holder is not None
                    and holder.isVisible())
        box = box.parentWidget()
    return False


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


def set_in_task(objects: list[Any], prop: str, value: Any,
                unit: str = "") -> bool:
    """Make the edit in the open task panel's field; False if it has none.

    Expressions are never typed in; the panel would take them literally.
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
            number = units.internal_value(value, unit)
            if number is None:
                return False
            widget.setProperty("rawValue", number)
    except (RuntimeError, AttributeError, ValueError):
        return False
    return True


#: An offset start shows the offset handle; at zero, the same solid.
START_PROFILE, START_OFFSET = "Profile plane", "Offset"


def start_with_offset(obj: Any) -> bool:
    """Switch an edited Pad or Pocket to an offset start. True if changed.

    Set via the panel field so Cancel reverts it with the edit.
    """
    if not wants_offset_start(obj):
        return False
    return set_in_task([obj], "StartType", START_OFFSET)


def wants_offset_start(obj: Any) -> bool:
    """`obj` is an extrusion still starting at its profile plane."""
    return (str(getattr(obj, "TypeId", "")) in FIELDS
            and str(getattr(obj, "StartType", "")) == START_PROFILE)
