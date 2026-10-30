# Workflow

How a change is made, checked and handed over.

## Before writing code

- Read the code you are about to change, and its tests. Many odd-looking
  lines are deliberate: check `tree/DESIGN.md` "Decisions" and the
  module's docstring before "simplifying" anything.
- For a FreeCAD feature (a Part Design operation, a property), read
  FreeCAD's wiki page and its `.ui` file. Property names, enumeration values
  and widget object names come from FreeCAD, not from memory.
- If the request is ambiguous in a way that changes what you build, ask one
  question. Otherwise pick the conventional answer and say so.

## While writing

- Make the smallest change that does the job well. Don't refactor
  neighbouring code unasked; mention it instead.
- Match the patterns already in the codebase (see
  [architecture](architecture.md)). Reuse `core/`, `ui/quick_host.py`,
  `Nxt.Controls` before writing a new helper or control.
- If an attempt doesn't fix the problem, **revert what it added** before
  trying something else. Don't stack speculative fixes.
- When the fastest solution costs readability or adds much code, stop and
  lay out the options with their pros and cons. The maintainer decides.

## Git

- The maintainer creates branches, commits, merges and pushes.
- An assistant may run read-only git only (`status`, `log`, `diff`,
  `show`), with `--no-optional-locks` in a shared working copy.
- Hand over with a suggested commit message: a short imperative subject
  (`area: what changed`), a body saying why, wrapped at 72 columns.

## Files that stay out of the repository

- Scratch models, test documents and experiments go in `local/`, which is
  in `.git/info/exclude`. Keep a generator script there
  (`local/make_loft_cases.py`) rather than only the `.FCStd`.
- No binaries that can't be reviewed. The one exception is compiled
  translations (`.qm`), which a test proves are exactly what their `.ts`
  compiles to.

## Reporting back

- Lead with the outcome, then what changed, then what is left.
- State how it was verified: unit tests, headless QML, `freecadcmd`, or a
  running FreeCAD. Never imply a GUI check that didn't happen.
- Name anything you noticed but did not change.
