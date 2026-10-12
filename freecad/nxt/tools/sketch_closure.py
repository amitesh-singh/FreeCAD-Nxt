"""Why a sketch's profile is not closed, from its edges alone.

Pure (no FreeCAD); sketch_repair.py feeds it and applies the result.
Finds gaps, duplicates, stubs, loose ends, forks and overlaps.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from itertools import combinations
from math import atan2, hypot, tau

Point = tuple[float, float]
#: (edge index, START or END), as a constraint names it.
End = tuple[int, int]

#: Sketcher's point positions.
START, END = 1, 2

#: OpenCASCADE's tolerance, which decides whether the wire is closed.
JOINED = 1e-7
#: Gap distance, as a fraction of the sketch diagonal.
GAP_FRACTION = 0.01
#: Far tighter than a gap so a thin slot's sides are not an overlap.
OVERLAP_FRACTION = 1e-4


@dataclass(frozen=True)
class Edge:
    """One open, non-construction curve."""

    index: int
    start: Point
    end: Point
    mid: Point
    length: float
    straight: bool = False
    centre: Point | None = None


@dataclass(frozen=True)
class Findings:
    gaps: list[tuple[End, End]] = field(default_factory=list)
    #: Duplicates and stubs.
    surplus: list[int] = field(default_factory=list)
    #: Loose ends left after joining the gaps.
    open_ends: int = 0
    forks: int = 0
    overlaps: list[tuple[int, int]] = field(default_factory=list)

    def closed(self) -> bool:
        return not (self.gaps or self.surplus or self.open_ends
                    or self.forks or self.overlaps)


def _distance(a: Point, b: Point) -> float:
    return hypot(a[0] - b[0], a[1] - b[1])


def _near(points: Sequence[Point],
          radius: float) -> Iterator[tuple[float, int, int]]:
    """(distance, i, j) for point pairs within `radius`, swept in x."""
    order = sorted(range(len(points)), key=points.__getitem__)
    for at, i in enumerate(order):
        for j in order[at + 1:]:
            if points[j][0] - points[i][0] > radius:
                break
            distance = _distance(points[i], points[j])
            if distance <= radius:
                yield distance, i, j


def _vertices(points: Sequence[Point]) -> list[int]:
    """A vertex id for each point: points that already meet share one."""
    vertex = list(range(len(points)))

    def root(i: int) -> int:
        while vertex[i] != i:
            vertex[i] = i = vertex[vertex[i]]
        return i

    for _distance_apart, i, j in _near(points, JOINED):
        vertex[root(i)] = root(j)
    return [root(i) for i in range(len(points))]


def _diagonal(edges: Sequence[Edge]) -> float:
    xs, ys = zip(*(p for e in edges for p in (e.start, e.end, e.mid)))
    return hypot(max(xs) - min(xs), max(ys) - min(ys))


def _places(on: Edge, other: Edge, slack: float) -> list[float] | None:
    """Distance along `on` of `other`'s points; None if not on it."""
    points = (other.start, other.mid, other.end)
    if on.straight:
        dx, dy = on.end[0] - on.start[0], on.end[1] - on.start[1]
        places = []
        for x, y in points:
            px, py = x - on.start[0], y - on.start[1]
            if abs(px * dy - py * dx) > slack * on.length:
                return None
            places.append((px * dx + py * dy) / on.length)
        return places
    if on.centre is None:
        return None
    cx, cy = on.centre
    radius = _distance(on.centre, on.start)
    if any(abs(_distance(on.centre, p) - radius) > slack for p in points):
        return None

    def angle(point: Point) -> float:
        return atan2(point[1] - cy, point[0] - cx)

    # Normalise to counter-clockwise from `begin`.
    begin, sweep = angle(on.start), (angle(on.end) - angle(on.start)) % tau
    if (angle(on.mid) - begin) % tau > sweep:
        begin, sweep = angle(on.end), tau - sweep
    places = [((angle(p) - begin) % tau) * radius for p in points]
    # Just short of where the arc begins is before it, not a lap past it.
    beyond = (sweep + tau) / 2 * radius
    return [at - tau * radius if at > beyond else at for at in places]


def _lies_on(on: Edge, other: Edge, slack: float) -> bool:
    """Whether part of `other` lies inside `on`."""
    places = _places(on, other, slack)
    return places is not None \
        and any(slack < at < on.length - slack for at in places)


def _overlaps(edges: Sequence[Edge],
              slack: float) -> list[tuple[int, int]]:
    shaped = [e for e in edges if e.straight or e.centre is not None]
    return [(a.index, b.index) for a, b in combinations(shaped, 2)
            if _lies_on(a, b, slack) or _lies_on(b, a, slack)]


def inspect(edges: Sequence[Edge],
            fraction: float = GAP_FRACTION) -> Findings:
    """What keeps these edges from closing."""
    surplus = [e.index for e in edges if e.length <= JOINED]
    edges = [e for e in edges if e.length > JOINED]
    if not edges:
        return Findings(surplus=surplus)
    diagonal = _diagonal(edges)
    tolerance = fraction * diagonal

    # Edge k has points 2k and 2k + 1.
    points = [p for e in edges for p in (e.start, e.end)]
    vertex = _vertices(points)

    kept: dict[frozenset[int], list[Edge]] = {}
    duplicate: set[int] = set()
    for k, edge in enumerate(edges):
        twins = kept.setdefault(
            frozenset((vertex[2 * k], vertex[2 * k + 1])), [])
        if any(_distance(edge.mid, twin.mid) <= JOINED for twin in twins):
            duplicate.add(k)
        else:
            twins.append(edge)
    surplus += [edges[k].index for k in sorted(duplicate)]

    live = [i for i in range(len(points)) if i // 2 not in duplicate]
    degree = Counter(vertex[i] for i in live)
    loose = [i for i in live if degree[vertex[i]] == 1]
    forks = sum(1 for meeting in degree.values() if meeting > 2)

    gaps: list[tuple[End, End]] = []
    joined: set[int] = set()
    for _distance_apart, a, b in sorted(
            _near([points[i] for i in loose], tolerance)):
        i, j = loose[a], loose[b]
        if i // 2 == j // 2 or i in joined or j in joined:
            continue    # an edge's own two ends, or an end already paired
        joined.update((i, j))
        gaps.append(((edges[i // 2].index, START + i % 2),
                     (edges[j // 2].index, START + j % 2)))

    # An overlap always leaves a loose end or a fork.
    pairs = _overlaps(
        [e for k, e in enumerate(edges) if k not in duplicate],
        OVERLAP_FRACTION * diagonal) if loose or forks else []
    return Findings(gaps, surplus, len(loose) - len(joined), forks, pairs)
