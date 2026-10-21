"""Nxt chamfer test cases: fillet_cases.py's cases, chamfered.

Run with FreeCAD's command line:
    freecadcmd tests/chamfer_cases.py                  # build, check, save
    freecadcmd tests/chamfer_cases.py --pass record    # and record volumes

Saves tests/models/chamfer_cases.FCStd; volumes go to chamfer_cases.json.
"""

import runpy
import sys
from pathlib import Path

sys.argv.append("chamfer")
runpy.run_path(str(Path(__file__).with_name("fillet_cases.py")),
               run_name="__main__")
