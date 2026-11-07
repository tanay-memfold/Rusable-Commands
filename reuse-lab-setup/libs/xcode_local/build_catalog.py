"""Writes xcode/catalog.json. Local only."""
import json
M = "Verified on macOS 15.6.1 with Xcode 16.4 only, so it isn't known to work on macOS 26 or any other version."
EN = "It depends on English names and was tested only in English."
ROOT = "Only touches what XCODE_ALLOWED_ROOT allows if it is set."
UIM = {"name": "mode", "type": "str", "required": False, "default": "ui", "meaning": "\"ui\" (on screen)."}
V = {"name": "ValueError", "when": "an argument is invalid or mode isn't \"ui\" or \"background\""}
U = {"name": "UIError", "when": "a named element never appeared, or the result wasn't seen in time"}
S = {"name": "StateBlocked", "when": "an Xcode sheet holds typed text or can't be cancelled, or another app came to the front; nothing more was done"}
NF = {"name": "NotFound", "when": "the folder, project or template doesn't exist; nothing is done"}
OUT = {"name": "OutsideAllowedRoot", "when": "XCODE_ALLOWED_ROOT is set and a path is outside it; nothing is done"}
NS = {"name": "NotSupported", "when": "the mode wasn't verified"}
PRE = "The program has Accessibility, and Automation for System Events ()."
def cmd(name, desc, args, modes, req, eff, post, ret, errs, gaps):
    return {"name": name, "description": desc, "args": args, "modes": modes, "example_requests": req, "effects": eff, "destructive": False, "precondition": PRE, "postcondition": post, "returns": ret, "errors": errs, "known_gaps": gaps}
cmds = [
 cmd("project_new", "Makes a new Xcode project from a template (File > New > Project…) in a folder; Xcode makes folder/name/name.xcodeproj and opens it.",
     [{"name": "name", "type": "str", "required": True, "default": None, "meaning": "The product name; also the new folder's name."},
      {"name": "folder", "type": "str", "required": True, "default": None, "meaning": "The existing folder to make it in, an absolute path or one starting with ~."},
      {"name": "platform", "type": "str", "required": False, "default": "iOS", "meaning": "\"iOS\" or \"macOS\"."},
      {"name": "template", "type": "str", "required": False, "default": "App", "meaning": "The template's name as Xcode shows it; only App was verified."},
      {"name": "organization", "type": "str", "required": False, "default": "com.example", "meaning": "The Organization Identifier, a reverse-DNS prefix."},
      {"name": "git", "type": "bool", "required": False, "default": False, "meaning": "Whether Xcode makes a Git repository; only False was verified."}, UIM],
     {"verified": ["ui"], "default": "ui"}, ["Create a new iOS app project called MyApp in Documents/XcodeProjects", "Start a macOS app in Xcode", "Make a SwiftUI project"],
     "non_idempotent", "The project folder holds name.xcodeproj and the template's sources; Xcode shows it.", {"type": "object", "fields": ["name", "path", "folder", "platform", "template"]},
     [V, U, S, NF, {"name": "AlreadyExists", "when": "folder/name exists; nothing is overwritten"}, OUT, NS],
     [M, ROOT, EN, "Interface, language, testing and storage keep Xcode's defaults (SwiftUI, Swift).", "No team is set, so the project isn't signed.", "Xcode also rewrites the window-state file (UserInterfaceState.xcuserstate) of projects already open in it."]),
 cmd("project_open", "Opens an .xcodeproj or .xcworkspace in Xcode.",
     [{"name": "path", "type": "str", "required": True, "default": None, "meaning": "The .xcodeproj or .xcworkspace, an absolute path or one starting with ~."}, UIM],
     {"verified": ["ui"], "default": "ui"}, ["Open MyApp in Xcode", "Open this Xcode project", "Show the workspace in Xcode"],
     "idempotent", "Xcode shows the project.", {"type": "object", "fields": ["name", "path"]}, [V, U, S, NF, OUT, NS],
     [M, ROOT, EN, "Whether it opened was read from Xcode's window, which isn't independent of Xcode.", "Opening through Xcode's own scripting brought Xcode to the front, so there is no background mode."]),
 cmd("project_build", "Builds a project with Product > Build for its current scheme and destination, opening it first if Xcode doesn't show it, and reports whether the build succeeded.",
     [{"name": "path", "type": "str", "required": True, "default": None, "meaning": "The .xcodeproj or .xcworkspace, an absolute path or one starting with ~."}, UIM],
     {"verified": ["ui"], "default": "ui"}, ["Build my Mac app in Xcode", "Compile this Xcode project", "Does the project build?"],
     "non_idempotent", "Xcode built the scheme; a successful build's app is in Xcode's DerivedData.", {"type": "object", "fields": ["name", "succeeded", "products"]},
     [V, U, S, NF, OUT, {"name": "NotSupported", "when": "the scheme needs platform support Xcode would download (it is declined with Cancel), or the mode wasn't verified"}],
     [M, ROOT, EN, "Only macOS App builds were verified; an iOS scheme needed iOS 18.5 support Xcode wanted to download, which is declined.", "A failed build returns succeeded false and no products; its errors are in Xcode's Issue navigator.", "It waits up to 10 minutes for the build."]),
 cmd("project_clean", "Deletes a project's build products and intermediate files with Product > Clean Build Folder…, pressing Clean only when Xcode's question names the project.",
     [{"name": "path", "type": "str", "required": True, "default": None, "meaning": "The .xcodeproj or .xcworkspace, an absolute path or one starting with ~."}, UIM],
     {"verified": ["ui"], "default": "ui"}, ["Clean the build folder of my Xcode project", "Clean MyApp before rebuilding", "Delete the build products"],
     "idempotent", "The project's build folder in DerivedData holds nothing but Xcode's own build database; its source files are unchanged.", {"type": "object", "fields": ["name", "cleaned"]},
     [V, U, S, NF, OUT, NS], [M, ROOT, EN, "It deletes only what Xcode's Clean Build Folder deletes (build products and intermediates, which a build makes again).", "Added overnight in its own section and tested on its own."]),
]
json.dump({"app": "Xcode", "import": "import xcode", "macos_version": "15.6.1 (24G90)", "app_version": "16.4 (23792)", "commands": cmds}, open("../xcode/catalog.json", "w"), indent=2, ensure_ascii=False); open("../xcode/catalog.json", "a").write("\n"); print(len(cmds))
