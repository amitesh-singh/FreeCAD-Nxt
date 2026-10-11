"""Messages to FreeCAD's Report view."""

from __future__ import annotations

import traceback

import FreeCAD as App


def error(message: str) -> None:
    """Report a failure, with the traceback of the exception being handled."""
    App.Console.PrintError("Nxt: %s\n" % message)
    App.Console.PrintError(traceback.format_exc())
