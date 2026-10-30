"""Typed wrappers for FreeCAD calls missing from or too narrow in the stubs."""

from __future__ import annotations

from typing import Any

import FreeCADGui as Gui


def active_view() -> Any:
    """The active document's view, or None.

    Any: the real API is wider than the stubs, and it may be any MDI view.
    """
    gui_doc = Gui.ActiveDocument
    return gui_doc.ActiveView if gui_doc is not None else None


def object_of(view_provider: Any) -> Any:
    """The document object a view provider shows, or None.

    Not every view provider's Python type has `Object`: Assembly's
    (AssemblyGui.ViewProviderAssembly) does not, yet it enters and
    leaves edit like any other.
    """
    return getattr(view_provider, "Object", None)


def list_commands() -> list[str]:
    """Every registered command's name (not in the stubs)."""
    return list(getattr(Gui, "listCommands")())
