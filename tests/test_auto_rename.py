"""Auto rename: which new objects open in rename, and when.

Run with: python3 tests/test_auto_rename.py
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

from PySide6 import QtCore  # noqa: E402

from freecad.nxt.tree import auto_rename  # noqa: E402


class Doc:
    def __init__(self) -> None:
        self.Name = "Doc"
        self.Restoring = False
        self.Transacting = False
        self.objects: dict[str, Any] = {}

    def getObject(self, name: str) -> Any:
        return self.objects.get(name)


class AutoRenameTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = QtCore.QCoreApplication.instance() or \
            QtCore.QCoreApplication([])
        self.doc = Doc()
        self.on = True
        App.isRestoring = lambda: False
        App.getDocument = lambda _name: self.doc
        auto_rename.settings = types.SimpleNamespace(
            get=lambda key: self.on if key == "AutoRename" else None)
        self.renamed: list[str] = []
        self.watch = auto_rename.AutoRename(None, self.renamed.append)

    def make(self, name: str, type_id: str) -> Any:
        obj = types.SimpleNamespace(Name=name, TypeId=type_id,
                                    Document=self.doc)
        self.doc.objects[name] = obj
        self.watch.created(obj)
        return obj

    def settle(self) -> None:
        self.watch._timer.stop()
        self.watch._fire()

    def test_container_renamed_once_made(self) -> None:
        self.make("Body", "PartDesign::Body")
        self.settle()
        self.assertEqual(self.renamed, ["Body"])

    def test_feature_renamed_when_its_edit_closes(self) -> None:
        pad = self.make("Pad", "PartDesign::Pad")
        self.watch.edit_opened(pad)
        self.settle()
        self.assertEqual(self.renamed, [])
        self.watch.edit_closed(pad)
        self.settle()
        self.assertEqual(self.renamed, ["Pad"])

    def test_cancelled_edit_renames_nothing(self) -> None:
        sketch = self.make("Sketch", "Sketcher::SketchObject")
        self.watch.edit_opened(sketch)
        self.watch.edit_closed(sketch)
        del self.doc.objects["Sketch"]
        self.watch.deleted(sketch)
        self.settle()
        self.assertEqual(self.renamed, [])

    def test_later_edits_and_old_objects_are_left_alone(self) -> None:
        pad = types.SimpleNamespace(Name="Pad", TypeId="PartDesign::Pad",
                                    Document=self.doc)
        self.doc.objects["Pad"] = pad
        self.watch.edit_opened(pad)
        self.watch.edit_closed(pad)
        self.settle()
        self.assertEqual(self.renamed, [])

    def test_loading_undo_and_setting_off(self) -> None:
        self.doc.Restoring = True
        self.make("Part", "App::Part")
        self.doc.Restoring = False
        self.doc.Transacting = True
        self.make("Group", "App::DocumentObjectGroup")
        self.doc.Transacting = False
        self.on = False
        self.make("Body", "PartDesign::Body")
        self.settle()
        self.assertEqual(self.renamed, [])


class ViewProviderWithoutObjectTests(unittest.TestCase):
    """Assembly's view provider has no `Object`; its edits are skipped."""

    def test_observers_skip_it_quietly(self) -> None:
        from freecad.nxt.tools import sketch_repair
        from freecad.nxt.tree import observers
        seen: list[Any] = []
        bridge = types.SimpleNamespace(
            invalidate=lambda **_k: None,
            auto_rename=types.SimpleNamespace(edit_opened=seen.append,
                                              edit_closed=seen.append))
        assembly_view = object()
        gui = observers._GuiObserver(bridge)
        gui.slotInEdit(assembly_view)
        gui.slotResetEdit(assembly_view)
        repair = types.SimpleNamespace(
            consider=lambda obj, edited: seen.append(obj))
        sketch_repair._Observer(repair).slotResetEdit(assembly_view)
        self.assertEqual(seen, [])


if __name__ == "__main__":
    unittest.main()
