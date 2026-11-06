# Notes commands

`notes.py`: plain Python functions for Apple Notes on the local **On My Mac** account. Python 3.9+, standard
library only. Put this folder on `sys.path` (or copy `notes.py` next to your program) and `import notes`.

```python
import notes

found = notes.note_search(query="Goa trip", limit=20, fields="title,folder,modified_date")
if found:
    notes.note_append(match=found[0]["title"], folder=found[0]["folder"], text="Book the cab")
```

## Two modes, one interface

Every function takes `mode=` and returns the same value in either mode.

- `mode="ui"`: the change is made **on screen**. System Events clicks buttons, menu items and rows that it
  finds by name and role, never by screen position, and text is pasted through the clipboard. The clipboard is
  saved first and restored afterwards, so emoji, accents, quotes and line breaks arrive exactly. This is the
  default for functions that change something.
- `mode="background"`: Notes' own scripting is used and nothing appears on screen. If Notes isn't running, it is
  started hidden. This is the default for functions that only read.

In UI mode the note to act on is found by its exact title through Notes' own scripting, then shown. The call
checks that the editor holds that note before it types anything. Nothing is ever typed into a field that the call
didn't open or find by name.

## Left out

- `checklist_create` and `note_pin` have no background mode: Notes' scripting can't make a checklist and has no
  pinned property.
- `note_rename`, `note_delete`, `folder_rename` and `folder_delete` have no background mode. With Notes open, a
  change made through Notes' scripting showed in Notes but did not reach Notes' database within 150 seconds, in
  two runs. A call can't be verified against data that isn't there, so these four are UI only.
- The reads (`note_get`, `note_search`, `note_list`, `folder_list`) are background only. They read Notes' data
  directly, which gives exact fields; the screen shows dates relatively and bodies cut short.
- A function and mode that isn't verified raises `NotSupported` with its reason.

If Notes isn't running, a background call starts it hidden and quits it again at the end. That makes Notes write
the change to disk at once.

## Start states (UI mode)

Each UI call first brings Notes to the front and clears away only Notes' own transient UI: an open menu, a
popover, a search, a hidden sidebar, or a confirmation with a Cancel button and no typed text. It then works from
any of these states:

- Notes closed, still launching, hidden or minimized
- another app in front, or two Notes windows open
- another folder showing, or a note selected
- the cursor in another note with half-typed text (that text is kept)
- a search with text in the search field
- a confirmation dialog open

If a dialog holds typed text, or isn't Notes' own, the call raises `StateBlocked` and changes nothing. It never
destroys what the user was doing.

## Matching and errors

`match` is the exact title. Add `folder=` (or `from_folder=` for `note_move`) when the same title exists in
several folders.

| Error | When |
|---|---|
| `NotFound` | no note or folder has that exact title or name |
| `Ambiguous` | more than one note matches; nothing is changed |
| `AlreadyExists` | `folder_create` or `folder_rename` would make a second folder of the same name |
| `StateBlocked` | the screen holds something the call won't destroy, such as a dialog with typed text |
| `UIError` | a named element never appeared within the timeout |
| `NotSupported` | the mode can't do this, or wasn't verified (the message gives the reason) |

## Fields and return values

Notes are returned as dicts. `fields=` picks the keys, as a comma-separated string or a list, from:
`id`, `title`, `body` (the text after the title line), `folder`, `created_date`, `modified_date`.
Dates are `YYYY-MM-DD HH:MM` in local time. The default is `title,body,folder,modified_date`; functions that
change a note also return `id`.

## Versions

`VERIFIED` at the top of `notes.py` records, for each function and mode, the macOS and Notes versions and builds
it was verified on. Every call compares them with the running versions. If they differ, the call still runs, but
its result gains `"unverified_version": true` together with both versions, and a warning is issued.

## Functions

### note_create(title, body="", folder=None, mode="ui") → note
Makes a note whose first line is `title`, followed by `body` (line breaks kept), in `folder`; with no folder it
goes into the default folder, Notes.
UI steps: select the folder row in the Folders sidebar, click the toolbar button **New Note**, wait for the new
empty note's text area to take focus, paste `title`, a line break and `body`.
```python
notes.note_create(title="Packing list", body="passport\ncharger", folder="Travel")
```

### checklist_create(title, items, folder=None, mode="ui") → note + `items`
Makes a note holding a real Notes checklist, with one unchecked item per entry. Each item must be one line.
UI only: Notes' scripting can't make a checklist, and an HTML list would only be a fake one.
UI steps: as for note_create, then paste the title, press Return, click the toolbar button **Checklist**, and
paste the items.
```python
notes.checklist_create(title="Groceries", items=["milk", "eggs", "coffee ☕️"])
```

### note_get(match, fields=None, folder=None, mode="background") → note
```python
notes.note_get(match="Packing list", fields="title,body,created_date")
```

### note_search(query, limit=20, fields=None, mode="background") → [note]
Notes whose title or text contains `query`, ignoring case, newest first.
```python
notes.note_search(query="invoice", limit=50, fields="title,folder")
```

### note_list(folder=None, limit=50, fields=None, mode="background") → [note]
The notes in `folder`, or in every folder when no folder is given, newest first.
```python
notes.note_list(folder="Travel", fields="title,modified_date")
```

### note_append(match, text, folder=None, mode="ui") → note
Adds `text` as new lines at the end of the note.
UI steps: show the note, check the editor holds it, move the cursor to the end (⌘↓), paste a line break and
`text`.
```python
notes.note_append(match="Packing list", text="sunscreen")
```

### note_rename(match, title, folder=None, mode="ui") → note
Changes the note's first line.
UI steps: show the note, select its first line (⌘↑, then ⇧⌘→), paste `title`.

### note_replace_body(match, body, folder=None, mode="ui") → note
Replaces everything after the title with `body`.
UI steps: show the note, select from the end of the first line to the end of the note (⌘↑, ⌘→, ⇧⌘↓), paste a
line break and `body`. An empty `body` deletes the selection, or does nothing if the note has no text after its title.

### note_move(match, folder, from_folder=None, mode="ui") → note
UI steps: show the note, then the toolbar menu **More** › **Move to** › *folder*.
```python
notes.note_move(match="Acme invoice 42", folder="Invoices")
```

### note_delete(match, folder=None, mode="ui") → note as it was, with `"deleted": true`
Moves the note to Recently Deleted.
UI steps: show the note, then the toolbar menu **More** › **Delete Note**. If Notes shows its one-time notice
("Deleted notes are moved to the Recently Deleted folder"), the call clicks **OK**.

### note_pin(match, folder=None, mode="ui") → note + `"pinned": true`
UI only: Notes' scripting has no pinned property. A note that is already pinned stays pinned, and the call succeeds.
UI steps: show the note, then the menu **File** › **Pin Note**, and wait for the item to change to **Unpin Note**.

### folder_create(name, mode="ui") → {name, notes}
UI steps: click the toolbar button **Add Folder**, wait for the new folder's name field to take focus, paste
`name`, press Return.

### folder_list(mode="background") → [{name, notes}]
Every folder except Recently Deleted, with its number of notes.

### folder_rename(name, to, mode="ui") → {name, notes}
UI steps: select the folder row, focus the sidebar, then **Edit** › **Rename Folder**, paste `to`, press Return.

### folder_delete(name, mode="ui") → {name, notes, "deleted": true}
Deletes the folder. Its notes go to Recently Deleted.
UI steps: select the folder row, focus the sidebar, then **Edit** › **Delete Folder**, and click **Delete** in
the confirmation.

## Images (added later, macOS 15.6.1 only)

Verified on macOS 15.6.1 with Notes 4.12.7, unlike the commands above (macOS 26.6.2). It uses its own script, added after the code
above, which is unchanged. Background mode only.

### note_attach_image(match, path, folder=None, mode="background") → {title, folder, attached}
Adds the image at `path` (.png, .jpg, .jpeg, .gif, .heic, .tiff or .tif) to the end of the note titled `match`. The file is left as
it is.

- On the test VM, the first attachment made Notes upgrade its local store, which gave notes new ids; the note is found again by title.
- With Notes open, Notes' scripting can list one image twice, so the command doesn't return a count. What was stored was checked in
  NoteStore.sqlite: one attachment of the right type, and Notes' stored copy of the image had the same hash as the file.
- Only small images were tested. There is no UI mode.

Commands added later, verified separately:

| Function | Mode | Verified | Cases | macOS | App |
|---|---|---|---|---|---|
| `note_attach_image` | background | yes | 30 | 15.6.1 (24G90) | 4.12.7 (2998.63) |

## Verification

| Function | Mode | Verified | Cases | Start states |
|---|---|---|---|---|
| `checklist_create` | ui | yes | 11 | a confirmation dialog open, app closed, app hidden, app still launching, minimized, another app in front, another folder/list/view showing, search field with text, another item selected, two windows open, half-typed text in another item |
| `folder_create` | background | yes | 3 | app closed, app open |
| `folder_create` | ui | yes | 13 | a confirmation dialog open, app closed, app hidden, app still launching, minimized, another app in front, another folder/list/view showing, search field with text, another item selected, two windows open, half-typed text in another item |
| `folder_delete` | background | no | 3 | app closed, app open |
| `folder_delete` | ui | yes | 12 | a confirmation dialog open, app closed, app hidden, app still launching, minimized, another app in front, another folder/list/view showing, search field with text, another item selected, two windows open, half-typed text in another item |
| `folder_list` | background | yes | 2 | app closed, app open |
| `folder_rename` | background | no | 2 | app closed, app open |
| `folder_rename` | ui | yes | 11 | a confirmation dialog open, app closed, app hidden, app still launching, minimized, another app in front, another folder/list/view showing, search field with text, another item selected, two windows open, half-typed text in another item |
| `note_append` | background | yes | 4 | app closed, app open |
| `note_append` | ui | yes | 14 | a confirmation dialog open, app closed, app hidden, app still launching, minimized, another app in front, another folder/list/view showing, search field with text, another item selected, two windows open, half-typed text in another item |
| `note_create` | background | yes | 3 | app closed, app open |
| `note_create` | ui | yes | 13 | a confirmation dialog open, app closed, app hidden, app still launching, minimized, another app in front, another folder/list/view showing, search field with text, another item selected, two windows open, half-typed text in another item |
| `note_delete` | background | no | 4 | app closed, app open |
| `note_delete` | ui | yes | 13 | a confirmation dialog open, app closed, app hidden, app still launching, minimized, another app in front, another folder/list/view showing, search field with text, another item selected, two windows open, half-typed text in another item |
| `note_get` | background | yes | 4 | app closed, app open |
| `note_list` | background | yes | 2 | app closed, app open |
| `note_move` | background | yes | 4 | app closed, app open |
| `note_move` | ui | yes | 13 | a confirmation dialog open, app closed, app hidden, app still launching, minimized, another app in front, another folder/list/view showing, search field with text, another item selected, two windows open, half-typed text in another item |
| `note_pin` | ui | yes | 12 | a confirmation dialog open, app closed, app hidden, app still launching, minimized, another app in front, another folder/list/view showing, search field with text, another item selected, two windows open, half-typed text in another item |
| `note_rename` | background | no | 4 | app closed, app open |
| `note_rename` | ui | yes | 13 | a confirmation dialog open, app closed, app hidden, app still launching, minimized, another app in front, another folder/list/view showing, search field with text, another item selected, two windows open, half-typed text in another item |
| `note_replace_body` | background | yes | 3 | app closed, app open |
| `note_replace_body` | ui | yes | 12 | a confirmation dialog open, app closed, app hidden, app still launching, minimized, another app in front, another folder/list/view showing, search field with text, another item selected, two windows open, half-typed text in another item |
| `note_search` | background | yes | 2 | app closed, app open |

End-to-end programs (run in UI mode from a messy start state, outcome read from the app's database):

- Delete empty notes except those in a folder: passed.
- Goa trip / invoices: doesn't count. Every outcome check passed (newest Goa note appended, invoice notes moved into a new Invoices folder, other notes untouched), but the half-typed text that was part of its messy start state never reached the other note in that run. `note_create`'s typed-text start state is verified by a direct check instead.

Verified on macOS 26.6.2 (25G83), notes 4.13 (3146.141.6), 2026-11-02, in fresh VM clones.

## Permissions

UI mode needs **Accessibility** and **Automation** (System Events and Notes) for the program that runs Python.
Background mode needs **Automation** for Notes. Verification ran through `tart-guest-agent`, which had both.
