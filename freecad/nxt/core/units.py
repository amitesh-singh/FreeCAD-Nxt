"""Numbers and quantities as users type them and FreeCAD stores them."""

from __future__ import annotations

import re

import FreeCAD as App

NUMBER = r"[-+]?[\d.,]+(?:[eE][-+]?\d+)?"


def split_number_and_unit(text: str) -> tuple[str, str]:
    """'5.00 mm' -> ('5.00', 'mm'). A bare number has no unit."""
    match = re.match(r"^\s*(%s)\s*(.*)$" % NUMBER, text)
    if not match:
        return text, ""
    return match.group(1), match.group(2).strip()


def with_unit(text: str, unit: str) -> str:
    """A bare number typed into a quantity field takes the field's unit."""
    stripped = text.strip()
    if unit and re.fullmatch(NUMBER, stripped):
        return "%s %s" % (stripped, unit)
    return stripped


def number_value(text: str) -> float:
    """A number, or a quantity in the user's units; ValueError otherwise."""
    try:
        return float(text.replace(",", "."))
    except ValueError:
        return float(App.Units.Quantity(text).Value)


def internal_value(text: str, unit: str = "") -> float | None:
    """`text` ("75", "2 in", "25 mm * 2") in internal units, or None.

    A bare number is taken in `unit`, else in the internal unit.
    """
    text = with_unit(str(text or ""), unit)
    if not text:
        return None
    try:
        return float(App.Units.Quantity(text).Value)
    except Exception:
        try:
            return float(text.replace(",", "."))
        except ValueError:
            return None
