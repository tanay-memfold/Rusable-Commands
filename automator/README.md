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

### action_add_items(paths, action="Get Specified Finder Items", index=1, mode="ui") → {action, items}
**Add…**, then each item: Go to Folder to its folder, its name typed once the dialog lists it, **Add**. The added item's name is
checked; if the dialog picked something else, it is removed again and `UIError` is raised.

### action_set_folder(action, folder, option="To", index=1, mode="ui") → {action, option, folder}
The **To:** or **Where:** pop-up, **Other…**, Go to Folder, **Choose**.

### action_set_option(action, option, value, index=1, mode="ui") → {action, option, value}
A pop-up by its label (**To Type**, **Encoding**; Scale Images' **By**), a text field (**Save as**; Scale Images' **Size**, its
longest side) or a checkbox by its title (**Replacing existing files**, **Repeat for each subfolder found**).

### action_set_filter(attribute, operator, value=None, unit=None, action="Filter Finder Items", index=1, mode="ui") → {attribute, operator, value, unit}
Filter Finder Items' first rule, such as `("Date last modified", "is not in the last", 30, "days")`.

### workflow_run(mode="ui") → {ran, actions}
**Workflow > Run**, then waits while **Workflow > Stop** is on (up to 5 minutes). It succeeds only when Automator's status line says
"Workflow completed"; if an action stops the workflow, Automator's message is raised as `UIError`. With Automator closed it raises `NotFound` and starts nothing.

The five commands above were added on day 4 in their own section of the file and tested on their own; the code above them is
unchanged. **Your Desktop, Documents, Downloads and Pictures folders are guarded by macOS:** a workflow that reads or writes there may
show macOS's own "would like to access files" prompt, which these commands don't answer. Testing used other folders.

Four of MacArena's five Automator tasks can be built and run with these (with your own folders): convert PNGs to JPEG in another
folder, resize images to 600 px wide, move files older than 30 days, and list a folder's files into a text file (it lists full
paths). Not possible: a PDF from text files (Automator has no text-to-PDF action).

### workflow_open(path, mode="ui") → {name, path, actions}
Opens a saved `.workflow` in Automator, as a double-click on it would, and brings its window to the front, so `workflow_actions`,
`workflow_run` and the action commands act on it. If it's already open, its window is brought forward. If a fresh Automator also
shows its document chooser, that is closed with its own Close button, without choosing anything. The window must then hold that
file. `ValueError` if the path isn't a saved workflow. Added overnight in its own section and tested on its own.

## Left out

- Setting an action's options (such as the size in Scale Images or the type in Change Type of Images) and choosing its input files:
  each action has its own controls. They keep Automator's defaults.
- Running workflows: they'd need input files chosen in a dialog, and Automator's `execute` didn't answer.
- Quick Actions, Applications and the other document types.

## How it was verified

The day-4 commands: each option was read back from the saved workflow's document.wflow (saved with `workflow_save`), and
whole workflows were run and checked by the files they made (real JPEGs, image sizes, which files moved, the text file's lines).

In fresh copies of one VM, inside one test folder. Each saved workflow was read back from its `document.wflow` with separate code:
its actions had to be the bundles of the named actions, in order (each name matched to its bundle through the action's own
Info.plist on disk). Every case set a small clipboard first and checked it came back, and one ran with a very large clipboard.

| Function | Mode | Verified | Cases | Start states |
|---|---|---|---|---|
| `action_add_items` | ui | yes | 7 | app hidden, app open, another app in front |
| `action_set_filter` | ui | yes | 4 | app hidden, app open, another app in front |
| `action_set_folder` | ui | yes | 12 | app hidden, app open, another app in front |
| `action_set_option` | ui | yes | 15 | app hidden, app open, another app in front |
| `workflow_actions` | ui | yes | 3 | app closed, app open, another app in front |
| `workflow_add_action` | ui | yes | 8 | app closed, app open, another app in front |
| `workflow_new` | ui | yes | 3 | app closed, app open, another app in front |
| `workflow_open` | ui | yes | 14 | app closed, app open, another app in front |
| `workflow_run` | ui | yes | 5 | app hidden, Automator closed (no workflow), app open, another app in front |
| `workflow_save` | ui | yes | 19 | app closed, app open, another app in front |

Verified on macOS 15.6.1 (24G90), automator 2.10 (528), 2026-11-06, in fresh VM clones.

## Permissions

**Accessibility** and **Automation** for System Events.
