# Translations

Nxt's user-facing text is marked for translation: `translate("Nxt", ...)`
and `QT_TRANSLATE_NOOP("Nxt", ...)` from `freecad/nxt/app/i18n.py` in
Python (commands use their own name as the context), and `qsTr()` in QML
(context: the QML file's name). The inspector templates' titles, hints
and labels are extracted too, into the `NxtTemplate` context with the
template's id as the disambiguation. Console output is developer-facing
and is not translated.

Where FreeCAD already translates the same text ("Pad", "Reversed", or
"Nxt Fillet" for "Fillet"), Nxt shows FreeCAD's translation, so only
Nxt's own text needs translating here. Property names and enum values
stay as FreeCAD shows them.

From the repository root (needs PySide6's tools):

```bash
python scripts/i18n.py update --locale de    # extract into Nxt.ts, Nxt_de.ts
python scripts/i18n.py build                 # compile every Nxt_*.ts to .qm
python scripts/i18n.py check --locale de     # completeness, placeholders
python scripts/i18n.py terms --freecad PATH  # refresh app/freecad_terms.py
```

`update` keeps existing translations of the same text. Commit each
`.qm` with its `.ts`: the tests check that the `.qm` is exactly what its
`.ts` compiles to, so the binary can be reviewed through the `.ts`.
Name each file with FreeCAD's language code (`Nxt_es-ES.ts`, not
`Nxt_es.ts`), or FreeCAD won't load it. `init_gui.py` adds this folder to FreeCAD's language path.
