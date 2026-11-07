"""Writes anaconda/catalog.json. Local only."""
import json
M = "Verified on macOS 15.6.1 with Anaconda Navigator 2.6.6 only, so it isn't known to work on macOS 26 or any other version."
EN = "It depends on English names and was tested only in English."
UIM = {"name": "mode", "type": "str", "required": False, "default": "ui", "meaning": "Must be \"ui\": Navigator has no scripting."}
V = {"name": "ValueError", "when": "an argument is invalid or mode isn't \"ui\" or \"background\""}
U = {"name": "UIError", "when": "a named element never appeared, Navigator's dialog didn't name the environment, or the result wasn't seen in time"}
S = {"name": "StateBlocked", "when": "a Navigator dialog holds typed text or can't be cancelled, or another app came to the front; nothing more was done"}
NS = {"name": "NotSupported", "when": "mode is \"background\""}
PRE = "The program has Accessibility, and Automation for System Events."
ROWS = "Navigator's environment rows have no names: the environment is searched for by name, its row pressed in the middle of the row's own frame, and the selection checked by name in Navigator's Remove dialog before anything happens."
OFFERS = "On launch, Navigator's offer to update itself gets No, remind me later and its offer to sign in for AI help is closed; nothing is updated or signed in."
def cmd(name, desc, args, req, eff, post, ret, errs, gaps):
    out = {"name": name, "description": desc, "args": args, "modes": {"verified": ["ui"], "default": "ui"}, "example_requests": req, "effects": eff, "destructive": name == "environment_remove", "precondition": PRE, "postcondition": post, "returns": ret, "errors": errs, "known_gaps": gaps}
    if name == "environment_remove":
        out["confirm"] = "Remove the conda environment <name> and everything installed in it?"
    return out
cmds = [
 cmd("environment_remove", "Removes a conda environment and everything in it, on Navigator's Environments page (the environment, Remove, Remove); Navigator's dialog must name it first.",
     [{"name": "name", "type": "str", "required": True, "default": None, "meaning": "The environment's name; not the root environment."}, UIM],
     ["Remove the data_analysis environment", "Delete my old conda env", "Get rid of the test environment"], "non_idempotent", "The environment's folder is gone.", {"type": "object", "fields": ["name", "path", "removed"]},
     [V, U, S, {"name": "NotFound", "when": "no environment has that name; nothing is done"}, NS], [M, EN, ROWS, OFFERS]),
]
json.dump({"app": "Anaconda Navigator", "import": "import anaconda", "macos_version": "15.6.1 (24G90)", "app_version": "2.6.6", "commands": cmds}, open("../anaconda/catalog.json", "w"), indent=2, ensure_ascii=False); open("../anaconda/catalog.json", "a").write("\n"); print(len(cmds))
