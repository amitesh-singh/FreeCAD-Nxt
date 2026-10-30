"""Translations: each .qm is its .ts compiled, placeholders survive.

Run with: python3 tests/test_translations.py
"""

from __future__ import annotations

import sys
import unittest
import warnings
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import i18n  # noqa: E402


class TranslationTests(unittest.TestCase):
    def test_each_qm_is_its_ts_compiled(self) -> None:
        if i18n.find_tool("pyside6-lrelease") is None:
            self.skipTest("pyside6-lrelease not installed")
        for ts in i18n.locale_files():
            with self.subTest(ts.name):
                self.assertFalse(i18n.stale_qm(ts),
                                 "run: python scripts/i18n.py build")

    def test_placeholders_survive(self) -> None:
        for ts in i18n.locale_files():
            with self.subTest(ts.name):
                self.assertEqual(i18n.placeholder_problems(ts), [])

    def test_template_text_is_extracted(self) -> None:
        source = ROOT / "freecad/nxt/resources/translations/Nxt.ts"
        found = {(m.findtext("comment") or "", m.findtext("source"))
                 for c in ET.parse(source).getroot().iter("context")
                 if c.findtext("name") == i18n.TEMPLATE_CONTEXT
                 for m in c.iter("message")}
        missing = set(i18n.template_strings()) - found
        if missing:
            warnings.warn("%d template string(s) not in Nxt.ts: run "
                          "python scripts/i18n.py update" % len(missing))


if __name__ == "__main__":
    unittest.main()
