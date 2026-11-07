"""Writes vscode/catalog.json. Local only."""
import json
M = "Verified on macOS 15.6.1 with VS Code 1.105.1 only, so it isn't known to work on macOS 26 or any other version."
EN = "It depends on English names and was tested only in English."
ROOT = "Only touches what VSCODE_ALLOWED_ROOT allows if it is set."
UIM = {"name": "mode", "type": "str", "required": False, "default": "ui", "meaning": "Must be \"ui\": VS Code's command-line tool is a shell command, so it isn't offered as a mode."}
V = {"name": "ValueError", "when": "an argument is invalid or mode isn't \"ui\" or \"background\""}
U = {"name": "UIError", "when": "a named element never appeared, or the change wasn't seen in time"}
S = {"name": "StateBlocked", "when": "another app came to the front; nothing more was done"}
NF = {"name": "NotFound", "when": "nothing is at the path; nothing is done"}
OUT = {"name": "OutsideAllowedRoot", "when": "VSCODE_ALLOWED_ROOT is set and a path is outside it; nothing is done"}
NS = {"name": "NotSupported", "when": "mode is \"background\""}
PRE = "The program has Accessibility, and Automation for System Events."
SR = "VS Code is asked to show its window to Accessibility, which turns on its Screen Reader Optimized mode while it runs."
TRUST = "VS Code's \"Do you trust the authors of the files in this folder?\" is answered No, so the folder opens in Restricted Mode."
def cmd(name, desc, args, req, eff, post, ret, errs, gaps):
    return {"name": name, "description": desc, "args": args, "modes": {"verified": ["ui"], "default": "ui"}, "example_requests": req, "effects": eff, "destructive": False, "precondition": PRE, "postcondition": post, "returns": ret, "errors": errs, "known_gaps": gaps}
P = lambda m: {"name": "path", "type": "str", "required": True, "default": None, "meaning": m}
cmds = [
 cmd("folder_open", "Opens a folder in VS Code with File > Open Folder….", [P("The folder, an absolute path or one starting with ~."), UIM], ["Open my project folder in VS Code", "Open the src folder", "Show this folder in VS Code"], "idempotent", "VS Code's window shows the folder; nothing on disk changes.", {"type": "object", "fields": ["name", "path", "window"]}, [V, U, S, NF, OUT, NS], [M, ROOT, EN, SR, TRUST, "Whether it opened was read from the window title, which isn't independent of VS Code."]),
 cmd("file_open", "Opens a file in VS Code with File > Open….", [P("The file, an absolute path or one starting with ~."), UIM], ["Open main.js in VS Code", "Edit this file in VS Code", "Show the README in VS Code"], "idempotent", "The file is open in VS Code; nothing on disk changes.", {"type": "object", "fields": ["name", "path", "window"]}, [V, U, S, NF, OUT, NS], [M, ROOT, EN, SR, TRUST, "Whether it opened was read from the window title, which isn't independent of VS Code."]),
 cmd("file_new", "Makes a new file with text at a path that doesn't exist (File > New Text File, then Save As…); it stays open.", [P("A new file's path, an absolute path or one starting with ~; its folder must exist."), {"name": "text", "type": "str", "required": False, "default": "", "meaning": "The file's text."}, UIM], ["Create a new JavaScript file called app.js", "Make a notes.md with this text", "Start a new file in the project"], "non_idempotent", "The file holds exactly the text.", {"type": "object", "fields": ["name", "path"]}, [V, U, S, NF, {"name": "AlreadyExists", "when": "the path is taken; nothing is overwritten"}, OUT, NS], [M, ROOT, EN, "The text is pasted through the clipboard, which is restored afterwards; VS Code's own formatting on paste was off.", "Whether the pasted text landed is judged from the window title only; if the paste is lost (say, a VS Code dialog takes it), the new file is saved empty and UIError is raised, leaving that empty file."]),
 cmd("extension_install", "Installs an extension from the Marketplace by its id in VS Code's Extensions view; the first extension from a publisher gets VS Code's own Trust Publisher & Install.",
     [{"name": "ext_id", "type": "str", "required": True, "default": None, "meaning": "The extension's id, publisher.name, such as esbenp.prettier-vscode."}, UIM],
     ["Install the Prettier extension", "Add ESLint to VS Code", "Get the YAML extension"], "non_idempotent", "The extension is installed for this user.", {"type": "object", "fields": ["id", "installed"]},
     [V, U, S, {"name": "AlreadyExists", "when": "the extension is already installed; nothing is changed"}, NS],
     [M, EN, SR, "It needs the internet; it downloads from Microsoft's Marketplace.", "Install is pressed only on the search result for exactly this id; if VS Code installs anything else too, the result lists it under also_installed.", "VS Code's Trust Publisher & Install is pressed for a new publisher; a workspace-trust question gets plain Install, which doesn't trust the workspace.", "Added on day 4 in its own section and tested on its own."]),
]
json.dump({"app": "VS Code", "import": "import vscode", "macos_version": "15.6.1 (24G90)", "app_version": "1.105.1 (1.105.1)", "commands": cmds}, open("../vscode/catalog.json", "w"), indent=2, ensure_ascii=False); open("../vscode/catalog.json", "a").write("\n"); print(len(cmds))
