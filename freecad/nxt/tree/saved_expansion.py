"""Which objects a document file saved as expanded in the tree.

Read from GuiDocument.xml because FreeCAD sets State "Expanded" only
after the panel has laid the document out.
"""

from __future__ import annotations

import re
import zipfile

_PROVIDER = re.compile(rb"<ViewProvider\b([^>]*)>")
_NAME = re.compile(rb'\bname="([^"]*)"')
_EXPANDED = re.compile(rb'\bexpanded="1"')


def read(path: str) -> set[str]:
    """Names of the objects saved expanded in `path`; empty if unknown."""
    if not path:
        return set()
    try:
        with zipfile.ZipFile(path) as archive:
            data = archive.read("GuiDocument.xml")
    except (OSError, KeyError, zipfile.BadZipFile):
        return set()
    return parse(data)


def parse(data: bytes) -> set[str]:
    out = set()
    for match in _PROVIDER.finditer(data):
        attributes = match.group(1)
        if not _EXPANDED.search(attributes):
            continue
        name = _NAME.search(attributes)
        if name:
            out.add(name.group(1).decode("utf-8", "replace"))
    return out
