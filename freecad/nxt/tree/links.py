"""Dependency arrows: what the selected object reads, and what reads it.

Plain data for DependencyArrows.qml. Links shown by nesting are skipped;
hidden targets go to their nearest shown ancestor.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

_ATTACH = {"AttachmentSupport", "Support", "MapMode", "AttacherEngine"}
_EXPRESSION = {"ExpressionEngine"}
_LINK = {"LinkedObject", "Objects", "LinkedObjects"}


def kind_of(props: Iterable[str]) -> str:
    """"geometry", "attachment", "expression" or "link"."""
    props = set(props)
    if props & _LINK:
        return "link"
    if props and props <= _ATTACH:
        return "attachment"
    if props and props <= _EXPRESSION:
        return "expression"
    if props & _ATTACH and not props - _ATTACH - _EXPRESSION:
        return "attachment"
    return "geometry"


def _visible_row(name: str, nodes: dict[str, Any],
                 row_of: Callable[[str], int]) -> int:
    """The row showing `name`, or its nearest shown ancestor's; -1 if none."""
    seen: set[str] = set()
    cursor: str | None = name
    while cursor and cursor not in seen:
        row = row_of(cursor)
        if row >= 0:
            return row
        seen.add(cursor)
        node = nodes.get(cursor)
        cursor = node.parent if node is not None else None
    return -1


def arrows(snapshot: Any, name: str,
           row_of: Callable[[str], int]) -> dict[str, Any]:
    """The arrows for `name`: {"source": row, "links": [...]}.

    Each link: {"row", "dir" ("in"/"out"), "kind", "count", "names"}.
    Empty when `name` has no row or no links.
    """
    nodes = snapshot.nodes
    node = nodes.get(name)
    source = _visible_row(name, nodes, row_of) if node is not None else -1
    if node is None or source < 0:
        return {"source": -1, "links": []}

    raw: list[tuple[str, str, str]] = []
    for other, _label, _severity, _part in node.refs:
        if snapshot.is_ancestor(other, name):
            continue
        entry = nodes.get(other)
        props: list[str] = []
        if entry is not None:
            for consumer, _l, consumer_props in entry.consumers:
                if consumer == name:
                    props = list(consumer_props)
        raw.append((other, "in", kind_of(props)))
    for other, _label, props in node.consumers:
        if snapshot.is_ancestor(name, other):
            continue
        raw.append((other, "out", kind_of(props)))

    merged: dict[tuple[int, str, str], dict[str, Any]] = {}
    for other, direction, kind in raw:
        row = _visible_row(other, nodes, row_of)
        if row < 0 or row == source:
            continue
        key = (row, direction, kind)
        entry_out = merged.setdefault(key, {
            "row": row, "dir": direction, "kind": kind,
            "count": 0, "names": []})
        entry_out["count"] += 1
        entry_out["names"].append(other)
    links = sorted(merged.values(),
                   key=lambda e: (abs(e["row"] - source), e["row"]))
    return {"source": source, "links": links}
