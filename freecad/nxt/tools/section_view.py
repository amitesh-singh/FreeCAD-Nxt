"""Section view: a clip plane through the model, its cut faces hatched.

The model is clipped by a Coin clip plane. The cut is capped on the GPU:
the visible solids' faces are drawn again into the stencil buffer only,
inverting a bit per pixel at every surface, so an odd count marks where
the plane passes through material; a lit quad on the plane is drawn
only there, then a stipple hatch over it. Only GL render passes touch GL.

The cap's look follows FreeCAD PR #33186 (SoFCSectionCap): the part's
colour, lit, stipple lines every 8 px, and a pattern per part so
neighbours read apart. Nxt keeps the cap lighter and its lines 2 px.
"""

from __future__ import annotations

import ctypes
import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import FreeCAD as App
import FreeCADGui as Gui

from ..core import log, opengl
from ..core.qt import QtCore, QtWidgets
from . import section_aim

GL_DEPTH_TEST = 0x0B71
GL_STENCIL_TEST = 0x0B90
GL_CULL_FACE = 0x0B44
GL_STENCIL_BUFFER_BIT = 0x0400
GL_ALWAYS = 0x0207
GL_NOTEQUAL = 0x0205
GL_KEEP = 0x1E00
GL_INVERT = 0x150A
GL_CLIP_PLANE0 = 0x3000
GL_LESS = 0x0201
GL_LEQUAL = 0x0203
GL_POLYGON_STIPPLE = 0x0B42
GL_COLOR_MATERIAL = 0x0B57
GL_FRONT_AND_BACK = 0x0408
GL_AMBIENT_AND_DIFFUSE = 0x1602
GL_LIGHTING = 0x0B50
GL_TEXTURE_2D = 0x0DE1
GL_POLYGON = 0x0009
GL_LINES = 0x0001
GL_LINE_WIDTH = 0x0B21
GL_MAX_CLIP_PLANES = 0x0D32
GL_ALPHA_TEST = 0x0BC0
GL_GREATER = 0x0204
GL_RGBA = 0x1908
GL_UNSIGNED_BYTE = 0x1401
GL_TEXTURE_WRAP_S = 0x2802
GL_TEXTURE_WRAP_T = 0x2803
GL_TEXTURE_MIN_FILTER = 0x2801
GL_TEXTURE_MAG_FILTER = 0x2800
GL_REPEAT = 0x2901
GL_NEAREST = 0x2600
GL_TEXTURE_ENV = 0x2300
GL_TEXTURE_ENV_MODE = 0x2200
GL_MODULATE = 0x2100

#: The cap is its part's colour at this share, lit like a face.
CAP_SHADE = 0.8
#: The hatch lines are the cap darkened to this share, lit like it.
INK_SHARE = 0.8
#: How much colour the cap loses toward grey, 0-1.
CAP_DESATURATE = 0.3
#: Hatch line spacing and width on screen, in pixels.
HATCH_STEP = 8
HATCH_WIDTH = 2
DEFAULT_BODY = (0.8, 0.8, 0.8)
#: Tessellation tolerance of the stencil mesh; it is never seen.
MESH_TOLERANCE = 0.05
#: The arrow's length as a share of the model's diagonal.
HANDLE_SCALE = 0.08
#: Frame margin around the model, as a share of its diagonal.
FRAME_MARGIN = 0.06
#: How near the pointer must be to the frame to grab it, in pixels.
FRAME_REACH = 8.0
FRAME_COLOUR = (0.24, 0.68, 0.91)
FRAME_HOVER = (0.98, 0.72, 0.22)
FRAME_WIDTH = 2.0
#: The fill inside the frame, in FreeCAD's selection colour.
FILL_TRANSPARENCY = 0.88
VIEW_PARAMS = "User parameter:BaseApp/Preferences/View"
SELECTION_DEFAULT = 0x1CAD1CFF
#: The tilt arcs: radius as a share of the diagonal, sweep, and points.
ARC_SCALE = 0.07
ARC_SWEEP = 50.0
ARC_STEPS = 9
#: Tilt snapping, in degrees: a plain drag, with Ctrl; Shift drags free.
TILT_STEP = 5.0
TILT_STEP_COARSE = 15.0
#: Within this many degrees of X, Y or Z, a tilted plane squares up.
SQUARE_SNAP = 3.0

#: Below this share of the in-plane scale the normal is too foreshortened
#: on screen to follow; the drag then goes by height instead.
HEAD_ON = 0.25

#: How long the plane must rest before the exact cut is made.
SETTLE_MS = 300
#: The clip sits this share of the diagonal behind the plane, so the
#: exact cut lying on the plane is not clipped away with the rest.
CLIP_SLACK = 1e-5
CUT_NAME = "SectionCut"
CUT_LINE = (0.1, 0.1, 0.1)
CUT_LINE_WIDTH = 1.0
#: The line where one section's cap meets another's, in screen pixels.
SEAM_WIDTH = 2.0
#: How near a trimmed corner must be to a plane to lie on it, as a share
#: of the model's diagonal.
SEAM_TOLERANCE = 1e-6

Point = tuple[float, float]
Vec3 = tuple[float, float, float]
#: A half-space kept by a section: n·p >= d.
Plane = tuple[Vec3, float]


def clip_polygon(points: list[Vec3], planes: list[Plane]) -> list[Vec3]:
    """`points`, a convex polygon, less what any plane cuts away."""
    for (nx, ny, nz), d in planes:
        out: list[Vec3] = []
        for i, a in enumerate(points):
            b = points[(i + 1) % len(points)]
            da = nx * a[0] + ny * a[1] + nz * a[2] - d
            db = nx * b[0] + ny * b[1] + nz * b[2] - d
            if da >= 0:
                out.append(a)
            if (da >= 0) != (db >= 0):
                t = da / (da - db)
                out.append((a[0] + (b[0] - a[0]) * t,
                            a[1] + (b[1] - a[1]) * t,
                            a[2] + (b[2] - a[2]) * t))
        points = out
    return points if len(points) >= 3 else []


def seams(points: list[Vec3], planes: list[Plane],
          tolerance: float) -> list[tuple[Vec3, Vec3]]:
    """The edges of a trimmed polygon that lie on one of `planes`.

    Those are where another section cut it: where two caps meet.
    """
    def on(p: Vec3, plane: Plane) -> bool:
        (nx, ny, nz), d = plane
        return abs(nx * p[0] + ny * p[1] + nz * p[2] - d) <= tolerance

    out = []
    for i, a in enumerate(points):
        b = points[(i + 1) % len(points)]
        if any(on(a, plane) and on(b, plane) for plane in planes):
            out.append((a, b))
    return out


def cut_faces(shapes: list[Any], normal: Any,
              distance: float) -> list[list[Any]]:
    """The faces a plane cuts through each solid, in order.

    `distance` is the plane's along its normal from the origin. Holes
    come out as holes; a shape the plane misses gives no faces.
    """
    import Part
    out: list[list[Any]] = []
    for shape in shapes:
        faces: list[Any] = []
        try:
            wires = shape.slice(normal, distance)
            if wires:
                made = Part.makeFace(wires, "Part::FaceMakerBullseye")
                faces = list(made.Faces)
        except Exception as exc:
            log.error("section: could not cut a shape: %s" % exc)
        out.append(faces)
    return out


def stipple(lit: Any) -> bytes:
    """A 32x32 GL polygon stipple, rows from the bottom: `lit(x, y)`."""
    bits = bytearray(128)
    for y in range(32):
        for x in range(32):
            if lit(x, y):
                bits[y * 4 + x // 8] |= 0x80 >> (x % 8)
    return bytes(bits)


def _on_step(a: int) -> bool:
    return a % HATCH_STEP < HATCH_WIDTH


def _dot(x: int, y: int) -> bool:
    return (x - 4) % HATCH_STEP < 2 and (y - 4) % HATCH_STEP < 2


#: Hatches handed out by part, as drafting does to tell neighbours apart.
PATTERNS: dict[str, bytes] = {
    "diag45": stipple(lambda x, y: _on_step(x - y)),
    "diag135": stipple(lambda x, y: _on_step(x + y)),
    "horizontal": stipple(lambda x, y: _on_step(y)),
    "vertical": stipple(lambda x, y: _on_step(x)),
    "diagcross": stipple(lambda x, y: _on_step(x - y) or _on_step(x + y)),
    "dots": stipple(_dot),
}


def pattern_rgba(pattern: bytes) -> bytes:
    """A stipple as a 32x32 RGBA tile: white lines, clear between."""
    out = bytearray()
    for y in range(32):
        for x in range(32):
            on = pattern[y * 4 + x // 8] & (0x80 >> (x % 8))
            out += b"\xff\xff\xff\xff" if on else b"\x00\x00\x00\x00"
    return bytes(out)


def snapped_tile(world_per_pixel: float) -> float:
    """The hatch tile's size on the plane, for this zoom.

    About 32 px on screen, snapped to a power of two in model units, so
    the lines stay on the part as it turns and only step as the zoom
    doubles or halves.
    """
    target = 32 * world_per_pixel
    if target <= 0:
        return 1.0
    return float(2.0 ** round(math.log2(target)))


#: GL texture names per (3D view, pattern), made on first use; a view
#: draws in one GL context. (Coin's cache context is not reachable from
#: pivy: callbacks get a plain SoAction.)
_textures: dict[tuple[int, str], int] = {}


def _texture(g: Any, context: int, name: str) -> int:
    key = (context, name)
    if key not in _textures:
        tex = ctypes.c_uint(0)
        g.glGenTextures(1, ctypes.byref(tex))
        g.glBindTexture(GL_TEXTURE_2D, tex)
        for param, value in ((GL_TEXTURE_WRAP_S, GL_REPEAT),
                             (GL_TEXTURE_WRAP_T, GL_REPEAT),
                             (GL_TEXTURE_MIN_FILTER, GL_NEAREST),
                             (GL_TEXTURE_MAG_FILTER, GL_NEAREST)):
            g.glTexParameteri(GL_TEXTURE_2D, param, value)
        data = pattern_rgba(PATTERNS[name])
        g.glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, 32, 32, 0, GL_RGBA,
                       GL_UNSIGNED_BYTE, data)
        _textures[key] = tex.value
    return _textures[key]


def pattern_for(name: str) -> str:
    """The hatch a part always gets, from its name (FNV-1a)."""
    h = 14695981039346656037
    for byte in name.encode("utf-8"):
        h = ((h ^ byte) * 1099511628211) & 0xFFFFFFFFFFFFFFFF
    names = list(PATTERNS)
    return names[h % len(names)]


def snap_angle(degrees: float, step: float) -> float:
    """An angle to the nearest step; a step of 0 leaves it free."""
    return round(degrees / step) * step if step > 0 else degrees


def polyline_distance(p: Point, points: list[Point]) -> float:
    """Distance from p to a polyline, on screen."""
    return min((segment_distance(p, a, b)
                for a, b in zip(points, points[1:])), default=float("inf"))


def top_left(points: list[Point], avoid: int = -1) -> int:
    """Which point shows nearest the screen's top left, passing `avoid`.

    Points are in Coin's pixels (y up). The frame's buttons go there, so
    they stay put on screen however the plane is turned.
    """
    order = sorted(range(len(points)),
                   key=lambda i: points[i][0] - points[i][1])
    return next(i for i in order if i != avoid)


def segment_distance(p: Point, a: Point, b: Point) -> float:
    """Distance from p to the segment ab, on screen."""
    ax, ay = b[0] - a[0], b[1] - a[1]
    length = ax * ax + ay * ay
    t = 0.0 if length == 0 else max(0.0, min(1.0, (
        (p[0] - a[0]) * ax + (p[1] - a[1]) * ay) / length))
    dx, dy = a[0] + ax * t - p[0], a[1] + ay * t - p[1]
    return float((dx * dx + dy * dy) ** 0.5)


def drag_amount(start: Point, now: Point, normal_px: Point,
                plane_px: float, away: bool) -> float:
    """How far a drag from `start` to `now` moves the plane.

    `normal_px` is one model unit along the normal on screen, `plane_px`
    one unit in the plane. A normal seen nearly end-on is followed by
    height instead: up brings the plane toward the camera.
    """
    dx, dy = now[0] - start[0], now[1] - start[1]
    nx, ny = normal_px
    along = nx * nx + ny * ny
    if plane_px <= 0:
        return 0.0
    if along ** 0.5 < HEAD_ON * plane_px:
        return (-dy if away else dy) / plane_px
    return (dx * nx + dy * ny) / along


_gl: Any = None


def gl() -> Any:
    """The process's OpenGL entry points, loaded once."""
    global _gl
    if _gl is None:
        _gl = opengl.library()
    return _gl


def desaturate(rgb: tuple[float, float, float], amount: float
               ) -> tuple[float, float, float]:
    """A colour taken `amount` of the way toward its own grey."""
    grey = 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]
    return (rgb[0] + (grey - rgb[0]) * amount,
            rgb[1] + (grey - rgb[1]) * amount,
            rgb[2] + (grey - rgb[2]) * amount)


def shade(rgb: tuple[float, float, float], share: float
          ) -> tuple[float, float, float]:
    """A colour taken toward black, keeping `share` of it."""
    return (rgb[0] * share, rgb[1] * share, rgb[2] * share)


def body_colour(obj: Any) -> tuple[float, float, float]:
    """The colour an object is drawn in, as 0-1 RGB."""
    view: Any = getattr(obj, "ViewObject", None)
    try:
        colour = view.ShapeAppearance[0].DiffuseColor
    except Exception:
        colour = getattr(view, "ShapeColor", None) or DEFAULT_BODY
    return (float(colour[0]), float(colour[1]), float(colour[2]))


def plane_axes(normal: App.Vector) -> tuple[App.Vector, App.Vector]:
    """Two unit vectors spanning the plane with this normal."""
    helper = App.Vector(0, 0, 1)
    if abs(normal.dot(helper)) > 0.9:
        helper = App.Vector(1, 0, 0)
    u = normal.cross(helper)
    u.normalize()
    v = normal.cross(u)
    v.normalize()
    return u, v


def facing_axis(view_direction: App.Vector) -> App.Vector:
    """The principal axis nearest the view direction, pointing away.

    The clip keeps the side the normal points to: the far half stays and
    the cut faces the camera.
    """
    components = (view_direction.x, view_direction.y, view_direction.z)
    index = max(range(3), key=lambda i: abs(components[i]))
    axis = [0.0, 0.0, 0.0]
    axis[index] = 1.0 if components[index] >= 0 else -1.0
    return App.Vector(*axis)


@dataclass(frozen=True)
class Instance:
    """One solid as the view draws it: in place, in its own colour."""

    name: str
    shape: Any
    colour: tuple[float, float, float]


#: Containers whose children are cut one by one, never as one compound.
GROUP_TYPES = ("App::Part", "App::DocumentObjectGroup")
#: How deep containers and links are followed.
MAX_DEPTH = 16


def _container(obj: Any) -> Any:
    try:
        return obj.getParentGeoFeatureGroup()
    except Exception:
        return None


def _parent_group(obj: Any) -> Any:
    try:
        return obj.getParentGroup()
    except Exception:
        return None


def _shown(obj: Any) -> bool:
    view = getattr(obj, "ViewObject", None)
    if view is not None:
        return bool(view.Visibility)
    return bool(getattr(obj, "Visibility", True))


def _is_group(obj: Any) -> bool:
    try:
        return any(obj.isDerivedFrom(t) for t in GROUP_TYPES)
    except Exception:
        return False


def _linked(obj: Any) -> Any:
    try:
        return obj.getLinkedObject(True) or obj
    except Exception:
        return obj


def _own_colour(obj: Any, target: Any) -> bool:
    """Whether to paint with this object's colour, not its target's.

    A link draws its target's colours unless told to override them;
    its own colour property is only a default.
    """
    if target is not obj:
        view = getattr(obj, "ViewObject", None)
        return bool(getattr(view, "OverrideMaterial", False))
    return True


def cut_instances(doc: Any, shape_of: Callable[[Any], Any] | None = None
                  ) -> list[Instance]:
    """Every visible solid, each once, placed where the view draws it.

    Parts, assemblies and groups are opened up so each body keeps its
    own colour, and links are followed to what they show. A Body is one
    solid (it draws its tip; counting both would cancel the cap out).
    """
    if shape_of is None:
        import Part
        shape_of = Part.getShape
    out: list[Instance] = []
    for obj in doc.Objects:
        if _container(obj) is None and _parent_group(obj) is None:
            _walk(obj, App.Placement(), out, shape_of, 0)
    return out


def _walk(obj: Any, parent: Any, out: list[Instance],
          shape_of: Callable[[Any], Any], depth: int) -> None:
    if depth > MAX_DEPTH or not _shown(obj):
        return
    target = _linked(obj)
    if _is_group(target):
        here = parent.multiply(getattr(obj, "Placement", App.Placement()))
        for child in getattr(target, "Group", None) or ():
            _walk(child, here, out, shape_of, depth + 1)
        return
    try:
        shape = shape_of(obj)
    except Exception:
        return
    if shape is None or shape.isNull() or not shape.Solids:
        return
    shape = shape.copy()
    shape.Placement = parent.multiply(shape.Placement)
    painted = obj if _own_colour(obj, target) else target
    out.append(Instance(obj.Name, shape, body_colour(painted)))


def _is_render(action: Any) -> bool:
    from pivy import coin
    return bool(action.isOfType(coin.SoGLRenderAction.getClassTypeId()))


def _count_begin(_data: Any, action: Any) -> None:
    """Before the faces are drawn again: invert a stencil bit per surface."""
    if not _is_render(action):
        return
    g = gl()
    g.glClearStencil(0)
    g.glClear(GL_STENCIL_BUFFER_BIT)
    g.glEnable(GL_STENCIL_TEST)
    g.glStencilFunc(GL_ALWAYS, 0, 0xFF)
    g.glStencilOp(GL_KEEP, GL_KEEP, GL_INVERT)
    g.glColorMask(0, 0, 0, 0)
    g.glDepthMask(0)
    g.glDisable(GL_DEPTH_TEST)
    g.glDisable(GL_CULL_FACE)


#: GL clip planes switched off for counting and capping, to restore.
_unclipped: list[int] = []
_plane_count: list[int] = []


def _unclip_all(g: Any) -> None:
    """Switch off every GL clip plane, whichever index Coin gave it.

    The count adds its own plane back through Coin; the cap is trimmed
    by the other sections on the CPU (Section.cap_polygon).
    """
    if not _plane_count:
        most = ctypes.c_int(0)
        g.glGetIntegerv(GL_MAX_CLIP_PLANES, ctypes.byref(most))
        _plane_count.append(most.value or 6)
    for plane in range(GL_CLIP_PLANE0, GL_CLIP_PLANE0 + _plane_count[0]):
        if g.glIsEnabled(plane):
            _unclipped.append(plane)
            g.glDisable(plane)


def _restore_clips(g: Any) -> None:
    while _unclipped:
        g.glEnable(_unclipped.pop())


def _reclip(_data: Any, action: Any) -> None:
    if not _is_render(action):
        return
    _restore_clips(gl())


def _cap_begin(_data: Any, action: Any) -> None:
    """Draw the cap only where the count was left odd."""
    if not _is_render(action):
        return
    g = gl()
    g.glColorMask(1, 1, 1, 1)
    g.glDepthMask(1)
    g.glEnable(GL_DEPTH_TEST)
    g.glEnable(GL_STENCIL_TEST)
    g.glStencilFunc(GL_NOTEQUAL, 0, 0x01)
    g.glStencilOp(GL_KEEP, GL_KEEP, GL_KEEP)
    # Level with the exact cut, which lies on the plane too.
    g.glDepthFunc(GL_LEQUAL)
    _unclip_all(g)


def _cap_end(_data: Any, action: Any) -> None:
    if not _is_render(action):
        return
    g = gl()
    g.glDepthFunc(GL_LESS)
    g.glDisable(GL_POLYGON_STIPPLE)
    g.glEnable(GL_COLOR_MATERIAL)
    g.glDisable(GL_STENCIL_TEST)
    _reclip(_data, action)


def _cap_drawer(section: Any, cap: tuple[float, float, float],
                pattern: str) -> Any:
    """A render callback drawing one solid's cap straight in GL.

    Coin is bypassed for the cap: FreeCAD leaves GL_COLOR_MATERIAL on
    and Coin's lazy state re-sends whatever colour it last saw, so a
    material node never reached the screen. The cap is lit in `cap`;
    the hatch, `cap` darkened to INK_SHARE, is a texture on the plane,
    so its lines stay on the part as the view turns.
    """
    diffuse = (ctypes.c_float * 4)(cap[0], cap[1], cap[2], 1.0)
    darker = (ctypes.c_float * 4)(*(c * INK_SHARE for c in cap), 1.0)
    f = ctypes.c_float

    def quad(g: Any, corners: list[Vec3], textured: bool) -> None:
        g.glBegin(GL_POLYGON)
        for corner in corners:
            if textured:
                g.glTexCoord2f(*(f(t) for t in section.hatch_at(corner)))
            g.glVertex3f(*(f(c) for c in corner))
        g.glEnd()

    def seam_lines(g: Any, edges: list[tuple[Vec3, Vec3]]) -> None:
        """Outline where the cap was trimmed.

        The stencil keeps it on the part, and the cap it meets draws the
        same line.
        """
        width = f(0.0)
        g.glGetFloatv(GL_LINE_WIDTH, ctypes.byref(width))
        g.glDisable(GL_LIGHTING)
        g.glColor3f(*(f(c) for c in CUT_LINE))
        g.glLineWidth(f(SEAM_WIDTH))
        g.glBegin(GL_LINES)
        for a, b in edges:
            g.glVertex3f(*(f(c) for c in a))
            g.glVertex3f(*(f(c) for c in b))
        g.glEnd()
        g.glLineWidth(width)

    def draw(_data: Any, action: Any) -> None:
        if not _is_render(action):
            return
        corners, edges = section.cap_shape()
        if not corners:
            return
        g = gl()
        _cap_begin(None, action)
        lit = g.glIsEnabled(GL_LIGHTING)
        was_textured = g.glIsEnabled(GL_TEXTURE_2D)
        g.glDisable(GL_TEXTURE_2D)
        g.glDisable(GL_COLOR_MATERIAL)
        g.glEnable(GL_LIGHTING)
        g.glMaterialfv(GL_FRONT_AND_BACK, GL_AMBIENT_AND_DIFFUSE, diffuse)
        nx, ny, nz = section.cap_normal
        g.glNormal3f(f(nx), f(ny), f(nz))
        quad(g, corners, False)
        g.glEnable(GL_TEXTURE_2D)
        g.glBindTexture(GL_TEXTURE_2D,
                        _texture(g, id(section.view), pattern))
        g.glTexEnvi(GL_TEXTURE_ENV, GL_TEXTURE_ENV_MODE, GL_MODULATE)
        g.glEnable(GL_ALPHA_TEST)
        g.glAlphaFunc(GL_GREATER, f(0.5))
        g.glMaterialfv(GL_FRONT_AND_BACK, GL_AMBIENT_AND_DIFFUSE, darker)
        quad(g, corners, True)
        g.glDisable(GL_ALPHA_TEST)
        g.glBindTexture(GL_TEXTURE_2D, 0)
        if edges:
            g.glDisable(GL_TEXTURE_2D)
            seam_lines(g, edges)
        (g.glEnable if was_textured else g.glDisable)(GL_TEXTURE_2D)
        (g.glEnable if lit else g.glDisable)(GL_LIGHTING)
        _cap_end(None, action)

    draw.kept = (diffuse, darker)  # type: ignore[attr-defined]
    return draw


def _fill_begin(_data: Any, action: Any) -> None:
    """The fill hides behind the model and the cap, and hides nothing."""
    if not _is_render(action):
        return
    g = gl()
    g.glEnable(GL_DEPTH_TEST)
    g.glDepthMask(0)


def _fill_end(_data: Any, action: Any) -> None:
    if not _is_render(action):
        return
    g = gl()
    g.glDepthMask(1)
    g.glDisable(GL_DEPTH_TEST)


def selection_colour() -> tuple[float, float, float]:
    """FreeCAD's selection colour, as 0-1 RGB."""
    packed = App.ParamGet(VIEW_PARAMS).GetUnsigned(
        "SelectionColor", SELECTION_DEFAULT)
    return tuple((packed >> shift & 0xFF) / 255.0  # type: ignore[return-value]
                 for shift in (24, 16, 8))


def _callback(function: Any) -> Any:
    from pivy import coin
    node = coin.SoCallback()
    node.setCallback(function)
    return node


def _mesh(shape: Any) -> Any:
    """The shape's faces as triangles, for counting only."""
    from pivy import coin
    points, triangles = shape.tessellate(MESH_TOLERANCE)
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


class Section:
    """One section plane in one 3D view."""

    def __init__(self, view: Any, doc: Any, normal: App.Vector,
                 obj: Any = None) -> None:
        from pivy import coin
        self.view = view
        self.doc = doc
        #: The section object this draws, if any; it keeps the plane.
        self.obj = obj
        self.normal = App.Vector(normal)
        self.normal.normalize()
        #: The frame's own in-plane axes; tilts turn them with the plane.
        self.u, self.v = plane_axes(self.normal)
        self._tilt: dict[str, Any] | None = None
        self.offset = 0.0
        self.origin = App.Vector()
        self.span = 1.0
        self._placed = False
        self._root = view.getSceneGraph()

        self._clip = coin.SoClipPlane()
        # After everything else, edge lines included, so none show
        # through; the callbacks turn the depth test back on.
        self._cap = coin.SoAnnotation()
        # Never culled: a box wholly on the clipped side would skip the
        # stencil set-up and leave the cap drawn everywhere.
        self._cap.renderCulling = coin.SoSeparator.OFF
        self._cap.renderCaching = coin.SoSeparator.OFF
        unpickable = coin.SoPickStyle()
        unpickable.style = coin.SoPickStyle.UNPICKABLE
        self._cap.addChild(unpickable)
        # Counted and capped one solid at a time, each in its own shade.
        self._make_cap_parts()
        self._bodies = coin.SoGroup()
        self._cap.addChild(self._bodies)
        self._on_camera = self._camera_moved
        self._camera_sensor = coin.SoNodeSensor(self._on_camera, None)

        self._handle_xf = coin.SoTransform()
        self._dragger = coin.SoTranslate1Dragger()
        # A field sensor, not the dragger's own callbacks: those crash
        # inside pivy on the first drag. Both are kept referenced.
        self._on_drag = self._dragged
        self._drag_sensor = coin.SoFieldSensor(self._on_drag, None)
        self._drag_sensor.attach(self._dragger.translation)
        # Ahead of the clip plane, so it neither clips nor stops picking
        # the handle; drawn last and on top, so the model cannot hide it.
        self._handle = coin.SoAnnotation()
        self._handle.renderCulling = coin.SoSeparator.OFF
        self._handle.addChild(self._frame())
        arrow = coin.SoSeparator()
        arrow.addChild(self._handle_xf)
        arrow.addChild(self._dragger)
        self._handle.addChild(arrow)

        self._box_corners: list[App.Vector] = []
        self._extents = (-1.0, 1.0, -1.0, 1.0)
        self._grab: tuple[Point, float] | None = None
        self._hover = False
        self._on_event = self._event
        cut = getattr(obj, "Cut", None)
        self._cut_name = cut.Name if cut is not None else ""
        self._settle = QtCore.QTimer()
        self._settle.setSingleShot(True)
        self._settle.setInterval(SETTLE_MS)
        self._settle.timeout.connect(self.cut_exactly)
        from .section_field import OffsetBox, ToolButtons
        self.editing = True
        self._offset_box = OffsetBox(self)
        self._flip_button = ToolButtons(self)
        self._clicks = _ArrowClicks(self)
        view.addEventCallbackPivy(coin.SoEvent.getClassTypeId(),
                                  self._on_event)

        self._clips = _clip_group(self._root)
        self._clips.addChild(self._clip)
        self.refresh()
        self._root.insertChild(self._handle, 0)
        self._root.addChild(self._cap)

    def _frame(self) -> Any:
        """The plane's outline: drag it to slide the plane."""
        from pivy import coin
        frame = coin.SoSeparator()
        # Grabbed by its own pointer test; picks go through to the model.
        unpickable = coin.SoPickStyle()
        unpickable.style = coin.SoPickStyle.UNPICKABLE
        frame.addChild(unpickable)
        light = coin.SoLightModel()
        light.model = coin.SoLightModel.BASE_COLOR
        frame.addChild(light)
        style = coin.SoDrawStyle()
        style.lineWidth = FRAME_WIDTH
        frame.addChild(style)
        self._frame_colour = coin.SoBaseColor()
        self._frame_colour.rgb = FRAME_COLOUR
        frame.addChild(self._frame_colour)
        self._frame_points = coin.SoCoordinate3()
        frame.addChild(self._frame_points)
        line = coin.SoLineSet()
        line.numVertices = 5
        frame.addChild(line)
        arcs = coin.SoSeparator()
        self._arc_points = coin.SoCoordinate3()
        arcs.addChild(self._arc_points)
        arc_lines = coin.SoLineSet()
        arc_lines.numVertices.setValues(0, 2, [ARC_STEPS, ARC_STEPS])
        arcs.addChild(arc_lines)
        frame.addChild(arcs)
        fill = coin.SoSeparator()
        fill.addChild(_callback(_fill_begin))
        material = coin.SoMaterial()
        material.diffuseColor = selection_colour()
        material.transparency = FILL_TRANSPARENCY
        fill.addChild(material)
        fill.addChild(self._frame_points)
        face = coin.SoFaceSet()
        face.numVertices = 4
        fill.addChild(face)
        fill.addChild(_callback(_fill_end))
        frame.addChild(fill)
        return frame

    def _make_cap_parts(self) -> None:
        """What every solid's cap shares: its quad and its normal."""
        self.quad_corners: list[tuple[float, float, float]] = []
        self.cap_normal = (0.0, 0.0, 1.0)
        #: World length of one hatch tile at the current zoom.
        self.hatch_tile = 1.0
        # pivy holds callbacks by a borrowed reference, and the stipple
        # buffers must outlive every frame that draws them.
        self._kept: list[Any] = []

    def _body_cap(self, solid: Instance) -> Any:
        """Count one solid's surfaces, then cap it in its own shade."""
        from pivy import coin
        node = coin.SoSeparator()
        node.renderCulling = coin.SoSeparator.OFF
        node.renderCaching = coin.SoSeparator.OFF
        count = coin.SoSeparator()
        count.renderCulling = coin.SoSeparator.OFF

        def begin(data: Any, action: Any) -> None:
            if _is_render(action):
                _count_begin(data, action)
                _unclip_all(gl())

        self._kept.append(begin)
        count.addChild(_callback(begin))
        # Counted against this plane alone: Coin enables it again here,
        # at whatever GL index it is free, and drops it at the end.
        count.addChild(self._clip)
        count.addChild(_mesh(solid.shape))
        node.addChild(count)
        cap = shade(desaturate(solid.colour, CAP_DESATURATE), CAP_SHADE)
        draw = _cap_drawer(self, cap,
                           pattern_for(solid.name))
        self._kept.append(draw)
        node.addChild(_callback(draw))
        return node

    def refresh(self) -> None:
        """Re-read the solids: after a recompute or a visibility change."""
        solids = cut_instances(self.doc)
        self._bodies.removeAllChildren()
        self._kept.clear()
        camera = self.view.getCameraNode()
        if self._camera_sensor.getAttachedNode() is not camera:
            self._camera_sensor.detach()
            self._camera_sensor.attach(camera)
        if not solids:
            return
        box = solids[0].shape.BoundBox
        for solid in solids[1:]:
            box.add(solid.shape.BoundBox)
        for solid in solids:
            try:
                self._bodies.addChild(self._body_cap(solid))
            except Exception as exc:
                log.error("section: could not mesh %s: %s"
                          % (solid.name, exc))
        self.span = max(box.DiagonalLength, 1.0)
        if not self._placed:
            self.origin = box.Center
            self._placed = True
        self._box_corners = [App.Vector(x, y, z)
                             for x in (box.XMin, box.XMax)
                             for y in (box.YMin, box.YMax)
                             for z in (box.ZMin, box.ZMax)]
        self._fit_frame()
        self._place_handle()
        self.move(self.offset)

    def _fit_frame(self) -> None:
        """Size the frame to the model as seen along the normal."""
        u, v = self.u, self.v
        us = [(c - self.origin).dot(u) for c in self._box_corners]
        vs = [(c - self.origin).dot(v) for c in self._box_corners]
        if not us:
            return
        m = self.span * FRAME_MARGIN
        self._extents = (min(us) - m, max(us) + m, min(vs) - m, max(vs) + m)

    def _frame_corners(self, point: App.Vector) -> list[App.Vector]:
        u, v = self.u, self.v
        u0, u1, v0, v1 = self._extents
        return [point + u * a + v * b
                for a, b in ((u0, v0), (u1, v0), (u1, v1), (u0, v1))]

    def _place_handle(self) -> None:
        from pivy import coin
        n = self.normal
        self._handle_xf.rotation = coin.SbRotation(
            coin.SbVec3f(1, 0, 0), coin.SbVec3f(n.x, n.y, n.z))
        scale = self.span * HANDLE_SCALE
        self._handle_xf.scaleFactor = (scale, scale, scale)
        # At the frame's corner, clear of the model.
        o = self._frame_corners(self.origin)[2]
        self._handle_xf.translation = (o.x, o.y, o.z)

    def _dragged(self, _data: Any, _sensor: Any) -> None:
        local = self._dragger.translation.getValue()[0]
        self.move(local * self.span * HANDLE_SCALE, from_handle=True)

    def move(self, offset: float, from_handle: bool = False) -> None:
        """Put the plane `offset` along its normal from where it began."""
        from pivy import coin
        self.offset = offset
        n = self.normal
        point = self.origin + n * offset
        behind = point - n * (self.span * CLIP_SLACK)
        self._clip.plane = coin.SbPlane(coin.SbVec3f(n.x, n.y, n.z),
                                        coin.SbVec3f(*behind))
        corners = self._frame_corners(point)
        self._frame_points.point.setValues(
            0, 5, [(c.x, c.y, c.z) for c in corners + corners[:1]])
        arc_points = [p for arc in self._arcs(point).values() for p in arc]
        self._arc_points.point.setValues(
            0, len(arc_points), [(p.x, p.y, p.z) for p in arc_points])
        u, v = self.u, self.v
        half = self.span
        corners = [point + u * su * half + v * sv * half
                   for su, sv in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
        self.quad_corners = [(c.x, c.y, c.z) for c in corners]
        self._face_viewer()
        self._place_offset_box()
        if not from_handle:
            local = offset / (self.span * HANDLE_SCALE)
            self._dragger.translation = (local, 0, 0)
        self._settle.start()

    def cut_exactly(self) -> None:
        """Put the exact cut in the document, to select and measure.

        Its faces are invisible (the hatched cap shows) but pickable;
        its edges draw the cut's outline. Made outside any transaction,
        so moving the plane leaves nothing to undo.
        """
        import Part
        n = self.normal
        point = self.origin + n * self.offset
        solids = cut_instances(self.doc)
        per_solid = cut_faces([i.shape for i in solids], n, n.dot(point))
        faces = [face for cut in per_solid for face in cut]
        cut_obj = (self.doc.getObject(self._cut_name) if self._cut_name
                   else None)
        if cut_obj is None:
            cut_obj = self.doc.addObject("Part::Feature", CUT_NAME)
            self._cut_name = cut_obj.Name
            view = cut_obj.ViewObject
            if view is not None:
                view.Transparency = 100
                view.LineColor = CUT_LINE
                view.LineWidth = CUT_LINE_WIDTH
                view.PointSize = 1
            if self.obj is not None:
                from . import section_object
                cut_obj.Label = "%s cut" % self.obj.Label
                section_object.group(self.doc).addObject(cut_obj)
                self.obj.Cut = cut_obj
        cut_obj.Shape = Part.makeCompound(faces)
        if cut_obj.ViewObject is not None:
            cut_obj.ViewObject.Visibility = True
        self._store()

    def _store(self) -> None:
        """Write the plane to the section object, if it has one."""
        obj = self.obj
        if obj is None:
            return
        base = self.origin + self.normal * self.offset
        for name, value in (("Base", base), ("Normal", self.normal),
                            ("XAxis", self.u)):
            if (getattr(obj, name) - value).Length > 1e-9:
                setattr(obj, name, value)

    def _camera_moved(self, _data: Any, _sensor: Any) -> None:
        self._face_viewer()
        self._place_offset_box()

    def set_editing(self, editing: bool) -> None:
        """Show the frame and its controls, or only the cut."""
        if editing == self.editing:
            return
        self.editing = editing
        shown = self._root.findChild(self._handle) >= 0
        if editing and not shown:
            self._root.insertChild(self._handle, 0)
        elif not editing and shown:
            self._root.removeChild(self._handle)
        if editing:
            self._place_offset_box()
        else:
            self._grab = self._tilt = None
            self._offset_box.hide()
            self._flip_button.hide()
            self._clicks.stop()

    def _place_offset_box(self) -> None:
        """The offset field rides at the arrow's tip."""
        if not self._box_corners or not self.editing:
            return
        corners = self._frame_corners(
            self.origin + self.normal * self.offset)
        self._offset_box.place(self.view, corners[2])
        self._flip_button.place(
            self.view, corners[top_left([self._screen(c) for c in corners],
                                        avoid=2)])
        self._clicks.watch()

    def set_plane(self, normal: App.Vector, point: App.Vector,
                  x_axis: App.Vector | None = None) -> None:
        """Re-aim the section: this normal, through this point."""
        n = App.Vector(normal)
        n.normalize()
        self.normal = n
        self.u, self.v = plane_axes(n)
        if x_axis is not None and x_axis.Length > 0:
            u = App.Vector(x_axis) - n * n.dot(x_axis)
            if u.Length > 1e-9:
                u.normalize()
                self.u, self.v = u, n.cross(u)
        self.origin = App.Vector(point)
        self.offset = 0.0
        self._fit_frame()
        self._place_handle()
        self.move(0.0)

    def _face_viewer(self) -> None:
        """Light the cap from whichever side the camera sees it."""
        n = self.normal
        look = App.Vector(self.view.getViewDirection())
        facing = n if n.dot(look) < 0 else -n
        self.cap_normal = (facing.x, facing.y, facing.z)
        self._map_hatch()

    def _map_hatch(self) -> None:
        """Lay the hatch tile on the plane at a size for this zoom."""
        from pivy import coin
        camera = self.view.getCameraNode()
        _width, height = self.view.getSize()
        if camera.isOfType(coin.SoOrthographicCamera.getClassTypeId()):
            seen = camera.height.getValue()
        else:
            seen = 2 * camera.focalDistance.getValue() * math.tan(
                camera.heightAngle.getValue() / 2)
        self.hatch_tile = snapped_tile(seen / height if height else 0.0)

    def hatch_at(self, corner: Vec3) -> tuple[float, float]:
        """The hatch texture's coordinates at a point on the plane."""
        p = App.Vector(*corner)
        return p.dot(self.u) / self.hatch_tile, p.dot(self.v) / self.hatch_tile

    def keep_plane(self) -> Plane:
        """The side the section keeps, as its clip plane has it."""
        n = self.normal
        behind = self.origin + n * (self.offset - self.span * CLIP_SLACK)
        return (n.x, n.y, n.z), n.dot(behind)

    def cap_shape(self) -> tuple[list[Vec3], list[tuple[Vec3, Vec3]]]:
        """The cap's quad, less what other sections cut, and the cut edges.

        The quad is trimmed by this view's other sections; the edges are
        where they cut it.
        """
        others = [s.keep_plane() for s in _sections.values()
                  if s is not self and self._clips.findChild(s._clip) >= 0]
        corners = clip_polygon(self.quad_corners, others)
        return corners, seams(corners, others,
                              self.span * SEAM_TOLERANCE)

    def _screen(self, p: App.Vector) -> Point:
        """Where a model point shows in the view, in Coin's pixels."""
        from pivy import coin
        width, height = self.view.getSize()
        camera = self.view.getCameraNode()
        volume = camera.getViewVolume(width / height if height else 1.0)
        # pivy returns the projection rather than filling an argument.
        out = volume.projectToScreen(coin.SbVec3f(p.x, p.y, p.z))
        x, y, _z = out.getValue()
        return x * width, y * height

    def _near_frame(self, pos: Point) -> bool:
        point = self.origin + self.normal * self.offset
        corners = [self._screen(c) for c in self._frame_corners(point)]
        return any(segment_distance(pos, corners[i], corners[i - 1])
                   <= FRAME_REACH for i in range(4))

    def _drag_to(self, pos: Point) -> None:
        if self._grab is None:
            return
        start, offset = self._grab
        base = self.origin + self.normal * offset
        step = self.span * 0.1
        u = self.u
        a = self._screen(base)
        b = self._screen(base + self.normal * step)
        c = self._screen(base + u * step)
        normal_px = ((b[0] - a[0]) / step, (b[1] - a[1]) / step)
        plane_px = ((c[0] - a[0]) ** 2 + (c[1] - a[1]) ** 2) ** 0.5 / step
        look = App.Vector(self.view.getViewDirection())
        away = self.normal.dot(look) > 0
        self.move(offset + drag_amount(start, pos, normal_px, plane_px,
                                       away))

    def _event(self, node: Any) -> None:
        """Grab the frame with the left button and slide the plane."""
        from pivy import coin
        event = node.getEvent()
        if not self.editing:
            return
        if event.isOfType(coin.SoKeyboardEvent.getClassTypeId()):
            if event.getKey() == coin.SoKeyboardEvent.ESCAPE and \
                    event.getState() == coin.SoButtonEvent.DOWN:
                self.set_editing(False)
                node.setHandled()
            return
        x, y = event.getPosition().getValue()
        pos = (float(x), float(y))
        if event.isOfType(coin.SoMouseButtonEvent.getClassTypeId()):
            if event.getButton() != coin.SoMouseButtonEvent.BUTTON1:
                return
            if event.getState() == coin.SoButtonEvent.DOWN:
                about = self._near_arc(pos)
                if about is not None:
                    self._begin_tilt(about, pos)
                    node.setHandled()
                elif self._near_frame(pos):
                    self._grab = (pos, self.offset)
                    node.setHandled()
            elif self._tilt is not None:
                self._tilt = None
                self._place_offset_box()
                node.setHandled()
            elif self._grab is not None:
                self._grab = None
                node.setHandled()
        elif event.isOfType(coin.SoLocation2Event.getClassTypeId()):
            if (self._grab is not None or self._tilt is not None) \
                    and not _left_held():
                # The release went elsewhere (over a floating field, or
                # outside the view): end the drag where it is.
                self.end_drag()
                return
            if self._tilt is not None:
                step = (0.0 if event.wasShiftDown() else
                        TILT_STEP_COARSE if event.wasCtrlDown()
                        else TILT_STEP)
                self._tilt_to(pos, step)
                node.setHandled()
                return
            if self._grab is not None:
                self._drag_to(pos)
                node.setHandled()
                return
            hover = self._near_arc(pos) is not None or self._near_frame(pos)
            if hover != self._hover:
                self._hover = hover
                self._frame_colour.rgb = (FRAME_HOVER if hover
                                          else FRAME_COLOUR)

    def _arcs(self, point: App.Vector) -> dict[str, list[App.Vector]]:
        """The two tilt arcs, by the in-plane axis each turns about.

        One bows out of the plane at the middle of the frame's side edge,
        the other at its top edge.
        """
        u0, u1, v0, v1 = self._extents
        radius = self.span * ARC_SCALE
        n = self.normal
        out: dict[str, list[App.Vector]] = {}
        for about, edge, outward in (
                ("v", point + self.u * u1 + self.v * ((v0 + v1) / 2),
                 self.u),
                ("u", point + self.v * v1 + self.u * ((u0 + u1) / 2),
                 self.v)):
            centre = edge - outward * radius
            out[about] = [
                centre + outward * (radius * math.cos(t))
                + n * (radius * math.sin(t))
                for t in (math.radians(-ARC_SWEEP + 2 * ARC_SWEEP * i
                                       / (ARC_STEPS - 1))
                          for i in range(ARC_STEPS))]
        return out

    def _near_arc(self, pos: Point) -> str | None:
        point = self.origin + self.normal * self.offset
        for about, arc in self._arcs(point).items():
            if polyline_distance(pos, [self._screen(p) for p in arc]) \
                    <= FRAME_REACH:
                return about
        return None

    def _begin_tilt(self, about: str, pos: Point) -> None:
        pivot = self.origin + self.normal * self.offset
        u0, u1, v0, v1 = self._extents
        outward = self.u if about == "v" else self.v
        reach = (u1 if about == "v" else v1)
        self._tilt = {"about": about, "start": pos, "pivot": pivot,
                      "n": App.Vector(self.normal), "u": App.Vector(self.u),
                      "v": App.Vector(self.v), "handle": pivot
                      + outward * reach, "outward": App.Vector(outward),
                      "degrees": 0.0}

    def _tilt_to(self, pos: Point, step: float) -> None:
        """Turn the plane by the pointer's travel along the arc."""
        tilt = self._tilt
        if tilt is None:
            return
        handle, pivot = tilt["handle"], tilt["pivot"]
        a, b = self._screen(handle), self._screen(pivot)
        c = self._screen(handle + tilt["n"] * (self.span * 0.05))
        tangent = (c[0] - a[0], c[1] - a[1])
        length = math.hypot(*tangent)
        radius = max(math.hypot(a[0] - b[0], a[1] - b[1]), 30.0)
        if length == 0:
            return
        start = tilt["start"]
        travel = ((pos[0] - start[0]) * tangent[0]
                  + (pos[1] - start[1]) * tangent[1]) / length
        degrees = snap_angle(math.degrees(travel / radius), step)
        # Turning about outward x n carries the handle toward +n.
        axis = tilt["outward"].cross(tilt["n"])
        turn = App.Rotation(axis, degrees)
        n = turn.multVec(tilt["n"])
        u = turn.multVec(tilt["u"])
        square = _square_to(n)
        if square is not None:
            n = square
            u = u - n * u.dot(n)
            u.normalize()
        tilt["degrees"] = degrees
        self.normal, self.u = n, u
        self.v = n.cross(u)
        self.origin = App.Vector(pivot)
        self.offset = 0.0
        self._fit_frame()
        self._place_handle()
        self.move(0.0)

    @property
    def tilt_degrees(self) -> float | None:
        """The tilt so far while an arc is dragged, else None."""
        return None if self._tilt is None else self._tilt["degrees"]

    def end_drag(self) -> None:
        """Let go of the frame or an arc."""
        if self._tilt is not None:
            self._tilt = None
            self._place_offset_box()
        self._grab = None

    def on_arrow(self, pos: Point) -> bool:
        """Whether a point in Coin's pixels is on the arrow."""
        tip = self._frame_corners(self.origin + self.normal * self.offset)[2]
        reach = self.normal * (self.span * HANDLE_SCALE)
        return segment_distance(pos, self._screen(tip - reach),
                                self._screen(tip + reach)) <= FRAME_REACH

    def arrow_position(self) -> float:
        return float(self._dragger.translation.getValue()[0])

    def flip(self) -> None:
        """Keep the other side."""
        self.normal = -self.normal
        self.v = self.normal.cross(self.u)
        self.offset = -self.offset
        self._fit_frame()
        self._place_handle()
        self.move(self.offset)

    def remove(self, delete_cut: bool = False) -> None:
        """Stop drawing; the exact cut is hidden, or deleted too."""
        from pivy import coin
        self._drag_sensor.detach()
        self.view.removeEventCallbackPivy(coin.SoEvent.getClassTypeId(),
                                          self._on_event)
        self._settle.stop()
        self._camera_sensor.detach()
        self._offset_box.remove()
        self._flip_button.remove()
        self._clicks.stop()
        if self._clips.findChild(self._clip) >= 0:
            self._clips.removeChild(self._clip)
        if self._clips.getNumChildren() == 0 and \
                self._root.findChild(self._clips) >= 0:
            self._root.removeChild(self._clips)
        for node in (self._cap, self._handle):
            if self._root.findChild(node) >= 0:
                self._root.removeChild(node)
        cut = self.doc.getObject(self._cut_name) if self._cut_name \
            else None
        if cut is None:
            return
        if delete_cut or self.obj is None:
            self.doc.removeObject(self._cut_name)
        elif cut.ViewObject is not None:
            cut.ViewObject.Visibility = False


#: Per scene root, the group holding every section's clip plane.
#: The name of the group holding a scene's section clip planes.
CLIP_GROUP = "NxtSectionClips"


def _clip_group(root: Any) -> Any:
    """The sections' clip planes, first in the scene; made on first use.

    Found by name: pivy hands out a new wrapper for the same root on
    each getSceneGraph(), so its id() can't key a cache, and a group per
    section would hide the others from cap_polygon.
    """
    from pivy import coin
    for i in range(root.getNumChildren()):
        child = root.getChild(i)
        if child.getName().getString() == CLIP_GROUP:
            return (child if hasattr(child, "addChild")
                    else coin.cast(child, "SoGroup"))
    group = coin.SoGroup()
    group.setName(CLIP_GROUP)
    root.insertChild(group, 0)
    return group


def _left_held() -> bool:
    buttons = QtWidgets.QApplication.mouseButtons()
    return bool(buttons & QtCore.Qt.MouseButton.LeftButton)


def _square_to(n: App.Vector) -> App.Vector | None:
    """X, Y or Z (either way) if `n` is within SQUARE_SNAP of it."""
    limit = math.cos(math.radians(SQUARE_SNAP))
    for axis in ((1, 0, 0), (0, 1, 0), (0, 0, 1)):
        a = App.Vector(*axis)
        d = n.dot(a)
        if abs(d) >= limit:
            return a if d > 0 else a * -1.0
    return None


class _ArrowClicks(QtCore.QObject):
    """A click on the arrow, pressed and let go without dragging, flips.

    Watched on the Qt viewport: once the arrow is grabbed Coin sends it
    every mouse event directly, so the scene never sees the release.
    """

    #: Further than this between press and release, in pixels, is a drag.
    STILL = 4.0

    def __init__(self, section: Any) -> None:
        super().__init__()
        self._section = section
        self._viewport: Any = None
        self._press: tuple[float, float, float] | None = None

    def watch(self) -> None:
        from ..core import view3d
        viewport = view3d.active_viewport()
        if viewport is self._viewport:
            return
        self.stop()
        if viewport is not None:
            viewport.installEventFilter(self)
            self._viewport = viewport

    def stop(self) -> None:
        from ..core import widgets
        if widgets.alive(self._viewport):
            self._viewport.removeEventFilter(self)
        self._viewport = None

    def _coin(self, event: Any) -> Point:
        point = event.position()
        ratio = self._viewport.devicePixelRatioF() or 1.0
        return (point.x() * ratio,
                (self._viewport.height() - point.y()) * ratio)

    def eventFilter(self, watched: Any, event: Any) -> bool:  # noqa: N802
        kind = event.type()
        press = QtCore.QEvent.Type.MouseButtonPress
        release = QtCore.QEvent.Type.MouseButtonRelease
        if watched is not self._viewport or kind not in (press, release):
            return False
        if event.button() != QtCore.Qt.MouseButton.LeftButton:
            return False
        x, y = self._coin(event)
        if kind == press:
            self._press = ((x, y, self._section.arrow_position())
                           if self._section.on_arrow((x, y)) else None)
            return False
        # After the scene has had the release, in case it never does.
        QtCore.QTimer.singleShot(0, self._section.end_drag)
        start, self._press = self._press, None
        if start is not None and math.hypot(x - start[0], y - start[1]) \
                <= self.STILL and abs(self._section.arrow_position()
                                      - start[2]) < 1e-9:
            # Deferred: the dragger is still finishing this release.
            QtCore.QTimer.singleShot(0, self._section.flip)
        return False


class _Recompute:
    """Re-reads each section's solids when its document recomputes."""

    def slotRecomputedDocument(self, doc: Any) -> None:  # noqa: N802
        for section in list(_sections.values()):
            if section.doc is doc:
                section.refresh()

    def slotDeletedDocument(self, doc: Any) -> None:  # noqa: N802
        for key, section in list(_sections.items()):
            if section.doc is doc:
                del _sections[key]


_sections: dict[str, Section] = {}
_observer: _Recompute | None = None


def _key(obj: Any) -> str:
    return "%s#%s" % (obj.Document.Name, obj.Name)


def _active() -> tuple[Any, Any] | None:
    gui_doc = Gui.ActiveDocument
    if gui_doc is None:
        return None
    view = gui_doc.ActiveView
    if view is None or not hasattr(view, "getSceneGraph"):
        return None
    return view, gui_doc.Document


def _watch() -> None:
    global _observer
    if _sections and _observer is None:
        _observer = _Recompute()
        App.addDocumentObserver(_observer)
    elif not _sections and _observer is not None:
        App.removeDocumentObserver(_observer)
        _observer = None


def running(obj: Any) -> bool:
    return _key(obj) in _sections


def start(obj: Any, editing: bool) -> Section | None:
    """Cut the object's document's view with this section object."""
    gui_doc = Gui.getDocument(obj.Document.Name)
    view = gui_doc.ActiveView if gui_doc is not None else None
    if view is None or not hasattr(view, "getSceneGraph"):
        return None
    section = Section(view, obj.Document, App.Vector(obj.Normal), obj)
    section.set_plane(App.Vector(obj.Normal), App.Vector(obj.Base),
                      App.Vector(obj.XAxis))
    section.set_editing(editing)
    _sections[_key(obj)] = section
    _watch()
    return section


def stop(obj: Any, delete_cut: bool = False) -> None:
    section = _sections.pop(_key(obj), None)
    if section is not None:
        section.remove(delete_cut)
    elif delete_cut:
        cut = getattr(obj, "Cut", None)
        if cut is not None:
            obj.Document.removeObject(cut.Name)
    _watch()


def edit(obj: Any) -> None:
    """Edit this section; any other is finished first."""
    for other in _sections.values():
        if other.obj is not obj and other.editing:
            other.set_editing(False)
    section = _sections.get(_key(obj))
    if section is not None:
        section.set_editing(True)


def current() -> Section | None:
    """The active document's edited section, else any it shows."""
    found = _active()
    if found is None:
        return None
    mine = [s for s in _sections.values() if s.doc is found[1]]
    editing = [s for s in mine if s.editing]
    chosen = editing or mine
    return chosen[0] if chosen else None


def end(section: Section) -> None:
    """Delete a section object, its exact cut and everything drawn."""
    obj = section.obj
    if obj is None:
        section.remove(delete_cut=True)
        return
    doc = obj.Document
    stop(obj, delete_cut=True)
    doc.removeObject(obj.Name)


def toggle() -> None:
    """Finish the section being edited, or start another.

    Sections already cutting the view stay; double-click one in the tree
    to edit it again.
    """
    from . import section_object
    found = _active()
    if found is None:
        return
    view, doc = found
    existing = current()
    if existing is not None and existing.editing:
        existing.set_editing(False)
        return
    mine = [s for s in _sections.values() if s.doc is doc]
    if len(mine) >= section_object.LIMIT:
        App.Console.PrintWarning(
            "Nxt: at most %d sections can cut the view at once; hide one "
            "to start another\n" % section_object.LIMIT)
        return
    if not cut_instances(doc):
        App.Console.PrintWarning(
            "Nxt section: nothing visible with a solid to cut\n")
        return
    look = App.Vector(view.getViewDirection())
    chosen = section_aim.from_selection()
    normal = (section_aim.facing(chosen[0], look) if chosen
              else facing_axis(look))
    solids = cut_instances(doc)
    box: Any = solids[0].shape.BoundBox
    for solid in solids[1:]:
        box.add(solid.shape.BoundBox)
    point = chosen[1] if chosen else box.Center
    u, _v = plane_axes(App.Vector(normal))
    obj = section_object.create(doc, normal, point, u)
    start(obj, editing=False)
    edit(obj)


def flip() -> None:
    section = current()
    if section is not None:
        section.flip()


def align_to_selection() -> bool:
    """Re-aim the section at the selected face, plane or three points.

    With nothing usable selected, it faces the camera square on.
    """
    section = current()
    if section is None:
        return False
    look = App.Vector(section.view.getViewDirection())
    chosen = section_aim.from_selection()
    if chosen is None:
        point = section.origin + section.normal * section.offset
        section.set_plane(look, point)
        return False
    section.set_plane(section_aim.facing(chosen[0], look), chosen[1])
    return True


def set_axis(name: str) -> None:
    """Cut across a principal axis, keeping the plane where it is."""
    section = current()
    if section is None:
        return
    look = App.Vector(section.view.getViewDirection())
    point = section.origin + section.normal * section.offset
    section.set_plane(section_aim.facing(section_aim.axis(name), look),
                      point)


def report() -> None:
    """Print where the section puts each solid, beside where FreeCAD does.

    A diagnostic for the Report view; nothing calls it.
    """
    import Part
    doc = App.ActiveDocument
    if doc is None:
        return
    shape_of: Any = Part.getShape

    def safe(read: Callable[[], Any]) -> str:
        try:
            return str(read())
        except Exception as exc:
            return "<%s>" % type(exc).__name__

    if doc.getObject("Assembly") is not None:
        top = doc.getObject("Assembly")
        App.Console.PrintMessage(
            "section: Assembly placement %s, shape centre %s\n" % (
                safe(lambda: top.Placement),
                safe(lambda: top.Shape.BoundBox.Center)))
    for solid in cut_instances(doc):
        obj = doc.getObject(solid.name)
        target = _linked(obj)
        App.Console.PrintMessage(
            "section: %s %s -> %s | ours %s | getShape %s | target %s"
            " | global %s | colour %s\n" % (
                solid.name, safe(lambda: obj.TypeId),
                safe(lambda: target.Name),
                safe(lambda: solid.shape.BoundBox.Center),
                safe(lambda: shape_of(obj).BoundBox.Center),
                safe(lambda: target.Shape.BoundBox.Center),
                safe(lambda: obj.getGlobalPlacement().Base),
                safe(lambda: solid.colour)))
