"""A language change mid-session: text is translated again.

Run with: python3 tests/test_i18n_live.py
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import fakes  # noqa: E402

App, Gui = fakes.install()

from freecad.nxt.app import i18n  # noqa: E402
from freecad.nxt.core.qt import QtWidgets  # noqa: E402

LANGUAGES = {"de": {"Tree": "Baum", "Pick": "Wählen"},
             "fr": {"Tree": "Arbre", "Pick": "Choisir"}}


class LiveLanguageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = QtWidgets.QApplication.instance() or \
            QtWidgets.QApplication([])
        self.language = "de"
        self.saved = i18n._qt
        i18n._qt = lambda _c, text, _d=None: \
            LANGUAGES[self.language].get(text, text)

    def tearDown(self) -> None:
        i18n._qt = self.saved

    def test_widgets_callbacks_and_templates_follow(self) -> None:
        box = QtWidgets.QGroupBox(i18n.translate("Nxt", "Tree"))
        label = QtWidgets.QLabel(i18n.translate("Nxt", "Pick"), box)
        combo = QtWidgets.QComboBox(box)
        combo.addItem(i18n.translate("Nxt", "Tree"))
        i18n.follow(box)
        self.assertEqual(i18n.template_text("Pick", "t"), "Wählen")
        self.language = "fr"
        i18n._changed()
        self.assertEqual((box.title(), label.text(), combo.itemText(0)),
                         ("Arbre", "Choisir", "Arbre"))
        self.assertEqual(i18n.template_text("Pick", "t"), "Choisir")

    def test_callback_of_a_gone_owner_is_dropped(self) -> None:
        class Owner:
            def __init__(self) -> None:
                self.seen = 0

            def changed(self) -> None:
                self.seen += 1

        owner = Owner()
        i18n.on_change(owner.changed)
        i18n._changed()
        self.assertEqual(owner.seen, 1)
        del owner
        before = len(i18n._callbacks)
        i18n._changed()
        self.assertLess(len(i18n._callbacks), before)


if __name__ == "__main__":
    unittest.main()
