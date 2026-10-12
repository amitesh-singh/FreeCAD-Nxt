"""The Property Inspector's contents, laid out from FreeCAD's groups.

Several objects show the properties they share; differing values are
"mixed". Pure Python over duck-typed objects, so it runs in the tests.
"""

from __future__ import annotations

import math
import re
import traceback
from typing import Any

import FreeCAD as App

from ..core import property_kinds, units
from ..core.transaction import transaction
from . import templates as inspector_templates

DocObject = Any

DATA, VIEW = "Data", "View"

#: Kinds that fit half a row. Everything else takes a whole one.
COMPACT = frozenset({"quantity", "number", "bool", "enum", "color"})

#: Groups collapsed unless something in them has an expression.
QUIET_GROUPS = frozenset({"Base", "Attachment", "Object Style",
                          "Display Options", "Selection"})

LENGTH_UNIT = "mm"
ANGLE_UNIT = "°"
AXES = ("x", "y", "z")
NUMBER_FORMAT = "%.6g"


def label_for(name: str) -> str:
    """'UseCustomVector' -> 'Use Custom Vector', as the native panel does."""
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", name)


def _expressions(obj: DocObject) -> dict[str, str]:
    return dict(getattr(obj, "ExpressionEngine", None) or ())


def _number(value: float) -> str:
    return NUMBER_FORMAT % value


def _labels(value: Any) -> list[str]:
    """Labels of whatever a link property holds, in any of its shapes."""
    out: list[str] = []
    items = value if isinstance(value, (list, tuple)) else [value]
    for item in items:
        if hasattr(item, "Label"):
            out.append(item.Label)
        elif isinstance(item, (list, tuple)) and item:
            out.extend(_labels(item[0]))
    return out


def _hex(colour: Any) -> str:
    try:
        r, g, b = (max(0, min(255, round(c * 255))) for c in colour[:3])
    except Exception:
        return ""
    return "#%02X%02X%02X" % (r, g, b)


def _entry(container: Any, prop: str, expressions: dict[str, str]
           ) -> dict[str, Any] | None:
    """One property, shaped for QML, or None if it is not for showing."""
    modes = property_kinds.editor_modes(container, prop)
    if "Hidden" in modes:
        return None
    try:
        type_id = container.getTypeIdOfProperty(prop)
        value = getattr(container, prop)
    except Exception:
        return None
    kind = property_kinds.kind_of(type_id)
    try:
        tip = container.getDocumentationOfProperty(prop) or ""
    except Exception:
        tip = ""
    entry: dict[str, Any] = {
        "name": prop, "label": label_for(prop), "kind": kind,
        "wide": kind not in COMPACT, "text": "", "unit": "",
        "checked": False, "options": [], "links": [], "parts": [],
        "expression": expressions.get(prop, ""),
        "readOnly": "ReadOnly" in modes, "mixed": False, "tip": tip,
    }
    if kind == "quantity":
        text = getattr(value, "UserString", str(value))
        entry["text"], entry["unit"] = units.split_number_and_unit(text)
    elif kind in ("number", "text"):
        entry["text"] = str(value)
    elif kind == "bool":
        entry["checked"] = bool(value)
    elif kind == "enum":
        entry["text"] = str(value)
        entry["options"] = list(
            container.getEnumerationsOfProperty(prop) or ())
    elif kind == "color":
        entry["text"] = _hex(value)
    elif kind == "link":
        entry["links"] = _labels(value)
    elif kind == "vector":
        unit = LENGTH_UNIT if type_id in property_kinds.LENGTH_VECTORS else ""
        entry["parts"] = [
            {"path": axis, "label": axis.upper(),
             "text": _number(getattr(value, axis)), "unit": unit}
            for axis in AXES]
    elif kind == "placement":
        base, rotation = value.Base, value.Rotation
        axis = rotation.Axis
        entry["parts"] = (
            [{"path": "Base." + a, "label": a.upper(),
              "text": _number(getattr(base, a)), "unit": LENGTH_UNIT}
             for a in AXES]
            + [{"path": "Axis." + a, "label": a.upper(),
                "text": _number(getattr(axis, a)), "unit": ""}
               for a in AXES]
            + [{"path": "Angle", "label": "Angle",
                "text": _number(math.degrees(rotation.Angle)),
                "unit": ANGLE_UNIT}])
    else:
        entry["text"] = str(value)
    return entry


def _container(obj: DocObject, tab: str) -> Any:
    return getattr(obj, "ViewObject", None) if tab == VIEW else obj


def _merge(first: dict[str, Any], other: dict[str, Any]) -> None:
    """Fold another object's value for the same property into `first`."""
    same = all(first[key] == other[key]
               for key in ("text", "checked", "links", "parts"))
    if not same:
        first["mixed"] = True
    first["readOnly"] = first["readOnly"] or other["readOnly"]
    if first["expression"] != other["expression"]:
        first["expression"] = ""


def _type_name(obj: DocObject) -> str:
    return str(getattr(obj, "TypeId", "")).split("::")[-1]


def describe(objects: list[DocObject], tab: str = DATA,
             text_filter: str = "") -> list[dict[str, Any]]:
    """The inspector's groups for `objects`: [{name, open, items}]."""
    if not objects:
        return []
    containers = [_container(obj, tab) for obj in objects]
    if any(c is None for c in containers):
        return []
    needle = text_filter.strip().lower()
    groups: dict[str, list[dict[str, Any]]] = {}
    first, rest = containers[0], containers[1:]
    expressions = [_expressions(obj) if tab == DATA else {}
                   for obj in objects]
    for prop in list(getattr(first, "PropertiesList", ()) or ()):
        entry = _entry(first, prop, expressions[0])
        if entry is None:
            continue
        if needle and needle not in entry["label"].lower() \
                and needle not in prop.lower():
            continue
        shared = True
        for container, exprs in zip(rest, expressions[1:]):
            other = (_entry(container, prop, exprs)
                     if prop in (container.PropertiesList or ()) else None)
            if other is None or other["kind"] != entry["kind"]:
                shared = False
                break
            _merge(entry, other)
        if not shared:
            continue
        try:
            group = first.getGroupOfProperty(prop) or ""
        except Exception:
            group = ""
        groups.setdefault(group or "Other", []).append(entry)

    template = (inspector_templates.for_objects(objects)
                if tab == DATA else None)
    cards = (inspector_templates.apply(template, objects, groups)
             if template is not None else [])

    own = _type_name(objects[0]) if len(objects) == 1 else ""
    out = []
    for index, (name, items) in enumerate(groups.items()):
        opened = (bool(needle)
                  or any(item["expression"] for item in items)
                  or (not cards and (name == own
                                     or name not in QUIET_GROUPS)))
        out.append({"name": name, "open": opened, "items": items,
                    "first": name == own and not cards})
    out.sort(key=lambda group: not group["first"])
    if cards and out:
        out[0]["rest"] = True
    return cards + out


# -- editing --

def _assign(container: Any, obj: DocObject, prop: str, value: Any,
            unit: str) -> None:
    kind = property_kinds.kind_of(container.getTypeIdOfProperty(prop))
    if property_kinds.is_expression(value) and container is obj:
        obj.setExpression(prop, property_kinds.expression_of(value))
        return
    if container is obj and prop in _expressions(obj):
        obj.setExpression(prop, None)
    if kind == "bool":
        setattr(container, prop, bool(value))
    elif kind == "number":
        current = getattr(container, prop)
        setattr(container, prop, type(current)(units.number_value(str(value))))
    elif kind == "quantity":
        setattr(container, prop, units.with_unit(str(value), unit))
    elif kind == "color":
        colour = _parse_colour(str(value))
        if colour is not None:
            setattr(container, prop, colour)
    else:
        setattr(container, prop, str(value))


def _parse_colour(text: str) -> tuple[float, float, float] | None:
    """Colours cross from QML as '#RRGGBB'."""
    match = re.fullmatch(r"#?([0-9a-fA-F]{6})", text.strip())
    if not match:
        return None
    digits = match.group(1)
    red, green, blue = (int(digits[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    return red, green, blue


def _assign_part(container: Any, prop: str, path: str, text: str) -> None:
    """Set one component of a vector or placement."""
    value = getattr(container, prop)
    number = units.number_value(text)
    if path in AXES:
        setattr(value, path, number)
    elif path.startswith("Base."):
        setattr(value.Base, path[len("Base."):], number)
    elif path.startswith("Axis."):
        axis = value.Rotation.Axis
        setattr(axis, path[len("Axis."):], number)
        value.Rotation = App.Rotation(axis, math.degrees(
            value.Rotation.Angle))
    elif path == "Angle":
        value.Rotation = App.Rotation(value.Rotation.Axis, number)
    setattr(container, prop, value)


def apply(objects: list[DocObject], prop: str, value: Any,
          tab: str = DATA, unit: str = "", part: str = "") -> bool:
    """Set `prop` on every object as one undo step, then recompute."""
    return apply_many(objects, [(prop, value, unit)], tab, part)


def apply_many(objects: list[DocObject],
               edits: list[tuple[str, Any, str]], tab: str = DATA,
               part: str = "") -> bool:
    """Make several (property, value, unit) edits as one undo step."""
    if not objects or not edits:
        return False
    doc = getattr(objects[0], "Document", None)
    if doc is None:
        return False
    try:
        with transaction(doc, "Edit %s" % edits[-1][0]):
            for prop, value, unit in edits:
                for obj in objects:
                    container = _container(obj, tab)
                    if part:
                        _assign_part(container, prop, part, str(value))
                    else:
                        _assign(container, obj, prop, value, unit)
    except Exception:
        App.Console.PrintError("Nxt: could not set %s\n"
                               % ", ".join("%s to %r" % (p, v)
                                           for p, v, _u in edits))
        App.Console.PrintError(traceback.format_exc())
        return False
    doc.recompute()
    return True
