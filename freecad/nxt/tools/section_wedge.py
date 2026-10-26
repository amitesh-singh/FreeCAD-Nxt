"""A section's second plane, hinged on the first, cutting out a wedge.

The two planes share a hinge: the frame's middle line along its v
axis. What is cut away lies behind both, so the part kept is what lies
in front of either. Each solid's own view provider already keeps the
front of the first plane; a second pass draws it again, in front of the
second plane and behind the first, so together they draw the union. The
second pass shares the view provider's own nodes under its placement;
it is never picked, so selecting still goes to the part itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import FreeCAD as App

from .section_cap import Clipped, local_plane

#: The wedge's widest opening: at that, the two planes are one.
MOST = 180.0
LEAST = 1.0


def opening(angle: Any) -> float:
    degrees = float(getattr(angle, "Value", angle))
    return min(max(degrees, LEAST), MOST)


def hinged(normal: App.Vector, hinge: App.Vector,
           degrees: float) -> App.Vector:
    """The second plane's normal: the wedge cut away opens `degrees`."""
    turned = App.Rotation(hinge, MOST - degrees).multVec(normal)
    turned.normalize()
    return turned


def outward(normal_b: App.Vector, hinge: App.Vector,
            normal_a: App.Vector) -> App.Vector:
    """In the second plane, away from the hinge, behind the first."""
    along = hinge.cross(normal_b)
    along.normalize()
    return along if along.dot(normal_a) <= 0 else along * -1.0


def behind(faces: list[Any], normal: App.Vector, point: App.Vector,
           size: float) -> list[Any]:
    """The parts of `faces` behind the plane: those the wedge cuts."""
    import Part
    first = normal.cross(App.Vector(1, 0, 0))
    if first.Length < 0.5:
        first = normal.cross(App.Vector(0, 1, 0))
    first.normalize()
    second = normal.cross(first)
    corners = [point + first * a * size + second * b * size
               for a, b in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
    wall = Part.Face(Part.makePolygon(corners + corners[:1]))
    half = wall.extrude(normal * -size)
    out = []
    for face in faces:
        try:
            out.extend(face.common(half).Faces)
        except Exception:  # noqa: BLE001 - left whole rather than lost
            out.append(face)
    return out


@dataclass
class Pass:
    """One solid drawn again, between the second plane and the first."""

    node: Any
    keep_b: Any
    not_a: Any
    parent: Any


class SecondPass:
    """Every cut solid drawn again for the wedge's second half."""

    def __init__(self) -> None:
        from pivy import coin
        self.root = coin.SoSeparator()
        unpickable = coin.SoPickStyle()
        unpickable.style = coin.SoPickStyle.UNPICKABLE
        self.root.addChild(unpickable)
        self.solids = coin.SoGroup()
        self.root.addChild(self.solids)
        self.items: list[Pass] = []

    def attach(self, clipped: list[Clipped]) -> None:
        """Share each solid's own nodes, less the first plane's clip."""
        from pivy import coin
        self.detach()
        for item in clipped:
            node = coin.SoSeparator()
            place = coin.SoTransform()
            base, q = item.parent.Base, item.parent.Rotation.Q
            place.translation = (base.x, base.y, base.z)
            place.rotation = coin.SbRotation(q[0], q[1], q[2], q[3])
            node.addChild(place)
            keep_b = coin.SoClipPlane()
            not_a = coin.SoClipPlane()
            node.addChild(keep_b)
            node.addChild(not_a)
            own = item.root.findChild(item.clip)
            for i in range(item.root.getNumChildren()):
                if i != own:
                    node.addChild(item.root.getChild(i))
            self.solids.addChild(node)
            self.items.append(Pass(node, keep_b, not_a, item.parent))

    def place(self, normal_a: App.Vector, point_a: App.Vector,
              normal_b: App.Vector, point_b: App.Vector) -> None:
        for item in self.items:
            _set(item.keep_b, *local_plane(normal_b, point_b, item.parent))
            _set(item.not_a, *local_plane(normal_a * -1.0, point_a,
                                          item.parent))

    def detach(self) -> None:
        self.solids.removeAllChildren()
        self.items = []


def _set(clip: Any, normal: App.Vector, point: App.Vector) -> None:
    from pivy import coin
    clip.plane = coin.SbPlane(coin.SbVec3f(normal.x, normal.y, normal.z),
                              coin.SbVec3f(point.x, point.y, point.z))


def set_world(clip: Any, normal: App.Vector, point: App.Vector) -> None:
    _set(clip, normal, point)
