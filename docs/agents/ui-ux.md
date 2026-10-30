# UI and UX

Nxt should feel like a well-made desktop application that happens to be
inside FreeCAD: quiet, quick, predictable.

## Feedback and responsiveness

- **Every control responds at once**: hover, press and release are drawn
  immediately. A switch or selector changes visually *first*; the work it
  triggers starts a frame later (`NxtSwitch`: flip now, `changedTo` after
  ~30 ms, settle back if the change never lands).
- **Widget state never waits on computation.** Recomputes, document walks
  and solver reads happen after the frame that shows the change.
- **Live previews degrade honestly.** If a live preview is too slow (the
  rollback bar's ~120 ms budget), fall back to apply-on-release and say so
  in the Report view, rather than stuttering.
- Animations are short (~90–150 ms) and never animate a colour through
  `"transparent"` (that is transparent *black*); animate opacity instead.

## Desktop conventions

- Arrow cursor on buttons, switches, rows and chips. Pointing hand only on
  text links.
- Double-click opens an object for editing; F2 or a click on an
  already-selected name renames (armed after the double-click interval).
- Escape backs out of the innermost thing (popup, detail strip, edit),
  never two at once. Return applies; Escape in a field reverts.
- Keyboard actions work on FreeCAD's selection, not a list's current row.
- Context menus open at the pointer and offer what is most likely next.
- Mouse wheel over a number steps it (fine; with the modifier, coarse), the
  same steps as the 3D drag handles.

## Controls

- **Switches, not checkboxes**, for on/off settings, in most places.
- **Segmented control** for a few choices that change the shape (One side
  / Two sides / Symmetric); **dropdown** for longer lists.
- Labels are short; explanation goes in a tooltip or a card hint.
- A value that can't be changed in the current mode is hidden, not shown
  disabled, unless seeing it helps (then read-only).
- The same control behaves the same everywhere (a chip that double-clicks
  to open on a row also does in the detail strip).

## Information

- **A mark means something is wrong.** Don't decorate every row; a marker
  on everything is read by no one. Severity has a shape before a colour
  (ring, triangle, disc).
- **Accessibility is a constraint**: every state has a non-colour cue
  (shape, dashed vs solid, italic). Interactive borders ≥ 3:1 contrast,
  text ≥ 4.5:1.
- **Whole name or clean icon, never a fragment.** Elide only where the full
  name is a hover away.
- Follow the host theme: colours from FreeCAD's stylesheet (`ui/theme.py`),
  in light and dark, docked and in overlay mode. Test both.
- Plain words in messages: what happened and what to do ("Repaired Sketch
  (2 gaps closed)", with Undo).

## Where things live

- The **detail strip** (under a tree row) only changes values. Structural
  edits (adding a variable, renaming its type) belong in the Property
  Inspector.
- **Task panels and the inspector use the same template**, so a feature
  looks and works the same in both.
- Nxt's automatic fixes (wire repair) are undoable in one click and never
  hide what they did.
- Commands that act without a dialog in FreeCAD act without one here.
