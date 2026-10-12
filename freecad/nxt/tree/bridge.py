"""The QML-facing object.

Everything QML is allowed to do to the document goes through a slot here.
QML never touches FreeCAD directly: it emits intent ("select this", "drop
these onto that") and this layer decides whether the intent is legal, wraps
it in a transaction, and lets the observers push the result back into the
models.

That one-way discipline is what keeps the panel consistent with the rest of
the UI. A visibility change made in the stock tree, the Python console or a
macro arrives here by exactly the same path as one made in our own delegate.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from functools import partial
from typing import Any

import FreeCAD as App
import FreeCADGui as Gui

from ..app import services
from ..app.i18n import translate
from ..core import fc, log, settings
from ..core.qt import QtCore
from ..core.transaction import transaction
from ..inspector import properties
from ..tools import editing, visibility
from . import (
    drag_drop,
    icons,
    links,
    models,
    picking,
    rollback,
    saved_expansion,
    scene,
)

#: Kept importable from here: tests and older callers use this name.
open_edit_transaction = editing.open_edit_transaction


#: How often to ask the Gui which container is active. There is no signal
#: for it, so this is the one poll in the panel.
ACTIVE_POLL_MS = 500


#: How long a click in the tree stands before its detail strip opens.
AUTO_DETAIL_MS = 300


class TreeBridge(QtCore.QObject):

    documentChanged = QtCore.Signal()
    profileCountChanged = QtCore.Signal()
    problemCountChanged = QtCore.Signal()
    revealTreeRow = QtCore.Signal(int)
    tipBarsChanged = QtCore.Signal()
    searchResultsChanged = QtCore.Signal()
    propertyInspectorRequested = QtCore.Signal(int)
    #: Open the context menu for the selection at this point in the
    #: panel's scene: where the row was right-clicked.
    contextMenuRequested = QtCore.Signal(float, float)
    #: Start renaming this row, as F2 does; asked for by the menu.
    renameRowRequested = QtCore.Signal(int)
    #: Briefly light up these rows: objects just picked outside the panel.
    flashRows = QtCore.Signal(list)
    pickOriginsChanged = QtCore.Signal()
    #: Auto-show is about to open or close strips: note where this row
    #: is, and put it back there once the rows have moved (rowReleased).
    rowHeld = QtCore.Signal(int)
    rowReleased = QtCore.Signal()
    detailAutoShowChanged = QtCore.Signal()
    pinnedDetailsChanged = QtCore.Signal()
    linkArrowsChanged = QtCore.Signal()

    def __init__(self, parent: QtCore.QObject | None = None,
                 widen: bool = False) -> None:
        super().__init__(parent)
        self._widen = widen
        self._tree = models.TreeRowModel(self)
        self._tree.opening = self._opening
        self._snapshot = scene.Snapshot()
        self._dirty = False
        self._icons_dirty = False
        self._pushing_selection = False
        self._related = False       # rows are lit up for the selection
        # Tip bars are addressed by row index, so they are invalidated by any
        # relayout - an expand/collapse moves them without the document
        # changing at all.
        self._tree.rowsRefreshed.connect(self._row_layout_changed)
        self._rollback = rollback.Rollback(self)
        self._drag_drop = drag_drop.DragDrop(self)
        self._search: list[dict[str, Any]] = []
        # Where Shift+click and Shift+arrow ranges start, and where the
        # arrow keys last moved to. Names, not rows: rows shift whenever a
        # branch opens or closes.
        self._anchor: str | None = None
        self._cursor: str | None = None
        # What the open context menu is for: the selection when it opened,
        # which an item that changes the selection must not change under it.
        self._menu_names: list[str] = []

        # Deferrals go through timers parented to this object, never through
        # the static QTimer.singleShot. A static single-shot holds a bound
        # method and outlives the object it was scheduled for, so on reload
        # it fires into a deleted C++ wrapper and raises RuntimeError from a
        # callback with nothing to catch it - which is exactly what filled
        # the report view with save-state errors on the panel. Restarting a
        # timer also debounces for free.
        self._rebuild_timer = self._deferral(self._rebuild_if_dirty)
        # The detail strip follows a click in the tree, after a moment:
        # see _auto_show_detail.
        self._auto_timer = self._deferral(self._auto_show_detail)
        self._activate_timer = self._deferral(self._activate_pending)
        self._pending_active = ""
        self._auto_timer.setInterval(AUTO_DETAIL_MS)
        self._auto_name = ""        # the row the timer is running for
        self._auto_detail = ""      # the strip auto-show has open
        self._pinned: set[str] = set()
        self._edit_timer = self._deferral(self._enter_pending_edit)
        self._recompute_timer = self._deferral(self._recompute_document)
        # Objects picked outside the panel since the last reveal, collected
        # so a box selection - one observer call per object - reveals once.
        self._picked: list[str] = []
        # The features that made what was last picked in the 3D view, when
        # that is not the selected object itself: marked in the tree as
        # SolidWorks marks the feature a picked face belongs to, until the
        # selection next changes.
        self._origins: list[str] = []
        # The dependency arrows now drawn (links.py), and a deferral so a
        # burst of selection and layout changes recomputes them once.
        self._arrows: dict[str, Any] = {"source": -1, "links": []}
        self._arrows_timer = self._deferral(self._update_arrows)
        self._reveal_timer = self._deferral(self._reveal_picked)
        self._pending_edit: tuple[str, str] | None = None

        # Which container new operations land in. There is no observer for
        # this - activating a Body is a Gui action and emits no document
        # signal - so it is polled. One attribute read every half second is
        # far below the noise floor of everything else the panel does, and
        # the alternative is an indicator that silently goes stale, which
        # is worse than no indicator at all.
        self._active = ""
        self._active_timer = QtCore.QTimer(self)
        self._active_timer.setInterval(ACTIVE_POLL_MS)
        self._active_timer.timeout.connect(self._sync_active)
        self._active_timer.start()

        self.rebuild()

    #: Keys `ActiveView.getActiveObject` answers to, in the order the
    #: panel prefers them: a Body inside a Part is the more specific
    #: answer, and the one an operation would actually land in.
    ACTIVE_KEYS: tuple[str, ...] = ("pdbody", "part")

    def active_container(self) -> str:
        """The active Body or Part, as the panel currently sees it."""
        return self._active

    def _read_active(self) -> str:
        try:
            view = fc.active_view()
        except Exception:
            return ""
        if view is None:
            return ""
        for key in self.ACTIVE_KEYS:
            try:
                obj = view.getActiveObject(key)
            except Exception:
                continue
            # Some builds answer with (object, placement, ...) rather than
            # a bare object. Unwrap rather than assume either shape.
            if isinstance(obj, tuple):
                obj = obj[0] if obj else None
            name = getattr(obj, "Name", "")
            if name and name in self._snapshot.nodes:
                return name
        return ""

    def _opening(self, snap: Any) -> set[str]:
        """What a document opens with: as FreeCAD saved it, else closed.

        Read from the file (saved_expansion.py): FreeCAD restores the same
        state into each object only later, through its own tree. What an
        object's State says already is added, for a document whose file
        is gone or not yet saved.
        """
        saved: set[str] = set()
        try:
            doc = App.getDocument(snap.doc_name)
            saved = saved_expansion.read(getattr(doc, "FileName", "") or "")
            saved |= {o.Name for o in doc.Objects
                      if "Expanded" in (getattr(o, "State", None) or ())}
        except Exception:
            pass
        return snap.opening_expansion(saved)

    def save_expansion(self, doc: Any) -> None:
        """Hand what is open in the panel to FreeCAD, as a save begins.

        FreeCAD writes into the file what its own tree has open, which is
        where `_opening` reads it back - here or in stock FreeCAD. Its tree
        is told container by container, parents first, since a stock tree
        item does not exist until its parent has been opened.
        """
        snap = self._snapshot
        if snap is None or doc is None or snap.doc_name != doc.Name:
            return
        try:
            gui_doc = Gui.getDocument(doc.Name)
        except Exception:
            return
        wanted = self._tree.expanded()
        depth: dict[str, int] = {}

        def level(name: str) -> int:
            if name not in depth:
                parent = snap.nodes[name].parent
                depth[name] = 0 if parent not in snap.nodes \
                    else level(parent) + 1
            return depth[name]

        names = [n for n, node in snap.nodes.items()
                 if node.is_container and not node.is_virtual]
        for name in sorted(names, key=level):
            obj = doc.getObject(name)
            if obj is None:
                continue
            want = name in wanted
            have = "Expanded" in (getattr(obj, "State", None) or ())
            if want == have:
                continue
            try:
                # 2 expands the stock tree's item, 1 collapses it.
                gui_doc.toggleTreeItem(obj, 2 if want else 1)
            except Exception:
                pass

    def _sync_active(self) -> None:
        name = self._read_active()
        if name == self._active:
            return
        self._active = name
        self._tree.set_active(name)
        if name:
            # The Body you are working in, and the way down to it, open.
            self._tree.reveal(name)
            self._tree.set_expanded(name, True)
        self._rollback.publish()        # the bar goes with the active Body

    def _deferral(self, slot: Callable[[], Any]) -> QtCore.QTimer:
        timer = QtCore.QTimer(self)
        timer.setSingleShot(True)
        timer.setInterval(0)
        timer.timeout.connect(slot)
        return timer

    # ------------------------------------------------------------------ #
    # properties for QML
    # ------------------------------------------------------------------ #

    @QtCore.Property(QtCore.QObject, constant=True)
    def treeModel(self) -> models.TreeRowModel:
        return self._tree

    @QtCore.Property(str, notify=documentChanged)
    def documentLabel(self) -> str:
        doc = App.ActiveDocument
        if doc is None:
            return ""
        return getattr(doc, "Label", doc.Name)

    @QtCore.Property(bool, notify=documentChanged)
    def hasDocument(self) -> bool:
        return App.ActiveDocument is not None

    @QtCore.Property(int, notify=profileCountChanged)
    def profileCount(self) -> int:
        return len(self._snapshot.profiles)

    @QtCore.Property(int, notify=problemCountChanged)
    def problemCount(self) -> int:
        return len(self._snapshot.problem_profiles())

    def _row_layout_changed(self) -> None:
        # Repeater rebuilds every delegate when its model changes, which
        # mid-drag would destroy the bar under the cursor and drop the mouse
        # grab. The live preview relays out constantly, so hold the signal
        # until the drag finishes.
        if self._rollback.drag is None:
            self._rollback.publish()
        self._arrows_timer.start()

    @QtCore.Property(list, notify=tipBarsChanged)
    def tipBars(self) -> list[dict[str, Any]]:
        return self._rollback.bars()

    # ------------------------------------------------------------------ #
    # rebuild plumbing
    # ------------------------------------------------------------------ #

    def invalidate(self, icons: bool = False) -> None:
        """Mark the snapshot stale.

        Coalesces a burst of document signals into a single rebuild on
        the next event-loop turn, which matters a lot during recompute
        of a large document.

        A tip drag is the one case where even that is too often. Moving the
        tip writes Tip, writes visibilities and recomputes, and every one of
        those reaches an observer - so each feature the bar crosses would
        re-walk the whole document, re-read every sketch's solver state and
        rebuild every row, to learn a handful of facts the bridge itself
        just wrote. The snapshot is patched in place instead (see
        `Rollback._apply_tip`), and the staleness is remembered until the
        drag ends.
        """
        self._icons_dirty = self._icons_dirty or icons
        self._dirty = True
        if self._rollback.drag is None:
            self._rebuild_timer.start()

    def _rebuild_if_dirty(self) -> None:
        if not self._dirty:
            return
        self.rebuild()

    def rebuild(self) -> None:
        bump = self._icons_dirty
        self._dirty = False
        self._icons_dirty = False
        previous = self._snapshot.doc_name if self._snapshot else ""
        self._snapshot = scene.capture(
            widen=self._widen, part_layout=settings.get("PartLayout"))
        self._rollback.restore_model_tips()
        self._tree.set_snapshot(self._snapshot, bump_icons=bump)
        self.sync_selection()
        # The snapshot may have replaced the node the mark was on, so the
        # model is told again rather than left holding a name from the
        # document that was open a moment ago.
        self._active = self._read_active()
        self._tree.set_active(self._active)
        if self._snapshot.doc_name != previous:
            self.documentChanged.emit()
        self.profileCountChanged.emit()
        self.problemCountChanged.emit()

    # ------------------------------------------------------------------ #
    # selection
    # ------------------------------------------------------------------ #

    def sync_selection(self, picked: bool = False) -> None:
        """Pull Gui.Selection into the model. Called by the observer.

        `picked` says the selection grew from outside the panel - a click
        in the 3D view, most often - and the rows it added should be
        brought into view; see _reveal_picked. The panel's own selections
        go through _push_selection, which this ignores while it runs.
        """
        if self._pushing_selection:
            return
        if self._origins:
            self._origins = []
            self.pickOriginsChanged.emit()
            self._arrows_timer.start()
        names: list[str] = []
        try:
            # Resolved (the default): a face picked on a Body's solid
            # gives the feature that made it, not the Body.
            for obj in Gui.Selection.getSelection(self._snapshot.doc_name):
                if obj.Name not in names:
                    names.append(obj.Name)
        except Exception:
            pass
        before = set(self._tree.selection())
        self._tree.set_selection(names)
        self._mark_related(names)
        self._arrows_timer.start()
        if picked:
            added = [n for n in names
                     if n not in before and n in self._snapshot.nodes]
            if added:
                self._picked += [n for n in added if n not in self._picked]
                self._reveal_timer.start()

    def picked(self, doc_name: str, top: str, subname: str) -> None:
        """Something was picked outside the panel: reveal what made it.

        Called by the selection observer with what it was given. A face on
        a Body's solid is reported against the tip; picking.target goes
        back to the feature that made the face (see picking.py).
        """
        if self._pushing_selection:
            return
        full = subname
        try:
            top, full = picking.full_pick(
                top, subname, Gui.Selection.getSelectionEx(doc_name, 0))
            name = picking.target(App.getDocument(doc_name), top, full)
        except Exception:
            log.error("could not trace the pick %s.%s" % (top, subname))
            name = None
        # Log level: shown in the Report view only with log messages on.
        App.Console.PrintLog("Nxt pick: %s -> %s.%s -> %s\n"
                             % (subname, top, full, name))
        if name and name in self._snapshot.nodes:
            if name not in self._picked:
                self._picked.append(name)
            self._reveal_timer.start()

    @QtCore.Property(list, notify=pickOriginsChanged)
    def pickOrigins(self) -> list[str]:  # noqa: N802 - QML API
        return list(self._origins)

    @QtCore.Property("QVariantMap",  # type: ignore[arg-type]
                     notify=linkArrowsChanged)
    def linkArrows(self) -> dict[str, Any]:  # noqa: N802 - QML API
        return dict(self._arrows)

    def _arrow_subject(self) -> str | None:
        """Whose links to draw, if anyone's.

        The feature a 3D pick traced to, else the one selected object;
        nothing when several are selected.
        """
        if len(self._origins) == 1:
            return self._origins[0]
        selected = list(self._tree.selection())
        return selected[0] if len(selected) == 1 else None

    def _update_arrows(self) -> None:
        arrows: dict[str, Any] = {"source": -1, "links": []}
        name = self._arrow_subject()
        if name is not None and settings.get("DependencyArrows"):
            try:
                arrows = links.arrows(self._snapshot, name,
                                      self._tree.row_of)
            except Exception:
                log.error("could not work out the links of %s" % name)
        if arrows != self._arrows:
            self._arrows = arrows
            self.linkArrowsChanged.emit()

    def _reveal_picked(self) -> None:
        """Mark what made the pick; open its path, scroll to it, flash it.

        The mark is always made. Scrolling, and the flash that says where
        the list moved to, follow the "Show objects picked in the 3D view"
        setting - SolidWorks' "Scroll selected item into view". Scrolls to
        the first picked row in tree order, so a box selection lands at
        the top of what it caught; every picked row flashes.

        None of it for an origin plane, axis or point a task is being
        given: opening the Origin under a pick made for the task moves
        the tree for nothing.
        """
        picked, self._picked = self._picked, []
        doc = App.ActiveDocument
        picked = [n for n in picked if n in self._snapshot.nodes
                  and not (doc is not None and editing.is_reference_pick(
                      doc.getObject(n)))]
        if not picked:
            return
        selected = self._tree.selection()
        origins = [n for n in picked if n not in selected]
        if origins != self._origins:
            self._origins = origins
            self.pickOriginsChanged.emit()
            self._arrows_timer.start()
        if not settings.get("FollowSelection"):
            return
        for name in picked:
            self._tree.reveal(name)
        rows = sorted(r for r in (self._tree.row_of(n) for n in picked)
                      if r >= 0)
        if rows:
            self.revealTreeRow.emit(rows[0])
            self.flashRows.emit(picked)

    def _push_selection(self, names: Iterable[str],
                        additive: bool) -> None:
        doc = App.ActiveDocument
        if doc is None:
            return
        self._pushing_selection = True
        try:
            if not additive:
                Gui.Selection.clearSelection()
            for name in names:
                if not scene.is_virtual(name):
                    Gui.Selection.addSelection(doc.Name, name)
        except Exception:
            log.error("selection push failed")
        finally:
            self._pushing_selection = False
        self.sync_selection()

    @QtCore.Slot(str, bool)
    def select(self, name: str, additive: bool = False) -> None:
        self._anchor = self._cursor = name
        if additive:
            self._auto_timer.stop()
        else:
            self._auto_name = name
            self._auto_timer.start()
        if additive:
            try:
                doc: Any = App.ActiveDocument
                already = {o.Name for o
                           in Gui.Selection.getSelection(doc.Name)}
                if name in already:
                    Gui.Selection.removeSelection(doc.Name, name)
                    self.sync_selection()
                    return
            except Exception:
                pass
        self._push_selection([name], additive)

    @QtCore.Slot()
    def clearSelection(self) -> None:
        try:
            Gui.Selection.clearSelection()
        except Exception:
            log.error("clear selection failed")
        self.sync_selection()

    # ------------------------------------------------------------------ #
    # visibility
    # ------------------------------------------------------------------ #

    def _show_alone(self, doc: Any, shown: Iterable[str]) -> None:
        """Hide the rest of a Body's features when one of them is shown.

        A Body shows through one feature at a time, so showing one is
        choosing it: whichever was showing before - the tip, or one picked
        earlier - gives way. Of several shown at once in the same Body,
        the latest in its history stays. Sketches and datums are not
        features of the stack and keep their own visibility.
        """
        nodes = getattr(self._snapshot, "nodes", None) or {}
        keep: dict[str, str] = {}           # Body -> the feature to show
        for name in shown:
            owner = getattr(nodes.get(name), "body", None) or ""
            body = nodes.get(owner)
            if body is None or name not in body.stack:
                continue
            held = keep.get(owner)
            if held is None or body.stack.index(name) > body.stack.index(
                    held):
                keep[owner] = name
        for body_name, name in keep.items():
            for other in nodes[body_name].stack:
                vo = getattr(doc.getObject(other), "ViewObject", None)
                if vo is None:
                    continue
                wanted = other == name
                if bool(vo.Visibility) != wanted:
                    vo.Visibility = wanted

    @QtCore.Slot(str)
    def toggleVisibility(self, name: str) -> None:
        doc = App.ActiveDocument
        if doc is None:
            return
        obj = doc.getObject(name)
        vo = getattr(obj, "ViewObject", None)
        if vo is None:
            return
        try:
            with transaction(doc, "Toggle visibility"):
                vo.Visibility = not bool(vo.Visibility)
                if vo.Visibility:
                    self._show_alone(doc, [name])
        except Exception:
            log.error("visibility toggle failed for %s" % name)
        self.invalidate()

    # ------------------------------------------------------------------ #
    # tip
    # ------------------------------------------------------------------ #

    @QtCore.Slot(str)
    def beginTipDrag(self, body_name: str) -> None:
        self._rollback.begin_drag(body_name)

    @QtCore.Slot(str, int)
    def previewTipRow(self, body_name: str, row: int) -> None:
        self._rollback.preview_row(body_name, row)

    @QtCore.Slot(str)
    def endTipDrag(self, body_name: str) -> None:
        self._rollback.end_drag(body_name)

    @QtCore.Slot(str)
    def cancelTipDrag(self, body_name: str) -> None:
        self._rollback.cancel_drag(body_name)

    @QtCore.Slot(str, int)
    def setTipToRow(self, body_name: str, row: int) -> None:
        self._rollback.set_tip_to_row(body_name, row)

    @QtCore.Slot(str, str)
    def setTip(self, body_name: str, feature_name: str) -> None:
        self._rollback.set_tip(body_name, feature_name)

    # ------------------------------------------------------------------ #
    # expansion
    # ------------------------------------------------------------------ #

    @QtCore.Slot(str, bool)
    def setExpanded(self, name: str, expanded: bool) -> None:
        self._tree.set_expanded(name, expanded)

    @QtCore.Slot(str)
    def toggleExpanded(self, name: str) -> None:
        self._tree.set_expanded(name, not self._tree.is_expanded(name))

    @QtCore.Slot()
    def expandAll(self) -> None:
        self._tree.expand_all()

    @QtCore.Slot()
    def collapseAll(self) -> None:
        self._tree.collapse_all()

    @QtCore.Slot(bool)
    def collapseTree(self, expand: bool) -> None:  # noqa: N802
        """The header's control: everything closed, or with Shift, open.

        Closing keeps the way down to the active Body or Part open, so
        where you are working is still a row in view.
        """
        if expand:
            self._tree.expand_all()
            return
        self._tree.collapse_all()
        if self._active:
            self._tree.reveal(self._active)

    # ------------------------------------------------------------------ #
    # cross-panel navigation
    # ------------------------------------------------------------------ #

    @QtCore.Slot(str)
    def revealObjectRow(self, name: str) -> None:
        """Select an object and scroll its row into view, opening the path.

        One destination now. When profiles lived in a shelf this had to
        choose a half first, and the choice was the only reason two of
        these existed.
        """
        self._push_selection([name], False)
        self._tree.reveal(name)
        row = self._tree.row_of(name)
        if row >= 0:
            self.revealTreeRow.emit(row)

    def _mark_related(self, names: Iterable[str]) -> None:
        """Light up the rows the selection is related to, if asked to.

        Both directions at once: a selected profile marks every feature
        that consumes it, a selected feature marks the profiles it reads.
        Off unless the "HighlightRelated" preference is on; it used to
        follow the pointer, which lit rows up on the way to somewhere else.
        """
        related: list[str] = []
        if settings.get("HighlightRelated"):
            chosen = set(names)
            for name in chosen:
                node = self._snapshot.nodes.get(name)
                if node is None:
                    continue
                related += [n for n, _l, _p in node.consumers]
                related += [n for n, _l, _s, _part in node.refs]
            related = [n for n in related if n not in chosen]
        if related or self._related:
            self._related = bool(related)
            self._tree.set_highlight(related)

    def refresh_related(self) -> None:
        """The preference changed: mark, or stop marking, at once."""
        self._mark_related(self._tree.selection())

    # ------------------------------------------------------------------ #
    # per-row detail
    # ------------------------------------------------------------------ #

    @QtCore.Slot(str, str, "QVariant")
    def setKeyProperty(self, name: str, prop: str, value: Any) -> None:
        """Edit one of the strip's key values, as one undo step."""
        doc = App.ActiveDocument
        obj = doc.getObject(name) if doc is not None else None
        if obj is not None and properties.apply(obj, prop, value):
            self.invalidate()

    @QtCore.Slot(str, float, float)
    def openPropertyInspector(self, name: str, left: float,
                              top: float) -> None:
        """Open the Property Inspector for `name` at a global position.

        `left` is the edge of the widest pill on screen when the panel is
        in the 3D view, and negative when docked, where the inspector lines
        up with the dock instead. The object is selected first: the borrowed
        editor always shows the selection.
        """
        from ..inspector import host as property_inspector
        if name:
            self._push_selection([name], False)
        property_inspector.open_inspector(
            left=int(left) if left >= 0 else None,
            top=int(top) if top >= 0 else None)

    def request_property_inspector(self) -> None:
        """Open the inspector for the selection, from its row if it has one.

        The row knows where its edge is, so QML is asked to open it; with
        no row on screen the inspector opens with no anchor.
        """
        name = self._sole_selection()
        row = self._tree.row_of(name) if name else -1
        if row >= 0:
            self.propertyInspectorRequested.emit(row)
        else:
            self.openPropertyInspector(name or "", -1.0, -1.0)

    # ------------------------------------------------------------------ #
    # context menu
    # ------------------------------------------------------------------ #

    @QtCore.Slot(str, float, float)
    def requestContextMenu(self, name: str, x: float, y: float) -> None:
        """Right-click on a row: select it, then open the menu at (x, y).

        The point is in the panel's scene, not on the screen: under
        Wayland an application cannot read the pointer's position on the
        screen, so a menu told to open "at the pointer" opened in a corner.

        A row that is already part of the selection keeps the selection as
        it is, as every file manager does, so a menu can act on several.
        """
        if name and name not in self._selected_names():
            self.select(name, False)
        # Opened on the next turn of the event loop, not inside the press
        # that asked for it: the selection change above is still being
        # delivered to FreeCAD's observers, and the menu is built from it.
        QtCore.QTimer.singleShot(
            0, self, lambda: self.contextMenuRequested.emit(x, y))

    @QtCore.Slot(result=int)
    def contextMenuRow(self) -> int:
        """The row the keyboard's menu opens beside.

        The cursor's row if it is selected, else the first selected row;
        -1 with nothing selected.
        """
        selected = self._selected_names()
        if self._cursor in selected:
            return self._tree.row_of(self._cursor or "")
        rows = [r for r in (self._tree.row_of(n) for n in selected)
                if r >= 0]
        return min(rows) if rows else -1

    @QtCore.Slot(result="QVariant")
    def contextMenu(self) -> dict[str, Any]:
        """The menu for the current selection, as plain data."""
        from . import menu_actions
        self._menu_names = self._selected_names()
        try:
            return menu_actions.build(self, self._menu_names)
        except Exception:
            log.error("the context menu could not be built")
            return {}

    @QtCore.Slot(str)
    def runMenuItem(self, command: str) -> None:
        from . import menu_actions
        menu_actions.run(self, command, list(self._menu_names))

    @QtCore.Slot(str, result=bool)
    def toggleDetail(self, name: str) -> bool:
        """Open or close a row's detail strip."""
        opened = self._tree.toggle_detail(name)
        if not opened and name in self._pinned:
            self._pinned.discard(name)      # closed by hand: unpinned
            self.pinnedDetailsChanged.emit()
        return opened

    def _auto_show_detail(self) -> None:
        """Open the clicked row's detail strip, and close the last one.

        The "DetailAutoShow" preference. Only for one row picked in the
        tree, and only once the click has stood for a moment, so a strip
        does not flicker open on every row passed through. The strip this
        opened before is closed again unless it has been pinned; strips
        opened by hand are never touched. The clicked row is held where
        it is on screen while the rows around it change height.
        """
        name = self._auto_name
        if not settings.get("DetailAutoShow") or not name \
                or self._selected_names() != [name]:
            return
        last = self._auto_detail
        if last == name:
            return
        self.rowHeld.emit(self._tree.row_of(name))
        if last and last not in self._pinned:
            self._tree.close_details([last])
        self._tree.toggle_detail(name, True)
        self._auto_detail = name
        self.rowReleased.emit()

    def refresh_auto_detail(self) -> None:
        """The preference changed: nothing is pinned once it is off."""
        if not settings.get("DetailAutoShow"):
            self._auto_timer.stop()
            self._auto_detail = ""
            if self._pinned:
                self._pinned = set()
                self.pinnedDetailsChanged.emit()
        self.detailAutoShowChanged.emit()

    @QtCore.Property(bool, notify=detailAutoShowChanged)
    def detailAutoShow(self) -> bool:  # noqa: N802 - QML API
        return bool(settings.get("DetailAutoShow"))

    @QtCore.Property(list, notify=pinnedDetailsChanged)
    def pinnedDetails(self) -> list[str]:  # noqa: N802 - QML API
        return sorted(self._pinned)

    @QtCore.Slot(str)
    def toggleDetailPin(self, name: str) -> None:  # noqa: N802
        """Keep this strip open while auto-show moves on, or stop."""
        self._pinned ^= {name}
        self.pinnedDetailsChanged.emit()

    @QtCore.Slot(result=bool)
    def closeDetail(self) -> bool:
        """Escape: close the selected rows' strips, else every open one."""
        return (self._tree.close_details(self._selected_names())
                or self._tree.close_details())

    # ------------------------------------------------------------------ #
    # search
    # ------------------------------------------------------------------ #

    @QtCore.Property(list, notify=searchResultsChanged)
    def searchResults(self) -> list[dict[str, Any]]:
        return self._search

    @QtCore.Slot(str)
    def setSearch(self, text: str) -> None:
        results: list[dict[str, Any]] = []
        for node in self._snapshot.search(text):
            path = self._snapshot.path_of(node.name)
            results.append({
                "name": node.name,
                "label": node.label,
                "context": " \u203a ".join(path),
                "isProfile": node.is_profile,
                "iconUrl": icons.url_for(self._snapshot.doc_name, node.name,
                                         self._tree.icon_revision()),
            })
        if results != self._search:
            self._search = results
            self.searchResultsChanged.emit()

    @QtCore.Slot()
    def revealFirstProblem(self) -> None:
        """Header count -> the first profile with something wrong with it."""
        problems = self._snapshot.problem_profiles()
        if problems:
            self.revealObjectRow(problems[0])
            self._tree.toggle_detail(problems[0], True)

    @QtCore.Slot(str)
    def revealObject(self, name: str) -> None:
        """Go to a search hit: select it, open the path to it, scroll it in."""
        if name in self._snapshot.nodes:
            self.revealObjectRow(name)

    # ------------------------------------------------------------------ #
    # rename
    # ------------------------------------------------------------------ #

    def _sole_selection(self) -> str | None:
        """The one selected object, or None.

        Keyboard actions work on the selection rather than on a list's
        current index, so the same key does the same thing wherever the
        row happens to be.
        """
        try:
            selected = Gui.Selection.getSelection(self._snapshot.doc_name)
        except Exception:
            return None
        if len(selected) != 1:
            return None
        return selected[0].Name

    @QtCore.Slot(result=int)
    def treeRenameRow(self) -> int:
        name = self._sole_selection()
        if name is None:
            return -1
        return self._tree.row_of(name)

    @QtCore.Slot()
    def toggleSelectedVisibility(self) -> None:
        """Space: show or hide everything selected, as one undo step.

        All the same way rather than each flipped: with a mix of shown and
        hidden objects, flipping each would swap them, which is never what
        is wanted. If any is shown they are all hidden, otherwise shown.
        """
        doc = App.ActiveDocument
        if doc is None:
            return
        # FreeCAD files a feature picked in a Body under the Body, so the
        # selection is read through visibility.targets: the feature, not
        # its container.
        visibility.toggle(doc, visibility.targets(doc), self._show_alone)
        self.invalidate()

    def _selected_names(self) -> list[str]:
        try:
            doc = App.ActiveDocument
            if doc is None:
                return []
            return [o.Name for o in Gui.Selection.getSelection(doc.Name)]
        except Exception:
            return []

    @QtCore.Slot(str)
    def selectRange(self, name: str) -> None:
        """Shift+click: every row from the anchor to `name`, inclusive.

        The anchor is the last row clicked without Shift, or moved to with
        an arrow key; without one, the range is just this row.
        """
        start = self._tree.row_of(self._anchor) if self._anchor else -1
        end = self._tree.row_of(name)
        if end < 0:
            return
        if start < 0:
            start = end
        self._cursor = name
        low, high = sorted((start, end))
        names = [self._tree.name_at(row) for row in range(low, high + 1)]
        self._push_selection([n for n in names if n is not None], False)

    @QtCore.Slot(int, bool, result=int)
    def stepSelection(self, step: int, extend: bool) -> int:
        """Up/Down: select the row above or below; with Shift, extend.

        Moves from the last row stepped to or clicked, so repeated presses
        walk the list even while a range is selected. Returns the new row,
        for the view to scroll to, or -1 when there is nowhere to go.
        """
        count = self._tree.rowCount()
        if count == 0:
            return -1
        here = self._tree.row_of(self._cursor) if self._cursor else -1
        if here < 0:
            selected = self._selected_names()
            rows = [self._tree.row_of(n) for n in selected]
            rows = [r for r in rows if r >= 0]
            here = (max(rows) if step > 0 else min(rows)) if rows else -1
        target = 0 if here < 0 else max(0, min(count - 1, here + step))
        return self._select_row(target, extend)

    @QtCore.Slot(bool, bool, result=int)
    def jumpSelection(self, to_end: bool, extend: bool) -> int:  # noqa: N802
        """Home/End: select the first or last row; with Shift, extend.

        Returns the row, for the view to scroll to, or -1 with no rows.
        """
        return self._select_row(
            self._tree.rowCount() - 1 if to_end else 0, extend)

    def _select_row(self, target: int, extend: bool) -> int:
        """Move the keyboard's place to a row. The row, or -1 if none."""
        name = self._tree.name_at(target)
        if name is None:
            return -1
        self._cursor = name
        if extend:
            self.selectRange(name)
        else:
            self._anchor = name
            self._push_selection([name], False)
        return target

    @QtCore.Slot(int, result="QVariantList")
    def breadcrumb(self, row: int) -> list[dict[str, Any]]:
        """The containers a row is shown inside, outermost first.

        For the strip pinned over the list once they have scrolled away
        (Breadcrumb.qml): each with its own row, to scroll back to.
        """
        crumbs = []
        for above in self._tree.ancestor_rows(row):
            name = self._tree.name_at(above)
            node = self._snapshot.nodes.get(name) if name else None
            if node is not None:
                crumbs.append({"row": above, "label": node.label})
        return crumbs

    @QtCore.Slot(int, result=int)
    def stepBranch(self, step: int) -> int:
        """Right/Left: open or close a branch, else move into or out of it.

        Right opens a closed branch, and on an open one moves to its first
        child. Left closes an open branch, and elsewhere moves to the
        parent. Acts on the row last stepped to or clicked. Returns the row
        now current, for the view to scroll to, or -1 when nothing moved.
        """
        name = self._cursor
        if name is None or self._tree.row_of(name) < 0:
            selected = self._selected_names()
            name = selected[-1] if selected else None
        here = self._tree.row_of(name) if name else -1
        if name is None or here < 0:
            return -1
        node = self._snapshot.nodes.get(name)
        branch = node is not None and bool(node.children)
        open_ = self._tree.is_expanded(name)
        depth = self._tree.depth_at(here)
        if step > 0:
            if branch and not open_:
                self._tree.set_expanded(name, True)
                return here
            target = here + 1
            if not (branch and open_ and self._tree.depth_at(target) > depth):
                return -1
        else:
            if branch and open_:
                self._tree.set_expanded(name, False)
                return self._tree.row_of(name)
            target = here - 1
            while target >= 0 and self._tree.depth_at(target) >= depth:
                target -= 1
            if target < 0:
                return -1
        found = self._tree.name_at(target)
        if found is None:
            return -1
        self._cursor = self._anchor = found
        self._push_selection([found], False)
        return target

    @QtCore.Slot(str, str)
    def rename(self, name: str, label: str) -> None:
        """Set an object's Label.

        Label, not Name: Name is the immutable internal identifier every
        link in the document is written against, and the panel addresses
        rows by it. Renaming touches only what is displayed.
        """
        doc = App.ActiveDocument
        if doc is None:
            return
        obj = doc.getObject(name)
        label = (label or "").strip()
        if obj is None or not label or label == obj.Label:
            return
        try:
            old = obj.Label
            with transaction(doc, "Rename"):
                obj.Label = label
            self._toast(doc, translate("Nxt", "Renamed %s to %s")
                        % (old, label))
        except Exception:
            log.error("could not rename %s" % name)
        self.invalidate()

    # ------------------------------------------------------------------ #
    # the undo toast
    # ------------------------------------------------------------------ #

    @staticmethod
    def _named(doc: Any, names: Iterable[Any]) -> str:
        """One object by its label; several by how many there are."""
        names = [str(n) for n in names]
        if len(names) != 1:
            return translate("Nxt", "%d objects") % len(names)
        obj = doc.getObject(names[0]) if doc is not None else None
        return str(getattr(obj, "Label", names[0]))

    def _toast(self, doc: Any, message: str, body: str = "") -> None:
        """Say what the panel just did, and offer to undo it (toast.py).

        `body` is the Body whose tip moved, if one did.
        """
        services.toast(
            doc, message,
            partial(self._rollback.show_through_tip, body) if body else None)

    # ------------------------------------------------------------------ #
    # activation
    # ------------------------------------------------------------------ #

    @QtCore.Slot(str)
    def activate(self, name: str) -> None:
        """Double-click: open a container, edit anything else.

        A Body, Part or assembly that is not the active one is made
        active first; only the active one opens and closes. Nothing for
        an origin plane, axis or point a task is being given.
        """
        doc = App.ActiveDocument
        if doc is None or editing.is_reference_pick(doc.getObject(name)):
            return
        node = self._snapshot.nodes.get(name)
        if node is not None and node.is_container and not node.is_lifted:
            if name != self._active and self._active_key(
                    doc.getObject(name)):
                # Deferred, as an edit is below: activating can switch
                # workbench or open a task.
                self._pending_active = name
                self._activate_timer.start()
                return
            self.toggleExpanded(name)
            return
        if doc.getObject(name) is None:
            return
        # Deferred: this is reached from a delegate's onDoubleClicked, and
        # setEdit opens a task dialog, which nests an event loop and tears
        # down docks. Anything that destroys the delegate while its handler
        # is still on the stack aborts the process.
        self._pending_edit = (doc.Name, name)
        self._edit_timer.start()

    @staticmethod
    def _active_key(obj: Any) -> str:
        """The key FreeCAD keeps this kind of active container under."""
        type_id = str(getattr(obj, "TypeId", ""))
        if type_id == "PartDesign::Body":
            return "pdbody"
        try:
            if type_id.startswith("Assembly::Assembly") \
                    or obj.isDerivedFrom("App::Part"):
                return "part"
        except Exception:
            pass
        return ""

    def _activate_pending(self) -> None:
        """Make the double-clicked container the active one.

        As FreeCAD's own tree does it - the view provider's double click,
        which also brings up the container's workbench - and, if that
        did not take, by setting the active object directly.
        """
        name, self._pending_active = self._pending_active, ""
        doc = App.ActiveDocument
        obj = doc.getObject(name) if doc is not None and name else None
        key = self._active_key(obj)
        if obj is None or not key:
            return
        try:
            obj.ViewObject.doubleClicked()
        except Exception:
            pass
        try:
            view = fc.active_view()
            if self._read_active() != name and view is not None:
                view.setActiveObject(key, obj)
        except Exception:
            log.error("could not make %s active" % name)
        self._sync_active()

    def edit_feature(self, doc_name: str, name: str) -> None:
        """Mark and reveal a feature opened for editing outside the panel.

        Connected to `services.featurePicked` (a face double-clicked in the
        3D view). The edit itself is the services' job, so it happens with
        the panel closed too; this is only what the panel adds when open.
        """
        if doc_name != getattr(App.ActiveDocument, "Name", None):
            return
        if name in self._snapshot.nodes:
            if name not in self._picked:
                self._picked.append(name)
            self._reveal_timer.start()

    def _enter_pending_edit(self) -> None:
        pending, self._pending_edit = self._pending_edit, None
        if pending is not None:
            self._enter_edit(*pending)

    def _recompute_document(self) -> None:
        doc = App.ActiveDocument
        if doc is None:
            return
        try:
            doc.recompute()
        except Exception:
            log.error("could not recompute after a drop")

    def _enter_edit(self, doc_name: str, name: str) -> None:
        """Edit an object inside an undo step of its own (editing.py)."""
        editing.open_for_edit(
            doc_name, name,
            handles=not settings.get("TreeEditHidesHandles"))

    # ------------------------------------------------------------------ #
    # drag and drop
    # ------------------------------------------------------------------ #

    @QtCore.Slot(str, result="QVariantList")
    def dragNames(self, name: str) -> list[str]:  # noqa: N802
        return self._drag_drop.drag_names(name)

    @QtCore.Slot("QVariantList", result=bool)
    def inOneBody(self, names: list[Any]) -> bool:  # noqa: N802
        return self._drag_drop.in_one_body(names)

    @QtCore.Slot("QVariantList", result=str)
    def slideContainer(self, names: list[Any]) -> str:  # noqa: N802
        return self._drag_drop.slide_container(names)

    @QtCore.Slot("QVariantList", str, result=bool)
    def canReorderOn(self, sources: list[Any], target_name: str) -> bool:  # noqa: N802
        return self._drag_drop.can_reorder_on(sources, target_name)

    @QtCore.Slot("QVariantList", str, result=bool)
    def canDropInto(self, sources: list[Any], target_name: str) -> bool:  # noqa: N802
        return self._drag_drop.can_drop_into(sources, target_name)

    @QtCore.Slot("QVariantList", str, result=bool)
    def reorderOn(self, sources: list[Any], target_name: str) -> bool:  # noqa: N802
        return self._drag_drop.reorder_on(sources, target_name)

    @QtCore.Slot("QVariantList", str, result=bool)
    def dropInto(self, sources: list[Any], target_name: str) -> bool:  # noqa: N802
        return self._drag_drop.drop_into(sources, target_name)

    @QtCore.Slot("QVariantList", str, result=bool)
    def canDropOn(self, sources: list[Any], target_name: str) -> bool:
        return self._drag_drop.can_drop_on(sources, target_name)

    @QtCore.Slot("QVariantList", str, result=str)
    def dropHint(self, sources: list[Any], target_name: str) -> str:  # noqa: N802
        return self._drag_drop.drop_hint(sources, target_name)

    @QtCore.Slot("QVariantList", str, result=bool)
    def dropOn(self, sources: list[Any], target_name: str) -> bool:
        return self._drag_drop.drop_on(sources, target_name)

    # -- the document root: the header's name, empty space when docked ---- #

    @QtCore.Slot("QVariantList", result=bool)
    def canDropOnRoot(self, sources: list[Any]) -> bool:  # noqa: N802
        return self._drag_drop.can_drop_on_root(sources)

    @QtCore.Slot("QVariantList", result=bool)
    def dropOnRoot(self, sources: list[Any]) -> bool:  # noqa: N802
        return self._drag_drop.drop_on_root(sources)

    # ------------------------------------------------------------------ #

    @QtCore.Slot()
    def refresh(self) -> None:
        self.rebuild()
