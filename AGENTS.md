# Working on Nxt with an AI coding assistant

Nxt is a FreeCAD addon that replaces parts of FreeCAD's QtWidgets interface
with Qt Quick (QML), entirely from Python: no changes to FreeCAD itself.
These files tell an assistant, or a new contributor, how code here is
written, how the interface behaves, and what has already gone wrong.

Read this file first, then the guide for the task at hand:

| Task | Read |
|---|---|
| Any change | [workflow](docs/agents/workflow.md), [code style](docs/agents/code-style.md) |
| New module, moving code, wiring QML | [architecture](docs/agents/architecture.md) |
| Anything a user sees or touches | [UI and UX](docs/agents/ui-ux.md) |
| Inspector cards, task panels | [templates and task panels](docs/agents/templates-and-task-panels.md) |
| Text a user reads | [translations](docs/agents/i18n.md) |
| Qt, QML, FreeCAD API work | [pitfalls](docs/agents/pitfalls.md) |
| Before you say "done" | [testing and checks](docs/agents/testing.md) |

Deeper records: `freecad/nxt/tree/DESIGN.md` (the tree's paradigm and the
"Decisions" list of constraints behind non-obvious code),
`freecad/nxt/tree/CONTEXT_MENU.md`, `REGRESSION.md` (manual checklist),
the template format at the top of `resources/inspector/partdesign.toml`.

## The rules that matter most

1. **Qt Quick first.** New interface is QML. QtWidgets only where FreeCAD
   requires a widget (a task dialog's form, a preferences page), and kept
   as thin as possible.
2. **Addon, not fork.** Never require a change to FreeCAD. Borrow FreeCAD's
   own objects, commands and dialogs; put back anything borrowed; leave no
   trace on uninstall (`app/cleanup.py`).
3. **The interface never waits.** Every control shows hover, press and its
   new state at once; heavy work follows on a later event-loop turn.
4. **Standard desktop conventions.** Arrow cursor on controls (a pointing
   hand only on links), double-click opens, F2 renames, Escape backs out,
   one undo step per user action.
5. **Short, self-explanatory code.** Names over comments; comments only for
   what the code cannot say (usually *why*). No magic numbers. Fewer lines
   when it costs no clarity. Fully typed.
6. **Priorities when they conflict:** performance, then readability, then
   Pythonic idiom. If an optimisation costs readability or SLOC, present the
   trade-off and let the maintainer decide.
7. **The maintainer runs git.** Do not commit, push, merge or switch
   branches. Suggest a commit message instead.
8. **A fix that didn't work is reverted** before the next attempt.
9. **Say what was and wasn't verified.** Headless tests are not a running
   FreeCAD; say which one you used.
