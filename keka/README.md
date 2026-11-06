# Keka commands

`keka.py`: plain Python functions to make archives with Keka. Python 3.9+, standard library only. Put this folder on `sys.path`
(or copy the file next to your program) and `import keka`.

```python
import keka

keka.archive_set_format(format="tar")   # also opens Keka if it's closed
keka.archive_create(paths=["~/Documents/report.txt", "~/Documents/data.csv"])   # ~/Documents/Archive.tar
```

**Verified on macOS 15.6.1 with Keka 1.6.0 only. This doesn't cover macOS 26 or any other version.** On another version, results
gain `"unverified_version": true` and both versions.

## Keeping it inside one folder

Set `KEKA_ALLOWED_ROOT` to a folder and every path is checked to be inside it, after following links, before anything happens.

## How it works

UI mode only. Keka is sandboxed: when it has no access to a folder, it asks where to save each new archive. `archive_create` opens
the items with Keka, then fills in Keka's save dialog by name (the folder through Go to Folder, the name Keka proposes) and presses
Compress. The format is chosen with the Format pop-up in Keka's window, by name. No screen coordinates. It depends on English names.

## Functions

### archive_set_format(format, mode="ui") → {format}
zip, tar, 7z, gzip, bzip2, xz, dmg or iso. Keka keeps using it until it's changed.

### archive_format(mode="ui") → {format}
The format currently chosen in Keka's window.

### archive_create(paths, mode="ui") → {name, path, format, from}
An archive of items in the same folder, in the current format, saved next to them under Keka's own name (the item's name for one
item, `Archive` for several). The items stay. A TAR is uncompressed.

### archive_extract(path, mode="ui") → {archive, items}
Opens the archive with Keka. When Keka asks where to extract ("Choose a folder to extract this file"), the archive's own folder is
chosen and **Extract** pressed; once that folder has been chosen, Keka doesn't ask again. The archive stays. An archive with several
items comes out in a new folder named after it (Keka's own choice); `items` then lists that folder. Needs Keka open and not
hidden, like `archive_create`.

## Left out

- **`archive_create` and `archive_extract` with Keka closed or hidden**: items handed to a closed or hidden Keka were dropped in testing (the save dialog
  never came), even after two fixes. In those states it raises `NotSupported` and does nothing. Open Keka first.

- **Keka's scripting** (`compress`, `extract`): it hung for two minutes without doing anything while Keka had no access to the
  folder, so there's no background mode.
- Passwords, splitting and compression levels are left as Keka has them.
- If Keka's main window was closed, the commands raise `UIError`.

## How it was verified

In fresh copies of one VM, with made-up files inside one test folder, including names with emoji, accents and quotes. Archives were
read back with Python's `zipfile` and `tarfile`, separately from Keka: every item had to be inside with the same content, a TAR had to
be a plain uncompressed one, and nothing else in the test folder could change. Every case set a small clipboard first and checked it
came back, and one ran with a very large clipboard (about 3.5 MB, text and other data) that had to come back exactly. The format shown
in Keka's window was read through Accessibility, which isn't independent of Keka.

| Function | Mode | Verified | Cases | Start states |
|---|---|---|---|---|
| `archive_create` | ui | yes | 21 | app closed, app hidden, minimized, app open, another app in front |
| `archive_extract` | ui | yes | 14 | app closed, app hidden, minimized, app open, another app in front |
| `archive_format` | ui | yes | 5 | app closed, app hidden, minimized, app open, another app in front |
| `archive_set_format` | ui | yes | 16 | app closed, app hidden, minimized, app open, another app in front |

Verified on macOS 15.6.1 (24G90), keka 1.6.0 (5638), 2026-11-06, in fresh VM clones.

## Permissions

**Accessibility** and **Automation** for System Events.
