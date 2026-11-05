# Finder commands

`finder.py`: plain Python functions for files and folders, done through Finder or the file system. Python 3.9+, standard
library only. Put this folder on `sys.path` (or copy the file next to your program) and `import finder`.

```python
import finder

for pdf in finder.file_find(query="*.pdf", folder="~/Downloads", fields="path"):
    finder.file_move(path=pdf["path"], to_folder="~/Documents/Invoices", mode="background")
```

**Verified on macOS 15.6.1 only. This doesn't cover macOS 26 or any other version.** On another version, results gain
`"unverified_version": true` and both versions.

## Keeping it inside one folder

Set `FINDER_ALLOWED_ROOT` to a folder and every path is checked to be inside it, after following links, before anything
happens. A path outside raises `OutsideAllowedRoot`. If it isn't set, these commands can act on any file you can reach,
so setting it is recommended for an agent.

**Left out on purpose: emptying the Trash and permanent delete.** `file_trash` only moves things to the Trash.

## Modes

- `mode="background"`: the change goes through the macOS file APIs, and nothing appears on screen. Finder shows the result.
- `mode="ui"`: the change is made in a Finder window. The call goes to the folder with **Go › Go to Folder…**, switches to
  **View › as List**, selects the item's row by its exact name, and uses menu items by name: **File › Move to Trash**,
  **File › New Folder**, **Edit › Copy “…”** with **Edit › Paste Item**, or Move Item Here (⌥⌘V). Names are pasted through
  the clipboard, which is restored afterwards. It depends on English names.
- `file_list`, `file_find` and `file_info` read the file system directly.
- `file_reveal` and `folder_open` are UI only, because showing something on screen is all they do.

## Start states (UI mode)

Each UI call brings Finder to the front, opens a window if none is open, and closes only its passing UI: a menu, a search,
or a dialog with no text in it. If a name is being edited, or a dialog still holds text, the call raises `StateBlocked`
and changes nothing. A Go to Folder dialog left open keeps its earlier path as text, so it counts as holding text.

It works with no Finder window open, another folder showing, Finder hidden or minimized, another app in front, a search
showing, another item selected, and two windows open.

## Paths and errors

Paths are absolute or start with `~`. Copies and moves keep the item's name and never overwrite.

| Error | When |
|---|---|
| `OutsideAllowedRoot` | `FINDER_ALLOWED_ROOT` is set and the path is outside it; nothing is done |
| `NotFound` | nothing exists at the path, or the target folder is missing |
| `AlreadyExists` | the new path is taken; nothing is overwritten |
| `StateBlocked` | a name is being edited, a dialog holds text, or another app came to the front during a step |
| `UIError` | a named element never appeared within the timeout |
| `NotSupported` | the mode can't do this, or it wasn't verified |
| `ValueError` | a new name with `/` or a line break, or an unknown field |

## Fields

`name`, `path`, `kind` (`file`, `folder` or `link`), `size` (bytes; `None` for folders), `created_date`, `modified_date`.
The default is `name,path,kind,size,modified_date`.

## Limits

- Finder writes its own `.DS_Store` file in folders it shows in UI mode.
- Finder can store a pasted name in a different Unicode form, so comparing accented names byte for byte may not match.
- UI mode selects rows that Finder lists for the folder; only small test folders were used, so very long folders are untested.
- The test VM's SSH session had Full Disk Access, so the prompts macOS shows for Desktop, Documents and Downloads weren't tested.

## Functions

### file_list(folder, limit=100, fields=None, mode="background") → [item]
The items directly in `folder`, by name. Hidden items are left out.

### file_find(query, folder="~", limit=100, fields=None, mode="background") → [item]
Items under `folder` whose name contains `query`, ignoring case, or matches it as a pattern such as `*.pdf`. Newest first.
Hidden folders and `~/Library` are skipped.

### file_info(path, fields=None, mode="background") → item

### folder_create(path, mode="ui") → item
The parent must exist.

### file_copy(path, to_folder, mode="ui") → the copy

### file_move(path, to_folder, mode="ui") → the item at its new place

### file_rename(path, to, mode="ui") → the renamed item

### file_trash(path, mode="ui") → item as it was, with `"trashed": true`
Moves it to the Trash. It can be put back from there.

### file_reveal(path, mode="ui") → item, with `"revealed": true`
Shows it selected in a Finder window.

### folder_open(path, mode="ui") → item, with `"opened": true`

## How it was verified

In fresh copies of one VM, with made-up files including emoji, accents and quotes, all inside one test folder. Every path was
checked to be inside it first. Results were read back from the file system with separate code, and every other test file was
compared by content before and after. The top level of the home folder was compared by name and modified time, and nothing
outside the test folder changed. `file_reveal` and `folder_open` change nothing on disk, so what they show was read from
Finder's window through Accessibility, which isn't independent of Finder.

| Function | Mode | Verified | Cases | Start states |
|---|---|---|---|---|
| `file_copy` | background | yes | 25 | a confirmation dialog open, app closed, app hidden, minimized, another app in front, another folder/list/view showing, search field with text, another item selected, two windows open |
| `file_copy` | ui | yes | 26 | a confirmation dialog open, app closed, app hidden, minimized, another app in front, another folder/list/view showing, search field with text, another item selected, two windows open, half-typed text in another item |
| `file_find` | background | yes | 21 | a confirmation dialog open, app closed, app hidden, minimized, another app in front, another folder/list/view showing, search field with text, another item selected, two windows open |
| `file_info` | background | yes | 13 | a confirmation dialog open, app closed, app hidden, minimized, another app in front, another folder/list/view showing, search field with text, another item selected, two windows open |
| `file_list` | background | yes | 13 | a confirmation dialog open, app closed, app hidden, minimized, another app in front, another folder/list/view showing, search field with text, another item selected, two windows open |
| `file_move` | background | yes | 16 | a confirmation dialog open, app closed, app hidden, minimized, another app in front, another folder/list/view showing, search field with text, another item selected, two windows open |
| `file_move` | ui | yes | 17 | a confirmation dialog open, app closed, app hidden, minimized, another app in front, another folder/list/view showing, search field with text, another item selected, two windows open, half-typed text in another item |
| `file_rename` | background | yes | 17 | a confirmation dialog open, app closed, app hidden, minimized, another app in front, another folder/list/view showing, search field with text, another item selected, two windows open |
| `file_rename` | ui | yes | 18 | a confirmation dialog open, app closed, app hidden, minimized, another app in front, another folder/list/view showing, search field with text, another item selected, two windows open, half-typed text in another item |
| `file_reveal` | ui | yes | 11 | a confirmation dialog open, app closed, app hidden, minimized, another app in front, another folder/list/view showing, search field with text, another item selected, two windows open, half-typed text in another item |
| `file_trash` | background | yes | 15 | a confirmation dialog open, app closed, app hidden, minimized, another app in front, another folder/list/view showing, search field with text, another item selected, two windows open |
| `file_trash` | ui | yes | 16 | a confirmation dialog open, app closed, app hidden, minimized, another app in front, another folder/list/view showing, search field with text, another item selected, two windows open, half-typed text in another item |
| `folder_create` | background | yes | 16 | a confirmation dialog open, app closed, app hidden, minimized, another app in front, another folder/list/view showing, search field with text, another item selected, two windows open |
| `folder_create` | ui | yes | 17 | a confirmation dialog open, app closed, app hidden, minimized, another app in front, another folder/list/view showing, search field with text, another item selected, two windows open, half-typed text in another item |
| `folder_open` | ui | yes | 11 | a confirmation dialog open, app closed, app hidden, minimized, another app in front, another folder/list/view showing, search field with text, another item selected, two windows open, half-typed text in another item |

Verified on macOS 15.6.1 (24G90), finder 15.5 (1732.6.4), 2026-11-04, in fresh VM clones.

## Permissions

UI mode needs **Accessibility** and **Automation** for System Events. `file_trash` in background mode, and the file reads, need
no Automation. Folders macOS protects may ask for access once.
