"""A resolved menu as plain data for QML; FreeCAD-free via `Lookup`."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ..app.i18n import translate
from . import labels
from .definitions import Item, Resolved

CONTEXT = "NxtMenu"


@dataclass(frozen=True)
class CommandInfo:
    """What FreeCAD says about one command."""

    label: str
    shortcut: str = ""
    active: bool = True
    icon: str = ""


Lookup = Callable[[str], CommandInfo | None]


@dataclass(frozen=True)
class Subject:
    """What the menu is about, for its header and a few labels."""

    title: str
    subtitle: str = ""
    count: int = 1
    any_shown: bool = True


def present(menu: Resolved, subject: Subject,
            lookup: Lookup) -> dict[str, Any]:
    """The menu as QML reads it; unregistered commands are left out."""
    def entry(item: Item | None) -> dict[str, Any] | None:
        return None if item is None else _entry(item, subject, lookup)

    def entries(items: list[Item]) -> list[dict[str, Any]]:
        return [e for e in (entry(i) for i in items) if e is not None]

    bar = []
    for item in menu.bar:
        shown = entry(item)
        if shown is None:
            continue
        shown["short"] = _bar_label(item.command, subject)
        if item.command in menu.dimmed:
            shown["enabled"] = False
        bar.append(shown)

    return {
        "title": subject.title,
        "subtitle": subject.subtitle,
        "bar": bar,
        "lead": entry(menu.lead),
        "state": entries(menu.state),
        "sections": [{"name": translate(CONTEXT, name),
                      "items": items}
                     for name, items in ((n, entries(i))
                                         for n, i in menu.sections)
                     if items],
        "delete": entry(menu.delete),
        "more": [{"name": translate(CONTEXT, name), "items": items}
                 for name, items in ((n, entries(i)) for n, i in menu.more)
                 if items]
        + [{"name": "", "items": [_native_entry()]}],
    }


def entry(item: Item, subject: Subject,
          lookup: Lookup) -> dict[str, Any] | None:
    """One item as QML reads it; None if its command is unregistered."""
    return _entry(item, subject, lookup)


def _entry(item: Item, subject: Subject,
           lookup: Lookup) -> dict[str, Any] | None:
    if item.items:
        children = [e for e in (_entry(i, subject, lookup)
                                for i in item.items) if e is not None]
        if not children:
            return None
        return {"command": item.command,
                "label": translate(CONTEXT, item.label), "shortcut": "",
                "enabled": True, "icon": "", "items": children}
    command = item.command
    label = translate(CONTEXT, item.label) if item.label else ""
    shortcut, enabled, icon = "", True, ""

    if command.startswith("nxt:"):
        text = labels.ACTIONS.get(command, command)
        label = label or translate(CONTEXT, text)
        icon = labels.ICONS.get(command, "")
    elif command.startswith("edit:"):
        label = label or translate(CONTEXT, "Edit %1").replace(
            "%1", subject.title)
    else:
        info = lookup(command)
        if info is None:
            return None
        raw_label = label or info.label
        label = translate(CONTEXT, raw_label)
        if label == raw_label:
            cmd_text = getattr(labels, "COMMANDS", {}).get(command)
            if cmd_text:
                label = translate(CONTEXT, cmd_text)
            elif command in labels.ACTIONS:
                label = translate(CONTEXT, labels.ACTIONS[command])
            else:
                cmd_trans = translate(CONTEXT, command)
                if cmd_trans != command:
                    label = cmd_trans
        shortcut, enabled, icon = info.shortcut, info.active, info.icon

    return {"command": command, "label": _counted(label, command, subject),
            "shortcut": shortcut, "enabled": enabled, "icon": icon}


def _counted(label: str, command: str, subject: Subject) -> str:
    if subject.count < 2 or command not in labels.COUNTED or not label:
        return label
    return translate(CONTEXT, labels.COUNTED_LABEL).replace(
        "%1", label).replace("%2", str(subject.count))


def _isolating() -> bool:
    try:
        from ..app import services
        isolation = services.isolation()
        return isolation is not None and isolation.active()
    except Exception:
        return False


def _bar_label(command: str, subject: Subject) -> str:
    if command == "Std_ToggleVisibility":
        text = labels.BAR["hide" if subject.any_shown else "show"]
    elif command == "nxt:isolate" and _isolating():
        text = labels.BAR["nxt:isolate_exit"]
    else:
        text = labels.BAR.get(command, "")
    return _counted(translate(CONTEXT, text), command, subject)


def _native_entry() -> dict[str, Any]:
    return {"command": "nxt:native_menu",
            "label": translate(CONTEXT, labels.ACTIONS["nxt:native_menu"]),
            "shortcut": "", "enabled": True, "icon": ""}
