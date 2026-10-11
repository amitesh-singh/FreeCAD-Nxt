"""Property Inspector templates: a layout for one family of objects.

The inspector lays out any object from what it says about itself
(inspector.py). A template refines that for objects it knows: cards named
for the task rather than FreeCAD's groups, readable labels, an enumeration
as a row of buttons, and items shown only while another property calls for
them - a second length only for two lengths.

It never hides a property. What a template does not name stays where the
generic layout put it, under "Everything else"; a name the object does not
have is skipped, so one template serves FreeCAD versions whose property
sets differ. Templates are data: resources/inspector/*.toml, whose header
describes the format.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from fnmatch import fnmatchcase
from importlib.resources import files
from pathlib import Path
from typing import Any

import FreeCAD as App

#: How a template may ask for a property to be edited: "dropdown" (the
#: default for an enumeration), "segmented" (every choice in view; for a
#: yes/no, its two states named by `labels`) and "switch" (a yes/no).
EDITORS = frozenset({"", "dropdown", "segmented", "switch"})


@dataclass(frozen=True)
class Item:
    prop: str
    label: str = ""
    wide: bool | None = None
    editor: str = ""
    show_if: tuple[tuple[str, tuple[Any, ...]], ...] = ()
    #: Enumeration values left out of "choices" when the object has the
    #: named property: (value, property).
    omit_if: tuple[tuple[str, str], ...] = ()
    #: For a yes/no shown "segmented": what no and yes are called.
    labels: tuple[str, ...] = ()


@dataclass(frozen=True)
class Column:
    """Items stacked one above another, beside the card's other columns."""

    title: str
    items: tuple[Item, ...]
    show_if: tuple[tuple[str, tuple[Any, ...]], ...] = ()


@dataclass(frozen=True)
class Card:
    title: str
    items: tuple[Item, ...]
    hint: str = ""
    columns: tuple[Column, ...] = ()
    after: tuple[Item, ...] = ()

    def all_items(self) -> list[Item]:
        return [*self.items, *(i for c in self.columns for i in c.items),
                *self.after]


@dataclass(frozen=True)
class Couple:
    """A mode that is another one's value at zero, and is never chosen.

    A "Profile plane" start is an "Offset" start at zero. The mode's
    choices hold only `nonzero`; choosing it, or typing the value, writes
    `nonzero` - so the offset's handle shows in the 3D view even at zero.
    """

    value: str
    mode: str
    zero: str
    nonzero: str


@dataclass(frozen=True)
class Template:
    id: str
    types: tuple[str, ...]
    cards: tuple[Card, ...]
    choices: dict[str, str] = field(default_factory=dict)
    #: Properties never shown while the object has another: (hidden, the
    #: one that supersedes it) - Midplane, once SideType exists.
    hide_if: tuple[tuple[str, str], ...] = ()
    couples: tuple[Couple, ...] = ()

    def matches(self, type_id: str) -> bool:
        return any(fnmatchcase(type_id, pattern) for pattern in self.types)

    def names(self) -> set[str]:
        return {item.prop for card in self.cards
                for item in card.all_items()}


def _tests(raw: Any) -> tuple[tuple[str, tuple[Any, ...]], ...]:
    return tuple(
        (name, tuple(value) if isinstance(value, list) else (value,))
        for name, value in dict(raw or {}).items())


def _item(raw: Any) -> Item:
    if isinstance(raw, str):
        return Item(raw)
    show_if = _tests(raw.get("show_if"))
    omit_if = tuple((str(value), str(prop)) for value, prop
                    in dict(raw.get("omit_if", {})).items())
    editor = str(raw.get("editor", ""))
    if editor not in EDITORS:
        raise ValueError("%s: unknown editor %r" % (raw["prop"], editor))
    return Item(str(raw["prop"]), str(raw.get("label", "")),
                raw.get("wide"), editor, show_if, omit_if,
                tuple(str(label) for label in raw.get("labels", ())))


def parse(data: dict[str, Any]) -> list[Template]:
    out = []
    for raw in data.get("template", ()):
        cards = tuple(
            Card(str(card["title"]),
                 tuple(_item(item) for item in card.get("items", ())),
                 str(card.get("hint", "")),
                 tuple(Column(str(col.get("title", "")),
                              tuple(_item(i) for i in col.get("items", ())),
                              _tests(col.get("show_if")))
                       for col in card.get("column", ())),
                 tuple(_item(item) for item in card.get("after", ())))
            for card in raw.get("card", ()))
        hide_if = tuple((str(hidden), str(by)) for hidden, by
                        in dict(raw.get("hide_if", {})).items())
        couples = tuple(Couple(str(c["value"]), str(c["mode"]),
                               str(c["zero"]), str(c["nonzero"]))
                        for c in raw.get("couple", ()))
        out.append(Template(str(raw["id"]), tuple(raw.get("types", ())),
                            cards, dict(raw.get("choices", {})), hide_if,
                            couples))
    return out


def load(path: Path) -> list[Template]:
    try:
        return parse(tomllib.loads(path.read_text(encoding="utf-8")))
    except (OSError, tomllib.TOMLDecodeError, KeyError, TypeError,
            ValueError) as exc:
        App.Console.PrintWarning("Nxt inspector template %s: %s\n"
                                 % (path.name, exc))
        return []


_cache: list[Template] | None = None


def loaded() -> list[Template]:
    global _cache
    if _cache is None:
        folder = Path(str(files("freecad.nxt.resources") / "inspector"))
        _cache = [t for path in sorted(folder.glob("*.toml"))
                  for t in load(path)]
    return _cache


def invalidate() -> None:
    global _cache
    _cache = None


def for_objects(objects: list[Any],
                templates: list[Template] | None = None
                ) -> Template | None:
    """The template every one of `objects` matches, or None."""
    if not objects:
        return None
    for template in loaded() if templates is None else templates:
        if all(template.matches(str(getattr(o, "TypeId", "")))
               for o in objects):
            return template
    return None


def _same(value: Any, wanted: Any) -> bool:
    if isinstance(wanted, bool):
        return bool(value) is wanted
    return str(value) == str(wanted)


def shown(item: Item | Column, objects: list[Any]) -> bool:
    """Whether `item` is called for now: one of its tests holds.

    A test on a property an object lacks is left out; with none left, the
    item shows. Several objects that disagree show it.
    """
    tests = [(name, values) for name, values in item.show_if
             if all(hasattr(o, name) for o in objects)]
    if not tests:
        return True
    for name, values in tests:
        current = [getattr(o, name) for o in objects]
        if any(any(_same(v, w) for w in values) for v in current):
            return True
    return False


def apply(template: Template, objects: list[Any],
          groups: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    """Take the template's properties out of `groups` into its cards.

    `groups` are the generic layout's, name -> entries, and keep what the
    template does not place. Returns the cards, as groups, in order.
    """
    found: dict[str, dict[str, Any]] = {}
    for name, entries in groups.items():
        for entry in entries:
            found[entry["name"]] = entry
    placed = template.names() | {
        hidden for hidden, by in template.hide_if
        if all(hasattr(o, by) for o in objects)}
    for name in list(groups):
        groups[name] = [e for e in groups[name] if e["name"] not in placed]
        if not groups[name]:
            del groups[name]

    def laid_out(items: tuple[Item, ...]) -> list[dict[str, Any]]:
        out = []
        for item in items:
            generic = found.get(item.prop)
            if generic is None or not shown(item, objects):
                continue
            out.append(_shaped(template, item, generic, objects))
        return out

    cards = []
    for card in template.cards:
        items = laid_out(card.items)
        columns = [{"title": column.title, "items": laid_out(column.items)}
                   for column in card.columns if shown(column, objects)]
        columns = [c for c in columns if c["items"]]
        if len(columns) == 1:
            columns[0]["title"] = ""    # a heading only tells columns apart
        after = laid_out(card.after)
        count = (len(items) + len(after)
                 + sum(len(c["items"]) for c in columns))
        if count:
            cards.append({"name": card.title, "open": True, "items": items,
                          "columns": columns, "after": after,
                          "count": count, "first": True, "hint": card.hint,
                          "template": template.id})
    return cards


def _shaped(template: Template, item: Item, generic: dict[str, Any],
            objects: list[Any]) -> dict[str, Any]:
    """The generic entry for a property, as the template asks for it."""
    entry = dict(generic)
    if item.label:
        entry["label"] = item.label
    if item.wide is not None:
        entry["wide"] = bool(item.wide)
    if item.editor:
        entry["editor"] = item.editor
    if entry["kind"] == "bool" and item.labels:
        entry["optionLabels"] = list(item.labels)
    for couple in template.couples:
        if item.prop == couple.mode and couple.zero in entry["options"]:
            # Zero's mode is the other's, at zero: one choice for both.
            entry["options"] = [o for o in entry["options"]
                                if o != couple.zero]
            if entry["text"] == couple.zero:
                entry["text"] = couple.nonzero
        elif item.prop == couple.value and all(
                str(getattr(o, couple.mode, "")) == couple.zero
                for o in objects):
            # FreeCAD locks the value at zero's mode; typing unlocks it.
            entry["readOnly"] = False
    if entry["kind"] == "enum":
        omitted = {value for value, prop in item.omit_if
                   if all(hasattr(o, prop) for o in objects)}
        options = [o for o in entry["options"]
                   if o not in omitted or o == entry["text"]]
        entry["options"] = options
        entry["optionLabels"] = (
            list(item.labels) if len(item.labels) == len(options)
            else [template.choices.get(o, o) for o in options])
    return entry


def coupled(template: Template | None, objects: list[Any], prop: str,
            value: Any) -> list[tuple[str, Any]] | None:
    """The edits that setting `prop` to `value` makes, in order.

    None when no couple is involved: the edit is just itself. Zero's mode
    is never written: typing the value, or choosing the shared mode, sets
    the other one - an offset of zero is still an offset, and keeps its
    handle in the 3D view.
    """
    if template is None or not objects:
        return None
    for couple in template.couples:
        modes = {str(getattr(o, couple.mode, "")) for o in objects}
        if prop == couple.mode and value == couple.nonzero:
            return [] if modes == {couple.nonzero} else [(prop, value)]
        if prop == couple.value and couple.zero in modes:
            return [(couple.mode, couple.nonzero), (prop, value)]
    return None
