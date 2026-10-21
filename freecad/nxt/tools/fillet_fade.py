"""Rounds running out where a crease fades to tangent.

A crease running on tangentially from a rounded one can fade out: the
side of a plate tangent to a boss, past the hollow round at the boss's
foot, meets that round at a crease that flattens to nothing where the
side turns into the boss. Rolling on from the lead, the ball leaves the
lead's other face for the faded crease's (the hand-over) and, held
between that face and the face both share, shrinks to nothing at the
tangent end.

A boolean with a lofted tool would graze the faces along the contacts,
where the ball touches them, and leave slivers. Instead the part is
rebuilt there: its faces are split along the contact curves, made on
the faces' own surfaces, the strips between them and the crease are
dropped, and the ball's surface, lofted from its sections to a point at
the run-out, is sewn in. The lead's own round stops a little before the
hand-over, and the new surface starts on its last section.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import FreeCAD as App
import Part

from . import blend_fillet as bf

#: How far before the hand-over, in radii, the tool takes over from the
#: lead's: where the ball is still well on the lead's face.
LEAD_IN = 0.5
#: Most distance between sections, in radii.
STEP = 0.15
#: Fewest sections along the faded crease itself.
MIN_SECTIONS = 12
#: The gap between the ball's contacts, in radii, at which the round has
#: run out.
RUN_OUT = 1e-3
#: How far, in radii, a contact may stray past its face, as onto one
#: carrying on from it tangentially.
ROLL_OFF = 1e-2
#: Points along each edge checked against the new surface.
STRAY_SAMPLES = 24
#: Least distance, in radii, between sections.
MIN_GAP = 1e-2
#: How closely a settled ball must touch both faces, in radii.
SETTLED = 1e-6
#: How far, in radii, the new faces' edges may lie off their surfaces.
DEVIATION = 1e-3
#: Sewing tolerance, in radii, for the new surface's edges against the
#: contact curves it was lofted through.
SEWING = 1e-4
#: Points tried along the lead for one where the ball sits on its face.
HAND_OVER_SAMPLES = 16
#: Halvings when finding the hand-over.
HAND_OVER_STEPS = 30
#: Sections between checks that the ball stays on its faces.
CHECK_EVERY = 3
#: Sections between those of the corner's rough outline.
CORNER_EVERY = 4


class FadeError(ValueError):
    """The round could not be carried along the fading crease."""


@dataclass
class Fade:
    """How a round runs on along a fading crease.

    `lead` is the chosen crease it carries on from (None when there is
    none), `shared` the face both run along, `before` the lead's other
    face and `after` the faded crease's. The tool starts at `start` on
    the lead.
    """

    edge: Any
    end: App.Vector
    joint: App.Vector
    shared: Any
    after: Any
    convex: bool
    lead: Any = None
    before: Any = None
    start: float = 0.0
    handover: float = 0.0
    #: Whether the hand-over is on the faded crease rather than the lead.
    late: bool = False


def fading_end(shape: Any, edge: Any) -> App.Vector | None:
    """The end at which a crease fades out to tangent, if it does.

    Sharp along its middle and at its other end, so only a crease that
    runs out, not one that is tangent all along.
    """
    faces = bf._faces_of(shape, edge)
    if len(faces) != 2:
        return None
    first, last = edge.FirstParameter, edge.LastParameter

    def turn(t: float) -> float:
        point = edge.valueAt(first + (last - first) * t)
        return 1 - abs(bf._normal(faces[0], point).dot(
            bf._normal(faces[1], point)))

    if turn(0.5) < bf.MIN_TURN:
        return None
    for end, other in ((0.0, 0.98), (1.0, 0.02)):
        if turn(end) < bf.MIN_TURN <= turn(other):
            return edge.valueAt(first + (last - first) * end)
    return None


def fades(shape: Any, edge: Any) -> bool:
    return fading_end(shape, edge) is not None


def _foot(face: Any, point: App.Vector) -> App.Vector:
    """The nearest point of the face's whole surface."""
    u, v = face.Surface.parameter(point)
    return face.Surface.value(u, v)


def settled(face1: Any, face2: Any, point: App.Vector,
            tangent: App.Vector, centre: App.Vector,
            radius: float) -> bf.Station:
    """The ball across `point` touching both surfaces as they are.

    From a centre on the ball's side, it is moved to be the radius from
    each surface's nearest point, and kept in the plane across the edge
    at `point`, until it settles.
    """
    for _ in range(bf.ROLL_STEPS * 4):
        f1, f2 = _foot(face1, centre), _foot(face2, centre)
        n1, n2 = centre - f1, centre - f2
        if n1.Length < radius * SETTLED or n2.Length < radius * SETTLED:
            raise FadeError("the ball fell onto a face")
        n1.normalize()
        n2.normalize()
        rows = App.Matrix(n1.x, n1.y, n1.z, 0, n2.x, n2.y, n2.z, 0,
                          tangent.x, tangent.y, tangent.z, 0, 0, 0, 0, 1)
        if abs(rows.determinant()) < 1e-12:
            raise FadeError("the faces run parallel to the ball")
        moved = rows.inverse().multVec(App.Vector(
            radius + n1.dot(f1), radius + n2.dot(f2), tangent.dot(point)))
        step = (moved - centre).Length
        centre = moved
        if step < radius * SETTLED:
            break
    f1, f2 = _foot(face1, centre), _foot(face2, centre)
    if any(abs((centre - f).Length - radius) > radius * 1e-4
           for f in (f1, f2)):
        raise FadeError("the ball would not settle between the faces")
    return bf.Station(point, tangent, centre, f1, f2)


def section(station: bf.Station, radius: float) -> Any:
    """The ball's arc closed by a corner past the edge, in its own plane.

    Contacts on curved faces need not lie across the edge; in their own
    plane the section stays flat. The corner is beyond the edge, so the
    sides cross the faces rather than run along them.
    """
    centre = station.centre
    out = (station.contact1 - centre) + (station.contact2 - centre)
    out.normalize()
    corner = centre + out * ((station.point - centre).Length + radius)
    return Part.Wire([
        Part.LineSegment(corner, station.contact1).toShape(),
        bf._blend(station.contact1, station.contact2, centre, radius),
        Part.LineSegment(station.contact2, corner).toShape(),
    ])


#: Per fillet being solved, each fading crease's plan by its hash.
_plans: list[dict[int, Fade | None]] = []
#: Per fillet being solved, every crease chosen, fading ones included.
_chosen: list[list[Any]] = []
#: Per fillet being solved, each face's fellows on its surface, by hash.
_kin: list[dict[int, list[Any]]] = []


def begin(edges: list[Any]) -> None:
    """Start solving a fillet of these creases."""
    _plans.append({})
    _chosen.append(edges)
    _kin.append({})


def end() -> None:
    _plans.pop()
    _chosen.pop()
    _kin.pop()


def _fellows(shape: Any, face: Any) -> list[Any]:
    """The shape's faces on the same surface as `face`, itself included."""
    memo = _kin[-1] if _kin else {}
    key = face.hashCode()
    if key not in memo:
        memo[key] = [f for f in shape.Faces if _same_surface(f, face)]
    return memo[key]


def plan(shape: Any, edge: Any, radius: float) -> Fade | None:
    """The fading crease's plan, worked out once per fillet.

    None if it does not fade.
    """
    memo = _plans[-1] if _plans else {}
    key = edge.hashCode()
    if key not in memo:
        memo[key] = _planned(shape, edge, radius) \
            if fades(shape, edge) else None
    return memo[key]


def _lead(shape: Any, edge: Any, end: App.Vector) -> tuple[Any, Any] | None:
    """The chosen crease this one carries on from, and their shared face."""
    tolerance = max(shape.BoundBox.DiagonalLength * 1e-7, 1e-7)
    own = bf._faces_of(shape, edge)
    found = []
    for other in (_chosen[-1] if _chosen else []):
        if other.isSame(edge) or fades(shape, other):
            continue
        at = bf._runs_on(other, edge, tolerance)
        if at is None or bf._near(at, end, tolerance):
            continue
        faces = bf._faces_of(shape, other)
        shared = [f for f in faces if any(_same_surface(f, g) for g in own)]
        if len(shared) != 1:
            continue
        # The ball hands over from the lead's other face to the faded
        # crease's: the two must meet tangentially where the creases do.
        before = next(f for f in faces if not f.isSame(shared[0]))
        after = next(f for f in own if not _same_surface(f, shared[0]))
        if 1 - abs(bf._normal(before, at).dot(bf._normal(after, at))) \
                > bf.TANGENT_TOLERANCE * 10:
            continue
        found.append((other.Length, other, shared[0]))
    if not found:
        return None
    _length, other, shared_face = max(found, key=lambda f: f[0])
    return other, shared_face


def _same_surface(a: Any, b: Any) -> bool:
    """Whether two faces lie on one surface.

    The same face, or two that a seam or an earlier split has parted.
    """
    if a.isSame(b):
        return True
    if type(a.Surface) is not type(b.Surface):
        return False
    tolerance = max(a.BoundBox.DiagonalLength, b.BoundBox.DiagonalLength) \
        * 1e-7 + 1e-7
    try:
        for face, other in ((a, b), (b, a)):
            points = [v.Point for v in face.Vertexes[:3]]
            inside = bf._point_on(face, tolerance)
            if inside is not None:
                points.append(inside)
            for point in points:
                if (_foot(other, point) - point).Length > tolerance:
                    return False
    except Exception:  # noqa: BLE001 - no way to tell: not the same
        return False
    return True


def _toward(edge: Any, u: float, point: App.Vector) -> App.Vector:
    """The edge's direction at `u`, turned to head for `point`."""
    tangent = edge.tangentAt(u)
    tangent.normalize()
    if tangent.dot(point - edge.valueAt(u)) < 0:
        tangent = -tangent
    return tangent


def _planned(shape: Any, edge: Any, radius: float) -> Fade:
    end = fading_end(shape, edge)
    if end is None:
        raise FadeError("the crease does not fade out")
    first, last = edge.FirstParameter, edge.LastParameter
    joint = edge.valueAt(last if bf._near(edge.valueAt(first), end, 1e-9)
                         else first)
    convex = bf._convex_edge(shape, edge)
    if convex is None:
        raise FadeError("its kind of corner could not be told")
    found = _lead(shape, edge, end)
    if found is None:
        shared = bf._faces_of(shape, edge)[0]
        after = bf._faces_of(shape, edge)[1]
        return Fade(edge, end, joint, shared, after, convex)
    lead, shared = found
    after = next(f for f in bf._faces_of(shape, edge)
                 if not _same_surface(f, shared))
    before = next(f for f in bf._faces_of(shape, lead)
                  if not f.isSame(shared))
    fade = Fade(edge, end, joint, shared, after, convex, lead, before)
    fade.handover, fade.late = _handover(shape, fade, radius)
    fade.start = _back(lead, lead.Curve.parameter(joint) if fade.late
                       else fade.handover, joint, radius * LEAD_IN)
    return fade


def _far_end(lead: Any, joint: App.Vector) -> float:
    first, last = lead.FirstParameter, lead.LastParameter
    return first if bf._near(lead.valueAt(last), joint, 1e-6) or (
        (lead.valueAt(last) - joint).Length
        < (lead.valueAt(first) - joint).Length) else last


def _handover(shape: Any, fade: Fade, radius: float) -> tuple[float, bool]:
    """Where the ball's contact leaves the lead's face.

    And whether that is on the faded crease, past the joint, rather than
    on the lead.
    """
    lead = fade.lead
    at_joint = lead.Curve.parameter(fade.joint)
    far = _far_end(lead, fade.joint)
    tolerance = radius * SETTLED

    def held_on(along: Any, u: float, towards: App.Vector,
                guess: App.Vector | None) -> bf.Station:
        if guess is None:
            rough = bf._station(fade.before, fade.shared, lead, u, radius,
                                fade.convex)
            if rough is None:
                raise FadeError("the faces meet tangentially")
            guess = rough[0].centre
        return settled(fade.shared, fade.before, along.valueAt(u),
                       _toward(along, u, towards), guess, radius)

    befores = _fellows(shape, fade.before)

    def on(held: bf.Station) -> bool:
        return any(f.isInside(held.contact2, tolerance, True)
                   for f in befores)

    at = held_on(lead, at_joint, fade.joint, None)
    if on(at):
        return _late_handover(fade, at, on, radius), True
    # The nearest of a few points along the lead where the ball sits on
    # its face: its far end may run out of that face too. Each ball is
    # settled from the last one's centre, which is close by.
    guess = at.centre
    for k in range(1, HAND_OVER_SAMPLES + 1):
        u = at_joint + (far - at_joint) * k / HAND_OVER_SAMPLES
        ball = held_on(lead, u, fade.joint, guess)
        guess = ball.centre
        if on(ball):
            far = u
            break
    else:
        raise FadeError("the ball never sits on the lead's face")
    near = at_joint
    for _ in range(HAND_OVER_STEPS):
        middle = (near + far) / 2
        ball = held_on(lead, middle, fade.joint, guess)
        guess = ball.centre
        if on(ball):
            far = middle
        else:
            near = middle
    return far, False


def _late_handover(fade: Fade, at_joint: bf.Station, on: Any,
                   radius: float) -> float:
    """Where along the faded crease the ball leaves the lead's face."""
    edge = fade.edge
    first, last = edge.FirstParameter, edge.LastParameter
    a = first if bf._near(edge.valueAt(first), fade.joint, 1e-6) else last
    b = last if a == first else first
    guess = at_joint.centre

    def held(u: float) -> bf.Station:
        return settled(fade.shared, fade.before, edge.valueAt(u),
                       _toward(edge, u, fade.end), guess, radius)

    near = a
    for k in range(1, HAND_OVER_SAMPLES * 4 + 1):
        u = a + (b - a) * k / (HAND_OVER_SAMPLES * 4)
        try:
            ball = held(u)
        except FadeError:
            break
        if not on(ball):
            far = u
            break
        near, guess = u, ball.centre
    else:
        raise FadeError("the ball never leaves the lead's face")
    for _ in range(HAND_OVER_STEPS):
        middle = (near + far) / 2
        try:
            ball = held(middle)
            stays = on(ball)
        except FadeError:
            stays = False
        if stays:
            near, guess = middle, ball.centre
        else:
            far = middle
    return near


def _back(lead: Any, handover: float, joint: App.Vector,
          distance: float) -> float:
    """The parameter `distance` back along the lead from the hand-over.

    Kept to the first half of the lead from there.
    """
    far = _far_end(lead, joint)
    low, high = sorted((handover, far))
    room = lead.Curve.length(low, high)
    run = min(distance, room / 2)
    if run <= 0:
        return handover
    # Along the curve: halve towards the parameter at that length.
    a, b = handover, far
    for _ in range(HAND_OVER_STEPS):
        middle = (a + b) / 2
        if lead.Curve.length(*sorted((handover, middle))) < run:
            a = middle
        else:
            b = middle
    return (a + b) / 2


def _guide(fade: Fade, radius: float) -> list[tuple[Any, Any, float]]:
    """(edge, face, parameter) for each section, from start to end."""
    step = radius * STEP
    stations: list[tuple[Any, Any, float]] = []

    def run(along: Any, a: float, b: float, face: Any,
            closing: bool = False) -> None:
        length = along.Curve.length(*sorted((a, b)))
        if length < radius * 1e-6:
            return
        # Closer near the run-out, and no wider at its start than the
        # step, so the loft's sections change spacing gently.
        count = max(MIN_SECTIONS if closing else 2,
                    math.ceil((2 if closing else 1) * length / step))
        for k in range(count + 1):
            if stations and k == 0:
                continue
            share = 1 - (1 - k / count) ** 2 if closing else k / count
            stations.append((along, face, a + (b - a) * share))

    edge = fade.edge
    first, last = edge.FirstParameter, edge.LastParameter
    a, b = ((first, last) if bf._near(edge.valueAt(first), fade.joint, 1e-6)
            else (last, first))
    if fade.lead is not None:
        lead = fade.lead
        at_joint = lead.Curve.parameter(fade.joint)
        if fade.late:
            run(lead, fade.start, at_joint, fade.before)
            run(edge, a, fade.handover, fade.before)
            a = fade.handover
        else:
            run(lead, fade.start, fade.handover, fade.before)
            run(lead, fade.handover, at_joint, fade.after)
    run(edge, a, b, fade.after, closing=True)
    return stations


def stations(shape: Any, fade: Fade,
             radius: float) -> list[tuple[bf.Station, bool]]:
    """The ball held at each section, from the start to the run-out.

    With each, whether it sits on the lead's face there rather than the
    faded crease's.
    """
    held_all: list[tuple[bf.Station, bool]] = []
    centre = None
    for along, face, u in _guide(fade, radius):
        point = along.valueAt(u)
        tangent = _toward(along, u, fade.end)
        if centre is None:
            first = fade.before if fade.lead is not None else fade.after
            rough = bf._station(first, fade.shared, along, u, radius,
                                fade.convex)
            if rough is None:
                raise FadeError("the faces meet tangentially")
            centre = rough[0].centre
        try:
            held = settled(fade.shared, face, point, tangent, centre,
                           radius)
        except FadeError:
            if along is not fade.edge or not held_all:
                raise
            break                       # at the run-out, faces tangent
        if (held.contact1 - held.contact2).Length < radius * RUN_OUT:
            break
        # The contacts move smoothly: every few sections tell whether
        # the ball rolls off its faces.
        if len(held_all) % CHECK_EVERY == 0:
            _check_on(shape, fade.shared, held.contact1, radius)
            _check_on(shape, face, held.contact2, radius)
        centre = held.centre
        # Sections too close together upset the loft through them.
        on = face is fade.before
        if held_all and on == held_all[-1][1] and (
                held.point - held_all[-1][0].point).Length < radius * MIN_GAP:
            continue
        held_all.append((held, on))
    if len(held_all) < 2:
        raise FadeError("too little of the crease to round")
    last, on = held_all[-1]
    _check_on(shape, fade.shared, last.contact1, radius)
    _check_on(shape, fade.before if on else fade.after, last.contact2,
              radius)
    return held_all


def _check_on(shape: Any, face: Any, point: App.Vector,
              radius: float) -> None:
    """Fail unless the ball's contact is on the face, or its surface's.

    Past its edge the ball would roll onto yet another face.
    """
    if not any(f.isInside(point, radius * ROLL_OFF, True)
               for f in _fellows(shape, face)):
        raise FadeError("the ball rolls off the faces it is held between")


def _on_surface(face: Any, points: list[App.Vector]) -> Any:
    """An edge through the points made on the face's own surface."""
    surface = face.Surface
    uvs = [surface.parameter(p) for p in points]
    # Unwrapped across a periodic seam, so the curve does not jump.
    for k, period in ((0, surface.isUPeriodic() and surface.UPeriod()),
                      (1, surface.isVPeriodic() and surface.VPeriod())):
        if not period:
            continue
        for i in range(1, len(uvs)):
            step = uvs[i][k] - uvs[i - 1][k]
            shift = period * round(step / period)
            if shift:
                moved = list(uvs[i])
                moved[k] -= shift
                uvs[i] = tuple(moved)
    geom2d: Any = getattr(Part, "Geom2d")
    vector2d: Any = App.Base.Vector2d
    curve = geom2d.BSplineCurve2d()
    curve.interpolate([vector2d(u, v) for u, v in uvs])
    return curve.toShape(surface)


def _groups(fade: Fade, held: list[tuple[bf.Station, bool]],
            ) -> list[list[bf.Station]]:
    """The sections on the lead's face, to the hand-over, and those after.

    Lofted apart: across the hand-over the contact path turns from one
    face to the other, and one loft through both would ripple.
    """
    on = [h for h, before in held if before]
    if len(on) < 2:
        return [[h for h, _b in held]]
    on[-1] = bf.Station(on[-1].point, on[-1].tangent, on[-1].centre,
                        on[-1].contact1, _on_rim(fade, on[-1].contact2))
    return [on, on[-1:] + [h for h, before in held if not before]]


def _contact_edges(fade: Fade, groups: list[list[bf.Station]],
                   ) -> list[list[Any]]:
    """Each group's contact curves.

    On the shared face, and on the face the ball also touches there; the
    last runs on to the tangent end.
    """
    edges = []
    for k, group in enumerate(groups):
        last = k == len(groups) - 1
        end = [fade.end] if last else []
        other = fade.after if last else fade.before
        edges.append([
            _on_surface(fade.shared, [h.contact1 for h in group] + end),
            _on_surface(other, [h.contact2 for h in group] + end)])
    return edges


def _on_rim(fade: Fade, point: App.Vector) -> App.Vector:
    """The hand-over contact put on the rim between the two faces."""
    for edge in fade.before.Edges:
        if any(edge.isSame(e) for e in fade.after.Edges):
            return edge.valueAt(edge.Curve.parameter(point))
    return point


def applied(shape: Any, result: Any, edge: Any, radius: float) -> Any:
    """`result` with the fading crease's round built into it.

    Its faces are each checked, and mended where their edges stray; not
    against each other, which in practice never found a fault and cost
    more than the rest of the round.
    """
    fade = plan(shape, edge, radius)
    if fade is None:
        raise FadeError("the crease does not fade out")
    held = stations(shape, fade, radius)
    tolerance = radius * SEWING
    # What the corner held: the strips dropped must lie within it.
    corner = Part.makeLoft([section(h, radius) for h, _on
                            in held[:-1:CORNER_EVERY] + held[-1:]],
                           True, False)
    added = []
    start = None
    if fade.lead is not None:
        # Begun on the lead round's own end, which an approximate round
        # leaves a little off the ball held exactly here.
        start = _lead_end(result, held[0][0], tolerance, radius)
        if start is None:
            raise FadeError("the lead's round does not end where it should")
        a, b = (v.Point for v in start.Vertexes)
        first = held[0][0]
        if (a - first.contact1).Length + (b - first.contact2).Length \
                > (b - first.contact1).Length + (a - first.contact2).Length:
            a, b = b, a
        held[0] = (bf.Station(first.point, first.tangent, first.centre,
                              a, b), held[0][1])
    groups = _groups(fade, held)
    contacts = _contact_edges(fade, groups)
    # Up to the hand-over the ball is the lead's own: on an exact round
    # its surface carries on, so refining makes the two one face. Else,
    # and after the hand-over, each new face is the loft itself, whose
    # own edges, with their own curves on it, split the faces it meets.
    lead_face = _lead_face(result, start, held[0][0], tolerance)
    if lead_face is not None and len(groups) > 1:
        group = groups[0]
        closing = bf._blend(group[-1].contact1, group[-1].contact2,
                            group[-1].centre, radius)
        try:
            _on_lead(lead_face, [start] + contacts[0] + [closing],
                     _lofted(fade, group, start, fade.before, False,
                             radius)[0].Area, tolerance, radius)
        except FadeError:
            lead_face = None
    lofts: list[tuple[Any, float] | None] = []
    for k, group in enumerate(groups):
        last = k == len(groups) - 1
        if not last and lead_face is not None:
            lofts.append(None)
            continue
        face, sides, stray = _lofted(
            fade, group, start if k == 0 else None,
            fade.after if last else fade.before, last, radius)
        contacts[k] = sides
        lofts.append((face, stray))
    if fade.lead is None:
        # Nothing ends where the round starts: its own end, across the
        # crease, splits the faces there too.
        first = groups[0][0]
        contacts.append([
            _on_surface(fade.shared, [first.contact1, first.point]),
            _on_surface(fade.after, [first.contact2, first.point])])
    fuzz = max([tolerance] + [2 * x[1] for x in lofts if x is not None])
    split, pieces = result.generalFuse(
        [e for pair in contacts for e in pair], fuzz)
    if len(split.Solids) != 1:
        raise FadeError("the contact curves would not split the faces")
    solid = split.Solids[0]
    if start is not None:
        start = next((e for e in solid.Edges if e.isSame(start)), None) \
            or _same_edge(solid, start, tolerance)
        if start is None:
            raise FadeError("the lead's round end was lost in the split")
    walls = [e for group in pieces[1:] for e in group]
    dropped = _corner_faces(solid, edge, walls + ([start] if start else []),
                            tolerance)
    kept = [f for f in solid.Faces if not any(f.isSame(d) for d in dropped)]
    if len(dropped) < 2 or sum(f.Area for f in dropped) \
            > corner.Area * 1.1 + tolerance:
        raise FadeError("the corner along the crease was not found")
    if start is None:
        loft = lofts[0]
        if loft is None:
            raise FadeError("the round has no start")
        start = loft[0].Edges[0]
        sides = [e for i in (-2, -1) for e in pieces[i]]
        try:
            added.append(Part.Face(Part.Wire(Part.__sortEdges__(
                sides + [start]))))
        except Exception:  # noqa: BLE001 - not flat: filled then
            added.append(Part.makeFilledFace(sides + [start]))
    pieces = pieces[1:]
    new = []
    for k, group in enumerate(groups):
        loft = lofts[k]
        if loft is not None:
            face, stray = loft
            for e in face.Edges:
                if e.Tolerance < stray * 2:
                    e.fixTolerance(stray * 2)
            new.append(face)
            continue
        closing = bf._blend(group[-1].contact1, group[-1].contact2,
                            group[-1].centre, radius)
        rims = [e for i in (2 * k, 2 * k + 1) for e in pieces[i]]
        new.append(_on_lead(lead_face, [start] + rims + [closing],
                            None, tolerance, radius))
    faces = kept + new + added
    sewn = Part.Compound(faces)
    sewn.sewShape(tolerance)
    shells = sewn.Shells
    if len(shells) != 1 or not shells[0].isClosed():
        raise FadeError("the new round would not close the part")
    made = Part.Solid(shells[0])
    if made.Volume < 0:
        made.reverse()
    # Only around the new round has anything changed: the rest was
    # checked as it was made.
    near = Part.Compound(new + added).BoundBox
    near.enlarge(tolerance * 10)
    made = bf._tolerant(made, near)
    if not made.isValid():
        raise FadeError("the new round left the part invalid")
    change = result.Volume - made.Volume
    if (change < 0) == fade.convex \
            or abs(change) > abs(corner.Volume) * 1.1:
        raise FadeError("the new round changed the part by %.4g mm³"
                        % -change)
    return made


def _lofted(fade: Fade, group: list[bf.Station], start: Any, other: Any,
            last: bool, radius: float) -> tuple[Any, list[Any], float]:
    """A new face lofted through the group's sections.

    From the lead's end if given and, for the last, to the point at the
    run-out. With it, its two sides (on the shared face, then `other`),
    and how far they stray from those faces.
    """
    arcs = [bf._blend(h.contact1, h.contact2, h.centre, radius)
            for h in group]
    first = arcs[0]
    if start is not None:
        first = start
        if (start.valueAt(start.FirstParameter) - group[0].contact1).Length \
                > (start.valueAt(start.LastParameter)
                   - group[0].contact1).Length:
            first = start.reversed()
    ends = [Part.Vertex(fade.end)] if last else []
    try:
        face = Part.makeLoft([Part.Wire([first])]
                             + [Part.Wire([a]) for a in arcs[1:]] + ends,
                             False, False).Faces[0]
    except Exception as exc:  # noqa: BLE001 - reported as the reason
        raise FadeError("the round could not be lofted: %s" % exc) from exc
    across = [first] if last else [first, arcs[-1]]
    middles = [e.valueAt((e.FirstParameter + e.LastParameter) / 2)
               for e in across]
    sides = [e for e in face.Edges if e.Length > radius * SEWING
             and all(e.distToShape(Part.Vertex(m))[0] > radius * SEWING
                     for m in middles)]
    if len(sides) != 2:
        raise FadeError("the round came out the wrong shape")
    sides.sort(key=lambda e: _stray([e], fade.shared.Surface))
    stray = max(_stray([sides[0]], fade.shared.Surface),
                _stray([sides[1]], other.Surface))
    if stray > radius * DEVIATION:
        raise FadeError("the round strays from the faces it meets")
    return face, sides, stray


def _lead_face(result: Any, start: Any, first: bf.Station,
               tolerance: float) -> Any:
    """The lead's round, where it is exact enough to carry on, else None."""
    if start is None:
        return None
    for face in result.ancestorsOfType(start, Part.Face):
        if not _on_step(face, first, tolerance) and isinstance(
                face.Surface, (Part.Plane, Part.Cylinder, Part.Cone,
                               Part.Sphere, Part.Toroid)):
            return face
    return None


def _on_lead(lead_face: Any, bounds: list[Any], area: float | None,
             tolerance: float, radius: float) -> Any:
    """The lead's round carried on to the hand-over, on its own surface.

    About `area` in size, when given.
    """
    surface = lead_face.Surface
    stray = _stray(bounds, surface)
    if stray > radius * DEVIATION:
        raise FadeError("the lead's round does not carry on to the "
                        "hand-over")
    try:
        face = Part.Face(surface, Part.Wire(Part.__sortEdges__(bounds)))
        face.fix(tolerance, tolerance * 1e-3, tolerance)
    except Exception as exc:  # noqa: BLE001 - reported as the reason
        raise FadeError("the lead's round could not be carried on: %s"
                        % exc) from exc
    # On a closed surface the wire may have bounded the rest of it.
    if not face.isValid() or (area is not None
                              and abs(face.Area - area) > area * 0.05):
        raise FadeError("the lead's round could not be carried on")
    for e in face.Edges:
        if e.Tolerance < stray * 2:
            e.fixTolerance(stray * 2)
    return face


def _stray(edges: list[Any], surface: Any) -> float:
    """How far the edges stray from the surface at most."""
    most = 0.0
    for edge in edges:
        first, last = edge.FirstParameter, edge.LastParameter
        for k in range(STRAY_SAMPLES + 1):
            point = edge.valueAt(first + (last - first) * k / STRAY_SAMPLES)
            u, v = surface.parameter(point)
            most = max(most, (surface.value(u, v) - point).Length)
    return most


def _lead_end(result: Any, first: bf.Station, tolerance: float,
              radius: float) -> Any:
    """The lead round's end edge, near the ball's first section.

    Between the round and the flat end its tool left.
    """
    arc = bf._blend(first.contact1, first.contact2, first.centre, radius)
    middle = arc.valueAt((arc.FirstParameter + arc.LastParameter) / 2)
    reach = radius * 0.25
    best, nearest = None, reach
    for edge in result.Edges:
        ends = [v.Point for v in edge.Vertexes]
        if len(ends) != 2 or not all(
                min((end - w).Length for end in ends) < reach
                for w in (first.contact1, first.contact2)):
            continue
        faces = result.ancestorsOfType(edge, Part.Face)
        if len(faces) != 2 or sum(_on_step(f, first, tolerance)
                                  for f in faces) != 1:
            continue
        gap = edge.distToShape(Part.Vertex(middle))[0]
        if gap < nearest:
            best, nearest = edge, gap
    return best


def _corner_faces(solid: Any, crease: Any, walls: list[Any],
                  tolerance: float) -> list[Any]:
    """The faces between the crease and the curves walling it off.

    From those along the crease, every face reached across an edge that
    is not one of the walls: the strips the round replaces, and the end
    the lead's round left.
    """
    def on_crease(edge: Any) -> bool:
        if edge.Length < tolerance:
            return False            # a point, as where rounds run out
        middle = edge.valueAt((edge.FirstParameter + edge.LastParameter)
                              / 2)
        return crease.distToShape(Part.Vertex(middle))[0] < tolerance

    reached = [f for f in solid.Faces
               if any(on_crease(e) for e in f.Edges)]
    waiting = list(reached)
    while waiting:
        face = waiting.pop()
        for edge in face.Edges:
            if edge.Length < tolerance or any(edge.isSame(w) for w in walls):
                continue
            for other in solid.ancestorsOfType(edge, Part.Face):
                if not any(other.isSame(f) for f in reached):
                    reached.append(other)
                    waiting.append(other)
    return reached


def _on_step(face: Any, first: bf.Station, tolerance: float) -> bool:
    """Whether the face is the flat end the lead's tool left.

    Across the edge, where the first section is.
    """
    inside = bf._point_on(face, tolerance)
    return inside is not None and isinstance(face.Surface, Part.Plane) \
        and abs((inside - first.point).dot(first.tangent)) < tolerance \
        and abs(abs(App.Vector(face.Surface.Axis).dot(first.tangent)) - 1) \
        < 1e-6


def _same_edge(solid: Any, edge: Any, tolerance: float) -> Any:
    """The edge of `solid` lying where `edge` does."""
    middle = edge.valueAt((edge.FirstParameter + edge.LastParameter) / 2)
    for other in solid.Edges:
        if abs(other.Length - edge.Length) < tolerance and \
                other.distToShape(Part.Vertex(middle))[0] < tolerance:
            return other
    return None


def handed_over(shape: Any, edge: Any, made: Any, radius: float) -> Any:
    """A lead's tool, stopped where a fading crease's tool takes over."""
    size = shape.BoundBox.DiagonalLength * 4
    for other in (_chosen[-1] if _chosen else []):
        if other.isSame(edge):
            continue
        try:
            fade = plan(shape, other, radius)
        except FadeError:
            continue
        if fade is None or fade.lead is None or not fade.lead.isSame(edge):
            continue
        at = edge.valueAt(fade.start)
        made = made.cut(bf._half_space(
            at, _toward(edge, fade.start, fade.joint), size))
    return made
