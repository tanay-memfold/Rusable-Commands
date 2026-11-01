# Reusable Commands

This repo has two parts:

1. **Command libraries**: plain Python functions for macOS apps, for an agent that writes a short program to do
   a task. They are listed below.
2. **Replayable UI commands** (`commands/`): recorded step lists that any accessibility-tree agent can replay.
   See [Replayable UI commands](#replayable-ui-commands).

## Command libraries

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

### Two modes, one interface

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

### State independence (UI mode)

Before acting, a UI call brings the app to the front and clears away only the app's own transient UI: an open
menu, a popover, a search, or a confirmation with a Cancel button and no typed text. It works from the app
closed, launching, hidden or minimized, from another app in front, from another folder, list or view, and with
another item selected or half-typed text elsewhere. That typed text is kept.

If something on screen would be lost by clearing it, such as a dialog with typed text, the call raises
`StateBlocked` and changes nothing. It types only into fields it opened or found by name.

### Matching and errors

`match` is an exact title or name, plus a date (Calendar) or a list (Reminders) where needed. If nothing
matches, the call raises `NotFound`. If more than one item matches, it raises `Ambiguous` and changes nothing. A
call never acts on the wrong item.

Results are dicts, or lists of dicts. `fields=` picks the keys, and dates are `YYYY-MM-DD HH:MM` in local time.

### Versions

Each file starts with `VERIFIED = {...}`: for each function and mode, the macOS and app versions and builds it
was verified on. Every call reads the running versions. If they differ, the call still runs, but its result
gains `"unverified_version": true` with both versions, so callers know.

### Permissions

- **UI mode**: **Accessibility** and **Automation** (System Events, and the app) for the program that runs
  Python.
- **Background mode**: **Automation** for the app.

macOS asks the first time. Answer the prompt once, then the calls run without prompts.

### How they were verified

Each function and mode was run in fresh macOS VM clones. In each case:

1. The start state and distractors were set up with plain scripting, never the function under test. The
   distractors included similar names, the same name elsewhere, and other items.
2. The function was called with new made-up values: emoji, accents, quotes and line breaks among them, and,
   for Calendar, times across midnight and month ends.
3. The result was read back from the app's **own database** (NoteStore.sqlite, Calendar.sqlitedb, and so on),
   not through the same path, and every field was checked.
4. The distractors were checked unchanged, and the return value checked against the stored data. In UI mode the
   screen had to change and no dialog could be left open; in background mode nothing came to the front.

NotFound, Ambiguous and StateBlocked were checked to change nothing. Only function+modes that passed every case
are enabled. Each folder's `verification.json` lists every check and start state, and its README lists what was
left out and why.

### Verified

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


## Replayable UI commands

Verified, replayable UI commands for macOS apps. Each command is a short list of steps on named on-screen
controls (buttons, fields, menu items, list rows), with its inputs left as blanks. Any agent that can read the
macOS accessibility tree and press, type and send keys can replay one.

Only verified commands are stored here. Nothing is added from a single run.

### Commands

| App | Command | File |
|---|---|---|
| Notes | make a note titled {title} in Notes | [commands/notes/title.json](commands/notes/title.json) |
| Notes | make a note titled {title} with the text {text} in Notes | [commands/notes/body.json](commands/notes/body.json) |
| Notes | add the text {text} to the note titled {title} in Notes | [commands/notes/add-text.json](commands/notes/add-text.json) |
| Notes | make a folder named {name} in Notes | [commands/notes/folder.json](commands/notes/folder.json) |
| Notes | make a note titled {title} in the Notes folder {folder} | [commands/notes/in-folder.json](commands/notes/in-folder.json) |
| Notes | pin the note titled {title} in Notes | [commands/notes/pin.json](commands/notes/pin.json) |
| Reminders | make a list {name} in Reminders | [commands/reminders/list.json](commands/reminders/list.json) |
| Reminders | add a reminder {title} to the list {list} in Reminders | [commands/reminders/in-list.json](commands/reminders/in-list.json) |

`index.json` lists the same commands for programs.

### What "verified" means

A command is stored only if all of these held, each in a fresh macOS VM:

1. It was learned from a run that did the task and ended done.
2. Its steps were replayed and ended done from two different start states: the app closed, and the app open
   with other items in it.
3. Every run was confirmed by reading the app's own data (for example the Notes database), not only by the
   agent saying it was done.
4. Every run used new, made-up values.

A single failed replay keeps a command out. Steps on raw screen positions, drags and gestures are never stored.

### File format

See [schema.json](schema.json). In short:

- `request`: the request it answers, with `{param}` blanks.
- `params`: the blanks, in the order they appear in `request`.
- `precondition`: what must be true before step 1. Replay opens the app by name and waits for its window; a
  command never stores how the app was reached.
- `steps`: in order. Each is one of:
  - `press` a `control` (`role` + `name`)
  - `type` `text` into a `control`
  - `key`, with `keys` such as `Return`
- `verification`: the start state, run id and data checks of each run, the date, and the engine used.

### Control names

- `{param}` in a name or text is replaced with the value.
- `…` stands for any text. `{title}…` matches a list row whose name starts with the title, `…{title}` one whose
  name ends with it.
- In `text`, `\n` is a line break. In Notes the first line of the note is its title.

### Replaying a command

1. Fill every blank in `steps` with the request's values.
2. Make the precondition true: open the app by name, bring it to the front, wait for a window.
3. For each step, find the control with that role and name on screen, then press, type or send the key.
4. After each step, check it took effect (the typed value shows on screen). If a step's control is missing or
   nothing changes, stop and hand the task back to the agent. Don't guess.

### Scope and versions

Recorded on macOS 26.6.2, Notes 4.13 and Reminders 7.0, in English. Control names can change with app
versions or languages, so check `app.version` and `platform.version` before replaying, and verify again on a
new version.

Learned and verified with Voice Actions 3.9.3 and 3.9.4. The steps don't depend on that engine.
