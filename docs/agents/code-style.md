# Code style

## Priorities

1. Performance: the interface must stay responsive on large documents.
2. Readability: a newcomer can follow it without the history.
3. Pythonic idiom.

When these conflict, present the options and let the maintainer choose.

## Python

- Python 3.11, `from __future__ import annotations` in every module.
- **Fully typed.** mypy runs with `disallow_untyped_defs`. FreeCAD objects
  are `Any`; don't invent stubs for them.
- 79 columns. ruff (`E W F N D2 D3 D4 I`) and pycodestyle must pass.
- Qt and FreeCAD dictate camelCase for overrides, slots, properties and
  signals (`loadSettings`, `changeEvent`); mark those `# noqa: N802` where
  the file isn't in pyproject's per-file ignores.
- Names carry the meaning: `opening(angle)`, `hinged(...)`, `room_in_window`.
  Prefer a well-named small function to a comment.
- **Comments are rare.** Write one only where the code can't say it: a
  FreeCAD or Qt behaviour being worked around, a non-obvious reason, a
  unit. Never narrate what the next line does.
- **Docstrings:** a one-line summary saying what the thing *is* or
  gives ("The second plane's normal: the wedge cut away opens `degrees`.").
  Module docstrings explain the idea in a short paragraph.
- **No magic numbers.** Name them as module constants with a `#:` comment
  when the reason isn't obvious (`RESTORE_ROUNDS = 4`, `MOST = 180.0`).
- Fewer lines when clarity doesn't suffer: comprehensions, early returns,
  tables (dicts of field maps) instead of if-chains.
- `except Exception:` only at a boundary FreeCAD or Qt calls into, with
  `# noqa: BLE001 - <why>` and, where it matters, a line in the Report
  view (`App.Console.PrintError("Nxt: ...\n")`). Never silently swallow in
  logic.
- Imports of FreeCAD workbench modules (`Part`, `pivy.coin`, `PartDesignGui`)
  go inside the function that needs them, so modules import headlessly.
- Settings go through `core/settings.py` (`settings.get` / `put`, with a
  default in `DEFAULTS`). Never call `App.ParamGet` for Nxt's own values
  elsewhere.

## QML

- Components live in the `Nxt` module (`resources/qml/Nxt/{Controls,Tree,
  Inspector}`) with a `qmldir`; `tests/audit_qml_refs.py` checks every
  reference resolves.
- A short `//` header comment says what the component is and how to use it
  (see `NxtSwitch.qml`). Inline comments only for workarounds.
- Colours, sizes and fonts come from the `theme` context object
  (`theme.accent`, `theme.rowHeight`, `theme.fontSmall`). No hex literals,
  no hard-coded pixel sizes that should scale with the font.
- Python is reached only through the bridge objects set as context
  properties (`nxt`, `inspector`, `prefs`). QML holds no FreeCAD logic.
- Text the user reads is wrapped in `qsTr()`.
- Prefer drawing small primitives to `QtQuick.Controls`; where a Control
  is used it is `QtQuick.Controls.Basic`, fully restyled from `theme`.
- `property` names don't repeat a parent's name (it shadows it and reads
  as a binding loop).

## Naming in the interface

- User-facing words follow FreeCAD's terms where FreeCAD has one ("Pad",
  "Sketch", "Body"). Nxt's own tools are "Nxt <term>" ("Nxt Fillet").
- Labels are short: "Merge faces", not "Refine the resulting shape".
  Tooltips may be full sentences.
