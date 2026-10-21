"""Run by FreeCAD's Addon Manager when Nxt is uninstalled, if allowed.

Puts back the FreeCAD preferences Nxt changed and deletes its own
(freecad/nxt/app/cleanup.py). Nxt does the same at the next quit, in case
this is not allowed to run.
"""

try:
    from freecad.nxt.app import cleanup
    cleanup.remove_all()
except Exception as exc:
    import FreeCAD
    FreeCAD.Console.PrintError(
        "Nxt: could not clean up its settings: %s\n" % exc)
