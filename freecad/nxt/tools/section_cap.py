"""A section's clip on each solid it cuts, and its cap as real faces.

Each solid cut is clipped in its own view provider, so nothing else in
the scene is touched: sketches, datums, dimensions and other aids stay
whole. The cap is the exact cut (the solid sliced by the plane) drawn
as faces in the solid's own material, the hatch as their texture: lit
as the part is, highlighted with it, and hiding only what is behind it.
While the plane moves only the cut's outline is drawn, from the solid's
mesh; the faces follow once it rests.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import FreeCAD as App

from ..core import log

#: Tessellation tolerance of the cap, as a share of the part's diagonal.
CAP_TOLERANCE = 2e-4
#: Tessellation tolerance of the mesh the moving outline is cut from.
OUTLINE_TOLERANCE = 1e-3
#: The hatch tile's texture, square, in texels.
TILE = 32
#: The cap is drawn this far toward the viewer (polygon offset units),
#: clear of the plane's own fill lying on it.
CAP_FACTOR = -2.0
CAP_UNITS = -8.0
OUTLINE_COLOUR = (0.1, 0.1, 0.1)
OUTLINE_WIDTH = 2.0
VIEW_PARAMS = "User parameter:BaseApp/Preferences/View"
SELECTION_DEFAULT = 0x1CAD1CFF
HIGHLIGHT_DEFAULT = 0xE1E114FF


def _numpy() -> Any:
    """numpy, untyped: its stubs need a newer Python than some checks."""
    import importlib
    return importlib.import_module("numpy")


def view_root(obj: Any) -> Any:
    """The scene node that draws `obj`, or None."""
    view = getattr(obj, "ViewObject", None)
    try:
        return view.RootNode if view is not None else None
    except Exception:
        return None


def local_plane(normal: App.Vector, point: App.Vector,
                parent: Any) -> tuple[App.Vector, App.Vector]:
    """A world plane in the space a solid is drawn in, under `parent`."""
    inverse = parent.inverse()
    local_point = inverse.multVec(point)
    local_normal = inverse.Rotation.multVec(normal)
    return local_normal, local_point


def tile_image(mask: bytes, ink: float) -> bytes:
    """The hatch tile, grey: white paper, lines at `ink`.

    Multiplied into the cap's lit colour, so lines are the part's own
    colour darkened. `mask` is a 32x32 RGBA tile, its lines opaque.
    """
    paper = b"\xff\xff\xff\xff"
    level = round(ink * 255)
    lines = bytes((level, level, level, 255))
    out = bytearray()
    for i in range(TILE * TILE):
        out += lines if mask[i * 4 + 3] else paper
    return bytes(out)


def _packed(name: str, default: int) -> tuple[float, float, float]:
    packed = App.ParamGet(VIEW_PARAMS).GetUnsigned(name, default)
    return (((packed >> 24) & 0xFF) / 255.0, ((packed >> 16) & 0xFF) / 255.0,
            ((packed >> 8) & 0xFF) / 255.0)


def selection_colours() -> tuple[tuple[float, float, float],
                                 tuple[float, float, float]]:
    """FreeCAD's selection and preselection colours."""
    return (_packed("SelectionColor", SELECTION_DEFAULT),
            _packed("HighlightColor", HIGHLIGHT_DEFAULT))


@dataclass
class Look:
    """How a solid's faces are lit: its material, the cap's diffuse."""

    diffuse: tuple[float, float, float]
    ambient: tuple[float, float, float] = (0.2, 0.2, 0.2)
    specular: tuple[float, float, float] = (0.0, 0.0, 0.0)
    emissive: tuple[float, float, float] = (0.0, 0.0, 0.0)
    shininess: float = 0.2


def look_of(obj: Any, diffuse: tuple[float, float, float]) -> Look:
    """The object's own material, with the cap's colour."""
    look = Look(diffuse)
    try:
        material = obj.ViewObject.ShapeAppearance[0]
    except Exception:
        return look
    for name in ("AmbientColor", "SpecularColor", "EmissiveColor"):
        try:
            value = getattr(material, name)
            setattr(look, name[:-5].lower(),
                    (float(value[0]), float(value[1]), float(value[2])))
        except Exception:
            pass
    try:
        look.shininess = float(material.Shininess)
    except Exception:
        pass
    return look


@dataclass
class Clipped:
    """One solid's clip node, where it sits, and what places it."""

    root: Any
    clip: Any
    parent: Any


@dataclass
class CapPiece:
    """One solid's cut faces as a mesh, and its texture coordinates."""

    name: str
    node: Any
    material: Any
    coords: Any
    diffuse: tuple[float, float, float]
    points: list[Any] = field(default_factory=list)


class Clips:
    """The section's clip, put into each solid's own view provider."""

    def __init__(self) -> None:
        self.items: list[Clipped] = []

    def attach(self, solids: list[Any]) -> None:
        from pivy import coin
        self.detach()
        for solid in solids:
            root = view_root(solid.obj)
            if root is None:
                continue
            clip = coin.SoClipPlane()
            root.insertChild(clip, 0)
            self.items.append(Clipped(root, clip, solid.parent))

    def place(self, normal: App.Vector, point: App.Vector) -> None:
        from pivy import coin
        for item in self.items:
            n, p = local_plane(normal, point, item.parent)
            item.clip.plane = coin.SbPlane(coin.SbVec3f(n.x, n.y, n.z),
                                           coin.SbVec3f(p.x, p.y, p.z))

    def detach(self) -> None:
        for item in self.items:
            try:
                if item.root.findChild(item.clip) >= 0:
                    item.root.removeChild(item.clip)
            except Exception:  # noqa: BLE001 - its object is gone
                pass
        self.items = []


class Meshes:
    """Each solid's triangles, for cutting the outline as the plane moves."""

    def __init__(self) -> None:
        #: (solid, points, triangles), for each solid meshed.
        self.items: list[tuple[Any, Any, Any]] = []

    def read(self, solids: list[Any]) -> None:
        numpy = _numpy()
        self.items = []
        for solid in solids:
            try:
                size = max(solid.shape.BoundBox.DiagonalLength, 1e-6)
                points, triangles = solid.shape.tessellate(
                    size * OUTLINE_TOLERANCE)
            except Exception:  # noqa: BLE001 - no outline for it
                continue
            if not triangles:
                continue
            self.items.append((
                solid,
                numpy.array([(p.x, p.y, p.z) for p in points], dtype=float),
                numpy.array(triangles, dtype=int)))

    def outline(self, normal: App.Vector, distance: float
                ) -> list[tuple[float, float, float]]:
        """Where the plane crosses the triangles: segment end pairs."""
        numpy = _numpy()
        n = numpy.array((normal.x, normal.y, normal.z))
        out: list[tuple[float, float, float]] = []
        for _solid, points, triangles in self.items:
            level = points @ n - distance
            corners = points[triangles]                 # (m, 3, 3)
            heights = level[triangles]                  # (m, 3)
            crossings = []
            for a, b in ((0, 1), (1, 2), (2, 0)):
                ha, hb = heights[:, a], heights[:, b]
                cross = (ha > 0) != (hb > 0)
                t = numpy.where(cross, ha / numpy.where(cross, ha - hb, 1),
                                0.0)
                where = corners[:, a] + (corners[:, b] - corners[:, a]) \
                    * t[:, None]
                crossings.append((cross, where))
            count = sum(c.astype(int) for c, _w in crossings)
            two = count == 2
            if not two.any():
                continue
            ends = []
            for cross, where in crossings:
                ends.append(numpy.where(cross[:, None], where, numpy.nan))
            stacked = numpy.stack(ends, axis=1)[two]    # (k, 3, 3)
            # The two crossings of each triangle first, in edge order.
            order = numpy.argsort(numpy.isnan(stacked[:, :, 0]), axis=1,
                                  kind="stable")[:, :2]
            pairs = numpy.take_along_axis(stacked, order[:, :, None], axis=1)
            out.extend(map(tuple, pairs.reshape(-1, 3).tolist()))
        return out


class Cap:
    """The cut faces of every solid, hatched, under one node."""

    def __init__(self) -> None:
        from pivy import coin
        self.root = coin.SoSeparator()
        self.root.setName("NxtSectionCap")
        unpickable = coin.SoPickStyle()
        unpickable.style = coin.SoPickStyle.UNPICKABLE
        self.root.addChild(unpickable)
        #: The other sections' clips, in world space.
        self.trims = coin.SoGroup()
        self.root.addChild(self.trims)
        self.faces = coin.SoSeparator()
        hints = coin.SoShapeHints()
        # Lit from either side: the cap is seen from both.
        hints.vertexOrdering = coin.SoShapeHints.COUNTERCLOCKWISE
        hints.shapeType = coin.SoShapeHints.UNKNOWN_SHAPE_TYPE
        self.faces.addChild(hints)
        nearest = coin.SoComplexity()
        nearest.textureQuality = 0.01     # crisp hatch lines
        self.faces.addChild(nearest)
        offset = coin.SoPolygonOffset()
        offset.factor = CAP_FACTOR
        offset.units = CAP_UNITS
        self.faces.addChild(offset)
        self.pieces_node = coin.SoGroup()
        self.faces.addChild(self.pieces_node)
        self.root.addChild(self.faces)
        self.lines = coin.SoSeparator()
        light = coin.SoLightModel()
        light.model = coin.SoLightModel.BASE_COLOR
        self.lines.addChild(light)
        colour = coin.SoBaseColor()
        colour.rgb = OUTLINE_COLOUR
        self.lines.addChild(colour)
        style = coin.SoDrawStyle()
        style.lineWidth = OUTLINE_WIDTH
        self.lines.addChild(style)
        self.line_points = coin.SoCoordinate3()
        self.lines.addChild(self.line_points)
        self.line_set = coin.SoLineSet()
        self.lines.addChild(self.line_set)
        self.pieces: list[CapPiece] = []
        #: Solid names selected, and the one preselected.
        self.selected: set[str] = set()
        self.preselected = ""

    def trim_by(self, clips: list[Any]) -> None:
        self.trims.removeAllChildren()
        for clip in clips:
            self.trims.addChild(clip)

    def moving(self, segments: list[tuple[float, float, float]]) -> None:
        """While the plane moves: the outline only."""
        if self.root.findChild(self.faces) >= 0:
            self.root.removeChild(self.faces)
        if self.root.findChild(self.lines) < 0:
            self.root.addChild(self.lines)
        self.line_points.point.setNum(len(segments))
        if segments:
            self.line_points.point.setValues(0, len(segments), segments)
        self.line_set.numVertices.setValues(
            0, len(segments) // 2, [2] * (len(segments) // 2))
        self.line_set.numVertices.setNum(len(segments) // 2)

    def build(self, solids: list[Any], faces: list[list[Any]],
              image_of: Any, look_for: Any, tile: float, u: App.Vector,
              v: App.Vector, normal: App.Vector,
              trims_of: Any = None) -> None:
        """One textured mesh per solid's cut faces, in the outline's place.

        `trims_of(solid)`: the other sections' clips that cut that solid,
        and so its cap; a solid another section leaves whole keeps all.
        """
        self.pieces_node.removeAllChildren()
        self.pieces = []
        for solid, cut in zip(solids, faces):
            if not cut:
                continue
            try:
                piece = _piece(solid, cut, image_of(solid), look_for(solid),
                               normal)
                for clip in (trims_of(solid) if trims_of else ()):
                    piece.node.insertChild(clip, 0)
            except Exception as exc:  # noqa: BLE001 - that cap is left out
                log.error("section: could not cap %s: %s"
                          % (solid.name, exc))
                continue
            self.pieces.append(piece)
            self.pieces_node.addChild(piece.node)
        self.map(tile, u, v)
        self.paint()
        if self.root.findChild(self.lines) >= 0:
            self.root.removeChild(self.lines)
        if self.root.findChild(self.faces) < 0:
            self.root.addChild(self.faces)

    def map(self, tile: float, u: App.Vector, v: App.Vector) -> None:
        """Lay the hatch tile on the plane at this size."""
        for piece in self.pieces:
            uv = [(p.dot(u) / tile, p.dot(v) / tile) for p in piece.points]
            piece.coords.point.setValues(0, len(uv), uv)

    def paint(self) -> None:
        """Each cap in its solid's colour, or highlighted with it."""
        chosen, hovered = selection_colours()
        for piece in self.pieces:
            colour = (hovered if piece.name == self.preselected
                      else chosen if piece.name in self.selected
                      else piece.diffuse)
            piece.material.diffuseColor = colour


def _piece(solid: Any, cut: list[Any], image: bytes, look: Look,
           normal: App.Vector) -> CapPiece:
    import Part
    from pivy import coin
    compound = Part.makeCompound(cut)
    size = max(compound.BoundBox.DiagonalLength, 1e-6)
    points, triangles = compound.tessellate(size * CAP_TOLERANCE)
    node = coin.SoSeparator()
    material = coin.SoMaterial()
    material.diffuseColor = look.diffuse
    material.ambientColor = look.ambient
    material.specularColor = look.specular
    material.emissiveColor = look.emissive
    material.shininess = look.shininess
    node.addChild(material)
    texture = coin.SoTexture2()
    texture.image.setValue(coin.SbVec2s(TILE, TILE), 4, image)
    texture.model = coin.SoTexture2.MODULATE
    texture.wrapS = coin.SoTexture2.REPEAT
    texture.wrapT = coin.SoTexture2.REPEAT
    node.addChild(texture)
    coords = coin.SoTextureCoordinate2()
    node.addChild(coords)
    face_normal = coin.SoNormal()
    face_normal.vector = (normal.x, normal.y, normal.z)
    node.addChild(face_normal)
    binding = coin.SoNormalBinding()
    binding.value = coin.SoNormalBinding.OVERALL
    node.addChild(binding)
    vertices = coin.SoCoordinate3()
    vertices.point.setValues(0, len(points),
                             [(p.x, p.y, p.z) for p in points])
    node.addChild(vertices)
    mesh = coin.SoIndexedFaceSet()
    index: list[int] = []
    for a, b, c in triangles:
        index += [a, b, c, -1]
    mesh.coordIndex.setValues(0, len(index), index)
    mesh.textureCoordIndex.setValues(0, len(index), index)
    node.addChild(mesh)
    return CapPiece(solid.name, node, material, coords, look.diffuse,
                    [App.Vector(p) for p in points])


class Highlight:
    """Follows FreeCAD's selection, so the caps light up with their part."""

    def __init__(self, cap: Cap, names: Any, owner: Any) -> None:
        self._cap = cap
        #: The solids' names, to match against what is selected.
        self._names = names
        #: The solid a face of the exact cut belongs to, or "": the cut
        #: lies over the cap, so a click on the cap picks it.
        self._owner = owner

    def _which(self, obj: str, sub: str) -> str:
        owned = self._owner(obj, sub)
        if owned:
            return str(owned)
        names = self._names()
        for name in [obj] + (sub or "").split("."):
            if name in names:
                return name
        return ""

    def setPreselection(self, _doc: str, obj: str, sub: str) -> None:  # noqa: N802
        self._cap.preselected = self._which(obj, sub)
        self._cap.paint()

    def removePreselection(self, _doc: str, _obj: str, _sub: str) -> None:  # noqa: N802
        self._cap.preselected = ""
        self._cap.paint()

    def addSelection(self, _doc: str, obj: str, sub: str,  # noqa: N802
                     _pnt: Any = None) -> None:
        name = self._which(obj, sub)
        if name:
            self._cap.selected.add(name)
            self._cap.paint()

    def removeSelection(self, _doc: str, obj: str, sub: str) -> None:  # noqa: N802
        self.sync()

    def clearSelection(self, _doc: str) -> None:  # noqa: N802
        self._cap.selected.clear()
        self._cap.paint()

    def sync(self) -> None:
        """Read the whole selection again."""
        import FreeCADGui as Gui
        chosen: set[str] = set()
        for entry in Gui.Selection.getSelectionEx("", 0):
            for sub in list(entry.SubElementNames) or [""]:
                name = self._which(entry.ObjectName, sub)
                if name:
                    chosen.add(name)
        self._cap.selected = chosen
        self._cap.paint()
