"""Writes settings/catalog.json. Local only."""
import json, sys
VER = sys.argv[1]
M = f"Verified on macOS 15.6.1 with System Settings {VER} only, so it isn't known to work on macOS 26 or any other version."
EN = "It depends on English names and was tested only in English."
UIM = {"name": "mode", "type": "str", "required": False, "default": "ui", "meaning": "Must be \"ui\": System Settings has no scripting for this."}
PRE = "The program has Accessibility, and Automation for System Events."
V = {"name": "ValueError", "when": "an argument is invalid or mode isn't \"ui\" or \"background\""}
U = {"name": "UIError", "when": "a named element never appeared or the result wasn't seen in time"}
NS = {"name": "NotSupported", "when": "mode is \"background\""}
SB = {"name": "StateBlocked", "when": "a System Settings dialog is already open, or another app came to the front; nothing more was done"}
CLICK = "Wallpaper buttons ignore the Accessibility press, so the wallpaper is clicked in the middle of its own named button's frame, only once that frame is wholly inside the visible list and window (scrolled there with the wheel over the list's own frame, its group opened with Show All); never fixed screen positions."
REMOTE = "Wallpapers not on this Mac (that System Settings would download from Apple, such as Ventura and most aerials on the tested Mac) are refused, not downloaded."
def cmd(name, desc, args, req, eff, post, ret, errs, gaps):
    return {"name": name, "description": desc, "args": args, "modes": {"verified": ["ui"], "default": "ui"}, "example_requests": req, "effects": eff,
            "destructive": False, "precondition": PRE, "postcondition": post, "returns": ret, "errors": errs, "known_gaps": gaps}
cmds = [
 cmd("wallpaper_list", "Lists every wallpaper in System Settings > Wallpaper, whether it's on this Mac, and which is current.", [UIM],
     ["What wallpapers can I choose?", "Which desktop pictures are built in?", "What's my current wallpaper?"], "read_only", "Nothing changes.",
     {"type": "list", "fields": ["name", "on_this_mac", "current"]}, [V, U, SB, NS], [M, EN, "Takes about 20 s: the list is scrolled through and each group opened with Show All."]),
 cmd("wallpaper_set", "Sets the desktop picture of every display and Space to a named wallpaper from System Settings > Wallpaper.",
     [{"name": "name", "type": "str", "required": True, "default": None, "meaning": "The wallpaper's name as the pane shows it, e.g. Sonoma or Plum."}, UIM],
     ["Set my wallpaper to Sonoma", "Change the desktop background to a plain blue color", "Use the iMac Blue wallpaper"], "idempotent", "The pane and macOS's wallpaper store show the wallpaper.",
     {"type": "object", "fields": ["wallpaper", "changed"]},
     [V, U, NS, {"name": "NotFound", "when": "no wallpaper has that name"}, {"name": "StateBlocked", "when": "the wallpaper isn't on this Mac (it would be downloaded), Show on all Spaces is off, a System Settings dialog is open, or another app came to the front; nothing was done"}],
     [M, EN, CLICK, REMOTE]),
 cmd("login_item_list", "Lists the items that open at login (General > Login Items & Extensions > Open at Login).", [UIM],
     ["What opens when I log in?", "List my login items", "Which apps start automatically?"], "read_only", "Nothing changes.",
     {"type": "list", "fields": ["name", "kind"]}, [V, U, SB, NS], [M, EN]),
 cmd("login_item_add", "Adds an app to Open at Login with the pane's Add button and its Open dialog.",
     [{"name": "app_path", "type": "str", "required": True, "default": None, "meaning": "Path of an existing .app."}, UIM],
     ["Open Calculator automatically when I log in", "Add Notes to my login items", "Make this app start at login"], "non_idempotent", "The app is listed in Open at Login.",
     {"type": "object", "fields": ["name", "kind", "path"]},
     [V, U, SB, NS, {"name": "NotFound", "when": "there's no app at app_path"}, {"name": "AlreadyExists", "when": "the app already opens at login; nothing is done"}], [M, EN, "The app's path is pasted into the Open dialog's Go to Folder; the clipboard is restored."]),
 cmd("login_item_remove", "Stops an item opening at login: its Open at Login row is selected and checked by name, then Remove (the app isn't touched).",
     [{"name": "name", "type": "str", "required": True, "default": None, "meaning": "The item's name as Open at Login shows it."}, UIM],
     ["Stop Calculator opening at login", "Remove Stickies from my login items", "Don't start this app when I log in"], "non_idempotent", "The item is gone from Open at Login; the app is unchanged.",
     {"type": "object", "fields": ["name", "removed"]},
     [V, U, SB, NS, {"name": "NotFound", "when": "nothing by that name opens at login"}, {"name": "Ambiguous", "when": "two login items share the name"}], [M, EN]),
 cmd("appearance_set", "Sets macOS's appearance to light, dark or auto with System Settings > Appearance's own named buttons.",
     [{"name": "mode_name", "type": "str", "required": True, "default": None, "meaning": "\"light\", \"dark\" or \"auto\"."}, UIM],
     ["Turn on dark mode", "Switch my Mac to light mode", "Make the appearance change automatically"], "idempotent", "The pane shows that appearance selected.",
     {"type": "object", "fields": ["appearance", "changed"]}, [V, U, SB, NS], [M, EN, "Added overnight in its own section and tested on its own."]),
 cmd("dock_set", "Changes the Dock's auto-hide, position and recent-apps settings in System Settings > Desktop & Dock; only the values given change.",
     [{"name": "autohide", "type": "bool | None", "required": False, "default": None, "meaning": "Automatically hide and show the Dock."},
      {"name": "position", "type": "str | None", "required": False, "default": None, "meaning": "\"left\", \"bottom\" or \"right\"."},
      {"name": "show_recents", "type": "bool | None", "required": False, "default": None, "meaning": "Show suggested and recent apps in Dock."}, UIM],
     ["Hide the Dock automatically", "Move the Dock to the left", "Stop showing recent apps in the Dock"], "idempotent", "The pane shows the Dock settings given.",
     {"type": "object", "fields": ["autohide", "position", "show_recents", "changed"]}, [V, U, SB, NS], [M, EN, "Added overnight in its own section and tested on its own."]),
]
json.dump({"app": "System Settings", "import": "import system_settings", "macos_version": "15.6.1 (24G90)", "app_version": VER, "commands": cmds}, open("../settings/catalog.json", "w"), indent=2, ensure_ascii=False); open("../settings/catalog.json", "a").write("\n"); print(len(cmds))
