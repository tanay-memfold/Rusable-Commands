"""Writes reminders/catalog.json. Local only."""
import json
MACOS = "Verified on macOS 15.6.1 only, so it isn't known to work on macOS 26 or any other version."
LOCAL = "Only the local account was tested, with no iCloud or other account signed in to Reminders."
ENGLISH = "UI mode depends on English names and was tested only in English."
def mode(d, modes): return {"name": "mode", "type": "str", "required": False, "default": d, "meaning": ("Must be \"background\": this command has no verified ui mode." if modes == ["background"] else "\"ui\" or \"background\"; use one of this command's modes.")}
MATCH = {"name": "match", "type": "str", "required": True, "default": None, "meaning": "The reminder's exact title."}
LIST = {"name": "list", "type": "str | None", "required": False, "default": None, "meaning": "Only look in the list with this name."}
FIELDS = {"name": "fields", "type": "str | list | None", "required": False, "default": None, "meaning": "Fields to return, as a comma-separated string or a list; adds id and completed_date if asked."}
DUE = {"name": "due", "type": "str | None", "required": False, "default": None, "meaning": "\"YYYY-MM-DD HH:MM\" in local time or \"YYYY-MM-DD\"; needs background mode, and 00:00 is refused."}
NOTES = {"name": "notes", "type": "str | None", "required": False, "default": None, "meaning": "The reminder's notes."}
PRI = {"name": "priority", "type": "str | None", "required": False, "default": None, "meaning": "\"high\", \"medium\" or \"low\"; needs background mode."}
V = {"name": "ValueError", "when": "an argument is invalid or mode isn't \"ui\" or \"background\""}
U = {"name": "UIError", "when": "a named element never appeared, or the change wasn't seen in time"}
S = {"name": "StateBlocked", "when": "the screen holds typed text or another app came to the front; nothing is changed"}
NF = {"name": "NotFound", "when": "no reminder has that title, or no list has that name; nothing is changed"}
AM = {"name": "Ambiguous", "when": "more than one matches; nothing is changed"}
AE = {"name": "AlreadyExists", "when": "a list with that name already exists; nothing is changed"}
NS = {"name": "NotSupported", "when": "the mode can't do this, including due or priority in ui mode"}
NSB = {"name": "NotSupported", "when": "mode is \"ui\": this command only reads, and has no verified ui mode"}
PRE_B = "Reminders' local account is available, and the program has Automation permission for Reminders."
PRE_U = "For ui mode, the program also has Accessibility, and Automation for System Events."
ROW = ["title", "notes", "list", "due", "priority", "completed"]
ID = ["id"] + ROW
READ = {"type": "list", "fields": ROW, "optional_fields": ["id", "completed_date"]}
def cmd(name, desc, args, modes, default, req, eff, pre, post, ret, errs, gaps, confirm=None):
    c = {"name": name, "description": desc, "args": args, "modes": {"verified": modes, "default": default}, "example_requests": req, "effects": eff, "destructive": confirm is not None, "precondition": pre, "postcondition": post, "returns": ret, "errors": errs}
    if confirm: c["confirm"] = confirm
    c["known_gaps"] = gaps
    return c
BOTH, BG = ["ui", "background"], ["background"]
M, Lo = MACOS, LOCAL
cmds = [
 cmd("reminder_create", "Adds a reminder to a list, or the default list.", [{"name": "title", "type": "str", "required": True, "default": None, "meaning": "One non-empty line."}, LIST | {"meaning": "The list to add it to; the default list if not given."}, DUE, NOTES, PRI, mode("ui", BOTH)], BOTH, "ui",
     ["Remind me to call the dentist", "Add milk to my Shopping list", "Add a reminder to pay rent on 1 December at 9am"], "non_idempotent", PRE_B + " " + PRE_U, "One new reminder exists with these values.", {"type": "object", "fields": ID}, [V, U, S, NF, NS],
     [M, Lo, "Due dates and priority can't be set in ui mode because the date field exposes no parts to Accessibility, so use background mode.", "A due time of 00:00 is refused because it can't be told apart from a day without a time.", ENGLISH]),
 cmd("reminder_list", "Lists reminders in a list or in every list, newest first.", [LIST, {"name": "completed", "type": "bool | None", "required": False, "default": False, "meaning": "False for open ones, True for done ones, None for both."}, {"name": "limit", "type": "int", "required": False, "default": 100, "meaning": "The most reminders to return."}, FIELDS, mode("background", BG)], BG, "background",
     ["What's on my Shopping list?", "Show my reminders", "What have I completed in Work?"], "read_only", PRE_B, "Nothing is changed.", READ, [V, U, NF, NSB], [M, Lo]),
 cmd("reminder_search", "Finds reminders whose title or notes contain some text, ignoring case.", [{"name": "query", "type": "str", "required": True, "default": None, "meaning": "The text to look for."}, FIELDS, {"name": "completed", "type": "bool | None", "required": False, "default": None, "meaning": "False for open ones, True for done ones, None for both."}, mode("background", BG)], BG, "background",
     ["Do I have a reminder about the dentist?", "Find reminders mentioning rent", "Search my reminders for passport"], "read_only", PRE_B, "Nothing is changed.", READ, [V, U, NSB], [M, Lo]),
 cmd("reminder_get", "Returns the one reminder with this exact title.", [MATCH, LIST, FIELDS, mode("background", BG)], BG, "background",
     ["When is the dentist reminder due?", "Show me the rent reminder", "What are the notes on my passport reminder?"], "read_only", PRE_B, "Nothing is changed.", READ | {"type": "object"}, [V, U, NF, AM, NSB], [M, Lo, "A completed and an open reminder with the same title are Ambiguous."]),
 cmd("reminder_update", "Changes a reminder's title, notes, due date or priority, and only the values given.", [MATCH, LIST, {"name": "title", "type": "str | None", "required": False, "default": None, "meaning": "The new title, one non-empty line."}, DUE, NOTES, PRI, mode("background", BOTH)], BOTH, "background",
     ["Move the dentist reminder to Friday", "Rename the rent reminder", "Make the passport reminder high priority"], "idempotent", PRE_B + " " + PRE_U, "The reminder has the new values and the rest are unchanged.", {"type": "object", "fields": ID}, [V, U, S, NF, AM, NS],
     [M, Lo, "UI mode changes title and notes only, because due dates and priority can't be set on screen safely.", "A due date can't be cleared.", ENGLISH]),
 cmd("reminder_complete", "Marks a reminder as completed.", [MATCH, LIST, mode("ui", BOTH)], BOTH, "ui",
     ["I've done the dentist reminder", "Tick off the milk", "Complete the rent reminder"], "idempotent", PRE_B + " " + PRE_U, "The reminder is completed.", {"type": "object", "fields": ID}, [V, U, S, NF, AM],
     [M, Lo, "There is no command to mark a completed reminder as not done.", ENGLISH]),
 cmd("reminder_delete", "Deletes a reminder.", [MATCH, LIST, mode("ui", BOTH)], BOTH, "ui",
     ["Delete the dentist reminder", "Remove the milk reminder", "Get rid of the rent reminder"], "non_idempotent", PRE_B + " " + PRE_U, "The reminder is gone.", {"type": "object", "fields": ID + ["deleted"]}, [V, U, S, NF, AM],
     [M, Lo, ENGLISH], "Delete the reminder <match>?"),
 cmd("list_create", "Makes a new list in the local account.", [{"name": "name", "type": "str", "required": True, "default": None, "meaning": "One non-empty line, not already taken."}, mode("ui", BOTH)], BOTH, "ui",
     ["Make a list called Trip", "Create a Shopping list", "Add a new reminders list for work"], "non_idempotent", PRE_B + " " + PRE_U, "The list exists and is empty.", {"type": "object", "fields": ["name", "open"]}, [V, U, S, AE],
     [M, Lo, "A list's colour and icon can't be chosen.", ENGLISH]),
 cmd("list_list", "Lists the local lists with how many open reminders each has.", [mode("background", BG)], BG, "background",
     ["What reminder lists do I have?", "List my lists", "How many reminders are in each list?"], "read_only", PRE_B, "Nothing is changed.", {"type": "list", "fields": ["name", "open"]}, [V, U, NSB], [M, Lo, "Smart lists aren't included."]),
 cmd("list_rename", "Renames a list, and its reminders stay in it.", [{"name": "name", "type": "str", "required": True, "default": None, "meaning": "The list's exact name."}, {"name": "to", "type": "str", "required": True, "default": None, "meaning": "The new name, one non-empty line, not already taken."}, mode("ui", BOTH)], BOTH, "ui",
     ["Rename my Trip list to Goa", "Change the Work list's name to Office", "Call the Shopping list Groceries"], "non_idempotent", PRE_B + " " + PRE_U, "The list has the new name and the same reminders.", {"type": "object", "fields": ["name", "open"]}, [V, U, S, NF, AM, AE],
     [M, Lo, ENGLISH]),
 cmd("reminder_move", "Moves a reminder to another list, keeping its title, notes, due date and priority.", [MATCH, {"name": "to_list", "type": "str", "required": True, "default": None, "meaning": "The exact name of the list to move it to."}, LIST, mode("background", ["background"])], ["background"], "background", ["Move the milk reminder to Shopping", "Put this task in my Work list", "Move 'Call dentist' to Personal"], "idempotent", "The program has access to Reminders and Automation permission for Reminders.", "The reminder is in to_list and no longer in its old list.", {"type": "object", "fields": ID}, [V, U, NF, AM, {"name": "NotSupported", "when": "mode is \"ui\": moving on screen means dragging, and these commands use no screen positions"}], [MACOS, LOCAL, "In one of two full runs, Reminders came to the front once when this started it from closed; the rerun passed."]),
 cmd("reminder_reopen", "Marks a completed reminder as not completed again.", [MATCH, LIST, mode("background", ["background"])], ["background"], "background", ["Reopen the dentist reminder", "Mark 'Buy milk' as not done", "Undo completing this task"], "idempotent", "The program has access to Reminders and Automation permission for Reminders.", "The reminder is not completed; nothing else on it changed.", {"type": "object", "fields": ID}, [V, U, NF, AM, {"name": "ValueError", "when": "the reminder isn't completed; nothing is changed"}, {"name": "NotSupported", "when": "mode is \"ui\": this command has no verified ui mode"}], [MACOS, LOCAL, "Flagging isn't supported: Reminders' scripting ignores writes to flagged."]),
 cmd("list_delete", "Deletes a list and every reminder in it.", [{"name": "name", "type": "str", "required": True, "default": None, "meaning": "The list's exact name."}, mode("ui", BOTH)], BOTH, "ui",
     ["Delete my Trip list", "Remove the Shopping list", "Get rid of the old Work list"], "non_idempotent", PRE_B + " " + PRE_U, "The list and its reminders are gone.", {"type": "object", "fields": ["name", "open", "deleted"]}, [V, U, S, NF, AM],
     [M, Lo, ENGLISH], "Delete the list <name> and all its reminders?"),
]
json.dump({"app": "Reminders", "import": "import reminders", "macos_version": "15.6.1 (24G90)", "app_version": "7.0 (3740)", "commands": cmds}, open("../reminders/catalog.json", "w"), indent=2, ensure_ascii=False)
open("../reminders/catalog.json", "a").write("\n"); print(len(cmds))
