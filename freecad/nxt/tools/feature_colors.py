"""An Nxt feature looks like the feature it was made from.

Part Design copies the base feature's look onto each new feature; ours
are made by Nxt, so it is done here. Faces coloured one by one keep their
colour: each face of the result takes the colour of the base face it lies
on, and a new face (a round, a chamfer) the base's most common colour.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

import Part

from . import blend_fillet as bf

#: What Part Design's own features copy from their base.
VISUALS = ("ShapeAppearance", "LineColor", "PointColor", "LineWidth",
           "PointSize", "Transparency", "DisplayMode")

#: How far a sample point may be from a base face and still lie on it.
_ON_FACE = 1e-6


def copy_visuals(base: Any, obj: Any) -> None:
    source = getattr(base, "ViewObject", None)
    target = getattr(obj, "ViewObject", None)
    if source is None or target is None:
        return
    for name in VISUALS:
        try:
            setattr(target, name, getattr(source, name))
        except Exception:  # noqa: BLE001 - a property one of them lacks
            pass
    carry_face_colors(obj)


def _per_face(vobj: Any, shape: Any) -> list[Any] | None:
    """The view's materials, one per face, if they are not all the same."""
    try:
        materials = list(vobj.ShapeAppearance)
    except Exception:  # noqa: BLE001 - no appearance to carry
        return None
    if len(materials) != len(shape.Faces) or len(materials) < 2:
        return None
    first = materials[0]
    if all(m == first for m in materials[1:]):
        return None
    return materials


def _base_face_index(base_faces: list[Any], face: Any) -> int | None:
    for index, base_face in enumerate(base_faces):
        if face.isSame(base_face):
            return index
    point = bf._point_on(face, face.BoundBox.DiagonalLength * 1e-4)
    if point is None:
        return None
    vertex = Part.Vertex(point)
    for index, base_face in enumerate(base_faces):
        if type(base_face.Surface) is not type(face.Surface):
            continue
        try:
            if base_face.distToShape(vertex)[0] < _ON_FACE:
                return index
        except Exception:  # noqa: BLE001 - not this one
            continue
    return None


def carry_face_colors(obj: Any) -> None:
    """Give each face of `obj` the colour it had on the base feature."""
    base: Any = getattr(obj, "BaseFeature", None)
    source = getattr(base, "ViewObject", None)
    target = getattr(obj, "ViewObject", None)
    if source is None or target is None or obj.Shape.isNull():
        return
    materials = _per_face(source, base.Shape)
    if materials is None:
        return
    common = Counter(materials).most_common(1)[0][0]
    base_faces = base.Shape.Faces
    carried = []
    for face in obj.Shape.Faces:
        index = _base_face_index(base_faces, face)
        carried.append(common if index is None else materials[index])
    try:
        target.ShapeAppearance = carried
    except Exception:  # noqa: BLE001 - the view refused it; keep its look
        pass
