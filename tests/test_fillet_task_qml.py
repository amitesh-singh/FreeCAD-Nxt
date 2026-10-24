"""FilletTask.qml, loaded offscreen against a stub bridge.

Run with: python3 tests/test_fillet_task_qml.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import fakes  # noqa: E402
from PySide6 import QtCore, QtGui, QtQuick  # noqa: E402

App, Gui = fakes.install(ParamGet=fakes.params({}))

from freecad.nxt.ui.theme import Theme  # noqa: E402

QML = ROOT / "freecad" / "nxt" / "resources" / "qml"
BAD = ("binding loop", "is not defined", "cannot read property",
       "unable to assign", "typeerror", "referenceerror", "cannot assign",
       "is not a function", "required property")
problems: list[str] = []


def _handler(_mode: object, _context: object, message: str) -> None:
    print(message)
    if any(token in str(message).lower() for token in BAD):
        problems.append(str(message))


QtCore.qInstallMessageHandler(_handler)
app = QtGui.QGuiApplication(sys.argv)
calls: list[tuple[str, object]] = []
EDGES = [{"name": "Edge12", "short": False, "limit": ""},
         {"name": "Edge16", "short": True, "limit": "2.53 mm max"}]


def _value(kind: type, value: object) -> object:
    return QtCore.Property(kind, lambda _self: value, notify=changed)


def _slot(name: str, *kinds: type) -> object:
    def record(_self: object, *args: object) -> bool:
        calls.append((name, args[0] if args else None))
        return True
    return QtCore.Slot(*kinds, result=bool)(record)


changed = QtCore.Signal()
Stub = type("Stub", (QtCore.QObject,), {
    "changed": changed,
    "radiusText": _value(str, "3 mm"), "radius": _value(float, 3.0),
    "radiusNumber": _value(str, "3"), "radiusUnit": _value(str, "mm"),
    "fits": _value(float, 2.53),
    "fitsText": _value(str, "2.53 mm"), "failing": _value(int, 1),
    "source": _value(str, "Pad004"), "useAllEdges": _value(bool, False),
    "refine": _value(bool, True), "edges": _value(list, EDGES),
    "preview": _value(bool, True), "flat": _value(bool, True),
    "tangentEdges": _value(bool, True),
    "setTangentEdges": _slot("setTangentEdges", bool),
    "triangleCorners": _value(bool, True),
    "setTriangleCorners": _slot("setTriangleCorners", bool),
    "setPreview": _slot("setPreview", bool),
    "setRadiusText": _slot("setRadiusText", str),
    "step": _slot("step", int, bool), "useFits": _slot("useFits"),
    "remove": _slot("remove", str), "clear": _slot("clear"),
    "setUseAllEdges": _slot("setUseAllEdges", bool),
    "setRefine": _slot("setRefine", bool), "hover": _slot("hover", str),
})
task = Stub()
theme = Theme()

view = QtQuick.QQuickView()
view.engine().addImportPath(str(QML))
view.rootContext().setContextProperty("theme", theme)
view.rootContext().setContextProperty("task", task)
view.setResizeMode(QtQuick.QQuickView.ResizeMode.SizeRootObjectToView)
view.resize(340, 640)
view.setSource(QtCore.QUrl.fromLocalFile(str(QML / "FilletTask.qml")))
problems += [e.toString() for e in view.errors()]
view.show()
for _ in range(20):
    app.processEvents()
root = view.rootObject()
if root is None or root.property("implicitHeight") <= 0:
    problems.append("the panel has no height")

print("FILLET TASK QML PASSED" if not problems else "FILLET TASK QML FAILED")
for p in problems:
    print("  *", p)
sys.exit(1 if problems else 0)
