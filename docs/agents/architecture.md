# Architecture

## Packages and what may import what

```
freecad/nxt/
  init_gui.py   registration only; heavy setup deferred until the window exists
  app/          commands, services, version, i18n, cleanup, update check
  core/         fc, qt, qtquick, settings, log, units, transaction, events,
                view3d, widgets, property_kinds   (imports nothing from Nxt)
  ui/           theme, quick_host, prefs, toast, notices   (imports core)
  tools/        features: section view, fillets, gizmos, task layout/sync,
                sketch repair, isolate, visibility ...
  tree/         the model panel: scene, models, bridge, panel, observers ...
  inspector/    Property Inspector: layout, templates, bridge, host
  menus/        context menus (TOML in resources/menus)
  resources/    qml/Nxt/{Controls,Tree,Inspector}, inspector/*.toml,
                icons, translations
```

- `core` imports nothing from Nxt. `ui` imports only `core` and resources.
- Features import `core`/`ui`, never each other's internals; share through
  `core` or a small public function.
- QML controls know nothing about the tree or FreeCAD.

## The layers of a QML surface

| Layer | Role |
|---|---|
| Snapshot (`scene.py`) | Pure Python, no Qt: reads the document once into plain data. Testable with stubs. |
| Models (`models.py`) | Flat `QAbstractListModel`s; `depth` is a role, not a tree. |
| Bridge (`bridge.py`) | The only object QML may call. Owns transactions and timers. Slots are one-line delegates to feature modules. |
| Host (`panel.py`, `quick_host.make_view`) | Creates the `QQuickWidget`, sets context properties, places it. |
| View (`qml/`) | Presentation only. |

Every QML surface is created through `ui/quick_host.make_view`, which sets
the import path, the context, the language follow-up and the Wayland
placement helpers.

## Patterns to reuse

- **Rebuild and diff, not incremental mutation.** Document signals mark the
  snapshot dirty; one rebuild runs on the next event-loop turn and the row
  list is diffed, so views keep scroll position and delegates.
- **Targeted `dataChanged`**: announce only rows whose displayed fields
  changed; assign state *before* emitting.
- **Deferred work through timers owned by the bridge** (parented
  `QTimer`), never a static `QTimer.singleShot` on a bound method.
- **One user action, one undo step**: `core/transaction.py`. A drag that
  previews live commits once on release.
- **Borrow, don't rebuild, FreeCAD's own pieces** (the PropertyView, the
  task dialog with its preview and OK/Cancel, `Gui::Command`s) and put them
  back exactly where they were.
- **Settings in FreeCAD's parameter store** (`BaseApp/Preferences/Mod/Nxt`)
  via `core/settings.py`; reads never raise; writes coalesced.
- **Clean uninstall**: anything Nxt changes in FreeCAD's own parameters is
  recorded and restored by `app/cleanup.py`. A new FreeCAD preference Nxt
  touches must be added there.
- **Reload-safe**: `Reload Nxt` tears down inspector, services and panel
  before reloading modules. New long-lived objects (observers, filters,
  timers) need a teardown path.
- **Feature flags by detection, not version numbers**: a property or method
  FreeCAD lacks is skipped (`getattr`/`hasattr`), so one code path serves
  several FreeCAD versions.

## Where to put things

- A new interface surface: QML component in `Nxt.*`, a bridge object, a
  `make_view` call. QtWidgets only for what FreeCAD demands.
- A new property layout: a template in `resources/inspector/*.toml` (see
  [templates and task panels](templates-and-task-panels.md)), not code.
- A new context-menu entry: `resources/menus` TOML, see
  `tree/CONTEXT_MENU.md`.
- A constraint the code works around: one entry in `tree/DESIGN.md`
  "Decisions", so the code stays short.
