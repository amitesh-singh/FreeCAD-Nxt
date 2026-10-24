"""Space shows or hides what is selected - the feature, not its Body.

FreeCAD files a pick inside a Body under the Body ("Body", "Pad." or
"Face6"), so each entry is resolved to the feature it really means.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

import FreeCAD as App
import FreeCADGui as Gui

from ..core import view3d
from ..core.events import ApplicationEventFilter
from ..core.qt import QtCore
from ..core.transaction import transaction

BODY = "PartDesign::Body"
FEATURE = "PartDesign::Feature"


def _is(obj: Any, type_name: str) -> bool:
    try:
        return bool(obj.isDerivedFrom(type_name))
    except Exception:
        return False


def _shown(obj: Any) -> bool:
    return bool(getattr(getattr(obj, "ViewObject", None), "Visibility",
                        False))


def shown_feature(body: Any) -> Any:
    """The feature a Body's solid is drawn through: its tip, normally."""
    tip = getattr(body, "Tip", None)
    if tip is not None and _shown(tip):
        return tip
    for obj in getattr(body, "Group", ()):
        if _is(obj, FEATURE) and _shown(obj):
            return obj
    return tip


def _picked(doc: Any, top: Any, sub: str) -> Any:
    """The object one selection entry means."""
    path, _dot, element = sub.rpartition(".")
    if path:
        found = doc.getObject(path.split(".")[-1])
        if found is not None:
            return found
    if element and _is(top, BODY):
        return shown_feature(top) or top
    return top


def targets(doc: Any) -> list[Any]:
    """What Space should show or hide in `doc`, from the selection."""
    try:
        selection = Gui.Selection.getSelectionEx(doc.Name, 0)
    except Exception:
        return []
    found: list[Any] = []
    for entry in selection:
        top = getattr(entry, "Object", None)
        if top is None:
            continue
        subs = list(getattr(entry, "SubElementNames", ()) or ()) or [""]
        for sub in subs:
            obj = _picked(doc, top, sub or "")
            if obj is not None and obj not in found:
                found.append(obj)
    return found


def toggle(doc: Any, objects: list[Any],
           show_alone: Callable[[Any, list[str]], None] | None = None
           ) -> None:
    """Show or hide `objects` together, as one undo step.

    If any is shown all are hidden; `show_alone` runs after showing.
    """
    views = [(o, o.ViewObject) for o in objects
             if getattr(o, "ViewObject", None) is not None]
    if not views:
        return
    show = not any(bool(vo.Visibility) for _o, vo in views)
    hidden = [o for o, _vo in views]
    try:
        with transaction(doc, "Toggle visibility"):
            for _obj, vo in views:
                vo.Visibility = show
            if show and show_alone is not None:
                show_alone(doc, [o.Name for o, _vo in views])
            if not show:
                # A Body's feature hidden hands the display back to the
                # one before it; with none before, nothing is shown. The
                # Body's own visibility is never touched.
                for obj in hidden:
                    before = previous_feature(obj, hidden)
                    view = getattr(before, "ViewObject", None)
                    if view is not None:
                        view.Visibility = True
    except Exception:
        App.Console.PrintError("Nxt: visibility toggle failed\n")


def previous_feature(obj: Any, skipping: Sequence[Any] = ()) -> Any:
    """The Body feature `obj` was built on, past any in `skipping`.

    None if `obj` is not a Body's feature or is its first.
    """
    if not _is(obj, FEATURE):
        return None
    body = _body_of(obj)
    before = getattr(obj, "BaseFeature", None)
    seen = set()
    while before is not None and before in skipping \
            and before.Name not in seen:
        seen.add(before.Name)
        before = getattr(before, "BaseFeature", None)
    if (before is None or not _is(before, FEATURE) or body is None
            or not body.hasObject(before)):
        return None
    return before


def _body_of(obj: Any) -> Any:
    for parent in getattr(obj, "InList", ()) or ():
        if _is(parent, BODY):
            return parent
    return None


def toggle_selected() -> None:
    doc = App.ActiveDocument
    if doc is not None:
        toggle(doc, targets(doc))


def _editing() -> bool:
    try:
        gui_doc = Gui.ActiveDocument
        return gui_doc is not None and gui_doc.getInEdit() is not None
    except Exception:
        return False


class SpaceInView(ApplicationEventFilter):
    """Space in a 3D view, ahead of FreeCAD's shortcut; not during edits."""

    def __init__(self, parent: QtCore.QObject | None = None,
                 action: Callable[[], None] = toggle_selected) -> None:
        super().__init__(parent)
        self._action = action

    def eventFilter(self, watched: Any, event: Any) -> bool:  # noqa: N802
        # Sees every application event: cheap test first.
        kind = event.type()
        if kind not in (QtCore.QEvent.Type.ShortcutOverride,
                        QtCore.QEvent.Type.KeyPress):
            return False
        try:
            if (event.key() != QtCore.Qt.Key.Key_Space
                    or event.modifiers()
                    != QtCore.Qt.KeyboardModifier.NoModifier
                    or event.isAutoRepeat()
                    or view3d.view3d_holding(watched) is None or _editing()):
                return False
        except Exception:
            return False
        event.accept()
        if kind == QtCore.QEvent.Type.ShortcutOverride:
            return False        # accepted: the key comes as a KeyPress
        try:
            self._action()
        except Exception as exc:
            App.Console.PrintError("Nxt: Space failed: %s\n" % exc)
        return True
