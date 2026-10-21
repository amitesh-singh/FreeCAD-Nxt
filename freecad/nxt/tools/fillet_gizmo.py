"""The Nxt fillet's handles and preview in the 3D view.

Two of FreeCAD's own arrow handles (SoLinearDraggerContainer, the nodes
Part Design's fillet uses) sit at the middle of the first edge, one along
each face; dragging either sets the radius. Like Part Design they point
along the faces, so a handle's length is the contact distance, the radius
times 1/tan(half the angle between them). The preview is Part Design's
own (see blend_fillet.generated_faces).
"""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import Any

import FreeCAD as App
import Part

from . import blend_fillet

HANDLE = "SoLinearDraggerContainer"
GIZMOS = "User parameter:BaseApp/Preferences/Gui/Gizmos"
#: Qt modifier values FreeCAD's FineSnapModifier may hold.
SHIFT = 0x02000000
CTRL = 0x04000000
HANDLE_COLOUR = (0.95, 0.55, 0.1)
#: Handle size on screen, as Part Design's gizmos use.
SCREEN_SCALE = 0.015


def snapped(value: float, fine: float) -> float:
    """`value` on the coarse grid, unless Part Design's drags are fine now.

    The same rule as FreeCAD's gizmos: coarse by default unless its
    preference says fine first, the fine-snap key flipping either, and
    coarse steps CoarseLinearSnapMultiplier fine ones.
    """
    from ..core.qt import QtWidgets
    params = App.ParamGet(GIZMOS)
    if not params.GetBool("EnableCoarseSnap", True) or fine <= 0:
        return value
    key = params.GetInt("FineSnapModifier", SHIFT)
    if key != CTRL:
        key = SHIFT
    held: Any = QtWidgets.QApplication.queryKeyboardModifiers()
    pressed = int(getattr(held, "value", held)) == key
    coarse_first = params.GetInt("DefaultCoarseDragBehavior", 0) == 0
    if coarse_first == pressed:
        return value
    step = fine * max(1, params.GetInt("CoarseLinearSnapMultiplier", 5))
    return round(value / step) * step


def _rotation_from_y(direction: App.Vector) -> str:
    """Axis and angle turning +Y onto `direction`, as a field string."""
    y = App.Vector(0, 1, 0)
    d = App.Vector(direction)
    d.normalize()
    axis = y.cross(d)
    if axis.Length < 1e-9:
        return "1 0 0 %r" % (0.0 if d.y > 0 else math.pi)
    axis.normalize()
    angle = math.acos(max(-1.0, min(1.0, y.dot(d))))
    return "%r %r %r %r" % (axis.x, axis.y, axis.z, angle)


def into_face(face: Any, edge: Any, at: float) -> App.Vector:
    """The direction from the edge across `face`, at parameter `at`."""
    point = edge.valueAt(at)
    tangent = edge.tangentAt(at)
    tangent.normalize()
    u, v = face.Surface.parameter(point)
    normal = face.normalAt(u, v)
    across = normal.cross(tangent)
    across.normalize()
    step = max(edge.Length * 1e-3, 1e-4)
    ahead = face.distToShape(Part.Vertex(point + across * step))[0]
    behind = face.distToShape(Part.Vertex(point - across * step))[0]
    return across if ahead <= behind else -across


def set_frame(transform: Any, placement: Any) -> None:
    base = placement.Base
    axis = placement.Rotation.Axis
    transform.translation.setValue(base.x, base.y, base.z)
    transform.rotation.setValue(
        _coin_rotation(axis, placement.Rotation.Angle))


def _coin_rotation(axis: App.Vector, angle: float) -> Any:
    from pivy import coin
    return coin.SbRotation(coin.SbVec3f(axis.x, axis.y, axis.z), angle)


class Handles:
    """Two radius arrows on the first edge; `moved(radius)` on drag."""

    def __init__(self, view: Any, moved: Callable[[float], None],
                 viewed: Callable[[], None] | None = None,
                 flat: bool = False) -> None:
        from pivy import coin
        self._view = view
        #: A chamfer's size is the distance along each face itself.
        self._flat = flat
        self._moved = moved
        #: Called when the camera moves, to follow with anything placed.
        self._viewed = viewed
        self._dirs: list[App.Vector] = []
        self._local = App.Vector()
        self._root = coin.SoAnnotation()
        self._frame = coin.SoTransform()
        self._root.addChild(self._frame)
        self._kits: list[Any] = []
        self._sensors: list[Any] = []
        self._callbacks: list[Any] = []
        self._correction = 1.0
        self._set_length = -1.0
        self._placement = App.Placement()
        self._quiet = False
        self._place: App.Vector | None = None
        kind = coin.SoType.fromName(HANDLE)
        if kind.isBad():
            return
        for _ in range(2):
            kit = coin.cast(kind.createInstance(), "SoInteractionKit")
            kit.color.setValue(*HANDLE_COLOUR)
            kit.visible.setValue(False)
            self._root.addChild(kit)
            self._kits.append(kit)
            dragger = self._dragger(kit)
            dragger.labelVisible.setValue(False)
            callback = self._make_callback(dragger)
            sensor = coin.SoFieldSensor(callback, None)
            sensor.attach(dragger.translation)
            self._callbacks.append(callback)
            self._sensors.append(sensor)
        self._on_camera = self._rescale
        self._camera_sensor = coin.SoNodeSensor(self._on_camera, None)
        camera = view.getCameraNode()
        if camera is not None:
            self._camera_sensor.attach(camera)
        view.getSceneGraph().addChild(self._root)

    @staticmethod
    def _dragger(kit: Any) -> Any:
        from pivy import coin
        return coin.cast(kit.getPart("dragger", True), "SoDragger")

    def _make_callback(self, dragger: Any) -> Callable[[Any, Any], None]:
        def changed(_data: Any, _sensor: Any) -> None:
            # Field sensors fire later, after set_radius has returned, so
            # an echo of our own placing is told apart by its length.
            length = dragger.translation.getValue()[1]
            # The field is single precision: compare to its resolution.
            if self._quiet or abs(length - self._set_length) \
                    <= 1e-5 * max(1.0, abs(length)):
                return
            if length > 0:
                step = dragger.translationIncrement.getValue()
                radius = snapped(length / self._correction,
                                 step / self._correction)
                if radius <= 0:
                    return
                # The arrows show the snapped value, as FreeCAD's do.
                self.set_radius(radius)
                self._moved(radius)
        return changed

    def place(self, shape: Any, edge_name: str | None,
              radius: float) -> None:
        """At the middle of `edge_name` of `shape`, sized to `radius`."""
        if not self._kits:
            return
        if edge_name is None:
            for kit in self._kits:
                kit.visible.setValue(False)
            return
        try:
            edge = shape.getElement(edge_name)
            faces = blend_fillet._faces_of(shape, edge)
            if len(faces) != 2:
                raise ValueError
            middle = (edge.FirstParameter + edge.LastParameter) / 2
            dirs = [into_face(f, edge, middle) for f in faces]
        except Exception:  # noqa: BLE001 - no handles for odd edges
            for kit in self._kits:
                kit.visible.setValue(False)
            return
        angle = dirs[0].getAngle(dirs[1])
        self._correction = (1 / math.tan(angle / 2)
                            if angle > 1e-6 and not self._flat else 1.0)
        point = edge.valueAt(middle)
        self._local = point
        self._dirs = dirs
        self._place = self._placement.multVec(point)
        for kit, direction in zip(self._kits, dirs):
            kit.translation.setValue(point.x, point.y, point.z)
            kit.rotation.set(_rotation_from_y(direction))
            kit.visible.setValue(True)
        self.set_radius(radius)
        self._rescale()

    def set_radius(self, radius: float) -> None:
        """Move the arrows' tips to `radius` without reporting a drag."""
        length = radius * self._correction
        self._set_length = length
        self._quiet = True
        try:
            for kit in self._kits:
                dragger = self._dragger(kit)
                if abs(dragger.translation.getValue()[1] - length) \
                        > 1e-5 * max(1.0, length):
                    dragger.translation.setValue(0, length, 0)
        finally:
            self._quiet = False

    def tip(self) -> App.Vector | None:
        """Where the first arrow's tip is, in the document's frame."""
        if self._place is None or not self._dirs:
            return None
        local = self._local + self._dirs[0] * self._set_length
        return self._placement.multVec(local)

    def _rescale(self, *_args: Any) -> None:
        if self._viewed is not None:
            self._viewed()
        if self._place is None:
            return
        from pivy import coin
        camera = self._view.getCameraNode()
        if camera is None:
            return
        # As GizmoContainer does: the camera's own aspect, not the
        # viewport's, which would widen the volume and the arrows.
        volume = camera.getViewVolume(0.0)
        p = self._place
        scale = volume.getWorldToScreenScale(coin.SbVec3f(p.x, p.y, p.z),
                                             SCREEN_SCALE)
        for kit in self._kits:
            dragger = self._dragger(kit)
            dragger.geometryScale.setValue(scale, scale, scale)
            step = 10 ** math.floor(math.log10(scale)) if scale > 0 else 0.1
            dragger.translationIncrement.setValue(step * self._correction)

    def set_frame(self, placement: Any) -> None:
        """The Body's placement, which the base's shape sits in."""
        self._placement = placement
        set_frame(self._frame, placement)

    def remove(self) -> None:
        for sensor in self._sensors:
            sensor.detach()
        self._camera_sensor.detach()
        graph = self._view.getSceneGraph()
        if graph.findChild(self._root) >= 0:
            graph.removeChild(self._root)
