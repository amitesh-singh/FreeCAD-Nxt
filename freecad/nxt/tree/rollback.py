"""The rollback bars: where each sits, dragging one, and moving the tip."""

from __future__ import annotations

from typing import Any

import FreeCAD as App

from ..app.i18n import translate
from ..core import log


class Rollback:
    """Rollback bars for the tree; TreeBridge's slots call into this."""

    def __init__(self, bridge: Any) -> None:
        self._bridge = bridge
        #: The drag in progress, or None.
        self.drag: dict[str, Any] | None = None
        # Where each Body's bar was last put down, as the *object* whose
        # row it sits under rather than a row index - indices move whenever
        # a branch is expanded. Only a resting place that still resolves to
        # the current tip is honoured, so any other route to moving the tip
        # falls back to the tip's own row without having to know about this.
        self._bar_anchor: dict[str, str] = {}
        # model -> (tip, steps it was set against)
        self._model_tips: dict[str, tuple[str, tuple[str, ...]]] = {}
        self._pending_restore: list[str] = []
        self._pending_finish: tuple[str, bool] | None = None
        self._bars_timer = bridge._deferral(bridge.tipBarsChanged.emit)
        self._drain_timer = bridge._deferral(self._drain_tip_drag)
        self._finish_timer = bridge._deferral(self._finish_pending_drag)
        self._restore_timer = bridge._deferral(self._show_finished_models)

    @property
    def _snapshot(self) -> Any:
        return self._bridge._snapshot

    @property
    def _tree(self) -> Any:
        return self._bridge._tree

    @property
    def _active(self) -> str:
        return self._bridge._active

    def publish(self) -> None:
        """Announce new marker positions on the next event-loop turn.

        Never synchronously. `Repeater` destroys and rebuilds every delegate
        when its model changes, and this is reached from slots QML calls out
        of a marker's own `onReleased`. Destroying an object while one of
        its signal handlers is still on the stack is not merely unsupported
        in QML - `QQmlData::destroyed` calls qFatal, which aborts the
        process. One turn of the event loop is enough for the handler to
        have returned.
        """
        self._bars_timer.start()

    def bars(self) -> list[dict[str, Any]]:
        """The rollback bars: the active Body's, and each Part model's.

        Only the active Body has one. A bar on every Body offered a
        handle that changes the model on Bodies that are not being worked
        on; the one being worked on is the active one. A Part model has
        no active state, so its history bar is always there.

        `pos` is the row the bar sits *below*. A collapsed Body contributes
        nothing: there is no gap to put a bar in.
        """
        index = self._tree.row_index_map()
        bars: list[dict[str, Any]] = []
        for name, node in self._snapshot.nodes.items():
            if not node.stack:
                continue
            if not node.is_model and name != self._active:
                continue
            feature_rows = [index[f] for f in node.stack if f in index]
            if not feature_rows:
                continue
            child_rows = [index[c] for c in node.children if c in index]
            first_feature = min(feature_rows)
            last_child = max(child_rows) if child_rows else max(feature_rows)
            pos = self._resting_position(name, node, index)
            if pos is None and node.is_model and node.tip == name:
                pos = max(feature_rows)
            if pos is None:
                pos = index.get(node.tip) if node.tip else None
            if pos is None:
                pos = first_feature
            bars.append({
                "body": name,
                "label": node.label,
                "pos": pos,
                "minPos": first_feature,
                "maxPos": max(last_child, first_feature),
                "depth": self._tree.depth_at(first_feature),
            })
        return bars

    def _resting_position(self, name: str, node: Any,
                          index: dict[str, int]) -> int | None:
        """Where the bar was last put down, if it still sets this tip."""
        anchor = self._bar_anchor.get(name)
        resting = index.get(anchor) if anchor is not None else None
        if (resting is not None and
                self.tip_for_row(name, resting) == node.tip):
            return resting
        return None

    def tip_for_row(self, body_name: str, row: int) -> str | None:
        """The feature a bar dropped below `row` sets.

        Only a solid feature can be a tip, so a bar parked under a sketch
        sets the last feature above it and stays where it was put. Scanning
        rows rather than timeline positions makes this agree with what is
        on screen even when part of the Body is collapsed.
        """
        node = self._snapshot.nodes.get(body_name)
        if node is None or not node.stack:
            return None
        stack = set(node.stack)
        if node.is_model and row >= max(
                (self._tree.row_index_map().get(n, -1) for n in node.stack),
                default=-1):
            return body_name    # below the last step: the finished model
        cursor = min(row, self._tree.rowCount() - 1)
        while cursor >= 0:
            name = self._tree.name_at(cursor)
            if name in stack:
                return name
            cursor -= 1
        return None

    def begin_drag(self, body_name: str) -> None:
        """Start an interactive tip move.

        One transaction spans the whole drag, so a rollback that crossed six
        features is still a single undo step rather than six.
        """
        if self.drag is not None:
            self.end_drag(self.drag["body"])
        node = self._snapshot.nodes.get(body_name)
        doc = App.ActiveDocument
        if doc is None or node is None or not node.stack:
            return
        try:
            doc.openTransaction("Move tip")
        except Exception:
            log.error("could not open a transaction for the tip drag")
            return
        self.drag = {
            "body": body_name,
            "original": node.tip,
            "current": node.tip,    # what the document is actually showing
            "wanted": node.tip,     # which feature the bar would set
            "anchor": None,         # the row the bar is resting under
            "live": True,
            "applying": False,
            "ending": False,
        }

    def preview_row(self, body_name: str, row: int) -> None:
        """Note where the marker now is; the apply happens off this stack.

        Deliberately does not recompute here. This runs inside QML's delivery
        of a mouse-move event, and Qt's contract is that an exception must
        not propagate out of an event handler - it terminates the process
        rather than unwinding. A recompute on an old or damaged model is
        exactly where a feature throws, so the work is queued onto a
        zero-timer and performed from the event loop instead, where an
        exception has a Python frame to be caught in.

        Queuing also collapses a burst of moves: crossing four features
        while one recompute is still running applies only the last.
        """
        drag = self.drag
        if drag is None or drag["body"] != body_name:
            return
        # Recorded before the early return, not after: a move between two
        # consecutive sketches changes where the bar is without changing
        # what it sets, and that is exactly the case this has to remember.
        drag["anchor"] = self._tree.name_at(row)
        name = self.tip_for_row(body_name, row)
        if name is None or name == drag["wanted"]:
            return

        drag["wanted"] = name
        if not drag["live"] or drag["applying"]:
            return  # the running apply picks this up when it drains
        self._drain_timer.start()

    def _drain_tip_drag(self) -> None:
        """Apply the marker's latest position until it stops moving.

        Apply the marker's latest position, repeatedly, until it stops
        moving. Re-entrant by design rather than by accident: a recompute
        can spin the event loop - FreeCAD's progress indicator calls
        processEvents - so another mouse move can arrive mid-apply. The
        guard turns that into another lap of this loop instead of a nested
        recompute on a document already inside one.
        """
        drag = self.drag
        if drag is None or drag["applying"]:
            return

        drag["applying"] = True
        try:
            while (self.drag is drag and not drag["ending"] and
                   drag["wanted"] != drag["current"]):
                target = drag["wanted"]
                # Shown, not set: only which feature is visible changes
                # while the bar moves. Tip is set, and the Body
                # recomputed, once, when it is let go (_commit_tip_drag) -
                # a recompute per row made the bar unusable on a slow
                # model.
                if not self._preview_tip(drag["body"], target):
                    break
                drag["current"] = target
        finally:
            drag["applying"] = False

    def _defer_finish(self, body_name: str, commit: bool) -> None:
        """Retry a finish once the apply that is on the stack has unwound."""
        self._pending_finish = (body_name, commit)
        self._finish_timer.start()

    def _finish_pending_drag(self) -> None:
        pending, self._pending_finish = self._pending_finish, None
        if pending is not None:
            self._finish_tip_drag(*pending)

    def end_drag(self, body_name: str) -> None:
        self._finish_tip_drag(body_name, commit=True)

    def cancel_drag(self, body_name: str) -> None:
        self._finish_tip_drag(body_name, commit=False)

    def _finish_tip_drag(self, body_name: str, commit: bool) -> None:
        drag = self.drag
        if drag is None:
            return
        if drag["applying"]:
            # Closing the transaction from inside the apply would close it
            # in the middle of the change it is meant to contain: a
            # recompute spins the event loop, so the release can arrive
            # there. Let the apply unwind first.
            drag["ending"] = True
            self._defer_finish(body_name, commit)
            return

        self.drag = None
        if commit and drag["anchor"]:
            self._bar_anchor[body_name] = drag["anchor"]
        elif not commit:
            self._bar_anchor.pop(body_name, None)

        doc = App.ActiveDocument
        try:
            if commit:
                self._commit_tip_drag(doc, drag, body_name)
            elif doc is not None:
                doc.abortTransaction()
                # Visibility is view state; undo does not restore it. The
                # tip was never set, so there is nothing to recompute.
                if drag["current"] != drag["original"]:
                    self._preview_tip(body_name, drag["original"])
        except Exception:
            log.error("could not finish the tip drag on %s" % body_name)
        self._bridge.invalidate(icons=True)
        self.publish()

    def _commit_tip_drag(self, doc: Any, drag: dict[str, Any],
                         body_name: str) -> None:
        # The drag only showed features; the tip is set, and recomputed,
        # once, here.
        wanted = drag["wanted"]
        if wanted == drag["original"]:
            if drag["current"] != wanted:
                self._preview_tip(body_name, wanted)
            if doc is not None:
                doc.abortTransaction()  # nothing moved; no undo entry
            return
        if not self._apply_tip(body_name, wanted):
            self._preview_tip(body_name, drag["original"])
            if doc is not None:
                doc.abortTransaction()
            return
        if doc is not None:
            doc.commitTransaction()
            self._toast_tip(doc, body_name, wanted)

    def _preview_tip(self, body_name: str, feature_name: str) -> bool:
        """Show the Body as it would be with this tip, without setting it.

        Only visibility, and the panel's own picture: no Tip, no
        recompute. A feature past the tip shows its shape as last built.
        """
        node = self._snapshot.nodes.get(body_name)
        doc = App.ActiveDocument
        if node is None or doc is None:
            return False
        if node.is_model:
            return self._apply_tip(body_name, feature_name)
        try:
            for other in node.stack:
                vo = getattr(doc.getObject(other), "ViewObject", None)
                if vo is None:
                    continue
                wanted = other == feature_name
                if bool(getattr(vo, "Visibility", not wanted)) != wanted:
                    vo.Visibility = wanted
            self._tree.touch(self._snapshot.retip(body_name, feature_name))
            return True
        except Exception:
            log.error("could not show %s at %s" % (body_name, feature_name))
            return False

    def restore_model_tips(self) -> None:
        """Carry each model's history position across a rebuild.

        A Part model has no Tip property, so where its bar was is the
        panel's to remember. It is honoured only while the model has the
        same steps: a new operation always lands at the end, so the bar
        snaps back to the finished model rather than implying an insertion
        point that does not exist.
        """
        kept: dict[str, tuple[str, tuple[str, ...]]] = {}
        for name, (tip, stack) in self._model_tips.items():
            node = self._snapshot.nodes.get(name)
            if node is None or not node.is_model:
                continue
            if tuple(node.stack) == stack:
                self._snapshot.retip(name, tip)
                kept[name] = (tip, stack)
            else:
                self._pending_restore.append(name)
                self._bar_anchor.pop(name, None)
        self._model_tips = kept
        if self._pending_restore:
            self._restore_timer.start()

    def _show_finished_models(self) -> None:
        pending, self._pending_restore = self._pending_restore, []
        for name in pending:
            if name in self._snapshot.nodes:
                self._show_model_state(name, name)

    def _show_model_state(self, model_name: str, tip_name: str) -> None:
        doc = App.ActiveDocument
        if doc is None:
            return
        for name, (_built, shown) in self._snapshot.model_state(
                model_name, tip_name).items():
            vo = getattr(doc.getObject(name), "ViewObject", None)
            if vo is not None and bool(vo.Visibility) != shown:
                vo.Visibility = shown
        self._tree.touch(self._snapshot.retip(model_name, tip_name))
        if tip_name == model_name:
            self._model_tips.pop(model_name, None)
        else:
            self._model_tips[model_name] = (
                tip_name, tuple(self._snapshot.nodes[model_name].stack))

    def _apply_tip(self, body_name: str, feature_name: str) -> bool:
        """Set Tip and the stack's visibility.

        No transaction of its own - the caller owns that, whether it is
        a drag or a one-shot move.
        """
        doc = App.ActiveDocument
        if doc is None:
            return False
        body = doc.getObject(body_name)
        feature = doc.getObject(feature_name)
        body_node = self._snapshot.nodes.get(body_name)
        if body is None or feature is None or body_node is None:
            return False
        if body_node.is_model:
            try:
                self._show_model_state(body_name, feature_name)
                return True
            except Exception:
                log.error("could not roll %s back to %s"
                          % (body_name, feature_name))
                return False
        try:
            body.Tip = feature
            # Only the visibilities that actually differ. A Body shows
            # through exactly one feature, so a move changes two of them -
            # writing all of them touched the document once per stack
            # member and woke an observer for each, which on a long history
            # was most of the cost of a drag step.
            for other in body_node.stack:
                obj = doc.getObject(other)
                vo = getattr(obj, "ViewObject", None)
                if vo is None:
                    continue
                wanted = (other == feature_name)
                if bool(getattr(vo, "Visibility", not wanted)) != wanted:
                    vo.Visibility = wanted
            self._recompute(doc, body)
            # Patch the snapshot rather than waiting for a rebuild that a
            # drag suppresses anyway. Everything a tip move changes is
            # derivable from what the snapshot already holds, and
            # `Snapshot.retip` is tested against a full rebuild so the two
            # cannot drift.
            self._tree.touch(self._snapshot.retip(body_name, feature_name))
            return True
        except Exception:
            log.error("could not set the tip of %s to %s"
                      % (body_name, feature_name))
            return False

    @staticmethod
    def _recompute(doc: Any, body: Any) -> None:
        """Recompute the Body, not the document.

        Moving the tip touches the Body and nothing else - the features
        themselves are already up to date - so a whole-document recompute
        is work nobody asked for. It is also the difference between a
        recompute fast enough to pass unnoticed and one slow enough to
        raise FreeCAD's progress indicator, which spins the event loop and
        invites exactly the re-entrancy this drag path has to survive.
        """
        try:
            doc.recompute([body])
        except TypeError:
            doc.recompute()     # older signature, no object list

    def set_tip_to_row(self, body_name: str, row: int) -> None:
        name = self.tip_for_row(body_name, row)
        if name is not None:
            self.set_tip(body_name, name)

    def set_tip(self, body_name: str, feature_name: str) -> None:
        """Roll a Body's history to end at `feature_name`.

        Setting Tip is only half of it: FreeCAD shows a Body through exactly
        one visible feature, so the stock Move-tip command also hides every
        other member of the stack. Skip that and the Body keeps drawing the
        old state regardless of what Tip says.
        """
        doc = App.ActiveDocument
        if doc is None:
            return
        body = doc.getObject(body_name)
        feature = doc.getObject(feature_name)
        if body is None or feature is None:
            return

        node = self._snapshot.nodes.get(feature_name)
        body_node = self._snapshot.nodes.get(body_name)
        if node is None or body_node is None:
            return
        if node.body != body_name and feature_name != body_name:
            return              # not this Body's feature; refuse quietly
        if body_node.tip == feature_name:
            return

        # Moved by something other than the bar, so any place the bar was
        # resting is no longer a statement about this tip.
        self._bar_anchor.pop(body_name, None)
        try:
            doc.openTransaction("Move tip")
            if self._apply_tip(body_name, feature_name):
                doc.commitTransaction()
                self._toast_tip(doc, body_name, feature_name)
            else:
                doc.abortTransaction()
        except Exception:
            doc.abortTransaction()
            log.error("could not move the tip of %s to %s"
                      % (body_name, feature_name))
        self._bridge.invalidate(icons=True)

    def _toast_tip(self, doc: Any, body_name: str,
                   feature_name: str | None) -> None:
        node = self._snapshot.nodes.get(body_name)
        if node is not None and node.is_model:
            return      # a Part model's bar is a view; there is no undo
        self._bridge._toast(doc, translate("Nxt", "Tip of %s moved to %s") % (
            self._bridge._named(doc, [body_name]),
            self._bridge._named(doc, [feature_name or body_name])), body_name)

    def show_through_tip(self, body_name: str, doc: Any) -> None:
        """Show a Body through its tip again, after a tip move is undone.

        Undo puts Tip back but not what is shown: visibility is view
        state.
        """
        body = doc.getObject(body_name)
        if body is None:
            return
        tip = getattr(getattr(body, "Tip", None), "Name", None)
        for other in getattr(
                self._snapshot.nodes.get(body_name), "stack", ()):
            vo = getattr(doc.getObject(other), "ViewObject", None)
            if vo is not None and bool(vo.Visibility) != (other == tip):
                vo.Visibility = other == tip
