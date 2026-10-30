"""Translation helpers, per FreeCAD's convention for addons.

Nxt's text is translated in its own files (resources/translations). A
term FreeCAD already translates (freecad_terms.py, generated) takes
FreeCAD's wording first, so the two always read alike; "Nxt fillet" is
"Nxt " and FreeCAD's "Fillet".

FreeCAD can change language while it runs: widgets and QML views passed
to `follow` are translated again, and `on_change` callbacks run.
"""

from __future__ import annotations

import re
import weakref
from collections.abc import Callable
from functools import lru_cache
from typing import Any

import FreeCAD as App

CONTEXT = "Nxt"
#: The context of the inspector templates' text (scripts/i18n.py
#: extracts it from the TOML files), the template's id disambiguating.
TEMPLATE_CONTEXT = "NxtTemplate"
PREFIX = "Nxt "
_ACCELERATOR = re.compile(r"\(&\w\)|&")
_ELLIPSIS = re.compile(r"(…|\.\.\.)$")


def _qt(context: str, text: str, disambiguation: str | None = None) -> str:
    qt = getattr(App, "Qt", None)
    if qt is None or not hasattr(qt, "translate"):
        return text
    return str(qt.translate(context, text, disambiguation))


def term_key(text: str) -> str:
    """How a term is matched: no case, accelerator or trailing ellipsis."""
    return _ELLIPSIS.sub("", text.replace("&", "")).strip().lower()


def freecad_term(text: str) -> str | None:
    """FreeCAD's own translation of `text`, if it is a term FreeCAD has."""
    from .freecad_terms import TERMS
    prefix = ""
    if text.startswith(PREFIX) and term_key(text) not in TERMS:
        prefix, text = PREFIX, text[len(PREFIX):]
    found = TERMS.get(term_key(text))
    if found is None:
        return None
    context, source = found
    said = _ACCELERATOR.sub("", _qt(context, source)).strip()
    if said == _ACCELERATOR.sub("", source).strip():
        return None                     # FreeCAD has it untranslated here
    ellipsis = _ELLIPSIS.search(text)
    if ellipsis and not _ELLIPSIS.search(said):
        said += ellipsis.group(1)
    return prefix + said


def translate(context: str, text: str,
              disambiguation: str | None = None) -> str:
    """Translated text; pass a literal context for lupdate."""
    if not text:
        return text
    said = freecad_term(text) or _qt(context, text, disambiguation)
    _sources[said] = (context, text, disambiguation)
    return said


@lru_cache(maxsize=None)
def template_text(text: str, template_id: str) -> str:
    """A template's label, title or choice, translated once a language."""
    return translate(TEMPLATE_CONTEXT, text, template_id)


def QT_TRANSLATE_NOOP(context: str, text: str) -> str:  # noqa: N802
    """Mark `text` for extraction without translating it here."""
    return text


#: Each translation given, back to what it was translated from.
_sources: dict[str, tuple[str, str, str | None]] = {}
_widgets: weakref.WeakSet[Any] = weakref.WeakSet()
_views: weakref.WeakSet[Any] = weakref.WeakSet()
_callbacks: list[weakref.ref[Any]] = []
_listener: Any = None


def again(text: str) -> str:
    """`text`, which `translate` gave, in the language now in use."""
    source = _sources.get(text)
    return translate(*source) if source else text


def follow(widget_or_view: Any) -> None:
    """Translate a widget's text, or a QML view, again on a change."""
    _listen()
    if hasattr(widget_or_view, "engine"):
        _views.add(widget_or_view)
    else:
        _widgets.add(widget_or_view)


def on_change(callback: Callable[[], Any]) -> None:
    """Call `callback` after the language changes, while its owner lives."""
    _listen()
    _callbacks.append(weakref.WeakMethod(callback)
                      if hasattr(callback, "__self__")
                      else weakref.ref(callback))


def _listen() -> None:
    global _listener
    if _listener is not None:
        return
    from ..core.qt import QtCore, QtWidgets

    class Listener(QtWidgets.QWidget):
        """Never shown: Qt tells every top-level widget of a change."""

        def __init__(self) -> None:
            super().__init__()
            self.pending = False

        def changeEvent(self, event: Any) -> None:  # noqa: N802
            if event.type() == QtCore.QEvent.Type.LanguageChange \
                    and not self.pending:
                # FreeCAD installs a translator per file: once for all.
                self.pending = True
                QtCore.QTimer.singleShot(0, self.changed)
            super().changeEvent(event)

        def changed(self) -> None:
            self.pending = False
            _changed()

    _listener = Listener()


def _changed() -> None:
    template_text.cache_clear()
    for widget in list(_widgets):
        _retranslate(widget)
    for view in list(_views):
        view.engine().retranslate()
    for ref in list(_callbacks):
        callback = ref()
        if callback is None:
            _callbacks.remove(ref)
        else:
            callback()


def _retranslate(root: Any) -> None:
    from ..core.qt import QtWidgets
    for widget in [root, *root.findChildren(QtWidgets.QWidget)]:
        widget.setWindowTitle(again(widget.windowTitle()))
        widget.setToolTip(again(widget.toolTip()))
        if isinstance(widget, (QtWidgets.QLabel,
                               QtWidgets.QAbstractButton)):
            widget.setText(again(widget.text()))
        elif isinstance(widget, QtWidgets.QGroupBox):
            widget.setTitle(again(widget.title()))
        elif isinstance(widget, QtWidgets.QComboBox):
            for i in range(widget.count()):
                widget.setItemText(i, again(widget.itemText(i)))
