# Automator commands

`automator.py`: plain Python functions to build and save Automator workflows. Python 3.9+, standard library only. Put this folder on
`sys.path` (or copy the file next to your program) and `import automator`.

```python
import automator

automator.workflow_new()
automator.workflow_add_action(name="Get Specified Finder Items")
automator.workflow_add_action(name="Change Type of Images", copy_first=True)
automator.workflow_save(path="~/Documents/to-jpeg.workflow")
```

**Verified on macOS 15.6.1 with Automator 2.10 only. This doesn't cover macOS 26 or any other version.** On another version,
results gain `"unverified_version": true` and both versions.

## How it works

UI mode only. Automator's own scripting (`add`, `execute`, action settings) didn't answer in testing: every call timed out, with no
prompt on screen. On screen, an action is selected by name in the library and added with Return, the same as double-clicking it.
For actions that change files Automator asks whether to add Copy Finder Items first; `copy_first` answers that. Saving uses the Save
dialog, filled in by name. No screen coordinates. It depends on English names.

## Functions

### workflow_new(mode="ui") → {name, actions}
**File > New**, then **Workflow** in Automator's "Choose a type for your document" dialog.

### workflow_add_action(name, copy_first=False, mode="ui") → {workflow, actions}
Adds the action with exactly that name to the end of the workflow in front.

### workflow_actions(mode="ui") → {workflow, actions}
The workflow's actions, in order.

### workflow_save(path, mode="ui") → {name, path, actions}
**File > Save…** as a new `.workflow` file.

## Left out

- Setting an action's options (such as the size in Scale Images or the type in Change Type of Images) and choosing its input files:
  each action has its own controls. They keep Automator's defaults.
- Running workflows: they'd need input files chosen in a dialog, and Automator's `execute` didn't answer.
- Quick Actions, Applications and the other document types.

## How it was verified

In fresh copies of one VM, inside one test folder. Each saved workflow was read back from its `document.wflow` with separate code:
its actions had to be the bundles of the named actions, in order (each name matched to its bundle through the action's own
Info.plist on disk). Every case set a small clipboard first and checked it came back, and one ran with a very large clipboard.

| Function | Mode | Verified | Cases | Start states |
|---|---|---|---|---|
| `workflow_actions` | ui | yes | 3 | app closed, app open, another app in front |
| `workflow_add_action` | ui | yes | 8 | app closed, app open, another app in front |
| `workflow_new` | ui | yes | 3 | app closed, app open, another app in front |
| `workflow_save` | ui | yes | 19 | app closed, app open, another app in front |

Verified on macOS 15.6.1 (24G90), automator 2.10 (528), 2026-11-06, in fresh VM clones.

## Permissions

**Accessibility** and **Automation** for System Events.
