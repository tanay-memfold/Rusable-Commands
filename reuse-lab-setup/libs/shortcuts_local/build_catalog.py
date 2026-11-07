"""Writes shortcuts/catalog.json. Local only."""
import json, sys
VER = sys.argv[1]
M = f"Verified on macOS 15.6.1 with Shortcuts {VER} only, so it isn't known to work on macOS 26 or any other version."
EN = "It depends on English names and was tested only in English."
BGM = {"name": "mode", "type": "str", "required": False, "default": "background", "meaning": "Must be \"background\": it uses Shortcuts Events, the app's own scripting."}
UIM = {"name": "mode", "type": "str", "required": False, "default": "ui", "meaning": "Must be \"ui\": Shortcuts Events accepts delete but nothing is deleted."}
PRE_BG = "The calling process has macOS's Automation permission for Shortcuts Events (a person allows it once; nothing here answers that prompt)."
PRE_UI = "The program has Accessibility, Automation for System Events, and Automation for Shortcuts Events."
V = {"name": "ValueError", "when": "an argument is invalid or mode isn't \"ui\" or \"background\""}
U = {"name": "UIError", "when": "a named element never appeared, a Shortcuts Events call failed, or the result wasn't seen in time"}
NF = {"name": "NotFound", "when": "no shortcut (or folder) has that name"}
AM = {"name": "Ambiguous", "when": "two shortcuts share the name; nothing was done"}
def ns(other): return {"name": "NotSupported", "when": f"mode is \"{other}\""}
def name_arg(meaning="The shortcut's exact name."): return {"name": "name", "type": "str", "required": True, "default": None, "meaning": meaning}
def cmd(name, desc, args, mode, req, eff, destructive, post, ret, errs, gaps):
    extra = {"confirm": "Delete the shortcut <name>? It can't be restored."} if destructive else {}
    return {**extra, "name": name, "description": desc, "args": args, "modes": {"verified": [mode], "default": mode}, "example_requests": req, "effects": eff,
            "destructive": destructive, "precondition": PRE_BG if mode == "background" else PRE_UI, "postcondition": post, "returns": ret, "errors": errs, "known_gaps": gaps}
cmds = [
 cmd("shortcut_list", "Lists every shortcut, at the top level and in folders, with its folder, action count and whether it accepts input.", [BGM], "background",
     ["What shortcuts do I have?", "List my shortcuts", "Which folder is my backup shortcut in?"], "read_only", False, "Nothing changes.",
     {"type": "list", "fields": ["name", "folder", "action_count", "accepts_input"]}, [V, U, ns("ui")], [M]),
 cmd("shortcut_run", "Runs a shortcut by name in the background through Shortcuts Events, optionally with text input, and returns its output as text.",
     [name_arg(), {"name": "input", "type": "str | None", "required": False, "default": None, "meaning": "Text passed as the shortcut's input."},
      {"name": "timeout", "type": "float", "required": False, "default": 60, "meaning": "Seconds to wait (1 to 600)."}, BGM], "background",
     ["Run my Morning Routine shortcut", "Run the shortcut called Backup Notes", "What does my Random Pick shortcut give me?"], "non_idempotent", False,
     "The shortcut ran once (whatever it does).", {"type": "object", "fields": ["name", "output"]},
     [V, U, NF, AM, ns("ui"), {"name": "PermissionNeeded", "when": "Shortcuts asks to allow the shortcut access (for example to save files), or such a question is already on screen; it's left for a person and nothing is answered"},
],
     [M, "A shortcut that reads or saves files makes Shortcuts ask once per shortcut; the call refuses at that question (PermissionNeeded) and never answers it.",
      "output is None unless the shortcut ends with Stop and Output (or another output); a non-text output is returned as AppleScript's text for it.",
      "Input to a shortcut that doesn't take input wasn't tested."]),
 cmd("folder_create", "Makes a new, empty shortcut folder through Shortcuts Events.", [name_arg("The new folder's name."), BGM], "background",
     ["Make a shortcuts folder called Work", "Create a folder for my backup shortcuts", "Add a new Shortcuts folder named Utilities"], "non_idempotent", False, "The folder is listed and empty.",
     {"type": "object", "fields": ["name"]}, [V, U, ns("ui"), {"name": "AlreadyExists", "when": "a folder by that name exists; nothing was done"}], [M]),
 cmd("shortcut_move", "Moves a shortcut into an existing folder through Shortcuts Events.",
     [name_arg(), {"name": "folder", "type": "str", "required": True, "default": None, "meaning": "An existing folder's name."}, BGM], "background",
     ["Move my Backup shortcut into the Work folder", "Put the Timer shortcut in Utilities", "File my Morning shortcut under Routines"], "idempotent", False, "The shortcut is in that folder.",
     {"type": "object", "fields": ["name", "folder", "moved"]}, [V, U, NF, AM, ns("ui")], [M, "There's no way back to the top level here."]),
 cmd("shortcut_delete", "Deletes a shortcut: the library is searched for its name, Edit > Select All and Edit > Delete, and Shortcuts' question is confirmed only once it names that shortcut.",
     [name_arg(), UIM], "ui",
     ["Delete my Old Timer shortcut", "Remove the shortcut called Test 2", "Get rid of my Draft Backup shortcut"], "non_idempotent", True, "The shortcut is gone from Shortcuts (it can't be restored from the trash).",
     {"type": "object", "fields": ["name", "deleted"]},
     [V, U, NF, ns("background"), {"name": "Ambiguous", "when": "two shortcuts share the name, or the library's search for it also shows other shortcuts (whose names contain it); nothing was deleted"},
      {"name": "StateBlocked", "when": "a Shortcuts sheet, file panel or privacy question is open, or another app came to the front; nothing was done"}],
     [M, EN, "Refused when another shortcut's name contains this one, since Delete acts on everything the search shows."]),
]
json.dump({"app": "Shortcuts", "import": "import shortcuts", "macos_version": "15.6.1 (24G90)", "app_version": VER, "commands": cmds}, open("../shortcuts/catalog.json", "w"), indent=2, ensure_ascii=False); open("../shortcuts/catalog.json", "a").write("\n"); print(len(cmds))
