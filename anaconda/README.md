# Anaconda Navigator commands

`anaconda.py`: plain Python functions for Anaconda Navigator: remove a conda environment. Python 3.9+,
standard library only. Put this folder on `sys.path` (or copy the file next to your program) and `import anaconda`.

```python
import anaconda

anaconda.environment_remove(name="data_analysis")
```

**Verified on macOS 15.6.1 with Anaconda Navigator 2.6.6 only. This doesn't cover macOS 26 or any other version.** On another
version, results gain `"unverified_version": true` and both versions.

## How it works

UI mode only (Navigator has no scripting). Buttons, the sidebar and the Search Environments and Search Packages fields are found by name
through the macOS Accessibility API. **Navigator's environment rows have no names**, so: the environment is searched for by name until only
its rows remain, a row is pressed **in the middle of the row's own frame**, and the
selection is **checked by name before anything happens**. Navigator's Remove dialog names the selected environment and its location
(it is opened and cancelled when only checking), and the root environment is the one with the `_anaconda_depends` package. No fixed
screen positions. It depends on English names.

On launch, Navigator's offer to update itself gets **No, remind me later**, and its offer to sign in for AI help is closed; nothing is
updated or signed in.

## Functions

### environment_remove(name, mode="ui") → {name, path, removed}
The environment, **Remove**, and **Remove** in Navigator's dialog, but only if the dialog names that environment and its folder. It
deletes the environment and everything in it. The root environment can't be removed (`ValueError`); `NotFound` if there's no such
environment.

## Left out

- **Making environments** (`environment_create`): in testing it didn't refuse when Navigator's Create dialog already held a typed
  name (day 3b), so it was taken out.
- **Updating every package in an environment**: Navigator has no button for it, only per-package marks.
- **Launching Jupyter Notebook**: it worked from the environment's ▶ menu (Open with Jupyter Notebook) in every start state but once.
  With Navigator hidden, a Navigator window was left open after the launch; it couldn't be reproduced, but both fixes were used, so it
  was taken out. The Home page's tiles have no names.

## How it was verified

In fresh copies of one VM, with made-up environments made by conda itself in each case's setup, with Navigator closed, open, on its
Environments page, behind another app, and hidden. Removal was read from conda's own folders (the environment's folder gone, every
other environment kept). Every case set a small clipboard first and checked it came back, and one ran with a
very large clipboard.

| Function | Mode | Verified | Cases | Start states |
|---|---|---|---|---|
| `environment_remove` | ui | yes | 8 | app closed, the Environments page showing, app hidden, app open, another app in front |

Verified on macOS 15.6.1 (24G90), anaconda 2.6.6, 2026-11-06, in fresh VM clones.

## Permissions

**Accessibility** and **Automation** for System Events.
