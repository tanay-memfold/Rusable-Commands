# TextEdit commands

`textedit.py`: plain Python functions for plain text (`.txt`) and rich text (`.rtf`) documents in TextEdit. Python 3.9+, standard
library only. Put this folder on `sys.path` (or copy the file next to your program) and `import textedit`.

```python
import textedit

textedit.document_create(path="~/Documents/notes.txt", text="First line\n")
textedit.document_append(path="~/Documents/notes.txt", text="Second line\n")
textedit.document_save(path="~/Documents/notes.txt")
print(textedit.document_read(path="~/Documents/notes.txt")["text"])
textedit.document_close(path="~/Documents/notes.txt")
```

**Verified on macOS 15.6.1 only. This doesn't cover macOS 26 or any other version.** On another version, results gain
`"unverified_version": true` and both versions.

## Keeping it inside one folder

Set `TEXTEDIT_ALLOWED_ROOT` to a folder and every path is checked to be inside it, after following links, before anything happens.
A path outside raises `OutsideAllowedRoot`. If it isn't set, these commands can act on any `.txt` or `.rtf` file you can reach, so
setting it is recommended for an agent.

## TextEdit keeps changes by itself

- `document_replace_text` and `document_append` change the open document. Call `document_save` to be sure the file has them.
- TextEdit can also write them sooner, by itself, for example when another app comes to the front. There is no way to rely on the
  file still holding the old text.
- `document_close` keeps changes: they are written to the file as the window closes. There is no close without saving.
- `document_save_as` on a document with changes leaves them in the old file too, and the window then shows the new file.

## Modes

- `mode="ui"`: the change is made on screen. Elements are found by role and name through the macOS Accessibility API, menu items are
  clicked by name, and text is pasted through the clipboard, which is restored afterwards. It depends on English names.
- `mode="background"`: TextEdit's own scripting is used, and the front app stays in front. A closed TextEdit is started hidden.
- `document_list` and `document_read` default to `background`. The others default to `ui`.
- **Left out: background mode with TextEdit closed**, for `document_open`, `document_read`, `document_replace_text` and
  `document_append`. TextEdit came to the front when started that way, and two fixes didn't stop it, so these raise `NotSupported`
  and do nothing. Use `mode="ui"` or start TextEdit first. `document_create` and `document_list` work in background mode when it's closed.

## Start states (UI mode)

It works with TextEdit closed, still launching, or open with no document, with the document open or not, with its text selected,
with another document in front, with changes in another document, with a dialog on another document (which stays open), with an Open
dialog showing (which is cancelled), with TextEdit hidden or minimized, another app in front, and the Find bar open with text in it.

If the document itself has a dialog open, the call raises `StateBlocked` and changes nothing. While a window is minimized, or while
TextEdit is hidden, macOS reports its document windows as dialogs; these commands tell them apart by their text area.

## Paths and errors

Paths are absolute or start with `~`, and end in `.txt` or `.rtf`. `.txt` is plain text and `.rtf` is rich text. Nothing is overwritten.

| Error | When |
|---|---|
| `OutsideAllowedRoot` | `TEXTEDIT_ALLOWED_ROOT` is set and the path is outside it; nothing is done |
| `NotFound` | no file at the path, the folder is missing, or `document_save`, `document_save_as` or `document_close` was given a document that isn't open |
| `AlreadyExists` | the new path is taken; nothing is overwritten |
| `StateBlocked` | the document has a dialog open, or another app came to the front during a step |
| `UIError` | a named element never appeared, a change wasn't seen in time, or TextEdit didn't answer |
| `NotSupported` | the mode wasn't verified, or background mode was asked to open a document while TextEdit is closed |
| `ValueError` | a path that isn't `.txt` or `.rtf`, `document_save_as` to another type, empty text for `document_append`, an empty document for `document_copy_to_new`, or an unknown mode |

## Limits

- **Typing stalls scripting in the test VM.** After text was typed into a document with the keyboard, TextEdit stopped answering its
  scripting for at least 47 seconds, stuck in macOS text checking. Background commands then raise `UIError` after about 30 seconds.
  Pasted text didn't cause this, so these commands and their tests paste. What UI commands do straight after typing wasn't tested.
- Formatting isn't handled. Text can be replaced and added in `.rtf` files, but fonts and styles weren't checked, and
  `document_append` in background mode sets the whole text, so it can lose styles.
- Other file types, large documents, other text encodings, and `\r\n` line breaks weren't tested.
- A file changed by another program while it's open wasn't tested.
- Background commands on a document with a dialog open weren't tested. They may wait, then raise `UIError`.
- A closed TextEdit opens an empty Untitled document as it starts. It can be left open in the launching state, where it's listed with
  `path` set to `None`. Unsaved documents can't be named by these commands.
- The test VM doesn't use iCloud, so an Open dialog at launch, as on Macs with iCloud Drive, is only covered by the Open dialog state.
- The test VM already allowed its SSH session to script TextEdit: no Automation prompt appeared. macOS may ask once on another Mac.

## Functions

### document_list(mode="background") → [{name, path}]
The documents open in TextEdit. Doesn't start TextEdit. `path` is `None` for one that has never been saved.

### document_create(path, text="", mode="ui") → {name, path}
Makes a new document and saves it at `path`, which must not exist. The folder must exist. In UI mode it stays open; in background mode it's closed.

### document_open(path, mode="ui") → {name, path}
Opens it, or finds it if it's already open. In UI mode it comes to the front.

### document_read(path, mode="background") → {name, path, text}
The text as TextEdit holds it, including changes not yet written. Opens it if it isn't open.

### document_replace_text(path, text, mode="ui") → {name, path, text}
Replaces all the text. Opens it if it isn't open.

### document_append(path, text, mode="ui") → {name, path, text}
Adds `text` at the end with nothing between, and returns the whole text. Opens it if it isn't open.

### document_copy_to_new(path, to, mode="ui") → {name, path, from}
Copies all of a document's text into a new document and saves it at `to`, which must not exist, of either type. In UI mode this is
Select All, Copy, New and Paste, the clipboard is restored afterwards, and both documents stay open. In background mode the text is
read and written through scripting, and the new document is closed. An empty document raises `ValueError`.

### document_save(path, mode="ui") → {name, path, saved}
Writes the open document to its file, and waits until the file holds its text.

### document_save_as(path, to, mode="ui") → {name, path, from}
Saves the open document at a new path of the same type. The window then shows the new file.

### document_close(path, mode="ui") → {name, path, closed}
Closes the open document, keeping its changes.

## How it was verified

In fresh copies of one VM, with made-up files including emoji, accents, quotes and line breaks, all inside one test folder. Every path
was checked to be inside it first. Results were read back from the files with plain file reads, and `textutil` for `.rtf`, never through
TextEdit. Every other test file was compared by content before and after, and the top level of the home folder by name and modified
time. Windows and the front app were read through Accessibility and System Events, which isn't independent of TextEdit.

Changes made by `document_replace_text` and `document_append` were written with a plain ⌘S from the test before reading the file.
`document_list` and `document_read` of unsaved text are compared with what TextEdit's window shows. Each command was also run with a
very large clipboard (about 3.5 MB, text and other data), and the clipboard had to come back exactly, read back with `pbpaste` and
separate code. Every other case checked that a small clipboard came back.

| Function | Mode | Verified | Cases | Start states |
|---|---|---|---|---|
| `document_append` | background | yes | 33 | app closed, unsaved changes in another document, the find bar open, app hidden, app still launching, minimized, no window open, app open, an Open dialog showing, another app in front, another document in front, a dialog on another document, another item selected |
| `document_append` | ui | yes | 34 | app closed, unsaved changes in another document, the find bar open, app hidden, app still launching, minimized, no window open, app open, an Open dialog showing, another app in front, another document in front, a dialog on another document, another item selected, half-typed text in another item |
| `document_close` | background | yes | 26 | unsaved changes in another document, the find bar open, app hidden, minimized, app open, an Open dialog showing, another app in front, another document in front, a dialog on another document, another item selected |
| `document_close` | ui | yes | 27 | unsaved changes in another document, the find bar open, app hidden, minimized, app open, an Open dialog showing, another app in front, another document in front, a dialog on another document, another item selected, half-typed text in another item |
| `document_copy_to_new` | background | yes | 19 | unsaved changes in another document, the find bar open, app hidden, minimized, app open, another app in front, another document in front |
| `document_copy_to_new` | ui | yes | 19 | unsaved changes in another document, the find bar open, app hidden, minimized, app open, another app in front, another document in front |
| `document_create` | background | yes | 47 | app closed, unsaved changes in another document, the find bar open, app hidden, app still launching, minimized, no window open, app open, an Open dialog showing, another app in front, another document in front, a dialog on another document, another item selected |
| `document_create` | ui | yes | 47 | app closed, unsaved changes in another document, the find bar open, app hidden, app still launching, minimized, no window open, app open, an Open dialog showing, another app in front, another document in front, a dialog on another document, another item selected |
| `document_list` | background | yes | 13 | app closed, unsaved changes in another document, the find bar open, app hidden, app still launching, minimized, no window open, app open, an Open dialog showing, another app in front, another document in front, a dialog on another document, another item selected |
| `document_list` | ui | yes | 14 | app closed, unsaved changes in another document, the find bar open, app hidden, app still launching, minimized, no window open, app open, an Open dialog showing, another app in front, another document in front, a dialog on another document, another item selected |
| `document_open` | background | yes | 42 | app closed, unsaved changes in another document, the find bar open, app hidden, app still launching, minimized, no window open, app open, an Open dialog showing, another app in front, another document in front, a dialog on another document, another item selected |
| `document_open` | ui | yes | 43 | app closed, unsaved changes in another document, the find bar open, app hidden, app still launching, minimized, no window open, app open, an Open dialog showing, another app in front, another document in front, a dialog on another document, another item selected, half-typed text in another item |
| `document_read` | background | yes | 31 | app closed, unsaved changes in another document, the find bar open, app hidden, app still launching, minimized, no window open, app open, an Open dialog showing, another app in front, another document in front, a dialog on another document, another item selected |
| `document_read` | ui | yes | 32 | app closed, unsaved changes in another document, the find bar open, app hidden, app still launching, minimized, no window open, app open, an Open dialog showing, another app in front, another document in front, a dialog on another document, another item selected, half-typed text in another item |
| `document_replace_text` | background | yes | 65 | app closed, unsaved changes in another document, the find bar open, app hidden, app still launching, minimized, no window open, app open, an Open dialog showing, another app in front, another document in front, a dialog on another document, another item selected |
| `document_replace_text` | ui | yes | 66 | app closed, unsaved changes in another document, the find bar open, app hidden, app still launching, minimized, no window open, app open, an Open dialog showing, another app in front, another document in front, a dialog on another document, another item selected, half-typed text in another item |
| `document_save` | background | yes | 36 | unsaved changes in another document, the find bar open, app hidden, minimized, app open, an Open dialog showing, another app in front, another document in front, a dialog on another document, another item selected |
| `document_save` | ui | yes | 37 | unsaved changes in another document, the find bar open, app hidden, minimized, app open, an Open dialog showing, another app in front, another document in front, a dialog on another document, another item selected, half-typed text in another item |
| `document_save_as` | background | yes | 38 | unsaved changes in another document, the find bar open, app hidden, minimized, app open, an Open dialog showing, another app in front, another document in front, a dialog on another document, another item selected |
| `document_save_as` | ui | yes | 39 | unsaved changes in another document, the find bar open, app hidden, minimized, app open, an Open dialog showing, another app in front, another document in front, a dialog on another document, another item selected, half-typed text in another item |

Verified on macOS 15.6.1 (24G90), textedit 1.20 (409), 2026-11-05, in fresh VM clones.

## Permissions

UI mode needs **Accessibility** and **Automation** for System Events. Background mode needs **Automation** for TextEdit. Folders macOS
protects may ask for access once.
