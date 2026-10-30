"""Show all, for the document and for one container.

Run with: python3 tests/test_show_all.py
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

from freecad.nxt.tools import show_all  # noqa: E402


class Doc:
    def __init__(self) -> None:
        self.Objects: list[Any] = []
        self.undo: list[str] = []

    def openTransaction(self, name: str) -> None:
        self.undo.append(name)

    def commitTransaction(self) -> None:
        pass


def thing(doc: Doc, name: str, *bases: str, shown: bool = False,
          parent: Any = None, **props: Any) -> Any:
    obj = types.SimpleNamespace(
        Name=name, Document=doc, ViewObject=types.SimpleNamespace(
            Visibility=shown),
        isDerivedFrom=lambda base: base in bases,
        getParentGeoFeatureGroup=lambda: parent, **props)
    doc.Objects.append(obj)
    return obj


class ShowContentsTests(unittest.TestCase):
    def setUp(self) -> None:
        doc = self.doc = Doc()
        self.origin = thing(doc, "Origin", "App::Origin")
        self.pad = thing(doc, "Pad", "PartDesign::Feature")
        self.tip = thing(doc, "Pocket", "PartDesign::Feature")
        self.body = thing(doc, "Body", "PartDesign::Body",
                          Group=[self.pad, self.tip], Tip=self.tip)
        for feature in (self.pad, self.tip):
            feature.getParentGeoFeatureGroup = lambda: self.body
        self.joint = thing(doc, "Joint", JointType="Fixed")
        self.box = thing(doc, "Box", "Part::Feature")
        self.inner = thing(doc, "Inner", "App::DocumentObjectGroup",
                           Group=[self.box])
        self.part = thing(doc, "Part", "App::Part",
                          Group=[self.origin, self.body, self.joint,
                                 self.inner])
        self.outside = thing(doc, "Outside", "Part::Feature")

    def shown(self) -> set[str]:
        return {o.Name for o in self.doc.Objects if o.ViewObject.Visibility}

    def test_container_shows_its_contents_and_itself_only(self) -> None:
        show_all.show_contents(self.part)
        self.assertEqual(self.shown(),
                         {"Part", "Body", "Pocket", "Inner", "Box"})
        self.assertEqual(self.doc.undo, ["Show all"])

    def test_kept_objects_keep_their_visibility(self) -> None:
        self.origin.ViewObject.Visibility = True
        show_all.show_contents(self.part)
        self.assertIn("Origin", self.shown())
        self.assertNotIn("Joint", self.shown())
        self.assertNotIn("Pad", self.shown())

    def test_document_show_all_still_reaches_everything(self) -> None:
        show_all.show_all(self.doc)
        self.assertIn("Outside", self.shown())
        self.assertIn("Box", self.shown())


if __name__ == "__main__":
    unittest.main()
