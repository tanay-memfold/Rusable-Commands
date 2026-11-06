# Obsidian commands

`obsidian.py`: plain Python functions for Obsidian vaults and notes. Python 3.9+, standard library only. Put this folder on
`sys.path` (or copy the file next to your program) and `import obsidian`.

```python
import obsidian

v = obsidian.vault_create(name="Research", folder="~/Documents")["path"]
obsidian.note_create(vault=v, title="Plan", text="See [[Sources]] for more.")
```

**Verified on macOS 15.6.1 with Obsidian 1.9.14 only (its own installed update ran as 1.12.7). This doesn't cover macOS 26 or any other version.** On another version,
results gain `"unverified_version": true` and both versions.

## Keeping it inside one folder

Set `OBSIDIAN_ALLOWED_ROOT` to a folder and every path is checked to be inside it, after following links, before anything happens.

## How it works

UI mode only. Obsidian is an Electron app, so it is first asked to show its window to Accessibility (`AXManualAccessibility`); its
buttons, fields and pop-ups are then found by role and name. Names are pasted through the clipboard, which is restored afterwards,
and the vault's folder is chosen in Obsidian's folder dialog through Go to Folder. `note_create` uses Obsidian's own `obsidian://new`
link, which only works for a vault Obsidian already knows. No screen coordinates. It depends on English names.

## Functions

### vault_create(name, folder, mode="ui") → {name, path}
**Create local vault** in Obsidian's vault picker: the name, the folder through **Browse**, then **Create**. Obsidian opens the new
vault and adds its own Welcome note.

### vault_list(mode="ui") → [{name, path}]
The vaults Obsidian knows, read from its registry file (`obsidian.json`).

### note_create(vault, title, text="", mode="ui") → {vault, title, path}
Writes `title.md` in the vault through `obsidian://new`. Wiki links such as `[[Other note]]` are kept as written, so a note that
links to another is just text with a link in it.

## Left out

- **Setting the light or dark theme** (MacArena's "switch to light" task): Settings > Appearance > Base color scheme worked in a manual
  try (typing the choice's name into the focused pop-up), but in the final runs Settings sometimes stayed unreadable to
  Accessibility, with Obsidian closed and with it open, even after two fixes.
- **Installing and turning on community plugins** (MacArena's Excalidraw task): it needs turning off restricted mode and browsing
  the plugin store, and wasn't attempted for time.
- Community themes, Sync, notes in subfolders, and opening an existing folder as a vault.

## How it was verified

In fresh copies of one VM, with made-up vault and note names including emoji, accents and quotes, inside one test folder. Results
were read back from disk, separately from Obsidian: the vault folder and its `.obsidian` settings, Obsidian's registry file, each
note's exact text. Every other test file was
compared before and after (files in each vault's `.obsidian` settings folder were allowed to change: Obsidian writes its own window state and settings
there by itself, such as `workspace.json`, `app.json` and `appearance.json` when it opens a vault; notes were always checked). Every case set a small clipboard first and checked it came back, and two ran with a very large clipboard
(about 3.5 MB, text and other data) that had to come back exactly.

| Function | Mode | Verified | Cases | Start states |
|---|---|---|---|---|
| `note_create` | ui | yes | 12 | app closed, app hidden, app open, another app in front |
| `vault_create` | ui | yes | 9 | app closed, app hidden, app open, another app in front |
| `vault_list` | ui | yes | 4 | app closed, app hidden, app open, another app in front |

Verified on macOS 15.6.1 (24G90), obsidian 1.9.14 (0.14.8), 2026-11-06, in fresh VM clones.

## Permissions

**Accessibility** and **Automation** for System Events.
