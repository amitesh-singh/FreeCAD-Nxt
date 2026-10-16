"""Show every object except reference geometry and joints."""

from __future__ import annotations

from typing import Any

import FreeCAD as App

from ..tree.scene import (
    BODY_BASES,
    DATUM_BASES,
    ORIGIN_BASES,
    _derived,
    is_joint,
)
from . import section_object

KEPT_HIDDEN_BASES = DATUM_BASES + ORIGIN_BASES + ("Assembly::JointGroup",)


def kept_as_is(obj: Any) -> bool:
    """Datums, coordinate systems, joints, sections, a Body's insides."""
    if _derived(obj, KEPT_HIDDEN_BASES) or is_joint(obj):
        return True
    if obj.Name == section_object.GROUP_NAME:
        return True
    if type(getattr(obj, "Proxy", None)).__name__ == "SectionPlane":
        return True
    body = _body_of(obj)
    return body is not None and getattr(body, "Tip", None) is not obj


def _body_of(obj: Any) -> Any:
    try:
        parent = obj.getParentGeoFeatureGroup()
    except Exception:
        return None
    if parent is not None and _derived(parent, BODY_BASES):
        return parent
    return None


def show_all(doc: Any) -> None:
    """Show the rest, undoably, then restore the kept objects.

    Showing a group can show its children, kept ones included.
    """
    views = [(o, o.ViewObject) for o in doc.Objects
             if getattr(o, "ViewObject", None) is not None]
    kept = {o.Name: v.Visibility for o, v in views if kept_as_is(o)}
    doc.openTransaction("Show all")
    try:
        for obj, view in views:
            if obj.Name not in kept and not view.Visibility:
                view.Visibility = True
        for obj, view in views:
            if obj.Name in kept and view.Visibility != kept[obj.Name]:
                view.Visibility = kept[obj.Name]
    finally:
        doc.commitTransaction()


def run() -> None:
    doc = App.ActiveDocument
    if doc is not None:
        show_all(doc)
