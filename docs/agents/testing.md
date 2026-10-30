# Testing and checks

## What CI runs (`.github/workflows/checks.yml`)

```bash
ruff check .
pycodestyle freecad tests
mypy
bandit -r . -q
for t in tests/test_*.py tests/audit_qml_refs.py; do python "$t"; done
```

Python 3.11, PySide6 below 6.12 (6.12.0 aborts on 3.11),
`QT_QPA_PLATFORM=offscreen`. Run all of it before handing a change over.

Bandit is what FreeCAD's Addon Report scores addons with, so it must stay
at zero findings. Fix the code rather than silencing it: `contextlib.
suppress(...)` for an exception deliberately ignored, `unittest`'s
`assert*` methods in tests, `defusedxml` for XML, `tempfile` for temporary
paths. Where a finding is a false positive, `# nosec B<id>  # reason` on
the flagged line, with the reason.

## Kinds of test

- **Logic with stubs**: `tests/fakes.py` installs stand-in `FreeCAD` and
  `FreeCADGui` modules, so snapshot, template, settings and tool logic run
  with no FreeCAD. Most tests are this kind; add to them.
- **Headless QML**: load the real QML in an offscreen `QQuickView` against
  stub context objects generated from the real bridge/theme classes
  (`test_qml.py`, `test_*_qml.py`). A `ListView` only realises delegates
  in a real view, and animations need real time to pass.
- **QML reference audit**: `audit_qml_refs.py` checks every component a
  QML file uses exists.
- **Translations**: `test_translations.py` (`.qm` matches `.ts`,
  placeholders, file names), `test_i18n_live.py` (language change).
- **Headless FreeCAD**: `QT_QPA_PLATFORM=offscreen freecadcmd` for geometry
  and document behaviour. No GUI there.
- **Running FreeCAD**: the only check for look and feel, overlay mode,
  docking, Wayland placement. Use `REGRESSION.md` as the checklist and say
  when this wasn't done.

## Good tests here

- Test the behaviour a user would notice (the bar lands on the right
  boundary when a row above is taller), not the implementation.
- A bug fix comes with the test that would have caught it.
- Per-feature test classes (`LoftTests`, `AssemblyTests`).
- Local, untracked FreeCAD documents for manual checks live in `local/`,
  built by a script so they can be regenerated.

## Diagnosing in FreeCAD

`from freecad.nxt.tree import probe; probe.run()` reports on the FreeCAD
API assumptions; `probe.benchmark()` times the snapshot on the open
document. Measure before optimising.
