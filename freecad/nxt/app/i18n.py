"""Translation helpers, per FreeCAD's convention for addons."""

from __future__ import annotations

import FreeCAD as App

CONTEXT = "Nxt"


def translate(context: str, text: str) -> str:
    """FreeCAD's `App.Qt.translate`; pass a literal context for lupdate."""
    qt = getattr(App, "Qt", None)
    if qt is None or not hasattr(qt, "translate"):
        return text
    return str(qt.translate(context, text))


def QT_TRANSLATE_NOOP(context: str, text: str) -> str:  # noqa: N802
    """Mark `text` for extraction without translating it here."""
    return text
