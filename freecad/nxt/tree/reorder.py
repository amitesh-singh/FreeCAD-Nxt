"""Reordering a Body, Part or group by drag and drop.

Mirrors PartDesign_MoveFeatureInTree, but checks legality before the drop
so the row can refuse it while hovered.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import FreeCAD as App

from ..core.transaction import transaction


@dataclass(frozen=True)
class Plan:
    """A reorder, worked out: the new order, or why there is none."""

    order: tuple[str, ...] = ()
    #: Consecutive names in `order`.
    moving: tuple[str, ...] = ()
    #: Why the plan is illegal; empty when legal.
    problem: str = ""

    @property
    def ok(self) -> bool:
        return not self.problem and bool(self.order)


def plan(members: Sequence[str], moving: Sequence[str], after: str | None,
         depends_on: Mapping[str, set[str]], base: str | None = None
         ) -> Plan:
    """The order with `moving` placed after `after` (None: first).

    Refused if anything would precede something it depends on.
    """
    moving = [m for m in members if m in set(moving)]   # keep Body order
    if not moving:
        return Plan(problem="nothing to move")
    if base is not None and base in moving:
        return Plan(problem="the Body's base feature cannot be moved")
    if after is not None and after not in members:
        return Plan(problem="%s is not in the same container" % after)
    if after in moving:
        return Plan(problem="cannot drop onto what is being moved")

    rest = [m for m in members if m not in moving]
    at = rest.index(after) + 1 if after is not None else 0
    order = rest[:at] + moving + rest[at:]
    if order == list(members):
        return Plan(problem="already there")

    position = {name: index for index, name in enumerate(order)}
    for name in order:
        for dependency in depends_on.get(name, ()):
            if position.get(dependency, -1) > position[name]:
                return Plan(problem="%s would come before %s, which it "
                                    "depends on" % (name, dependency))
    return Plan(order=tuple(order), moving=tuple(moving))


# -- FreeCAD --

def body_of(obj: Any) -> Any:
    """The Part Design Body holding `obj`, or None."""
    try:
        parent = obj.getParentGeoFeatureGroup()
    except Exception:
        return None
    if parent is not None and parent.TypeId == "PartDesign::Body":
        return parent
    return None


def plan_drop(sources: Sequence[Any], target: Any) -> tuple[Any, Plan]:
    """The Body and plan if this drop reorders within a Body, else None."""
    # By name: FreeCAD may return a new wrapper for the same object.
    body = body_of(sources[0]) if sources else None
    if body is None or any(_name(body_of(s)) != body.Name for s in sources):
        return None, Plan()
    if target.Name == body.Name:
        after = None
    elif _name(body_of(target)) == body.Name:
        after = target.Name
    else:
        return None, Plan()

    members = [m.Name for m in body.Group]
    base = body.BaseFeature.Name if body.BaseFeature is not None else None
    return body, plan(members, [s.Name for s in sources], after,
                      dependencies(body), base)


def dependencies(body: Any) -> dict[str, set[str]]:
    """Solid features each solid feature reads via non-solid inputs.

    Direct solid-to-solid links are skipped: the Body rewires BaseFeature
    on every move, so they never constrain one.
    """
    solids = {m.Name for m in body.Group
              if _is(m, "PartDesign::Feature")}
    out: dict[str, set[str]] = {}
    for member in body.Group:
        if member.Name not in solids:
            continue
        reads: set[str] = set()
        for obj in member.OutList:
            if _is(obj, "PartDesign::Feature"):
                continue
            try:
                chain = [obj] + list(obj.OutListRecursive)
            except Exception:
                chain = [obj] + list(obj.OutList)
            reads |= {o.Name for o in chain if o.Name in solids}
        reads.discard(member.Name)
        out[member.Name] = reads
    return out


def _name(obj: Any) -> str | None:
    return None if obj is None else str(obj.Name)


def group_of(obj: Any) -> Any:
    """The non-Body container whose Group lists `obj`, or None."""
    for parent in getattr(obj, "InList", None) or ():
        if getattr(parent, "TypeId", "") == "PartDesign::Body":
            continue
        members = getattr(parent, "Group", None)
        if not isinstance(members, (list, tuple)):
            continue
        if any(_name(m) == obj.Name for m in members):
            return parent
    return None


def plan_group_drop(sources: Sequence[Any], target: Any
                    ) -> tuple[Any, Plan]:
    """The container and plan if this drop reorders a Part or group.

    Order there has no model meaning, so dependencies are not checked.
    """
    container = group_of(sources[0]) if sources else None
    if container is None or any(_name(group_of(s)) != container.Name
                                for s in sources):
        return None, Plan()
    if target.Name == container.Name:
        after = None
    elif _name(group_of(target)) == container.Name:
        after = target.Name
    else:
        return None, Plan()
    members = [m.Name for m in container.Group]
    return container, plan(members, [s.Name for s in sources], after, {})


def apply_group(container: Any, the_plan: Plan) -> None:
    """Put a Part's or group's members in the planned order: one undo."""
    doc = container.Document
    with transaction(doc, "Reorder %s" % container.Label):
        container.Group = [doc.getObject(n) for n in the_plan.order]


def _is(obj: Any, type_name: str) -> bool:
    try:
        return bool(obj.isDerivedFrom(type_name))
    except Exception:
        return False


def apply(body: Any, the_plan: Plan) -> None:
    """Move the Body's members into the planned order, as one undo step.

    Uses remove/insert as Part Design does, so BaseFeature is rewired.
    The tip stays, unless a feature is dropped straight after it.
    """
    doc = body.Document
    tip = body.Tip
    moving = list(the_plan.moving)
    with transaction(doc, "Move feature in Body"):
        new_order = list(the_plan.order)
        for name in moving:
            index = new_order.index(name)
            before = doc.getObject(new_order[index - 1]) if index else None
            feature = doc.getObject(name)
            body.removeObject(feature)
            body.insertObject(feature, before, True)
        last = doc.getObject(moving[-1]) if moving else None
        tip_name = tip.Name if tip is not None else None
        dropped_after_tip = (
            last is not None and tip_name is not None
            and tip_name not in moving
            and new_order.index(moving[0]) == new_order.index(tip_name) + 1)
        if (dropped_after_tip and last is not None
                and last.isDerivedFrom("PartDesign::Feature")):
            body.Tip = last
        elif tip is not None and _name(body.Tip) != tip.Name:
            body.Tip = tip
    doc.recompute()


def report(problem: str) -> None:
    App.Console.PrintWarning("Nxt: cannot move there - %s\n" % problem)
