"""Writes obs/catalog.json. Local only."""
import json
M = "Verified on macOS 15.6.1 with OBS Studio 32.0.1 only, so it isn't known to work on macOS 26 or any other version."
EN = "It depends on English names and was tested only in English."
UIM = {"name": "mode", "type": "str", "required": False, "default": "ui", "meaning": "Must be \"ui\": OBS has no scripting for this."}
V = {"name": "ValueError", "when": "an argument is invalid or mode isn't \"ui\" or \"background\""}
U = {"name": "UIError", "when": "a named element never appeared, or the result wasn't seen in time"}
NS = {"name": "NotSupported", "when": "mode is \"background\""}
PRE = "The program has Accessibility, and Automation for System Events."
FIRST = "On OBS's first launch its question about checking for updates is answered Don't Check, and after OBS quit unexpectedly its Safe Mode question is answered Run in Normal Mode."
def cmd(name, desc, args, req, eff, post, ret, errs, gaps):
    return {"name": name, "description": desc, "args": args, "modes": {"verified": ["ui"], "default": "ui"}, "example_requests": req, "effects": eff, "destructive": False, "precondition": PRE, "postcondition": post, "returns": ret, "errors": errs, "known_gaps": gaps}
cmds = [
 cmd("scene_add", "Adds a scene with this name to OBS's current scene collection (Scenes › Add, the name, OK).",
     [{"name": "name", "type": "str", "required": True, "default": None, "meaning": "The new scene's name."}, UIM],
     ["Add a scene called Intro in OBS", "Make a new OBS scene for the interview", "Create a Gameplay scene"], "non_idempotent",
     "OBS's scene collection has the scene.", {"type": "object", "fields": ["name", "scenes"]},
     [V, U, {"name": "AlreadyExists", "when": "a scene with that name exists; nothing is done"}, {"name": "StateBlocked", "when": "an OBS dialog is open, or another app came to the front; nothing more was done"}, NS],
     [M, EN, FIRST, "It doesn't add sources to the scene."]),
 cmd("recording_start", "Starts recording with OBS's current scene and output settings (Controls › Start Recording).",
     [{"name": "allow_blank", "type": "bool", "required": False, "default": False, "meaning": "If the scene has no video source OBS warns it will record a blank screen: True answers Yes, False answers No and raises StateBlocked."}, UIM],
     ["Start recording in OBS", "Record a video with OBS", "Begin an OBS recording"], "non_idempotent",
     "OBS is recording into its recordings folder (by default ~/Movies).", {"type": "object", "fields": ["recording", "folder"]},
     [V, U, {"name": "StateBlocked", "when": "OBS is already recording, the scene has no video source and allow_blank is False, an OBS dialog is open, or another app came to the front"}, NS],
     [M, EN, FIRST, "Capturing the screen, a window, a game or a camera needs macOS permissions that these commands never ask for, so add such sources yourself; testing recorded the empty scene with Mic/Aux.", "On a Mac with a microphone, OBS's default Mic/Aux source may make macOS ask for Microphone access; the test VM has none, so that prompt wasn't seen, and these commands don't answer it."]),
 cmd("recording_stop", "Stops OBS's recording (Controls › Stop Recording) and returns the file it wrote.",
     [UIM], ["Stop the OBS recording", "End recording and tell me where the video is", "Stop recording"], "non_idempotent",
     "The recording file is complete in OBS's recordings folder.", {"type": "object", "fields": ["path", "bytes"]},
     [V, U, {"name": "StateBlocked", "when": "OBS isn't running or isn't recording; nothing is done"}, NS],
     [M, EN, "The file is found as the newest video in OBS's recordings folder (from its profile settings) written in the last 15 seconds."]),
 cmd("source_add", "Adds a new color or text source to OBS's current scene (Sources › Add, the kind, Create new with the name, OK, its properties, OK).",
     [{"name": "name", "type": "str", "required": True, "default": None, "meaning": "The new source's name; no other source or scene may have it."},
      {"name": "kind", "type": "str", "required": True, "default": None, "meaning": "\"color\" (OBS's default color, 1920×1080) or \"text\"."},
      {"name": "text", "type": "str", "required": False, "default": None, "meaning": "The text to show; required for kind=\"text\", not allowed otherwise."}, UIM],
     ["Add a text overlay saying Live in 5", "Put a color background in the OBS scene", "Add a caption source to OBS"], "non_idempotent",
     "The current scene has the source, saved in OBS's scene collection.", {"type": "object", "fields": ["name", "kind", "scene"]},
     [V, U, {"name": "AlreadyExists", "when": "a source or scene with that name exists; nothing is done"}, {"name": "StateBlocked", "when": "an OBS source dialog or properties window is open, or another app came to the front; nothing more was done"}, NS],
     [M, EN, FIRST, "Text uses OBS's default font, color and size; a color source keeps OBS's default color.", "Image, media, capture and camera sources aren't offered: OBS didn't take an image path typed through Accessibility, and capture needs macOS permissions."]),
]
json.dump({"app": "OBS Studio", "import": "import obs", "macos_version": "15.6.1 (24G90)", "app_version": "32.0.1", "commands": cmds}, open("../obs/catalog.json", "w"), indent=2, ensure_ascii=False); open("../obs/catalog.json", "a").write("\n"); print(len(cmds))
