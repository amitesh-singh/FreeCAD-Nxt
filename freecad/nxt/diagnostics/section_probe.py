"""Stencil-capped section view, as a test in FreeCAD's Python console.

    from freecad.nxt.diagnostics import section_probe as sp
    sp.start()                  # cut across X through the model's middle
    sp.move(5)                  # slide the plane 5 mm along its normal
    sp.start((0, 0, 1))         # a different normal
    sp.stop()

    sp.start(mode="clip")       # the clip plane only, no cap
    sp.start(mode="nostencil")  # the cap drawn without the stencil test
    sp.report()                 # how often each GL step ran

The model is clipped by a Coin clip plane; the hollow left behind is
filled where the plane passes through solid material, found by counting
surfaces per pixel in the stencil buffer, and hatched with a texture.
Only GL render passes touch GL; picking and bounding boxes skip it.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import math
from typing import Any

import FreeCAD as App
import FreeCADGui as Gui

GL_DEPTH_TEST = 0x0B71
GL_STENCIL_TEST = 0x0B90
GL_CULL_FACE = 0x0B44
GL_STENCIL_BUFFER_BIT = 0x0400
GL_STENCIL_BITS = 0x0D57
GL_ALWAYS = 0x0207
GL_NOTEQUAL = 0x0205
GL_KEEP = 0x1E00
GL_INVERT = 0x150A
GL_CLIP_PLANE0 = 0x3000
GL_POLYGON_OFFSET_FILL = 0x8037

#: Hatch period on the cap, in model units.
HATCH_PERIOD = 2.0
TEXTURE_SIZE = 32

_state: dict[str, Any] = {}


def _say(text: str) -> None:
    App.Console.PrintMessage("section probe: %s\n" % text)


def _gl() -> Any:
    for name in ("libOpenGL.so.0", "libGL.so.1",
                 ctypes.util.find_library("GL") or ""):
        if not name:
            continue
        try:
            return ctypes.CDLL(name)
        except OSError:
            continue
    raise OSError("no OpenGL library found")


def _is_render(action: Any) -> bool:
    from pivy import coin
    return bool(action.isOfType(coin.SoGLRenderAction.getClassTypeId()))


def _tick(name: str) -> None:
    calls = _state.setdefault("calls", {})
    calls[name] = calls.get(name, 0) + 1


def report() -> None:
    """How many times each GL step ran since start(); a frame runs all."""
    _say("calls: %s" % (_state.get("calls") or "none"))


def _stencil_on(_data: Any, action: Any) -> None:
    """Before the second model pass: count its surfaces per pixel."""
    if not _is_render(action):
        return
    _tick("count")
    gl = _state["gl"]
    if "bits" not in _state:
        bits = ctypes.c_int(-1)
        gl.glGetIntegerv(GL_STENCIL_BITS, ctypes.byref(bits))
        _state["bits"] = bits.value
        _say("stencil bits in this view: %d%s" % (
            bits.value, "" if bits.value > 0
            else " - no stencil buffer, the cap cannot be drawn"))
    gl.glClearStencil(0)
    gl.glClear(GL_STENCIL_BUFFER_BIT)
    gl.glEnable(GL_STENCIL_TEST)
    gl.glStencilFunc(GL_ALWAYS, 0, 0xFF)
    gl.glStencilOp(GL_KEEP, GL_KEEP, GL_INVERT)
    gl.glColorMask(0, 0, 0, 0)
    gl.glDepthMask(0)
    gl.glDisable(GL_DEPTH_TEST)
    gl.glDisable(GL_CULL_FACE)


def _cap_on(_data: Any, action: Any) -> None:
    """Before the cap: draw it only where an odd count was left."""
    if not _is_render(action):
        return
    _tick("cap")
    gl = _state["gl"]
    gl.glColorMask(1, 1, 1, 1)
    gl.glDepthMask(1)
    gl.glEnable(GL_DEPTH_TEST)
    gl.glEnable(GL_STENCIL_TEST)
    if _state.get("mode") == "nostencil":
        gl.glDisable(GL_STENCIL_TEST)
    gl.glStencilFunc(GL_NOTEQUAL, 0, 0x01)
    gl.glStencilOp(GL_KEEP, GL_KEEP, GL_KEEP)
    for i in range(6):
        gl.glDisable(GL_CLIP_PLANE0 + i)     # the cap lies on the plane
    gl.glEnable(GL_POLYGON_OFFSET_FILL)
    gl.glPolygonOffset(ctypes.c_float(-1.0), ctypes.c_float(-1.0))


def _cap_off(_data: Any, action: Any) -> None:
    if not _is_render(action):
        return
    _tick("done")
    gl = _state["gl"]
    gl.glDisable(GL_POLYGON_OFFSET_FILL)
    gl.glDisable(GL_STENCIL_TEST)


def _hatch_image() -> bytes:
    """A light fill with one dark diagonal, tiling seamlessly."""
    size = TEXTURE_SIZE
    width = size / 8
    out = bytearray()
    for y in range(size):
        for x in range(size):
            d = (x - y) % size
            d = min(d, size - d)
            ink = max(0.0, min(1.0, width - d + 0.5))
            light, dark = 205, 70
            v = int(light + (dark - light) * ink)
            out += bytes((v, v, v))
    return bytes(out)


def _axes(normal: App.Vector) -> tuple[App.Vector, App.Vector]:
    helper = App.Vector(0, 0, 1)
    if abs(normal.dot(helper)) > 0.9:
        helper = App.Vector(1, 0, 0)
    u = normal.cross(helper)
    u.normalize()
    v = normal.cross(u)
    v.normalize()
    return u, v


def _solids(doc: Any) -> list[Any]:
    out = []
    for obj in doc.Objects:
        shape = getattr(obj, "Shape", None)
        view = getattr(obj, "ViewObject", None)
        if (shape is None or view is None or not view.Visibility
                or not shape.Solids):
            continue
        out.append(obj)
    # A Body draws its tip itself; counting both cancels the cap out.
    return [o for o in out if _container(o) not in out]


def _mesh(shape: Any) -> Any:
    """The shape's faces as triangles, for counting only."""
    from pivy import coin
    points, triangles = shape.tessellate(0.05)
    node = coin.SoSeparator()
    coords = coin.SoCoordinate3()
    coords.point.setValues(0, len(points), [tuple(p) for p in points])
    node.addChild(coords)
    faces = coin.SoIndexedFaceSet()
    index: list[int] = []
    for a, b, c in triangles:
        index += [a, b, c, -1]
    faces.coordIndex.setValues(0, len(index), index)
    node.addChild(faces)
    return node


def _container(obj: Any) -> Any:
    try:
        return obj.getParentGeoFeatureGroup()
    except Exception:
        return None


def start(normal: tuple[float, float, float] = (1, 0, 0),
          offset: float | None = None, mode: str = "cap") -> None:
    """Cut the active view's visible solids; offset from the middle.

    mode: "cap" (normal), "clip" (no cap), "nostencil" (cap everywhere).
    """
    from pivy import coin
    stop()
    doc = App.ActiveDocument
    view: Any = (Gui.ActiveDocument.ActiveView if Gui.ActiveDocument
                 else None)
    if doc is None or view is None:
        _say("no active 3D view")
        return
    try:
        _state["gl"] = _gl()
    except OSError as exc:
        _say(str(exc))
        return
    solids = _solids(doc)
    if not solids:
        _say("nothing visible with a solid to cut")
        return
    box = solids[0].Shape.BoundBox
    for obj in solids[1:]:
        box.add(obj.Shape.BoundBox)
    n = App.Vector(*normal)
    n.normalize()
    centre = box.Center
    _say("objects: %s" % ", ".join(o.Name for o in solids))
    _state.update(view=view, normal=n, centre=centre, mode=mode,
                  span=max(box.DiagonalLength, 1.0))

    clip = coin.SoClipPlane()
    root = view.getSceneGraph()
    root.insertChild(clip, 0)

    # Drawn after everything else, edge lines included, so they cannot
    # show through it; the callbacks turn the depth test back on.
    cap = coin.SoAnnotation()
    cap.renderCaching = coin.SoSeparator.OFF
    unpickable = coin.SoPickStyle()
    unpickable.style = coin.SoPickStyle.UNPICKABLE
    cap.addChild(unpickable)

    # Never culled: Coin skips a separator whose box lies wholly on the
    # clipped side, which would skip the stencil set-up and leave the
    # cap drawn everywhere.
    cap.renderCulling = coin.SoSeparator.OFF
    count = coin.SoSeparator()
    count.renderCaching = coin.SoSeparator.OFF
    count.renderCulling = coin.SoSeparator.OFF
    begin = coin.SoCallback()
    begin.setCallback(_stencil_on)
    count.addChild(begin)
    # Faces only: the view's edge lines would flip the count along
    # every edge and punch holes in the cap.
    for obj in solids:
        count.addChild(_mesh(obj.Shape))
    cap.addChild(count)

    face = coin.SoSeparator()
    on = coin.SoCallback()
    on.setCallback(_cap_on)
    face.addChild(on)
    light = coin.SoLightModel()
    light.model = coin.SoLightModel.BASE_COLOR
    face.addChild(light)
    colour = coin.SoBaseColor()
    colour.rgb = (1, 1, 1)
    face.addChild(colour)
    texture = coin.SoTexture2()
    texture.image.setValue(coin.SbVec2s(TEXTURE_SIZE, TEXTURE_SIZE), 3,
                           _hatch_image())
    texture.wrapS = coin.SoTexture2.REPEAT
    texture.wrapT = coin.SoTexture2.REPEAT
    texture.model = coin.SoTexture2.MODULATE
    face.addChild(texture)
    coords = coin.SoTextureCoordinatePlane()
    face.addChild(coords)
    points = coin.SoCoordinate3()
    face.addChild(points)
    quad = coin.SoFaceSet()
    quad.numVertices = 4
    face.addChild(quad)
    off = coin.SoCallback()
    off.setCallback(_cap_off)
    face.addChild(off)
    cap.addChild(face)
    if mode != "clip":
        root.addChild(cap)

    _state.update(root=root, clip=clip, cap=cap, coords=coords,
                  points=points, offset=0.0)
    move(0.0 if offset is None else offset)
    _say("cutting %d object(s); sp.move(mm) slides, sp.stop() ends"
         % len(solids))


def move(offset: float) -> None:
    """Put the plane `offset` from the model's middle, along its normal."""
    from pivy import coin
    if "clip" not in _state:
        _say("not running; call start() first")
        return
    n, centre = _state["normal"], _state["centre"]
    origin = centre + n * offset
    _state["offset"] = offset
    # The clip plane keeps the side its normal points to.
    _state["clip"].plane = coin.SbPlane(coin.SbVec3f(n.x, n.y, n.z),
                                        coin.SbVec3f(*origin))
    u, v = _axes(n)
    half = _state["span"]
    corners = [origin + u * su * half + v * sv * half
               for su, sv in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
    _state["points"].point.setValues(0, 4, [tuple(c) for c in corners])
    scale = 1.0 / HATCH_PERIOD
    _state["coords"].directionS = coin.SbVec3f(*(u * scale))
    _state["coords"].directionT = coin.SbVec3f(*(v * scale))


def stop() -> None:
    """Remove the cut and the cap."""
    root = _state.get("root")
    if root is not None:
        for key in ("clip", "cap"):
            node = _state.get(key)
            if node is not None and root.findChild(node) >= 0:
                root.removeChild(node)
    _state.clear()


def sweep(start_mm: float = -20.0, end_mm: float = 20.0,
          steps: int = 80) -> None:
    """Slide the plane across, to judge the frame rate while it moves."""
    from ..core.qt import QtCore
    if "clip" not in _state:
        _say("not running; call start() first")
        return
    positions = [start_mm + (end_mm - start_mm) * i / max(steps, 1)
                 for i in range(steps + 1)]
    timer = QtCore.QTimer()
    _state["sweep"] = timer

    def step() -> None:
        if not positions or "clip" not in _state:
            timer.stop()
            return
        move(positions.pop(0))

    timer.timeout.connect(step)
    timer.start(int(math.ceil(1000 / 60)))
