# Reusable Commands

Plain Python functions for macOS apps, for an agent that writes a short program to do a task.

One folder per app, one Python file per app. Python 3.9 or later, standard library only: no package, no
install, no model, no keys.

| App | Folder | Import |
|---|---|---|
| Notes | [`notes/`](notes/) | `import notes` |
| Calendar | [`calendar/`](calendar/) | `import calendar_app as calendar` |

An agent writes a short program with keyword arguments, like this:

```python
import notes
import calendar_app as calendar

found = notes.note_search(query="Goa trip", limit=20, fields="title,folder,modified_date")
if found:
    notes.note_append(match=found[0]["title"], folder=found[0]["folder"], text="Book the cab")
calendar.event_create(title="Dentist", start="2026-11-18 15:15", end="2026-11-18 16:00", location="Room 4")
```

Put the app folders on `sys.path` (or copy the files next to the program). `calendar_app.py` is named so that it
doesn't clash with Python's own `calendar` module, so import it `as calendar`.

## Catalog

`notes/catalog.json` and `calendar/catalog.json` describe every verified command, so an agent can find and call
one without reading the code. Each file gives the app, its import line, the versions it was verified on, and one
entry per command: description, arguments, verified and default modes, example requests, effects, whether it is
destructive, precondition, postcondition, returned fields and errors.

To use them, match the request against `description` and `example_requests`, check `precondition`, then write a
program with the `import` line and the `args`, using only a mode listed under `modes`. Results can also carry the
version keys described under [Versions](#versions).

- `idempotent` (in `effects`): a repeat with the same arguments changes nothing more, though it may raise an error
  such as `NotFound`.
- `destructive`: true if the effect can't be easily undone. These commands also have `confirm`, the question to ask
  the user first, with roles like `<title>` to fill in.
- `known_gaps` (optional): behaviours that are untested or not directly confirmed. Read them before calling the
  command.

## Two modes, one interface

Every function takes `mode=` and returns the same value in both modes:

- **`mode="ui"`**: the change is made on screen, like a person would make it. System Events clicks buttons,
  menu items, rows and fields that it finds **by name and role**, never by screen position, and text is pasted
  through the clipboard. The clipboard is saved first and restored afterwards, so emoji, accents, quotes and line
  breaks arrive exactly. The item to act on is found by exact title through the app's own scripting, then shown,
  so the edit lands on that item only.
- **`mode="background"`**: the app's own scripting (AppleScript/JXA) is used and nothing appears on screen. A
  closed app is started hidden.

Functions that change something default to `ui`; functions that only read default to `background`. A mode that
wasn't verified raises `NotSupported`, and the message gives the reason.

## State independence (UI mode)

Before acting, a UI call brings the app to the front and clears away only the app's own transient UI: an open
menu, a popover, a search, or a confirmation with a Cancel button and no typed text. It works from the app
closed, launching, hidden or minimized, from another app in front, from another folder, list or view, and with
another item selected or half-typed text elsewhere. That typed text is kept.

If something on screen would be lost by clearing it, such as a dialog with typed text, the call raises
`StateBlocked` and changes nothing. It types only into fields it opened or found by name.

## Matching and errors

`match` is an exact title or name, plus a date (Calendar) where needed. If nothing
matches, the call raises `NotFound`. If more than one item matches, it raises `Ambiguous` and changes nothing. A
call never acts on the wrong item.

Results are dicts, or lists of dicts. `fields=` picks the keys, and dates are `YYYY-MM-DD HH:MM` in local time.

## Versions

Each file starts with `VERIFIED = {...}`: for each function and mode, the macOS and app versions and builds it
was verified on. Every call reads the running versions. If they differ, the call still runs, but its result
gains `"unverified_version": true` with both versions, so callers know.

## Permissions

- **UI mode**: **Accessibility** and **Automation** (System Events, and the app) for the program that runs
  Python.
- **Background mode**: **Automation** for the app.

macOS asks the first time. Answer the prompt once, then the calls run without prompts.

## How they were verified

Each function and mode was run in fresh macOS VM clones. In each case:

1. The start state and distractors were set up with plain scripting, never the function under test. The
   distractors included similar names, the same name elsewhere, and other items.
2. The function was called with new made-up values: emoji, accents, quotes and line breaks among them, and,
   for Calendar, times across midnight and month ends.
3. The result was read back from the app's **own database** (NoteStore.sqlite, Calendar.sqlitedb),
   not through the same path, and every field was checked.
4. The distractors were checked unchanged, and the return value checked against the stored data. In UI mode the
   screen had to change and no dialog could be left open; in background mode nothing came to the front.

NotFound, Ambiguous and StateBlocked were checked to change nothing. Only function+modes that passed every case
are enabled. Each folder's README lists the cases and start states, and what was left out and why.

## Verified

**Notes** ([README](notes/README.md)):

| Function | Background | UI |
|---|---|---|
| `checklist_create` | — | verified |
| `folder_create` | verified | verified |
| `folder_delete` | — | verified |
| `folder_list` | verified | — |
| `folder_rename` | — | verified |
| `note_append` | verified | verified |
| `note_create` | verified | verified |
| `note_delete` | — | verified |
| `note_get` | verified | — |
| `note_list` | verified | — |
| `note_move` | verified | verified |
| `note_pin` | — | verified |
| `note_rename` | — | verified |
| `note_replace_body` | verified | verified |
| `note_search` | verified | — |

**Calendar** ([README](calendar/README.md)):

| Function | Background | UI |
|---|---|---|
| `calendar_create` | verified | verified |
| `calendar_delete` | verified | verified |
| `calendar_list` | verified | — |
| `event_create` | verified | — |
| `event_delete` | verified | verified |
| `event_get` | verified | — |
| `event_list` | verified | — |
| `event_search` | verified | — |
| `event_update` | verified | — |
