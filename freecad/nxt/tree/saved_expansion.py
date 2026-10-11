"""Which objects a document file saved as expanded in the tree.

FreeCAD writes each object's tree state into the file's GuiDocument.xml
(`<ViewProvider name="Body" expanded="1" ...>`). It also restores it into
each object's State ("Expanded") - but only through its own tree, and only
some time after the document has loaded, which is after the panel has
already laid the document out. So the panel reads the file itself.
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
