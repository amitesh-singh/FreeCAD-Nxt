"""CAM cycle times: each operation's, and an Operations group's total.

The tree shows an operation's estimate as a chip, and under each expanded
Operations group a "Total Cycle Time:" row adding up its operations.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

#: Names of the total rows: never a document object's name.
TOTAL_PREFIX = "\x00cycle-total:"
TOTAL_LABEL = "Total Cycle Time:"


def total_name(group: str) -> str:
    return TOTAL_PREFIX + group


def is_total(name: str) -> bool:
    return name.startswith(TOTAL_PREFIX)


def group_of_total(name: str) -> str:
    return name[len(TOTAL_PREFIX):]


def seconds(text: Any) -> float | None:
    """An estimate as CAM writes it ("H:MM:SS"), in seconds; None if none."""
    parts = str(text or "").strip().split(":")
    try:
        values = [float(p) for p in parts]
    except ValueError:
        return None
    if not values or len(values) > 3:
        return None
    total = 0.0
    for value in values:
        total = total * 60 + value
    return total


def formatted(total: float) -> str:
    whole = int(round(total))
    hours, rest = divmod(whole, 3600)
    minutes, secs = divmod(rest, 60)
    return "%d:%02d:%02d" % (hours, minutes, secs)


def of(obj: Any) -> str:
    """The object's cycle time for its chip, or "" when it has none."""
    found = seconds(getattr(obj, "CycleTime", None))
    return formatted(found) if found is not None else ""


def operation_groups(doc: Any) -> set[str]:
    """The names of CAM Jobs' Operations groups in the document."""
    groups = set()
    for obj in getattr(doc, "Objects", ()) or ():
        if not (hasattr(obj, "Operations") and hasattr(obj, "Stock")):
            continue
        group = getattr(obj, "Operations", None)
        if group is not None and hasattr(group, "Name"):
            groups.add(group.Name)
    return groups


def total(doc: Any, operations: Iterable[str]) -> str:
    """The summed estimate of the active operations, or "" if none has one."""
    found = []
    for name in operations:
        obj = doc.getObject(name) if doc is not None else None
        if obj is None or not getattr(obj, "Active", True):
            continue
        value = seconds(getattr(obj, "CycleTime", None))
        if value is not None:
            found.append(value)
    return formatted(sum(found)) if found else ""


def with_totals(rows: Sequence[tuple[str, int]], groups: set[str],
                expanded: Iterable[str]) -> list[tuple[str, int]]:
    """`rows` with a total row closing each expanded Operations group.

    It goes after the group's last descendant, one level in.
    """
    open_groups = groups & set(expanded)
    out: list[tuple[str, int]] = []
    pending: list[tuple[str, int]] = []     # (group, its depth)
    for name, depth in rows:
        while pending and depth <= pending[-1][1]:
            group, at = pending.pop()
            out.append((total_name(group), at + 1))
        out.append((name, depth))
        if name in open_groups:
            pending.append((name, depth))
    while pending:
        group, at = pending.pop()
        out.append((total_name(group), at + 1))
    return out
