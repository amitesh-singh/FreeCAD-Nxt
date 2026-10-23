"""Compare Nxt fillet speed modes in FreeCAD, in the Report view.

Run from FreeCAD: Macro > Macros... > (browse to this file) > Execute, or
in the Python console:  exec(open(r"<path>/tests/check_modes_macro.py").read())

Opens the saved case models (tests/models/fillet_cases.FCStd and
chamfer_cases.FCStd, made by fillet_cases.py and chamfer_cases.py) and
recomputes each Nxt fillet and chamfer in them, as editing one would,
in each mode:

  base        Nxt's own fillet
  occt_first  OCCT's fillet where likely to match, Nxt's otherwise

Other modes: any name in blend_fillet.SPEED.

Reports per feature: time, whether the result is a valid single solid
passing the BOP check (checked here, not timed), new problems, and
deviation from base (symmetric difference / volume). One feature runs
per turn of the event loop, so the Report view fills in as it goes.
The models are not saved; close them without saving afterwards.
Every result is also written to tests/results/check_modes_<time>.csv,
one row per feature and mode, for a spreadsheet.
"""

import csv
import time
from pathlib import Path

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore

import freecad.nxt
from freecad.nxt.tools import blend_fillet as bf

ROOT = Path(freecad.nxt.__file__).resolve().parents[2]
MODELS = [ROOT / "tests" / "models" / name
          for name in ("fillet_cases.FCStd", "chamfer_cases.FCStd")]
MODES = ("base", "occt_first")
#: Results further than this from base count as deviating.
MARGIN = 1e-3
RESULTS = ROOT / "tests" / "results"
COLUMNS = ("model", "feature", "mode", "time_s", "speedup_vs_base",
           "sound", "problems", "deviation_vs_base", "worse_than_base")
#: The rows written to the CSV once the run ends.
rows = []


def say(text):
    App.Console.PrintMessage(text + "\n")


def features_of(doc):
    """The Nxt features, in the order they were made."""
    found = [o for o in doc.Objects
             if isinstance(getattr(o, "Proxy", None), bf.BlendFillet)]
    return [(o.getParentGeoFeatureGroup().Name + "/" + o.Label, o)
            for o in found]


def sound(obj):
    shape = obj.Shape
    if "Invalid" in obj.State or not shape.isValid() \
            or len(shape.Solids) != 1:
        return False
    try:
        shape.check(True)
    except Exception:
        return False
    return True


def deviation(a, b):
    try:
        return (a.cut(b).Volume + b.cut(a).Volume) / a.Volume
    except Exception:
        return 1.0


def steps():
    """The whole comparison, one feature per step."""
    for path in MODELS:
        if not path.exists():
            say("check modes: %s missing; run its cases script first"
                % path.name)
            continue
        doc = App.openDocument(str(path))
        Gui.SendMsgToActiveView("ViewFit")
        features = features_of(doc)
        results = {}
        for mode in MODES:
            bf.SPEED.clear()
            if mode != "base":
                bf.SPEED.add(mode)
            say("--- %s: %s ---" % (path.stem, mode))
            for name, obj in features:
                obj.touch()
                start = time.perf_counter()
                obj.recompute()
                took = time.perf_counter() - start
                ok = sound(obj)
                results[mode, name] = (
                    took, ok, len(getattr(obj.Proxy, "problems", [])),
                    obj.Shape.copy())
                say("  %-34s %7.3f s  %s" % (name, took,
                                             "ok" if ok else "FAILED"))
                yield
        bf.SPEED.clear()
        for _name, obj in features:
            obj.touch()
        doc.recompute()
        summary(path.stem, features, results)
        yield
    written = save()
    say("check modes: done (models not saved); results in %s" % written)


def save():
    RESULTS.mkdir(parents=True, exist_ok=True)
    path = RESULTS / ("check_modes_%s.csv" % time.strftime("%Y%m%d_%H%M%S"))
    with path.open("w", newline="") as out:
        writer = csv.writer(out)
        writer.writerow(COLUMNS)
        writer.writerows(rows)
    return path


def summary(kind, features, results):
    for mode in MODES:
        for name, _obj in features:
            b, m = results["base", name], results[mode, name]
            d = 0.0 if mode == "base" else deviation(b[3], m[3])
            rows.append((kind, name, mode, "%.4f" % m[0],
                         "%.3f" % (b[0] / m[0]) if m[0] else "",
                         "yes" if m[1] else "no", m[2], "%.2e" % d,
                         "yes" if m[1] < b[1] or m[2] > b[2] else "no"))
    say("=== %s summary (vs base) ===" % kind)
    base_total = sum(results["base", n][0] for n, _o in features)
    for mode in MODES[1:]:
        total = sum(results[mode, n][0] for n, _o in features)
        worse, off = [], []
        for name, _obj in features:
            b, m = results["base", name], results[mode, name]
            if m[1] < b[1] or m[2] > b[2]:
                worse.append(name)
            d = deviation(b[3], m[3])
            if d > MARGIN:
                off.append("%s (%.1e)" % (name, d))
        say("%-16s %6.2f s vs %6.2f s  speedup %.2fx" % (
            mode, total, base_total, base_total / total))
        say("    worse than base: %s" % (", ".join(worse) or "none"))
        say("    deviating > %.0e: %s" % (MARGIN, ", ".join(off) or "none"))


def run():
    walk = steps()

    def step():
        try:
            next(walk)
        except StopIteration:
            return
        except Exception as exc:
            bf.SPEED.clear()
            App.Console.PrintError("check modes stopped: %s\n" % exc)
            return
        QtCore.QTimer.singleShot(0, step)

    QtCore.QTimer.singleShot(0, step)


run()
