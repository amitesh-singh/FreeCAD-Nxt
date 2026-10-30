"""Translations: each .qm is its .ts compiled, placeholders survive.

Run with: python3 tests/test_translations.py
"""

from __future__ import annotations

import sys
import unittest
import warnings
from pathlib import Path

from defusedxml.ElementTree import parse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import i18n  # noqa: E402

#: FreeCAD's language codes: a file under any other name never loads.
FREECAD_LOCALES = frozenset("""
    af ar be bg ca cs da de el es-AR es-ES eu fi fil fr gl hr hu id it ja
    ka kab ko lt nl no pl pt-BR pt-PT ro ru sk sl sr sr-CS sv-SE tr uk
    val-ES vi zh-CN zh-TW""".split())


class TranslationTests(unittest.TestCase):
    def test_each_qm_is_its_ts_compiled(self) -> None:
        if i18n.find_tool("pyside6-lrelease") is None:
            self.skipTest("pyside6-lrelease not installed")
        for ts in i18n.locale_files():
            with self.subTest(ts.name):
                self.assertFalse(i18n.stale_qm(ts),
                                 "run: python scripts/i18n.py build")

    def test_files_use_freecads_language_codes(self) -> None:
        for ts in i18n.locale_files():
            with self.subTest(ts.name):
                self.assertIn(ts.stem[len("Nxt_"):], FREECAD_LOCALES)

    def test_placeholders_survive(self) -> None:
        for ts in i18n.locale_files():
            with self.subTest(ts.name):
                self.assertEqual(i18n.placeholder_problems(ts), [])

    def test_template_text_is_extracted(self) -> None:
        source = ROOT / "freecad/nxt/resources/translations/Nxt.ts"
        found = {(m.findtext("comment") or "", m.findtext("source"))
                 for c in parse(source).getroot().iter("context")
                 if c.findtext("name") == i18n.TEMPLATE_CONTEXT
                 for m in c.iter("message")}
        missing = set(i18n.template_strings()) - found
        if missing:
            warnings.warn("%d template string(s) not in Nxt.ts: run "
                          "python scripts/i18n.py update" % len(missing))


if __name__ == "__main__":
    unittest.main()
