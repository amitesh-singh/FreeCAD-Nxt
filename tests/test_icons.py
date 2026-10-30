"""Tree icons: rows of a closing or opening document draw blank, quietly.

Run with: python3 tests/test_icons.py
"""

from __future__ import annotations

import os
import sys
import types
import unittest
from pathlib import Path
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import fakes  # noqa: E402

App, Gui = fakes.install()

from PySide6 import QtCore, QtGui, QtWidgets  # noqa: E402

APP = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

from freecad.nxt.tree import icons  # noqa: E402


class Gone:
    @property
    def ViewObject(self) -> Any:  # noqa: N802
        raise RuntimeError("This object is deleted")


class IconTests(unittest.TestCase):
    def setUp(self) -> None:
        self.errors: list[str] = []
        App.Console = types.SimpleNamespace(PrintError=self.errors.append)
        red = QtGui.QPixmap(16, 16)
        red.fill(QtGui.QColor("red"))
        shown = types.SimpleNamespace(
            ViewObject=types.SimpleNamespace(Icon=QtGui.QIcon(red)))
        doc = types.SimpleNamespace(
            getObject=lambda name: {"Pad": shown, "Gone": Gone()}.get(name))
        App.listDocuments = lambda: {"Doc": doc}
        self.provider = icons.IconProvider()

    def pixel(self, image_id: str) -> QtGui.QColor:
        pixmap = self.provider.requestPixmap(image_id, None,
                                             QtCore.QSize(16, 16))
        return pixmap.toImage().pixelColor(8, 8)

    def test_a_live_object_draws_its_icon(self) -> None:
        self.assertEqual(self.pixel("Doc/Pad/0").name(), "#ff0000")

    def test_a_closed_document_draws_blank_without_an_error(self) -> None:
        self.assertEqual(self.pixel("Closed/Pad/0").alpha(), 0)
        self.assertEqual(self.errors, [])

    def test_a_deleted_object_draws_blank_without_an_error(self) -> None:
        self.assertEqual(self.pixel("Doc/Gone/0").alpha(), 0)
        self.assertEqual(self.pixel("Doc/Missing/0").alpha(), 0)
        self.assertEqual(self.errors, [])


class PinTests(unittest.TestCase):
    def test_the_detail_strips_pin_is_the_inspectors(self) -> None:
        from freecad.nxt.ui.glyphs import pin_icon
        for pinned in (True, False):
            served = icons.IconProvider().requestPixmap(
                "@pin/%d/336699" % pinned, None, QtCore.QSize(14, 14))
            drawn = pin_icon(14, pinned, QtGui.QColor("#336699")).pixmap(
                14, 14)
            self.assertEqual(served.toImage(), drawn.toImage())


if __name__ == "__main__":
    unittest.main()
