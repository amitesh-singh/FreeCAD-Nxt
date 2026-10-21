"""Check installed addons for updates once, after startup.

Runs the Addon Manager's own workers in the background: the addon list
first, then the update check over the installed addons. If any have an
update, opens the Addon Manager's "Update all" dialog, where each can be
reviewed, unticked and applied. Nothing is shown when all are current,
when the check fails, or when the Addon Manager is missing; while it
runs, its messages don't bring up a hidden Report view.
"""

from __future__ import annotations

import json
from typing import Any

import FreeCAD as App

from ..core import settings
from ..core.qt import QtCore, QtWidgets
from .i18n import translate

#: Wait after startup so the window, panel and documents load first.
DELAY_MS = 5000

#: The running check; held so Qt doesn't lose the workers, and so the
#: check runs once a session.
_check: Checker | None = None

#: FreeCAD's settings for bringing up a hidden Report view when a message
#: arrives. The Addon Manager's workers report fetch problems as warnings
#: and errors; during the check they are only logged.
OUTPUT = "User parameter:BaseApp/Preferences/OutputWindow"
POP_UPS = ("checkShowReportViewOnWarning", "checkShowReportViewOnError",
           "checkShowReportViewOnCritical",
           "checkShowReportViewOnNormalMessage",
           "checkShowReportViewOnLogMessage")
#: Longest the Report view is kept down, in case a worker never finishes.
QUIET_MS = 180000


def hush() -> None:
    """Stop the Report view popping up, noting what to put back.

    What it was is kept in Nxt's settings until put back, so a session
    that ends mid-check is put right at the next start.
    """
    if settings.get("QuietOriginals"):
        return
    group = App.ParamGet(OUTPUT)
    present = set(group.GetBools())
    settings.put("QuietOriginals", json.dumps({
        key: group.GetBool(key) if key in present else None
        for key in POP_UPS}))
    for key in POP_UPS:
        group.SetBool(key, False)


def unhush() -> None:
    """Put the Report view's settings back as they were."""
    try:
        before = json.loads(settings.get("QuietOriginals") or "{}")
    except ValueError:
        before = {}
    group = App.ParamGet(OUTPUT)
    for key, value in before.items():
        if value is None:
            group.RemBool(key)
        else:
            group.SetBool(key, bool(value))
    settings.put("QuietOriginals", "")


def pending(addons: list[Any], status: Any) -> list[Any]:
    """The addons whose status says an update is available."""
    return [a for a in addons if a.status() == status.UPDATE_AVAILABLE]


def installed(addons: list[Any], status: Any) -> list[Any]:
    """The addons the Addon Manager found installed."""
    return [a for a in addons if a.status() != status.NOT_INSTALLED]


def _addon_manager() -> dict[str, Any] | None:
    """The Addon Manager's parts, or None if it can't be used."""
    try:
        import addonmanager_freecad_interface as fci
        import addonmanager_utilities as utils
        import NetworkManager
        from Addon import Addon
        from addonmanager_update_all_gui import UpdateAllGUI
        from addonmanager_workers_startup import (
            CheckWorkbenchesForUpdatesWorker,
            CreateAddonListWorker,
        )
    except Exception as exc:  # noqa: BLE001 - any import failure means skip
        App.Console.PrintLog("Nxt: no addon update check (%s)\n" % exc)
        return None
    # The Addon Manager asks before it first goes online; until then,
    # neither does Nxt.
    if not fci.Preferences().get("readWarning2022"):
        App.Console.PrintLog(
            "Nxt: no addon update check until the Addon Manager has "
            "been opened once\n")
        return None
    # The workers fetch through the Addon Manager's network manager, which
    # its own command creates on opening. It must be made here, on the
    # main thread, before any worker starts.
    try:
        NetworkManager.InitializeNetworkManager()
    except Exception as exc:  # noqa: BLE001 - no network manager, no check
        App.Console.PrintLog(
            "Nxt: no addon update check, no network manager (%s)\n" % exc)
        return None
    return {"Addon": Addon, "UpdateAllGUI": UpdateAllGUI,
            "CreateAddonListWorker": CreateAddonListWorker,
            "CheckWorker": CheckWorkbenchesForUpdatesWorker,
            "restart": utils.restart_freecad}


class Checker(QtCore.QObject):
    """List the addons, check the installed ones, offer the updates."""

    def __init__(self, parts: dict[str, Any]) -> None:
        super().__init__()
        self.parts = parts
        self.status = parts["Addon"].Status
        self.addons: list[Any] = []
        self.updated: list[Any] = []
        self.worker: Any = None
        self.gui: Any = None

    def start(self) -> None:
        self.worker = self.parts["CreateAddonListWorker"]()
        self.worker.addon_repo.connect(self.found)
        self.worker.finished.connect(self.listed)
        self.worker.start()

    @QtCore.Slot(object)
    def found(self, addon: Any) -> None:
        self.addons.append(addon)

    @QtCore.Slot()
    def listed(self) -> None:
        self.addons = installed(self.addons, self.status)
        if not self.addons:
            unhush()
            return
        self.worker = self.parts["CheckWorker"](self.addons)
        self.worker.finished.connect(self.checked)
        self.worker.start()

    @QtCore.Slot()
    def checked(self) -> None:
        self.worker = None
        unhush()
        count = len(pending(self.addons, self.status))
        App.Console.PrintLog("Nxt: %d addon update(s) available\n" % count)
        if not count:
            return
        self.gui = self.parts["UpdateAllGUI"](self.addons)
        self.gui.addon_updated.connect(self.applied)
        self.gui.finished.connect(self.closed)
        self.gui.run()

    @QtCore.Slot(object)
    def applied(self, addon: Any) -> None:
        self.updated.append(addon)

    @QtCore.Slot()
    def closed(self) -> None:
        self.gui = None
        if self.updated:
            QtCore.QTimer.singleShot(0, self.offer_restart)

    def offer_restart(self) -> None:
        """Updates take effect on restart; offer one now."""
        names = ", ".join(a.display_name for a in self.updated)
        answer = QtWidgets.QMessageBox.question(
            None, translate("Nxt", "Addons updated"),
            translate("Nxt", "Updated: {}.\n\nRestart FreeCAD now to use "
                             "the new versions?").format(names))
        if answer == QtWidgets.QMessageBox.StandardButton.Yes:
            self.parts["restart"]()


def _run() -> None:
    global _check
    if _check is not None:
        return
    parts = _addon_manager()
    if parts is None:
        return
    _check = Checker(parts)
    hush()
    QtCore.QTimer.singleShot(QUIET_MS, unhush)
    try:
        _check.start()
    except Exception:  # noqa: BLE001 - a failed check must not break startup
        unhush()
        App.Console.PrintLog("Nxt: the addon update check failed\n")


def install() -> None:
    """Schedule the check, once a session, if the preference allows."""
    unhush()                    # left down by a session that ended mid-check
    app = QtCore.QCoreApplication.instance()
    if app is not None:
        app.aboutToQuit.connect(unhush)
    if settings.get("CheckAddonUpdates"):
        QtCore.QTimer.singleShot(DELAY_MS, _run)
