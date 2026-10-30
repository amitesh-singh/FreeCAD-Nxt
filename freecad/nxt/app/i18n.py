"""Translation helpers, per FreeCAD's convention for addons.

Nxt's text is translated in its own files (resources/translations). A
term FreeCAD already translates (freecad_terms.py, generated) takes
FreeCAD's wording first, so the two always read alike; "Nxt fillet" is
"Nxt " and FreeCAD's "Fillet".
"""

from __future__ import annotations

import re
from functools import lru_cache

import FreeCAD as App

CONTEXT = "Nxt"
#: The context of the inspector templates' text (scripts/i18n.py
#: extracts it from the TOML files), the template's id disambiguating.
TEMPLATE_CONTEXT = "NxtTemplate"
PREFIX = "Nxt "
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
    said = _qt(context, source)
    if said == source:
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
    return freecad_term(text) or _qt(context, text, disambiguation)


@lru_cache(maxsize=None)
def template_text(text: str, template_id: str) -> str:
    """A template's label, title or choice, translated once.

    The language is fixed while FreeCAD runs.
    """
    return translate(TEMPLATE_CONTEXT, text, template_id)


def QT_TRANSLATE_NOOP(context: str, text: str) -> str:  # noqa: N802
    """Mark `text` for extraction without translating it here."""
    return text
