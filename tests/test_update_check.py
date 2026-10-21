"""The startup addon update check, against a stand-in Addon Manager.

Run with: python3 tests/test_update_check.py   (needs PySide6)
"""

from __future__ import annotations

import enum
import os
import sys
import types
import unittest
from pathlib import Path
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6 import QtCore, QtWidgets  # noqa: E402

App = types.ModuleType("FreeCAD")
App.Console = types.SimpleNamespace(  # type: ignore[attr-defined]
    PrintError=print, PrintMessage=print, PrintLog=lambda _m: None,
    PrintWarning=print)
STORE: dict[str, dict[str, Any]] = {}


class Group:
    def __init__(self, path: str) -> None:
        self.values = STORE.setdefault(path, {})

    def _get(self, key: str, default: Any = None) -> Any:
        return self.values.get(key, default)

    def _set(self, key: str, value: Any) -> None:
        self.values[key] = value

    def GetBools(self) -> list[str]:  # noqa: N802 - FreeCAD's API
        return [k for k, v in self.values.items() if isinstance(v, bool)]

    def RemBool(self, key: str) -> None:  # noqa: N802 - FreeCAD's API
        del self.values[key]

    GetBool = GetInt = GetFloat = GetString = _get
    SetBool = SetInt = SetFloat = SetString = _set


App.ParamGet = Group  # type: ignore[attr-defined]
sys.modules["FreeCAD"] = App
sys.modules["FreeCADGui"] = types.ModuleType("FreeCADGui")

APP = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


class Status(enum.IntEnum):
    NOT_INSTALLED = 0
    UNCHECKED = 1
    NO_UPDATE_AVAILABLE = 2
    UPDATE_AVAILABLE = 3


class Addon:
    Status = Status

    def __init__(self, name: str, status: Status,
                 has_update: bool = False) -> None:
        self.display_name = name
        self._status = status
        self.has_update = has_update

    def status(self) -> Status:
        return self._status


CATALOG: list[Addon] = []
LOG: list[str] = []


class ListWorker(QtCore.QObject):
    addon_repo = QtCore.Signal(object)
    finished = QtCore.Signal()

    def start(self) -> None:
        for addon in CATALOG:
            self.addon_repo.emit(addon)
        self.finished.emit()


class CheckWorker(QtCore.QObject):
    finished = QtCore.Signal()

    def __init__(self, addons: list[Addon]) -> None:
        super().__init__()
        self.addons = addons
        LOG.append("check %s" % [a.display_name for a in addons])

    def start(self) -> None:
        for addon in self.addons:
            addon._status = (Status.UPDATE_AVAILABLE if addon.has_update
                             else Status.NO_UPDATE_AVAILABLE)
        self.finished.emit()


class UpdateAllGUI(QtCore.QObject):
    finished = QtCore.Signal()
    addon_updated = QtCore.Signal(object)
    last: UpdateAllGUI | None = None

    def __init__(self, addons: list[Addon]) -> None:
        super().__init__()
        self.addons = addons
        UpdateAllGUI.last = self

    def run(self) -> None:
        LOG.append("dialog")


def _module(name: str, **items: Any) -> None:
    module = types.ModuleType(name)
    module.__dict__.update(items)
    sys.modules[name] = module


READ_WARNING = {"readWarning2022": True}
_module("addonmanager_freecad_interface",
        Preferences=lambda: types.SimpleNamespace(get=READ_WARNING.get))
_module("addonmanager_utilities",
        restart_freecad=lambda: LOG.append("restart"))
NETWORK: list[str] = []
_module("NetworkManager",
        InitializeNetworkManager=lambda: NETWORK.append("init"))
_module("Addon", Addon=Addon)
_module("addonmanager_update_all_gui", UpdateAllGUI=UpdateAllGUI)
_module("addonmanager_workers_startup", CreateAddonListWorker=ListWorker,
        CheckWorkbenchesForUpdatesWorker=CheckWorker)

from freecad.nxt.app import update_check  # noqa: E402


class UpdateCheckTest(unittest.TestCase):
    def setUp(self) -> None:
        STORE.clear()
        update_check._check = None
        UpdateAllGUI.last = None
        READ_WARNING["readWarning2022"] = True
        LOG.clear()
        CATALOG[:] = [Addon("Remote", Status.NOT_INSTALLED, True),
                      Addon("Current", Status.UNCHECKED),
                      Addon("Stale", Status.UNCHECKED, True)]

    def test_checks_only_installed_addons(self) -> None:
        update_check._run()
        self.assertEqual(LOG[0], "check ['Current', 'Stale']")

    def test_offers_the_updates(self) -> None:
        update_check._run()
        self.assertIn("dialog", LOG)
        gui = UpdateAllGUI.last
        assert gui is not None
        self.assertEqual(
            [a.display_name for a in update_check.pending(gui.addons,
                                                          Status)],
            ["Stale"])

    def test_silent_when_all_current(self) -> None:
        CATALOG[2].has_update = False
        update_check._run()
        self.assertNotIn("dialog", LOG)

    def test_network_manager_made_first(self) -> None:
        NETWORK.clear()
        update_check._run()
        self.assertEqual(NETWORK, ["init"])

    def test_runs_once_a_session(self) -> None:
        update_check._run()
        update_check._run()
        self.assertEqual(LOG.count("dialog"), 1)

    def test_waits_for_addon_manager_consent(self) -> None:
        READ_WARNING["readWarning2022"] = False
        update_check._run()
        self.assertEqual(LOG, [])

    def test_restart_offered_after_updating(self) -> None:
        update_check._run()
        gui = UpdateAllGUI.last
        assert gui is not None
        check = update_check._check
        assert check is not None
        asked: list[bool] = []
        check.offer_restart = lambda: asked.append(True)  # type: ignore
        gui.addon_updated.emit(CATALOG[2])
        gui.finished.emit()
        APP.processEvents()
        self.assertEqual(asked, [True])

    def pop_ups(self) -> dict[str, Any]:
        return dict(STORE.get(update_check.OUTPUT, {}))

    def test_report_view_kept_down_while_checking(self) -> None:
        seen: list[dict[str, Any]] = []
        start = ListWorker.start
        ListWorker.start = lambda w: (  # type: ignore[method-assign]
            seen.append(self.pop_ups()), start(w))
        try:
            update_check._run()
        finally:
            ListWorker.start = start  # type: ignore[method-assign]
        self.assertTrue(seen and not any(seen[0].values()))

    def test_report_view_settings_put_back(self) -> None:
        STORE[update_check.OUTPUT] = {"checkShowReportViewOnWarning": True}
        update_check._run()
        self.assertEqual(self.pop_ups(),
                         {"checkShowReportViewOnWarning": True})

    def test_left_down_by_last_session_put_back(self) -> None:
        STORE[update_check.OUTPUT] = {"checkShowReportViewOnError": True}
        update_check.hush()
        update_check.install()
        self.assertEqual(self.pop_ups(),
                         {"checkShowReportViewOnError": True})

    def test_no_restart_when_nothing_updated(self) -> None:
        update_check._run()
        gui = UpdateAllGUI.last
        assert gui is not None
        check = update_check._check
        assert check is not None
        asked: list[bool] = []
        check.offer_restart = lambda: asked.append(True)  # type: ignore
        gui.finished.emit()
        APP.processEvents()
        self.assertEqual(asked, [])


if __name__ == "__main__":
    unittest.main()
