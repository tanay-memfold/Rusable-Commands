# System Settings commands

`system_settings.py`: plain Python functions for macOS System Settings: list and set the desktop wallpaper, list, add and remove
the apps that open at login, switch between light and dark appearance, and set the Dock's hiding, position and recent apps. Python
3.9+, standard library only. Put this folder on `sys.path` (or copy the file next to your program) and `import system_settings`.

```python
import system_settings as settings

settings.wallpaper_set(name="Sonoma")
settings.login_item_add(app_path="/System/Applications/Calculator.app")
settings.login_item_remove(name="Calculator")
```

**Verified on macOS 15.6.1 (System Settings 15.0) only. This doesn't cover macOS 26 or any other version.** On another version,
results gain `"unverified_version": true` and both versions.

## How it works

UI mode only. Panes are opened by System Settings' own `x-apple.systempreferences:` links. Buttons, rows, the Wallpapers list and the
Open dialog are found by name or identifier through the macOS Accessibility API. It depends on English names.

**Wallpaper:** each wallpaper is a button named after it. Pressing it through Accessibility does nothing, so it's **clicked in the
middle of the wallpaper's own button frame**. That happens only once the frame is wholly inside the visible Wallpapers list and the
window, and System Settings is in front. To get it there, the list is scrolled with the wheel over the list's own frame, and the
button's group is opened with its own **Show All** button (groups are closed again with Show Less afterwards, as far as they're
loaded). No fixed screen positions. The pane must then name it as the selected wallpaper. It sets every display and Space, and
refuses if "Show on all Spaces" is off. **Wallpapers that aren't on this Mac** (System Settings would download them from Apple on
first use) **are refused** with `StateBlocked` and nothing is done. On the tested Mac that includes Ventura and most aerials.

**Login items:** Open at Login's **Add** (+) opens an Open dialog. The app's path is pasted into Go to Folder (the clipboard is
restored), then Open. To remove an item, its row is selected and checked by name, then **Remove** (−). The app itself isn't
touched.

**Appearance and the Dock:** Appearance's Light, Dark and Auto buttons are found by name, and the Dock's controls by their
identifiers (auto-hide-dock, position, show-recents). These are pressed through Accessibility; no clicks are needed.

It refuses (`StateBlocked`, nothing done) when a System Settings dialog is already open.

## Functions

### wallpaper_list(mode="ui") → [{name, on_this_mac, current}]
Every wallpaper in the Wallpaper pane, found by scrolling through it (each group opened with Show All). Takes about 20 s.

### wallpaper_set(name, mode="ui") → {wallpaper, changed}
`changed` is false if it was already the wallpaper. `NotFound` if there's no such wallpaper. `StateBlocked` if it isn't on this Mac or
Show on all Spaces is off.

### login_item_list(mode="ui") → [{name, kind}]
Open at Login, in the pane's order (by name). A pane that's already showing is reloaded first (by way of General), because it
doesn't pick up changes made elsewhere.

### login_item_add(app_path, mode="ui") → {name, kind, path}
`app_path` must be an existing `.app`. `AlreadyExists` if it already opens at login.

### login_item_remove(name, mode="ui") → {name, removed}
`NotFound` if nothing by that name opens at login.

### appearance_set(mode_name, mode="ui") → {appearance, changed}
Sets macOS's appearance to `"light"`, `"dark"` or `"auto"` with **System Settings > Appearance**'s own **Light**, **Dark** and
**Auto** buttons (found by name and pressed). The pane must then show that button selected. `changed` is false if it already was.
Added overnight in its own section and tested on its own (read back with `defaults read -g`, separately from the pane).

### dock_set(autohide=None, position=None, show_recents=None, mode="ui") → {autohide, position, show_recents, changed}
**System Settings > Desktop & Dock**: **Automatically hide and show the Dock** (`autohide`), **Position on screen** (`position`:
`"left"`, `"bottom"` or `"right"`) and **Show suggested and recent apps in Dock** (`show_recents`). Each control is found by its
identifier, and only the values given change. The result reads all three back from the pane, and `changed` lists what changed.
Added overnight in its own section and tested on its own (read back with `defaults read com.apple.dock`).

## How it was verified

In fresh copies of one VM, with System Settings closed, open on another pane, already on the same pane, behind another app, and
hidden. Results were read independently of the pane. Wallpaper came from macOS's wallpaper store (the picture file or provider it
records, and that it changed). Login items came from System Events' login items, which the tests also used to set up and clear items.
Test values were wallpapers already on the Mac (Colors, Pictures and Dynamic ones, not Ventura) and built-in apps (not Calculator).
Every case set a small clipboard first and checked it came back, and one ran with a very large clipboard.

| Function | Mode | Verified | Cases | Start states |
|---|---|---|---|---|
| `appearance_set` | ui | yes | 18 | app closed, app hidden, app open, another app in front, the same pane already showing |
| `dock_set` | ui | yes | 23 | app closed, app hidden, app open, another app in front, the same pane already showing |
| `login_item_add` | ui | yes | 10 | app closed, app hidden, app open, another app in front, the same pane already showing |
| `login_item_list` | ui | yes | 5 | app closed, app hidden, app open, another app in front, the same pane already showing |
| `login_item_remove` | ui | yes | 6 | app closed, app hidden, app open, another app in front, the same pane already showing |
| `wallpaper_list` | ui | yes | 5 | app closed, app hidden, app open, another app in front, the same pane already showing |
| `wallpaper_set` | ui | yes | 8 | app closed, app hidden, app open, another app in front, the same pane already showing |

## Permissions

**Accessibility** and **Automation** for System Events.
