"""Translation maintenance tool for FreeCAD-Nxt.

Extracts, compiles, and checks Qt translations (.ts and .qm files).
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "freecad" / "nxt"
TRANSLATIONS_DIR = SRC_DIR / "resources" / "translations"
DEFAULT_LOCALE = "zh-CN"


def _find_tool(name: str) -> Path | None:
    """Locate a Qt tool executable across PATH and Python environments."""
    found = shutil.which(name)
    if found:
        return Path(found)

    candidates = [
        Path(sys.prefix) / "Scripts" / f"{name}.exe",
        Path(sys.prefix) / "bin" / name,
    ]

    home = Path.home()
    py_ver = f"Python{sys.version_info.major}{sys.version_info.minor}"
    roaming = home / "AppData" / "Roaming" / "Python" / py_ver / "Scripts"
    candidates.append(roaming / f"{name}.exe")

    for cand in candidates:
        if cand.is_file():
            return cand
    return None


def _get_source_files() -> list[str]:
    """Collect all Python and QML files for translation extraction."""
    files: list[str] = []
    for ext in ("*.py", "*.qml"):
        for path in SRC_DIR.rglob(ext):
            files.append(str(path))
    files.sort()
    return files


def cmd_update(args: argparse.Namespace) -> int:
    """Extract and update source strings to TS files."""
    lupdate = _find_tool("pyside6-lupdate")
    if not lupdate:
        print("Error: pyside6-lupdate not found.", file=sys.stderr)
        return 1

    files = _get_source_files()
    if not files:
        print("Error: No source files found to extract.", file=sys.stderr)
        return 1

    TRANSLATIONS_DIR.mkdir(parents=True, exist_ok=True)
    ts_template = TRANSLATIONS_DIR / "Nxt.ts"
    ts_locale = TRANSLATIONS_DIR / f"Nxt_{args.locale}.ts"

    cmd = [str(lupdate), *files, "-ts", str(ts_template), str(ts_locale)]
    print(f"Updating {ts_template.name} and {ts_locale.name}...")
    res = subprocess.run(cmd)
    return res.returncode


def cmd_build(args: argparse.Namespace) -> int:
    """Compile TS files into binary QM files."""
    lrelease = _find_tool("pyside6-lrelease")
    if not lrelease:
        print("Error: pyside6-lrelease not found.", file=sys.stderr)
        return 1

    ts_files = list(TRANSLATIONS_DIR.glob(f"Nxt_{args.locale}.ts"))
    if not ts_files:
        ts_files = list(TRANSLATIONS_DIR.glob("*.ts"))

    if not ts_files:
        print("Error: No .ts files found to build.", file=sys.stderr)
        return 1

    ret = 0
    for ts in ts_files:
        qm = ts.with_suffix(".qm")
        print(f"Compiling {ts.name} -> {qm.name}...")
        res = subprocess.run([str(lrelease), str(ts), "-qm", str(qm)])
        if res.returncode != 0:
            ret = res.returncode
    return ret


def cmd_check(args: argparse.Namespace) -> int:
    """Validate translation completion and placeholder integrity."""
    ts_path = TRANSLATIONS_DIR / f"Nxt_{args.locale}.ts"
    if not ts_path.exists():
        print(f"Error: {ts_path} does not exist.", file=sys.stderr)
        return 1

    tree = ET.parse(ts_path)
    root = tree.getroot()

    total = 0
    translated = 0
    unfinished = 0
    vanished = 0
    issues: list[str] = []

    placeholder_pattern = re.compile(r"(%[0-9]+|%[sd]|{[a-zA-Z0-9_]*})")

    for context in root.findall("context"):
        ctx_name = context.find("name")
        cname = ctx_name.text if ctx_name is not None else "unknown"

        for msg in context.findall("message"):
            total += 1
            src_elem = msg.find("source")
            trans_elem = msg.find("translation")

            src = src_elem.text if src_elem is not None else ""
            trans = trans_elem.text if trans_elem is not None else ""
            trans_type = (
                trans_elem.get("type") if trans_elem is not None else None
            )

            if trans_type == "vanished":
                vanished += 1
                continue
            if trans_type == "unfinished" or not trans:
                unfinished += 1
                continue

            translated += 1

            src_tokens = sorted(placeholder_pattern.findall(src or ""))
            trans_tokens = sorted(placeholder_pattern.findall(trans or ""))
            if src_tokens != trans_tokens:
                issues.append(
                    f"[{cname}] Placeholder mismatch:\n"
                    f"  Source:      {src}\n"
                    f"  Translation: {trans}\n"
                    f"  Expected:    {src_tokens} vs Got: {trans_tokens}"
                )

    pct = (translated / total * 100) if total else 0.0
    print("=" * 60)
    print(f"Translation Status for {ts_path.name}:")
    print(f"  Total entries:      {total}")
    print(f"  Translated:         {translated} ({pct:.1f}%)")
    print(f"  Unfinished:         {unfinished}")
    print(f"  Vanished (obsolete): {vanished}")
    print("=" * 60)

    if issues:
        print("\nPlaceholder validation issues detected:")
        for issue in issues:
            print(issue)
        return 1

    print("\nAll translated entries have valid placeholders!")
    return 0


def main() -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="FreeCAD-Nxt Translation Manager"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_update = sub.add_parser("update", help="Extract/update TS files")
    p_update.add_argument(
        "--locale", default=DEFAULT_LOCALE, help="Target locale code"
    )

    p_build = sub.add_parser("build", help="Compile TS to QM")
    p_build.add_argument(
        "--locale", default=DEFAULT_LOCALE, help="Target locale code"
    )

    p_check = sub.add_parser("check", help="Verify translation completeness")
    p_check.add_argument(
        "--locale", default=DEFAULT_LOCALE, help="Target locale code"
    )

    args = parser.parse_args()
    if args.command == "update":
        return cmd_update(args)
    if args.command == "build":
        return cmd_build(args)
    if args.command == "check":
        return cmd_check(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
