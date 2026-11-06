# VS Code commands

`vscode.py`: plain Python functions for Visual Studio Code: open folders and files, and make files. Python 3.9+,
standard library only. Put this folder on `sys.path` (or copy the file next to your program) and `import vscode`.

```python
import vscode

vscode.folder_open(path="~/Projects/site")
vscode.file_new(path="~/Projects/site/app.js", text="console.log('hi');\n")
```

**Verified on macOS 15.6.1 with VS Code 1.105.1 only. This doesn't cover macOS 26 or any other version.** On another version,
results gain `"unverified_version": true` and both versions.

## How it works

UI mode only. VS Code's `code` command-line tool works, but it's a shell command, so it isn't offered as a mode. Menu items are
clicked by name, and the Open Folder, Open and Save As dialogs are filled in by name (Go to Folder).
To find VS Code's own dialogs, VS Code (an Electron app) is asked to show its window to Accessibility, which also turns on
its Screen Reader Optimized mode while it runs. VS Code's own "Do you trust the authors of the files in this folder?" is answered **No**, so folders open in Restricted Mode and
nothing is trusted. No screen coordinates. It depends on English names.

## Functions

### folder_open(path, mode="ui") → {name, path, window}
**File > Open Folder…**.

### file_open(path, mode="ui") → {name, path, window}
**File > Open…**, going to the file itself in the dialog.

### file_new(path, text="", mode="ui") → {name, path}
**File > New Text File**, the text pasted in (the clipboard is restored), then **Save As…** to `path`. The file stays open.
Whether the paste landed is judged from the window title only. If the paste is lost (say, one of VS Code's own dialogs takes it), the
file is saved empty and the call raises `UIError`, leaving that empty file. Reading the editor's text through Accessibility instead
was tried twice and failed in testing.

**Left out: installing extensions.** The first extension from a publisher makes VS Code ask "Trust Publisher & Install"; that is a
trust prompt, and these commands don't answer trust prompts. Use VS Code's own Extensions view.

## How it was verified

In fresh copies of one VM, with made-up projects inside one test folder, including names with emoji, accents and quotes. New files
were read back from disk (exact text),. Opening was checked by
the window title, which isn't independent of VS Code. Every case set a small clipboard first and checked it came back, and one ran
with a very large clipboard.

| Function | Mode | Verified | Cases | Start states |
|---|---|---|---|---|
| `file_new` | ui | yes | 9 | app closed, app open, another app in front |
| `file_open` | ui | yes | 4 | app closed, app open, another app in front |
| `folder_open` | ui | yes | 8 | app closed, app open, another app in front |

Verified on macOS 15.6.1 (24G90), vscode 1.105.1 (1.105.1), 2026-11-06, in fresh VM clones.

## Permissions

**Accessibility** and **Automation** for System Events.
