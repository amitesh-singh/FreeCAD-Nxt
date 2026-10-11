"""Reading a document file's saved tree state.

Run with: python3 tests/test_saved_expansion.py
"""

from __future__ import annotations

import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from freecad.nxt.tree import saved_expansion  # noqa: E402

GUI = b"""<?xml version='1.0' encoding='utf-8'?>
<Document SchemaVersion="1" HasExpansion="1">
    <Expand count="1"/>
    <ViewProviderData Count="3">
        <ViewProvider name="Part" expanded="1" treeRank="0">
        </ViewProvider>
        <ViewProvider name="Body" expanded="0" treeRank="1">
        </ViewProvider>
        <ViewProvider name="Washer" expanded="1" Extensions="True">
        </ViewProvider>
    </ViewProviderData>
</Document>
"""


class ReadTests(unittest.TestCase):

    def test_the_expanded_ones(self) -> None:
        self.assertEqual(saved_expansion.parse(GUI), {"Part", "Washer"})

    def test_from_a_document_file(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = str(Path(folder) / "Doc.FCStd")
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("GuiDocument.xml", GUI)
            self.assertEqual(saved_expansion.read(path), {"Part", "Washer"})

    def test_nothing_to_read(self) -> None:
        self.assertEqual(saved_expansion.read(""), set())
        self.assertEqual(saved_expansion.read("/no/such/file.FCStd"), set())


if __name__ == "__main__":
    unittest.main(verbosity=2)
