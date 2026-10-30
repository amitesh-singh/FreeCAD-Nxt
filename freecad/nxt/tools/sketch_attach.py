"""A new sketch on three picked points, without the attachment dialog.

Sets "plane by 3 points" and presses the dialog's own OK, which is what
commits the sketch. Shift or the PartDesign preference keeps the dialog.
"""

from __future__ import annotations

import contextlib
import traceback
from typing import Any

import FreeCAD as App
import FreeCADGui as Gui

from ..core import settings
from ..core.qt import QtCore, QtWidgets
from .float_input import task_ok_button

SKETCH = "Sketcher::SketchObject"
MODE = "ThreePointsPlane"
#: Matched by substring: builds spell "PartGui::" or "PartGui__".
ATTACHER_PANEL = "TaskAttacher"
#: The dialog's OK can take a moment to appear.
RETRY_MS = 50
RETRIES = 20
PARTDESIGN_PREFERENCES = "User parameter:BaseApp/Preferences/Mod/PartDesign"

#: Datums picked whole, with no sub-element name.
POINTS = ("App::Point", "PartDesign::Point")
LINES = ("App::Line", "PartDesign::Line")
#: (points, edges) selections answered for.
PLANES = frozenset({(3, 0), (1, 1)})


def _derived(obj: Any, bases: tuple[str, ...]) -> bool:
    return any(obj.isDerivedFrom(base) for base in bases)


def _picked(support: Any) -> tuple[int, int] | None:
    """(points, edges) in the support; None for anything else."""
    points = edges = 0
    for obj, subs in support or ():
        for sub in subs or ("",):
            element = sub.rsplit(".", 1)[-1]
            if element.startswith("Vertex") \
                    or not element and _derived(obj, POINTS):
                points += 1
            elif element.startswith("Edge") \
                    or not element and _derived(obj, LINES):
                edges += 1
            else:
                return None
    return points, edges


def _dialog_asked_for() -> bool:
    shift = QtCore.Qt.KeyboardModifier.ShiftModifier
    return bool(QtWidgets.QApplication.queryKeyboardModifiers() & shift) \
        or bool(App.ParamGet(PARTDESIGN_PREFERENCES).GetBool(
            "NewSketchUseAttachmentDialog", False))


def _log(why: str) -> None:
    App.Console.PrintLog("Nxt new sketch: %s\n" % why)


def _attacher_ok() -> Any:
    for widget in Gui.getMainWindow().findChildren(QtWidgets.QWidget):
        if widget.isVisible() and (
                ATTACHER_PANEL in widget.metaObject().className()
                or ATTACHER_PANEL in widget.objectName()):
            return task_ok_button()
    return None


def _set_mode(sketch: Any) -> bool:
    """Set the 3-point mode; False (reverted) if it does not fit."""
    before = sketch.MapMode
    if before == MODE:
        return True
    if MODE not in sketch.Attacher.suggestModes()["allApplicableModes"]:
        return False            # a curved edge
    sketch.MapMode = MODE
    sketch.recompute()
    if sketch.isValid():
        return True
    sketch.MapMode = before     # points in line
    sketch.recompute()
    return False


class _Observer:
    def __init__(self, attach: SketchAttach) -> None:
        self._attach = attach

    def slotCreatedObject(self, obj: Any) -> None:  # noqa: N802
        if obj.isDerivedFrom(SKETCH):
            self._attach.created(obj)


class SketchAttach(QtCore.QObject):
    """Answers the attachment dialog a new sketch was created with."""

    def __init__(self, parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        self._observer = _Observer(self)
        self._created: tuple[str, str] | None = None
        self._tries = 0
        # Fire after the creating command, once its dialog is up.
        self._timer = QtCore.QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._answer)

    def install(self) -> None:
        App.addDocumentObserver(self._observer)

    def remove(self) -> None:
        self._timer.stop()
        with contextlib.suppress(Exception):
            App.removeDocumentObserver(self._observer)

    def created(self, sketch: Any) -> None:
        if settings.get("AttachSketchByPoints"):
            self._created = (sketch.Document.Name, sketch.Name)
            self._tries = 0
            self._timer.start(0)

    def _answer(self) -> None:
        created, self._created = self._created, None
        try:
            doc = App.ActiveDocument
            if created is None or doc is None or doc.Name != created[0]:
                return
            sketch = doc.getObject(created[1])
            if sketch is None:
                return
            if _dialog_asked_for():
                return _log("Shift or the preference asks for the dialog")
            picked = _picked(sketch.AttachmentSupport)
            if picked not in PLANES:
                return _log("not three points or an edge and a point: %r"
                            % (picked,))
            ok = _attacher_ok()
            if ok is None:
                self._tries += 1
                if self._tries > RETRIES:
                    return _log("no attachment dialog with an OK to press")
                self._created = created
                return self._timer.start(RETRY_MS)
            if not _set_mode(sketch):
                return _log("plane by 3 points does not fit the selection")
            ok.click()
        except Exception:
            App.Console.PrintError(
                "Nxt: could not attach the new sketch by its points\n")
            App.Console.PrintError(traceback.format_exc())
