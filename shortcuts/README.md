# Shortcuts commands

`shortcuts.py`: plain Python functions for the macOS Shortcuts app: list, run, make folders for, move and delete shortcuts. Python
3.9+, standard library only. Put this folder on `sys.path` (or copy the file next to your program) and `import shortcuts`.

```python
import shortcuts

shortcuts.shortcut_list()
shortcuts.shortcut_run(name="Random Pick")
shortcuts.folder_create(name="Work")
shortcuts.shortcut_move(name="Random Pick", folder="Work")
shortcuts.shortcut_delete(name="Old Timer")
```

**Verified on macOS 15.6.1 (Shortcuts 7.0) only. This doesn't cover macOS 26 or any other version.** On another version, results
gain `"unverified_version": true` and both versions.

## How it works

**Background mode** (list, run, folders, move) uses **Shortcuts Events**, the app's own scripting, and shows nothing. The first call
from a program makes macOS ask "… wants access to control Shortcuts Events". A person must allow that once; nothing here answers it.
Values go to the script as arguments, never into its text.

**Running:** a shortcut that reads or saves files makes Shortcuts ask, once per shortcut, "Allow '<name>' to …?" (Don't Allow /
Allow Once / Always Allow). `shortcut_run` never answers it: it raises `PermissionNeeded`, and the question stays on screen for a
person. While such a question is showing, `shortcut_run` refuses with `PermissionNeeded` and runs nothing.

**Deleting** is UI mode (Shortcuts Events accepts `delete` but nothing is deleted). The library window's search field gets the name.
It must then show exactly that one shortcut; if other shortcuts whose names contain it show too, the call refuses (`Ambiguous`), since
Delete acts on everything shown. Then Edit > Select All and Edit > Delete (menu items by name). Shortcuts asks "Delete shortcut
“<name>”?", and the call presses Delete only if the question names that shortcut; otherwise it presses Cancel. The search is cleared
afterwards. It depends on English names.

**Not here: making shortcuts.** `shortcut_create` is in the file but raises `NotSupported`: it was left out after two fixes, because
Shortcuts didn't always take the action's name in its library search, or the new name, whether set through Accessibility or pasted.

## Functions

### shortcut_list(mode="background") → [{name, folder, action_count, accepts_input}]
Every shortcut, sorted by name. `folder` is None at the top level.

### shortcut_run(name, input=None, timeout=60, mode="background") → {name, output}
Runs the shortcut once. `output` is its output as text, or None if it has none (a shortcut gives output with **Stop and Output**).
`PermissionNeeded` at Shortcuts' privacy question (left on screen). `NotFound`, `Ambiguous` (two shortcuts share the name).

### folder_create(name, mode="background") → {name}
`AlreadyExists` if a folder by that name exists.

### shortcut_move(name, folder, mode="background") → {name, folder, moved}
The folder must exist. `moved` is false if the shortcut was already there.

### shortcut_delete(name, mode="ui") → {name, deleted}
**Permanent.** See How it works.

## How it was verified

In fresh copies of one VM (macOS 15.6.1, made from the lab's base VM with the Automation permission for Shortcuts Events allowed by
a person), with Shortcuts closed, open and behind another app. Results were read independently of the library: Shortcuts' own
database, read-only (names, deleted flags, run counts), and the `shortcuts` command-line tool (folders and their shortcuts). Test
shortcuts and folders had made-up names, some with accents, emoji, quotes and symbols. Running was checked by the shortcut's run
count going up by one; the privacy question was raised with a made-up folder-archiving shortcut and checked to be left unanswered,
with nothing saved. Every case set a small clipboard first and checked it came back.

| Function | Mode | Verified | Cases | Start states |
|---|---|---|---|---|
| `folder_create` | background | yes | 5 | app closed, app open |
| `shortcut_delete` | ui | yes | 11 | app closed, app open, another app in front |
| `shortcut_list` | background | yes | 2 | app closed, app open |
| `shortcut_move` | background | yes | 8 | app closed, app open |
| `shortcut_run` | background | yes | 9 | app closed, app open |

## Permissions

**Automation** for Shortcuts Events (all commands) and for System Events, and **Accessibility** (`shortcut_delete`).
