"""Blends where several Nxt fillets meet at one vertex.

Rounds that meet at a vertex at an angle, or of opposite kinds (a
round on an outer edge running into a hollow at the foot of a boss),
cannot simply be cut and added one after another: near the vertex they
cut into each other. As other CAD systems do, each round is set back
from the vertex to where it stands clear of the others, and the hole
left between them is filled with one smooth patch. The patch is bounded
by the rounds' end sections and by curves on the faces they share.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import FreeCAD as App
import Part

from . import blend_fillet as bf

#: Extra setback past where the rounds stop touching, per radius.
MARGIN = 0.25
#: Steps per radius when searching how far rounds reach each other.
SEARCH_STEPS = 4
#: Points on each curve a patch boundary is built from.
BOUNDARY_POINTS = 24


@dataclass
class Arm:
    """One filleted edge, as it leaves a junction."""

    index: int
    edge: Any
    faces: list[Any]
    from_start: bool
    radius: float
    width: float = 0.0
    setback: float = 0.0
    station: Any = None
    away: Any = None
    edge_shape: Any = None

    def parameter(self, along: float) -> float:
        length = self.edge.Length
        at = max(0.0, min(length, along if self.from_start
                          else length - along))
        return float(self.edge.getParameterByLength(at))

    def contact(self, side: list[Any]) -> App.Vector:
        """Where the round touches the faces of `side`."""
        if _holds(side, self.faces[0]):
            return self.station.contact1
        return self.station.contact2


@dataclass
class Junction:
    """Arms around a vertex in order, and the faces between each pair.

    Between two arms lies one face, or faces meeting smoothly there.
    """

    point: App.Vector
    arms: list[Arm]
    shared: list[list[Any]]
    #: The ball's centre, where the junction is a sphere corner.
    centre: Any = None


def _holds(side: list[Any], face: Any) -> bool:
    return any(face.isSame(f) for f in side)


def _nearest(side: list[Any], point: App.Vector) -> Any:
    """The face of `side` that `point` lies on, or nearest."""
    if len(side) == 1:
        return side[0]
    vertex = Part.Vertex(point)
    return min(side, key=lambda f: f.distToShape(vertex)[0])


def _onto(side: list[Any], point: App.Vector) -> App.Vector:
    surface = _nearest(side, point).Surface
    u, v = surface.parameter(point)
    return surface.value(u, v)


def _side(shape: Any, face: Any, point: App.Vector,
          tolerance: float) -> list[Any]:
    """`face` and the faces carrying it on smoothly through `point`."""
    side = [face]
    normal = bf._normal(face, point)
    for edge in face.Edges:
        if edge.distToShape(Part.Vertex(point))[0] > tolerance:
            continue
        for other in bf._faces_of(shape, edge):
            if _holds(side, other):
                continue
            if 1 - abs(bf._normal(other, point).dot(normal)) < bf.MIN_TURN:
                side.append(other)
    return side


def _partners(shape: Any, a: Arm, b: Arm, point: App.Vector) -> bool:
    """Whether `b` simply carries `a` on: a tangent round of its kind."""
    tolerance = max(a.edge.Length, b.edge.Length) * 1e-6
    return (bf._runs_on(a.edge, b.edge, max(tolerance, 1e-7)) is not None
            and bf._convex_edge(shape, a.edge)
            == bf._convex_edge(shape, b.edge))


def _width(shape: Any, arm: Arm) -> float:
    """How far the arm's round reaches from its edge, across its faces."""
    along = min(arm.radius, arm.edge.Length / 4)
    found = bf._station(arm.faces[0], arm.faces[1], arm.edge,
                        arm.parameter(along), arm.radius, None)
    if found is None:
        return arm.radius
    station = found[0]
    return max((station.contact1 - station.point).Length,
               (station.contact2 - station.point).Length)


def _cycle(shape: Any, arms: list[Arm], point: App.Vector,
           tolerance: float) -> tuple[list[Arm], list[list[Any]]] | None:
    """The arms in order round the vertex, and the faces after each."""
    order: list[Arm] = [arms[0]]
    shared: list[list[Any]] = []
    face = arms[0].faces[1]
    while True:
        side = _side(shape, face, point, tolerance)
        shared.append(side)
        nxt = [a for a in arms if a is not order[-1]
               and any(_holds(side, f) for f in a.faces)]
        if len(nxt) != 1:
            return None
        arm = nxt[0]
        if arm is order[0]:
            break
        if arm in order:
            return None
        order.append(arm)
        face = arm.faces[1] if _holds(side, arm.faces[0]) else arm.faces[0]
    if len(order) != len(arms):
        return None
    return order, shared


def plan(shape: Any, edges: list[Any],
         radii: list[float]) -> list[Junction]:
    """The junctions among `edges` that get a blend, with setbacks.

    A vertex is one where two or more of the edges end, unless just two
    meet there as one round running on. Only vertices the rounds close
    all the way round take a patch.
    """
    tolerance = max(shape.BoundBox.DiagonalLength * 1e-7, 1e-7)
    points: list[App.Vector] = []
    for edge in edges:
        for vertex in edge.Vertexes:
            if not any((vertex.Point - p).Length < tolerance
                       for p in points):
                points.append(vertex.Point)
    junctions = []
    for point in points:
        arms = []
        for index, edge in enumerate(edges):
            faces = bf._faces_of(shape, edge)
            if len(faces) != 2 or edge.isClosed():
                continue
            ends = [(v.Point - point).Length < tolerance
                    for v in (edge.Vertexes[0], edge.Vertexes[-1])]
            if not any(ends):
                continue
            first = edge.valueAt(edge.FirstParameter)
            arms.append(Arm(index, edge, faces,
                            (first - point).Length < tolerance,
                            radii[index]))
        if len(arms) < 2:
            continue
        if len(arms) == 2 and _partners(shape, arms[0], arms[1], point):
            continue
        cycle = _cycle(shape, arms, point, tolerance * 100)
        if cycle is None:
            continue
        order, shared = cycle
        try:
            centre = _ball_corner(shape, order, shared, point)
            if centre is not None:
                junctions.append(Junction(point, order, shared, centre))
            elif _set_back(shape, order, point):
                junctions.append(Junction(point, order, shared))
        except Exception as exc:  # noqa: BLE001 - this one stays as is
            App.Console.PrintWarning("Nxt fillet: no blend at %s: %s\n"
                                     % (point, exc))
    return junctions


def _ball_corner(shape: Any, arms: list[Arm], shared: list[list[Any]],
                 point: App.Vector) -> App.Vector | None:
    """The ball's centre where three equal rounds meet on flat faces.

    Each round then stops where the ball touches it, and the ball itself
    rounds the corner. None for any other junction.
    """
    if len(arms) != 3 or len({round(a.radius, 9) for a in arms}) != 1:
        return None
    if any(len(side) != 1 or not isinstance(side[0].Surface, Part.Plane)
           for side in shared):
        return None
    if any(not bf._convex_edge(shape, a.edge) for a in arms):
        return None
    radius = arms[0].radius
    step = radius * 1e-3
    normals = []
    for side in shared:
        normal = App.Vector(side[0].Surface.Axis)
        if bf._contains(shape, point + normal * step, step * 0.1):
            normal = -normal
        normals.append(normal)
    n1, n2, n3 = normals
    volume = n1.dot(n2.cross(n3))
    if abs(volume) < 1e-6:
        return None
    centre = point - (n2.cross(n3) + n3.cross(n1) + n1.cross(n2)) * (
        radius / volume)
    for arm in arms:
        u0 = arm.parameter(0.0)
        away = arm.edge.tangentAt(u0)
        away.normalize()
        if not arm.from_start:
            away = -away
        along = (centre - point).dot(away)
        if along <= 0 or along >= arm.edge.Length * 0.95:
            return None
        arm.edge_shape = shape
        arm.setback = along
        u = arm.parameter(along)
        found = bf._station(arm.faces[0], arm.faces[1], arm.edge, u,
                            radius, True)
        if found is None:
            return None
        arm.station = found[0]
        arm.away = away
    return centre


def _set_back(shape: Any, arms: list[Arm], point: App.Vector) -> bool:
    """Each arm's setback: past where its round runs onto another's.

    A round's section reaches another round where one of its contacts
    lies within that round's reach of its edge.
    """
    for arm in arms:
        arm.width = _width(shape, arm)
        arm.edge_shape = shape
    step = min(a.radius for a in arms) / SEARCH_STEPS
    for arm in arms:
        radius = arm.radius
        others = [b for b in arms if b is not arm
                  and not _partners(shape, arm, b, point)]
        convex = bf._convex_edge(shape, arm.edge)
        reach = 0.0
        along = step
        while along < arm.edge.Length:
            found = bf._station(arm.faces[0], arm.faces[1], arm.edge,
                                arm.parameter(along), radius, convex)
            if found is not None:
                station = found[0]
                if any(min(b.edge.distToShape(Part.Vertex(c))[0]
                           for c in (station.contact1, station.contact2))
                       < b.width for b in others):
                    reach = along
                elif along > reach + 2 * (arm.width + radius):
                    break
            along += step
        arm.setback = reach + radius * MARGIN
        if arm.setback >= arm.edge.Length * 0.95:
            return False
        u = arm.parameter(arm.setback)
        found = bf._station(arm.faces[0], arm.faces[1], arm.edge, u,
                            radius, convex)
        if found is None:
            return False
        arm.station = found[0]
        away = arm.edge.tangentAt(u)
        away.normalize()
        arm.away = away if arm.from_start else -away
    return True


def trims(junctions: list[Junction]) -> dict[int, list[tuple[Any, Any]]]:
    """For each edge, the planes its round stops at: point, towards J."""
    out: dict[int, list[tuple[Any, Any]]] = {}
    for junction in junctions:
        for arm in junction.arms:
            out.setdefault(arm.index, []).append(
                (arm.station.point, -arm.away))
    return out


def _on_side(side: list[Any], points: list[App.Vector]) -> Any:
    placed = [_onto(side, p) for p in points]
    curve = Part.BSplineCurve()
    curve.interpolate(placed)
    return curve.toShape()


def _hermite(p: App.Vector, m0: App.Vector, q: App.Vector,
             m1: App.Vector, count: int) -> list[App.Vector]:
    points = []
    for i in range(count):
        t = i / (count - 1)
        points.append(p * (2 * t ** 3 - 3 * t ** 2 + 1)
                      + m0 * (t ** 3 - 2 * t ** 2 + t)
                      + q * (-2 * t ** 3 + 3 * t ** 2)
                      + m1 * (t ** 3 - t ** 2))
    return points


def _connector(side: list[Any], p: App.Vector, leaving: App.Vector,
               q: App.Vector, arriving: App.Vector, point: App.Vector,
               reach: float) -> tuple[Any, str] | None:
    """A curve on `side` from `p` to `q`, leaving and arriving tangent.

    Arms leaving the junction the same way meet it in a pocket: the
    curve runs in to the junction and back out.
    """
    gap = (q - p).Length
    if gap < 1e-6:
        return None
    if leaving.dot(arriving) >= 0.2:
        points = _hermite(p, leaving * gap, q, arriving * gap,
                          BOUNDARY_POINTS)
        return _on_side(side, points), LONG
    if gap <= reach:
        if len(side) == 1 and isinstance(side[0].Surface, Part.Plane):
            return Part.LineSegment(p, q).toShape(), SHORT
        points = [p + (q - p) * (i / (BOUNDARY_POINTS - 1))
                  for i in range(BOUNDARY_POINTS)]
        return _on_side(side, points), SHORT
    else:
        across = q - p
        across.normalize()
        first = (point - p).Length
        last = (q - point).Length
        points = _hermite(p, leaving * first, point, across * first,
                          BOUNDARY_POINTS)
        points += _hermite(point, across * last, q, arriving * last,
                           BOUNDARY_POINTS)[1:]
    return _on_side(side, points), POCKET


#: Kinds of curve between two arms on the faces they share: short
#: across the end of a corridor, long along one, or into the junction
#: and back out of it.
SHORT, LONG, POCKET = "short", "long", "pocket"


def outline(junction: Junction) -> list[tuple[Any, Any]]:
    """The hole's boundary in order, each curve with a strip beside it.

    The strip lies on the round or face just outside that curve; the
    patch is made tangent to it.
    """
    step = min(a.radius for a in junction.arms) * RAIL
    curves = _loop(junction)
    middle = _middle_of(curves)
    out = []
    for curve, face, arm, _kind in curves:
        if face is None:
            beside = _round_beside(arm, curve, step)
        else:
            beside = _face_beside(curve, face, middle, step)
        out.append((curve, Part.makeRuledSurface(curve, beside)))
    return out


#: A curve of a junction's outline: the curve, the faces it lies on
#: (None for a round's end arc), its arm, and its kind.
Piece = tuple[Any, Any, Arm, str]


def _loop(junction: Junction) -> list[Piece]:
    """The hole's outline in order: end arcs and the curves between."""
    count = len(junction.arms)
    curves: list[Piece] = []
    for i, arm in enumerate(junction.arms):
        before = junction.shared[i - 1]
        after = junction.shared[i]
        start, end = arm.contact(before), arm.contact(after)
        curves.append((bf._blend(start, end, arm.station.centre,
                                 arm.radius), None, arm, "arc"))
        nxt = junction.arms[(i + 1) % count]
        link = _connector(after, end, -arm.away, nxt.contact(after),
                          nxt.away, junction.point, arm.width + nxt.width)
        if link is not None:
            curves.append((link[0], after, arm, link[1]))
    return curves


def _middle_of(curves: list[Piece]) -> App.Vector:
    middle = App.Vector()
    for curve, _side, _arm, _kind in curves:
        middle += curve.valueAt(curve.FirstParameter)
    return middle * (1.0 / len(curves))


def _round_beside(arm: Arm, arc: Any, step: float) -> Any:
    """The arm's end arc, moved a step further from the junction."""
    radius = arm.radius
    u = arm.parameter(arm.setback + step)
    found = bf._station(arm.faces[0], arm.faces[1], arm.edge, u, radius,
                        bf._convex_edge(arm.edge_shape, arm.edge))
    if found is None:
        raise ValueError("the round ends too close to the junction")
    station = found[0]
    first = arc.valueAt(arc.FirstParameter)
    a, b = station.contact1, station.contact2
    if (a - first).Length > (b - first).Length:
        a, b = b, a
    return bf._blend(a, b, station.centre, radius)


def _face_beside(curve: Any, side: list[Any], middle: App.Vector,
                 step: float) -> Any:
    """The curve moved a step across `side`, away from the hole."""
    points = []
    for k in range(BOUNDARY_POINTS):
        u = curve.FirstParameter + (curve.LastParameter
                                    - curve.FirstParameter) * k / (
                                        BOUNDARY_POINTS - 1)
        p = curve.valueAt(u)
        across = bf._normal(_nearest(side, p), p).cross(curve.tangentAt(u))
        across.normalize()
        if across.dot(middle - p) > 0:
            across = -across
        points.append(_onto(side, p + across * step))
    spline = Part.BSplineCurve()
    spline.interpolate(points)
    return spline.toShape()


#: How far outside the hole the tangency strips reach, per radius.
RAIL = 0.3
#: Surface::Filling's code for tangent continuity.
G1 = 1
#: Spans the patch may use along each direction.
FILL_SEGMENTS = 24
#: Points along each boundary curve the patch is fitted to.
FILL_POINTS = 15


def patch(junction: Junction,
          parts: list[tuple[Any, Any]] | None = None) -> Any:
    """The face filling the hole, tangent to all round it."""
    import Surface  # noqa: F401 - registers Surface::Filling

    if parts is None:
        parts = outline(junction)
    radius = min(a.radius for a in junction.arms)
    doc = App.newDocument("NxtJunction", hidden=True, temp=True)
    try:
        holder = doc.addObject("Part::Feature", "Strips")
        holder.Shape = Part.makeCompound([strip for _c, strip in parts])
        shape = holder.Shape
        numbers = {e.hashCode(): i for i, e in enumerate(shape.Edges)}
        edges, faces = [], []
        # A compound keeps its faces in the order they were given.
        for face_index, (curve, _strip) in enumerate(parts):
            face = shape.Faces[face_index]
            mid = Part.Vertex(curve.valueAt((curve.FirstParameter
                                             + curve.LastParameter) / 2))
            edge = min(face.Edges, key=lambda e: e.distToShape(mid)[0])
            edges.append("Edge%d" % (numbers[edge.hashCode()] + 1))
            faces.append("Face%d" % (face_index + 1))
        filling = doc.addObject("Surface::Filling", "Patch")
        filling.BoundaryEdges = [(holder, name) for name in edges]
        filling.BoundaryFaces = faces
        filling.BoundaryOrder = [G1] * len(edges)
        filling.PointsOnCurve = FILL_POINTS
        filling.Tolerance3d = radius * 1e-5
        filling.MaximumSegments = FILL_SEGMENTS
        doc.recompute()
        if filling.Shape.isNull() or not filling.Shape.Faces:
            raise ValueError("the blend could not be filled")
        return filling.Shape.Faces[0].copy()
    finally:
        App.closeDocument(doc.Name)


def applied(shape: Any, junction: Junction) -> Any:
    """`shape` with the hole at the junction cut out and patched.

    A corner of three equal rounds on flat faces takes a sphere; a
    corridor between rounds takes a blend swept along it; anything
    else, or a sweep that does not close, a fitted patch. The hole's
    outline is printed onto the part's faces; the faces it encloses give
    way to the patch, and the rest is sewn to it.
    """
    if junction.centre is not None:
        with bf.timed("sphere corner"):
            return _sphere_corner(shape, junction)
    try:
        with bf.timed("swept blend"):
            swept = _swept(junction, _loop(junction))
            done = _sewn(shape, *swept) if swept is not None else None
        if done is not None and done.isValid():
            return done
    except Exception:  # noqa: BLE001 - the fitted patch next
        pass
    with bf.timed("fitted patch"):
        parts = outline(junction)
        return _sewn(shape, [patch(junction, parts)],
                     [curve for curve, _strip in parts])


def _sewn(shape: Any, patch_faces: list[Any], loop: list[Any],
          gap: float = 0.0) -> Any:
    tolerance = max(shape.BoundBox.DiagonalLength * 1e-7, 1e-7)
    slack = max(max(f.getTolerance(1) for f in patch_faces) * 10,
                tolerance * 100)
    # The outline lies on the part only as closely as it was fitted.
    off = max(shape.distToShape(Part.Vertex(c.valueAt(
        c.FirstParameter + (c.LastParameter - c.FirstParameter) * k / 4)))[0]
        for c in loop for k in range(5))
    printed = shape.generalFuse([Part.makeCompound(loop)],
                                max(tolerance * 10, off * 2))[0]
    if len(printed.Solids) != 1:
        raise ValueError("the blend's outline does not lie on the part")
    faces = printed.Solids[0].Faces

    outline = Part.makeCompound(loop)
    reach = outline.BoundBox
    reach.enlarge(slack)

    def on_loop(edge: Any) -> bool:
        if not reach.intersect(edge.BoundBox):
            return False
        span = edge.LastParameter - edge.FirstParameter
        return all(outline.distToShape(Part.Vertex(edge.valueAt(
            edge.FirstParameter + span * k / 4)))[0] < slack
                   for k in range(5))

    border = [e for e in printed.Solids[0].Edges if on_loop(e)]
    kept = _outside(faces, border)
    if len(kept) == len(faces):
        raise ValueError("the blend's outline does not close on the part")
    sewn = Part.makeCompound(kept + list(patch_faces))
    sewn.sewShape(max(max(f.getTolerance(1) for f in patch_faces) * 2,
                      tolerance * 10, gap))
    if len(sewn.Shells) != 1 or not sewn.Shells[0].isClosed():
        raise ValueError("the blend does not close the part")
    solid = Part.Solid(sewn.Shells[0])
    if solid.Volume < 0:
        solid.reverse()
    return solid


#: Sections along a swept blend.
SWEEP_SECTIONS = 16
#: Points along each section curve of a swept blend.
SECTION_POINTS = 12


def _swept(junction: Junction, pieces: list[Piece]
           ) -> tuple[list[Any], list[Any]] | None:
    """A blend lofted along a corridor between rounds; None otherwise.

    Each section runs from one long side to the other, leaving and
    arriving tangent to the faces there; the end sections are the
    rounds' own ends.
    """
    kinds = [piece[3] for piece in pieces]
    if kinds.count(LONG) == 2 and POCKET not in kinds:
        first = kinds.index(LONG)
        order = pieces[first:] + pieces[:first]
        second = [p[3] for p in order].index(LONG, 1)
        side1, side2 = order[0], order[second]
        wires = [_wire_of(order[second + 1:], True)]
        wires += [_through(p) for p in _middles(side1, side2)]
        wires.append(_wire_of(order[1:second], False))
    else:
        return None
    loft = Part.makeLoft(wires, False, False, False)
    counts: dict[int, int] = {}
    for face in loft.Faces:
        for edge in face.Edges:
            counts[edge.hashCode()] = counts.get(edge.hashCode(), 0) + 1
    border = [e for e in loft.Edges if counts.get(e.hashCode()) == 1
              and e.Length > 1e-9]
    return list(loft.Faces), border


def _wire_of(pieces: list[Piece], backwards: bool) -> Any:
    """Consecutive pieces as one wire, run backwards if asked.

    The rounds' own end curves, so the blend meets them edge for edge.
    """
    edges = [piece[0] for piece in pieces]
    if backwards:
        edges = [edge.reversed() for edge in reversed(edges)]
    return Part.Wire(edges)


def _through(points: list[App.Vector]) -> Any:
    curve = Part.BSplineCurve()
    curve.interpolate(points)
    return Part.Wire([curve.toShape()])


def _middles(side1: Piece, side2: Piece) -> list[list[App.Vector]]:
    """Sections between the long sides: side1 forwards, side2 back.

    Each leaves side1's faces and arrives on side2's tangent to them.
    """
    one, two = side1[0], side2[0]
    out = []
    count = SWEEP_SECTIONS
    for k in range(1, count):
        t = k / count
        p = one.valueAt(one.getParameterByLength(one.Length * t))
        q = two.valueAt(two.getParameterByLength(two.Length * (1 - t)))
        gap = (q - p).Length
        if gap < 1e-9:
            continue
        if bf._flat and bf._flat[-1]:
            # A chamfer's sections are straight, as its ends are.
            out.append([p + (q - p) * (i / (SECTION_POINTS - 1))
                        for i in range(SECTION_POINTS)])
            continue
        leave = _into(side1[1], one, p, q)
        arrive = -_into(side2[1], two, q, p)
        out.append(_hermite(p, leave * gap, q, arrive * gap,
                            SECTION_POINTS))
    return out


def _into(side: list[Any], curve: Any, at: App.Vector,
          towards: App.Vector) -> App.Vector:
    """Across `side`'s faces from the curve at `at`, towards the hole."""
    u = curve.Curve.parameter(at)
    across = bf._normal(_nearest(side, at), at).cross(curve.tangentAt(u))
    across.normalize()
    return across if across.dot(towards - at) > 0 else -across


def _sphere_corner(shape: Any, junction: Junction) -> Any:
    """The corner of three equal rounds on flat faces, as a sphere.

    What is left of the corner between the rounds' ends, less the ball
    there, is cut away.
    """
    size = shape.BoundBox.DiagonalLength * 4
    tolerance = max(shape.BoundBox.DiagonalLength * 1e-7, 1e-7)
    corner: Any = Part.makeBox(size, size, size, junction.point
                               - App.Vector(size, size, size) * 0.5)
    beyond: list[tuple[App.Vector, App.Vector]] = []
    for side in junction.shared:
        face = side[0]
        normal = App.Vector(face.Surface.Axis)
        if not _inside_of(shape,
                          junction.point - normal * tolerance * 100):
            normal = -normal
        beyond.append((junction.point, normal))
    for arm in junction.arms:
        beyond.append((arm.station.point, App.Vector(arm.away)))
    cell = _cell(junction.point, size, beyond)
    if cell is not None:
        corner = cell
    else:
        for point, away in beyond:
            corner = corner.cut(bf._half_space(point, away, size))
    radius = junction.arms[0].radius
    tool = corner.cut(Part.makeSphere(radius, junction.centre))
    done = shape.cut(tool, tolerance * 10)
    if len(done.Solids) != 1:
        raise ValueError("the corner did not cut cleanly")
    return done.Solids[0]


def _cell(centre: App.Vector, size: float,
          beyond: list[tuple[App.Vector, App.Vector]]) -> Any:
    """The box about `centre` less each half space in `beyond`, or None.

    Built directly as a convex polyhedron: no boolean per plane. None if
    the planes leave no solid. Each half space is (a point on its plane,
    the way it extends).
    """
    half = size / 2
    planes: list[tuple[App.Vector, float]] = []
    for axis in (App.Vector(1, 0, 0), App.Vector(0, 1, 0),
                 App.Vector(0, 0, 1)):
        planes.append((axis, axis.dot(centre) + half))
        planes.append((-axis, -axis.dot(centre) + half))
    for point, away in beyond:
        normal = App.Vector(away)
        normal.normalize()
        planes.append((normal, normal.dot(point)))
    eps = size * 1e-9
    corners: list[App.Vector] = []
    for i in range(len(planes)):
        for j in range(i + 1, len(planes)):
            for k in range(j + 1, len(planes)):
                at = _meet(planes[i], planes[j], planes[k])
                if at is None or any(n.dot(at) > d + eps
                                     for n, d in planes):
                    continue
                if not any((at - c).Length < eps * 10 for c in corners):
                    corners.append(at)
    faces = []
    for normal, d in planes:
        on = [c for c in corners if abs(normal.dot(c) - d) < eps * 10]
        if len(on) < 3:
            continue
        middle = sum(on, App.Vector()) * (1.0 / len(on))
        across = on[0] - middle
        across.normalize()
        upward = normal.cross(across)
        on.sort(key=lambda c: math.atan2((c - middle).dot(upward),
                                         (c - middle).dot(across)))
        faces.append(Part.Face(Part.makePolygon(on + [on[0]])))
    if len(faces) < 4:
        return None
    solid = Part.Solid(Part.Shell(faces))
    if solid.Volume < 0:
        solid.reverse()
    return solid if solid.isValid() else None


def _meet(a: tuple[App.Vector, float], b: tuple[App.Vector, float],
          c: tuple[App.Vector, float]) -> App.Vector | None:
    """Where three planes (normal, offset) meet; None if they do not."""
    (na, da), (nb, db), (nc, dc) = a, b, c
    cross = nb.cross(nc)
    det = na.dot(cross)
    if abs(det) < 1e-12:
        return None
    return (cross * da + nc.cross(na) * db + na.cross(nb) * dc) * (1 / det)


def _inside_of(shape: Any, point: App.Vector) -> bool:
    return bool(shape.isInside(point, 1e-9, True))


def _outside(faces: list[Any], border: list[Any]) -> list[Any]:
    """The faces reached from the largest without crossing `border`."""
    blocked = {e.hashCode() for e in border}
    owners: dict[int, list[int]] = {}
    for i, face in enumerate(faces):
        for edge in face.Edges:
            owners.setdefault(edge.hashCode(), []).append(i)
    start = max(range(len(faces)), key=lambda i: faces[i].Area)
    seen, waiting = {start}, [start]
    while waiting:
        for edge in faces[waiting.pop()].Edges:
            key = edge.hashCode()
            if key in blocked:
                continue
            for j in owners.get(key, []):
                if j not in seen:
                    seen.add(j)
                    waiting.append(j)
    return [faces[i] for i in sorted(seen)]
