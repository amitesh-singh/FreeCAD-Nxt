"""The tree colours a stylesheet sets, with FreeCAD's colour tokens resolved.

Qt stylesheets do not reliably update widget palettes, so the stylesheet
itself is read. Anything not readable exactly reads as None.
"""

from __future__ import annotations

import re
from collections.abc import Callable

from ..core.qt import QtGui

#: Most specific first. Containers are included because a theme (FreeCAD
#: Light) can leave the tree transparent and colour what is behind it.
SELECTORS = ("Gui--TreeWidget", "QTreeWidget", "QTreeView",
             "QAbstractItemView", "QAbstractScrollArea",
             "QDockWidget", "QMainWindow", "QWidget")

_COMMENT = re.compile(r"/\*.*?\*/", re.S)
_RULE = re.compile(r"([^{}]+)\{([^{}]*)\}")
_TOKEN = re.compile(r"^@([A-Za-z_][\w.-]*)$")
_MAX_DEPTH = 8

Lookup = Callable[[str], "str | int | None"]


def _declarations(body: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for part in body.split(";"):
        name, sep, value = part.partition(":")
        if sep:
            out[name.strip().lower()] = value.strip()
    return out


def rules_for(qss: str, selector: str) -> dict[str, str]:
    """Declarations for exactly the bare `selector`, later rules winning."""
    merged: dict[str, str] = {}
    for match in _RULE.finditer(_COMMENT.sub("", qss)):
        selectors = [s.strip() for s in match.group(1).split(",")]
        if selector in selectors:
            merged.update(_declarations(match.group(2)))
    return merged


def colour_of(value: str | int | None, lookup: Lookup,
              depth: int = 0) -> QtGui.QColor | None:
    """A stylesheet value or parameter as a colour, or None if unreadable."""
    if value is None or depth > _MAX_DEPTH:
        return None
    if isinstance(value, int):
        # FreeCAD stores colours as unsigned 0xRRGGBBAA.
        value &= 0xFFFFFFFF
        return QtGui.QColor((value >> 24) & 0xFF, (value >> 16) & 0xFF,
                            (value >> 8) & 0xFF)
    text = value.strip().rstrip(";").strip()
    if text.lower().endswith("!important"):
        text = text[:-len("!important")].strip()
    token = _TOKEN.match(text)
    if token:
        return colour_of(lookup(token.group(1)), lookup, depth + 1)
    if text.isdigit():
        return colour_of(int(text), lookup, depth + 1)
    rgb = re.fullmatch(r"rgba?\(([^)]*)\)", text, re.I)
    if rgb:
        parts = [p.strip() for p in rgb.group(1).split(",")]
        try:
            r, g, b = (int(float(p)) for p in parts[:3])
            alpha = float(parts[3]) if len(parts) > 3 else 255.0
        except ValueError:
            return None
        # Translucent means "whatever is behind". Qt alpha is 0-255, or
        # 0-1 with a decimal point.
        full = 1.0 if len(parts) > 3 and "." in parts[3] else 255.0
        if alpha < full:
            return None
        return QtGui.QColor(r, g, b)
    colour = QtGui.QColor(text)
    if not colour.isValid() or colour.alpha() < 255:
        return None
    return colour


def _background(decls: dict[str, str]) -> str | None:
    if "background-color" in decls:
        return decls["background-color"]
    value = decls.get("background")
    # `background` is a shorthand; only a single colour is read from it.
    return value if value and " " not in value.strip() else None


def tree_colours(qss: str, lookup: Lookup
                 ) -> tuple[QtGui.QColor | None, QtGui.QColor | None]:
    """(background, text) a stylesheet gives a tree; None where silent."""
    base: QtGui.QColor | None = None
    text: QtGui.QColor | None = None
    for selector in SELECTORS:
        decls = rules_for(qss, selector)
        if base is None:
            base = colour_of(_background(decls), lookup)
        if text is None:
            text = colour_of(decls.get("color"), lookup)
        if base is not None and text is not None:
            break
    return base, text
