"""Which feature made the thing picked in the 3D view.

A pick on a Body names its tip; the element map's tags (";:H16" is
object 0x16) say which feature made the element. Only the revealed row
changes, not FreeCAD's selection.
"""

from __future__ import annotations

import re
from typing import Any

#: Object tag in a mapped name; the last one is the generating object.
_TAG = re.compile(r";:H(-?[0-9a-fA-F]+)")


def element_of(subname: str) -> str:
    """The indexed element of a subname: "Pad.Face6" -> "Face6"."""
    leaf = subname.rsplit(".", 1)[-1] if subname else ""
    return "" if leaf.startswith(";") else leaf


def mapped_of(subname: str) -> str:
    """The mapped element name in a subname, without its ";" marker."""
    for part in subname.split("."):
        if part.startswith(";"):
            return part[1:]
    return ""


#: A longer chain is a loop.
_MAX_STEPS = 32


def _history(obj: Any, name: str) -> tuple[int, str]:
    """One step back: (owner ID, the owner's input name), or (0, "")."""
    names = [name]
    if name.startswith(";"):
        names.append(name[1:])
    else:
        names.insert(0, ";" + name)
    for candidate in names:
        try:
            history = obj.Shape.getElementHistory(candidate)
        except Exception:
            continue
        if history and isinstance(history[0], int) and history[0] != 0:
            return abs(history[0]), str(history[1] or "")
    return 0, ""


def _tag_in(name: str) -> int:
    """The outermost object tag in a mapped name, or 0."""
    tags = _TAG.findall(name)
    try:
        return abs(int(tags[-1], 16)) if tags else 0
    except ValueError:
        return 0


def _by_id(doc: Any, ident: int) -> Any:
    for candidate in getattr(doc, "Objects", []):
        if getattr(candidate, "ID", None) == ident:
            return candidate
    return None


def _is_feature(obj: Any) -> bool:
    try:
        return bool(obj.isDerivedFrom("PartDesign::Feature")
                    or obj.isDerivedFrom("Part::Feature")
                    and not obj.isDerivedFrom("Part::Part2DObject"))
    except Exception:
        return False


def origin(obj: Any, subname: str) -> Any:
    """The feature that first made the picked element of `obj`, or None.

    Walks the element map back until ";:G" (generated) or a non-solid
    owner; ";:M" (modified) and bare tags continue to the earlier feature.
    """
    mapped = mapped_of(subname)
    name = ";" + mapped if mapped else element_of(subname)
    if not name:
        return None
    doc = obj.Document
    current = obj
    found = None
    seen: set[int] = set()
    for _step in range(_MAX_STEPS):
        owner_id, before = _history(current, name)
        if not owner_id and current is obj:
            owner_id = _tag_in(mapped)
        owner = _by_id(doc, owner_id) if owner_id else None
        if owner is None or not _is_feature(owner) or owner_id in seen:
            break
        seen.add(owner_id)
        found = owner
        earlier = _by_id(doc, _tag_in(before)) if before else None
        if (";:G" in before or earlier is None
                or not _is_feature(earlier) or earlier is owner):
            break
        current, name, found = earlier, before, earlier
    if found is None or found is obj or found.Name == obj.Name:
        return None
    return found


def full_pick(top_name: str, subname: str,
              selection: Any) -> tuple[str, str]:
    """The pick as the selection holds it: (top object, full subname).

    Only the selection's subname carries the mapped name; the observer's
    does not. `selection` is Gui.Selection.getSelectionEx(doc, 0).
    """
    wanted = element_of(subname)
    for entry in reversed(list(selection or [])):
        entry_top = getattr(entry.Object, "Name", None)
        for candidate in reversed(list(entry.SubElementNames or [])):
            if not mapped_of(candidate) or element_of(candidate) != wanted:
                continue
            path = candidate.split(".")[:-2]
            if entry_top == top_name or top_name in path:
                return str(entry_top), candidate
    return top_name, subname


def target(doc: Any, top_name: str, subname: str) -> str | None:
    """The name of the row to reveal for one pick, or None."""
    top = doc.getObject(top_name) if doc is not None else None
    if top is None:
        return None
    picked = top
    if subname:
        try:
            leaf = top.getSubObject(subname, retType=1)
        except Exception:
            leaf = None
        if leaf is not None:
            picked = leaf
    made_by = origin(picked, subname)
    if made_by is not None:
        made_by = _first_holding(picked, subname, made_by)
    return (made_by or picked).Name


#: How far a point may sit off a surface and still lie on it.
_ON_SURFACE = 1e-6


def _surface_points(face: Any) -> list[Any]:
    """Points on `face`'s surface: its vertices and its middle."""
    u0, u1, v0, v1 = face.ParameterRange
    points = [v.Point for v in face.Vertexes]
    points.append(face.Surface.value((u0 + u1) / 2, (v0 + v1) / 2))
    return points


def _on_surface_of(face: Any, part: Any, points: list[Any]) -> bool:
    """Whether `face` is a piece of `part`: on its surface, touching it.

    A later feature may trim a face it did not make; the piece left keeps
    its maker's surface.
    """
    if type(face.Surface) is not type(part.Surface):
        return False
    try:
        if any(part.Surface.projectPoint(p, "LowerDistance") > _ON_SURFACE
               for p in points):
            return False
        return bool(part.distToShape(face)[0] < _ON_SURFACE)
    except Exception:
        return False


def _holds(feature: Any, face: Any) -> bool:
    try:
        points = _surface_points(face)
        return any(_on_surface_of(face, f, points)
                   for f in feature.Shape.Faces)
    except Exception:
        return False


def _first_holding(picked: Any, subname: str, found: Any) -> Any:
    """The earliest feature from `found` that has the face, or a piece of it.

    The element map can trace a face that a later feature made to an
    earlier one: a cut's new faces keep its input's tags. The face's
    geometry settles it.
    """
    element = element_of(subname)
    if not element.startswith("Face"):
        return found
    try:
        face = picked.getSubObject(subname)
    except Exception:
        return found
    if face is None or getattr(face, "ShapeType", "") != "Face" \
            or _holds(found, face):
        return found
    chain = []
    current = getattr(picked, "Tip", None) or picked
    for _step in range(_MAX_STEPS * 8):
        if current is None or current is found:
            break
        chain.append(current)
        current = getattr(current, "BaseFeature", None)
    if current is not found:
        return found
    for feature in reversed(chain):
        if _is_feature(feature) and _holds(feature, face):
            return feature
    return found
