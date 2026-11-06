"""OBS Studio commands for agents: plain functions with keyword arguments, to add scenes and record.

mode="ui" works on screen: elements are found by role and name through the macOS Accessibility API and pressed. No screen coordinates.
OBS's first-launch offer to check for updates is answered Don't Check. Nothing here adds a screen, window, camera or audio capture,
so nothing asks macOS for a permission.

Errors: AlreadyExists, StateBlocked (OBS isn't in a state the call can act on, or another app came to the front), UIError (an element
never appeared, or the result wasn't seen in time), NotSupported (the mode can't do it or wasn't verified)."""
from __future__ import annotations

import configparser
import ctypes
import json
import os
import plistlib
import subprocess
import time
import warnings

APP = "OBS"
BUNDLE_ID = "com.obsproject.obs-studio"
APP_PLIST = "/Applications/OBS.app/Contents/Info.plist"
CONFIG = os.path.expanduser("~/Library/Application Support/obs-studio")
TIMEOUT = 10
START_TIMEOUT = 60
VIDEO = (".mov", ".mkv", ".mp4", ".flv", ".ts", ".m3u8", ".fragmented.mov", ".fragmented.mp4")
BLANK = "haven't added any video sources"

VERIFIED: dict = {
    "recording_start": {
        "ui": {
            "macos": "15.6.1 (24G90)",
            "app": "32.0.1"
        }
    },
    "recording_stop": {
        "ui": {
            "macos": "15.6.1 (24G90)",
            "app": "32.0.1"
        }
    },
    "scene_add": {
        "ui": {
            "macos": "15.6.1 (24G90)",
            "app": "32.0.1"
        }
    },
    "source_add": {
        "ui": {
            "macos": "15.6.1 (24G90)",
            "app": "32.0.1"
        }
    }
}
UNSUPPORTED: dict = {}


class OBSError(Exception):
    pass


class AlreadyExists(OBSError):
    pass


class StateBlocked(OBSError):
    pass


class UIError(OBSError):
    pass


class NotSupported(OBSError):
    pass


def _run(args: list) -> str:
    done = subprocess.run(args, capture_output=True, text=True)
    if done.returncode:
        raise UIError(done.stderr.strip())
    return done.stdout.strip()


def _versions() -> dict:
    macos = f"{_run(['sw_vers', '-productVersion'])} ({_run(['sw_vers', '-buildVersion'])})"
    with open(APP_PLIST, "rb") as handle:
        info = plistlib.load(handle)
    return {"macos": macos, "app": info["CFBundleShortVersionString"]}


def _checked(function: str, mode: str, result):
    verified = VERIFIED.get(function, {}).get(mode)
    if verified is None:
        return result
    now = _versions()
    if now == verified:
        return result
    warnings.warn(f"{function} ({mode}) was verified on {verified}, running on {now}")
    return {**result, "unverified_version": True, "verified_on": verified, "running_on": now}


def _mode(function: str, mode: str, supported: tuple = ("ui",)) -> None:
    if mode not in ("ui", "background"):
        raise ValueError(f"mode must be 'ui' or 'background', not {mode!r}")
    if mode not in supported or (VERIFIED and mode not in VERIFIED.get(function, {})):
        raise NotSupported(f"{function} has no verified {mode} mode: {UNSUPPORTED.get((function, mode), 'it did not pass verification')}")


def _wait_for(what: str, test, timeout: float = TIMEOUT, every: float = 0.3):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            value = test()
        except UIError:
            value = None
        if value:
            return value
        time.sleep(every)
    raise UIError(f"{what} did not happen within {timeout}s")


_AS = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices")
_CF = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
_P = ctypes.c_void_p
for _f, _res, _args in [(_AS.AXUIElementCreateApplication, _P, [ctypes.c_int]),
                        (_AS.AXUIElementCopyAttributeValue, ctypes.c_int, [_P, _P, ctypes.POINTER(_P)]),
                        (_AS.AXUIElementSetAttributeValue, ctypes.c_int, [_P, _P, _P]),
                        (_AS.AXUIElementPerformAction, ctypes.c_int, [_P, _P]),
                        (_CF.CFStringCreateWithCString, _P, [_P, ctypes.c_char_p, ctypes.c_uint32]),
                        (_CF.CFStringGetLength, ctypes.c_long, [_P]),
                        (_CF.CFStringGetMaximumSizeForEncoding, ctypes.c_long, [ctypes.c_long, ctypes.c_uint32]),
                        (_CF.CFStringGetCString, ctypes.c_bool, [_P, ctypes.c_char_p, ctypes.c_long, ctypes.c_uint32]),
                        (_CF.CFGetTypeID, ctypes.c_ulong, [_P]), (_CF.CFStringGetTypeID, ctypes.c_ulong, []),
                        (_CF.CFArrayGetTypeID, ctypes.c_ulong, []), (_CF.CFArrayGetCount, ctypes.c_long, [_P]),
                        (_CF.CFArrayGetValueAtIndex, _P, [_P, ctypes.c_long])]:
    _f.restype, _f.argtypes = _res, _args
_UTF8 = 0x08000100
_TRUE = _P.in_dll(_CF, "kCFBooleanTrue")
_FALSE = _P.in_dll(_CF, "kCFBooleanFalse")
_names: dict = {}


def _cf(text: str):
    if text not in _names:
        _names[text] = _CF.CFStringCreateWithCString(None, text.encode(), _UTF8)
    return _names[text]


def _attr(element, name: str):
    out = _P()
    return out.value if _AS.AXUIElementCopyAttributeValue(element, _cf(name), ctypes.byref(out)) == 0 else None


def _string(element, name: str) -> str:
    value = _attr(element, name)
    if not value or _CF.CFGetTypeID(value) != _CF.CFStringGetTypeID():
        return ""
    size = _CF.CFStringGetMaximumSizeForEncoding(_CF.CFStringGetLength(value), _UTF8) + 1
    buffer = ctypes.create_string_buffer(size)
    return buffer.value.decode() if _CF.CFStringGetCString(value, buffer, size, _UTF8) else ""


def _children(element) -> list:
    value = _attr(element, "AXChildren")
    if not value or _CF.CFGetTypeID(value) != _CF.CFArrayGetTypeID():
        return []
    return [_CF.CFArrayGetValueAtIndex(value, i) for i in range(_CF.CFArrayGetCount(value))]


def _walk(root):
    stack = [root]
    while stack:
        element = stack.pop()
        yield element
        stack.extend(reversed(_children(element)))


def _role(element) -> str:
    return _string(element, "AXRole")


def _find(root, role: str, name: str):
    """The first element of this role whose title or description is exactly name."""
    for element in _walk(root):
        if _role(element) == role and name in (_string(element, "AXTitle"), _string(element, "AXDescription")):
            return element
    return None


def _press(element) -> None:
    if _AS.AXUIElementPerformAction(element, _cf("AXPress")):
        raise UIError("an element couldn't be pressed")


def _focus(element) -> None:
    _AS.AXUIElementSetAttributeValue(element, _cf("AXFocused"), _TRUE)






def _running() -> bool:
    return subprocess.run(["pgrep", "-x", APP], capture_output=True).returncode == 0


def _app():
    found = subprocess.run(["pgrep", "-x", APP], capture_output=True, text=True).stdout.split()
    if not found:
        raise UIError("OBS isn't running")
    return _AS.AXUIElementCreateApplication(int(found[0]))


def _windows() -> list:
    return [e for e in _children(_app()) if _role(e) == "AXWindow"]


def _main():
    return next((w for w in _windows() if _string(w, "AXTitle").startswith("OBS ")), None)


def _everything() -> list:
    return [e for w in _windows() for e in _walk(w)]


def _button(title: str = None, description: str = None):
    return next((e for e in _everything() if _role(e) == "AXButton" and (title is None or _string(e, "AXTitle") == title)
                 and (description is None or _string(e, "AXDescription") == description)), None)


def _text_shown(part: str) -> bool:
    return any(part in (_string(e, "AXValue") or _string(e, "AXTitle")) for e in _everything() if _role(e) == "AXStaticText")


def _system_events(body: str) -> str:
    return _run(["osascript", "-e", f'tell application "System Events" to tell process "{APP}"\n{body}\nend tell'])


def _front() -> bool:
    return _system_events("return frontmost") == "true"


def _forward() -> None:
    _system_events("set visible to true\nset frontmost to true")
    _wait_for("OBS in front", _front)


def _press(element) -> None:
    # A button that opens one of OBS's modal dialogs answers "cannot complete" (-25204) once the dialog is up; callers check the outcome.
    if element is None:
        raise UIError("a named element wasn't found")
    if _AS.AXUIElementPerformAction(element, _cf("AXPress")) not in (0, -25204):
        raise UIError("an element couldn't be pressed")


def _input_dialog(prompt: str):
    """OBS's name dialog: its prompt, field, OK and Cancel show up in the main window's tree."""
    if not _text_shown(prompt):
        return None
    field = next((e for e in _everything() if _role(e) == "AXTextField"), None)
    return field if field is not None and _button("OK") is not None else None


def _start() -> None:
    if not _running():
        _run(["open", "-b", BUNDLE_ID])

        def started():
            if not _running():
                return False
            # After OBS quit unexpectedly it asks whether to run in Safe Mode; it is started as usual (Run in Normal Mode).
            normal = _button("Run in Normal Mode")
            if normal is not None:
                _press(normal)
                return False
            return _main() is not None
        _wait_for("OBS to start", started, START_TIMEOUT, 0.5)
        time.sleep(2)
    _forward()
    # First launch asks whether to check for updates: Don't Check.
    later = _button("Don’t Check")
    if later is not None:
        _press(later)
        _wait_for("the update question to close", lambda: _button("Don’t Check") is None)
    if _text_shown("Please enter the name") or _text_shown(BLANK):
        raise StateBlocked("an OBS dialog is open; nothing was done")


def _scenes() -> list:
    collection = _collection()
    with open(collection, encoding="utf-8") as handle:
        return [s["name"] for s in json.load(handle).get("sources", []) if s.get("id") == "scene"]


def _collection() -> str:
    """The scene collection file OBS is using, from its own settings."""
    config = configparser.ConfigParser(strict=False, interpolation=None)
    config.read(os.path.join(CONFIG, "user.ini"), encoding="utf-8")
    config.read(os.path.join(CONFIG, "global.ini"), encoding="utf-8")
    name = config.get("Basic", "SceneCollectionFile", fallback="Untitled.json")
    return os.path.join(CONFIG, "basic", "scenes", name if name.endswith(".json") else name + ".json")


def _recordings_folder() -> str:
    config = configparser.ConfigParser(strict=False, interpolation=None)
    config.read(os.path.join(CONFIG, "user.ini"), encoding="utf-8")
    config.read(os.path.join(CONFIG, "global.ini"), encoding="utf-8")
    profile = config.get("Basic", "ProfileDir", fallback="Untitled")
    basic = configparser.ConfigParser(strict=False, interpolation=None)
    basic.read(os.path.join(CONFIG, "basic", "profiles", profile, "basic.ini"), encoding="utf-8")
    mode = basic.get("Output", "Mode", fallback="Simple")
    key = ("SimpleOutput", "FilePath") if mode == "Simple" else ("AdvOut", "RecFilePath")
    return os.path.expanduser(basic.get(*key, fallback="~/Movies"))


def _recording() -> bool:
    return _button("Stop Recording") is not None


# Commands ---------------------------------------------------------------------------------------------------------


def scene_add(name: str, mode: str = "ui") -> dict:
    """Add a scene (the Scenes dock's Add, then the name, OK)."""
    _mode("scene_add", mode)
    if not isinstance(name, str) or not name.strip():
        raise ValueError("name must not be empty")
    if name in _scenes():
        raise AlreadyExists(f"a scene named {name} already exists; nothing was done")
    _start()
    _press(_button(description="Add Scene"))
    field = _wait_for("the scene name dialog", lambda: _input_dialog("Please enter the name of the scene"))
    try:
        _AS.AXUIElementSetAttributeValue(field, _cf("AXFocused"), _TRUE)
        _AS.AXUIElementSetAttributeValue(field, _cf("AXValue"), _cf(name))
        _wait_for("the name to be typed", lambda: _string(field, "AXValue") == name)
        _press(_button("OK"))
    except Exception:
        cancel = _button("Cancel")
        if cancel is not None:
            _press(cancel)
        raise
    _wait_for(f"the scene {name} to be saved", lambda: name in _scenes(), TIMEOUT * 2)
    return _checked("scene_add", mode, {"name": name, "scenes": _scenes()})


def recording_start(allow_blank: bool = False, mode: str = "ui") -> dict:
    """Start recording (Controls › Start Recording). With no video source in the scene OBS warns it will record a blank screen:
    allow_blank=True answers Yes; otherwise No is pressed and StateBlocked is raised."""
    _mode("recording_start", mode)
    _start()
    if _recording():
        raise StateBlocked("OBS is already recording; nothing was done")
    _press(_button("Start Recording"))
    _wait_for("recording to start", lambda: _recording() or _text_shown(BLANK), TIMEOUT)
    if not _recording():
        if not allow_blank:
            _press(_button("No"))
            _wait_for("the warning to close", lambda: not _text_shown(BLANK))
            raise StateBlocked("the scene has no video source, so OBS would record a blank screen; pass allow_blank=True to record anyway")
        _press(_button("Yes"))
        _wait_for("recording to start", _recording, TIMEOUT)
    return _checked("recording_start", mode, {"recording": True, "folder": _recordings_folder()})


def recording_stop(mode: str = "ui") -> dict:
    """Stop recording (Controls › Stop Recording) and return the file OBS wrote."""
    _mode("recording_stop", mode)
    if not _running():
        raise StateBlocked("OBS isn't running, so it isn't recording")
    _start()
    if not _recording():
        raise StateBlocked("OBS isn't recording; nothing was done")
    folder = _recordings_folder()
    stopped = time.time()
    _press(_button("Stop Recording"))
    _wait_for("recording to stop", lambda: _button("Start Recording") is not None, TIMEOUT * 3)

    def newest():
        files = [os.path.join(folder, f) for f in os.listdir(folder) if f.lower().endswith(VIDEO)]
        files = [f for f in files if os.path.getmtime(f) >= stopped - 15]
        return max(files, key=os.path.getmtime) if files else None
    path = _wait_for("the recording file", newest, TIMEOUT)
    size = -1
    while os.path.getsize(path) != size:
        size = os.path.getsize(path)
        time.sleep(1)
    return _checked("recording_stop", mode, {"path": path, "bytes": size})


# Sources (added on day 3 in their own section, tested on their own) ------------------------------------------------

SOURCE_KINDS = {"color": ("Color Source", "color_source"), "text": ("Text (FreeType 2)", "text_ft2_source")}



def _sources() -> list:
    with open(_collection(), encoding="utf-8") as handle:
        return json.load(handle).get("sources", [])


def _current_scene() -> str:
    with open(_collection(), encoding="utf-8") as handle:
        return json.load(handle).get("current_scene", "")


def _scene_items(scene: str) -> list:
    found = next((s for s in _sources() if s.get("id") == "scene" and s.get("name") == scene), None)
    return [item.get("name") for item in (found or {}).get("settings", {}).get("items", [])]


def _press_quietly(element) -> None:
    # Menu items and buttons that open OBS's modal dialogs answer "cannot complete" once the dialog is up.
    if element is None:
        raise UIError("a named element wasn't found")
    _AS.AXUIElementPerformAction(element, _cf("AXPress"))


def source_add(name: str, kind: str, text: str = None, mode: str = "ui") -> dict:
    """Add a new source to the current scene (Sources › Add, the kind, Create new with the name, OK, its properties, OK).
    kind: "color" (OBS's default color, 1920×1080) or "text" (with text, in OBS's default font). Image sources are left out: OBS
    didn't take a path set or pasted into the Image File field through Accessibility."""
    _mode("source_add", mode)
    if kind not in SOURCE_KINDS:
        raise ValueError(f"kind must be one of {sorted(SOURCE_KINDS)}")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("name must not be empty")
    if kind == "text" and not text:
        raise ValueError("a text source needs text")
    if kind != "text" and text is not None:
        raise ValueError("text is only for kind=\"text\"")
    if any(s.get("name") == name for s in _sources()):
        raise AlreadyExists(f"a source or scene named {name} already exists; nothing was done")
    menu_name, source_id = SOURCE_KINDS[kind]
    _start()
    # A source dialog or a properties window already open is left alone. Its elements can take a moment to show up to
    # Accessibility, so look for any sign of one for two seconds.
    def dialog_open():
        return any((_role(e) == "AXButton" and _string(e, "AXTitle") in ("OK", "Defaults")) or
                   (_role(e) == "AXRadioButton" and _string(e, "AXTitle") in ("Create new", "Add Existing")) or
                   (_role(e) == "AXCheckBox" and _string(e, "AXTitle") == "Make source visible") for e in _everything())
    end = time.monotonic() + 2
    while time.monotonic() < end:
        if dialog_open():
            raise StateBlocked("an OBS source dialog is open; nothing was done")
        time.sleep(0.3)
    scene = _current_scene()
    _press_quietly(_button(description="Add Source"))
    item = _wait_for("the Add Source menu", lambda: next((e for e in _everything() if _role(e) == "AXMenuItem" and _string(e, "AXTitle") == menu_name), None))
    _press_quietly(item)
    field = _wait_for("the new source's name field", lambda: _button("OK") is not None and next(
        (e for e in _everything() if _role(e) == "AXTextField" and _string(e, "AXValue").startswith(menu_name.split(" ")[0])), None))
    try:
        _AS.AXUIElementSetAttributeValue(field, _cf("AXFocused"), _TRUE)
        _AS.AXUIElementSetAttributeValue(field, _cf("AXValue"), _cf(name))
        _wait_for("the name to be typed", lambda: _string(field, "AXValue") == name)
        _press_quietly(_button("OK"))
        # OBS opens the new source's properties; they can take a while to show up to Accessibility.
        def properties():
            return _text_shown(f"Properties for '{name}'") or _button("Defaults") is not None
        try:
            _wait_for(f"the properties of {name}", properties, TIMEOUT * 3)
        except UIError:
            if kind == "text":
                raise
            properties = None  # a color source needs nothing from its properties; it is checked in the scene file below
        if kind == "text":
            box = _wait_for("the Text box", lambda: next((e for e in _everything() if _role(e) == "AXTextArea"), None), TIMEOUT * 2)
            _AS.AXUIElementSetAttributeValue(box, _cf("AXFocused"), _TRUE)
            _AS.AXUIElementSetAttributeValue(box, _cf("AXValue"), _cf(text))
            _wait_for("the text to be typed", lambda: _string(box, "AXValue") == text)
        if properties is not None:
            _press_quietly(_button("OK"))
            _wait_for("the properties to close", lambda: not _text_shown(f"Properties for '{name}'") and _button("Defaults") is None, TIMEOUT * 2)
    except Exception:
        cancel = _button("Cancel")
        if cancel is not None:
            _press_quietly(cancel)
        raise

    def saved():
        found = next((s for s in _sources() if s.get("name") == name and s.get("id") == source_id), None)
        if found is None or name not in _scene_items(scene):
            return None
        settings = found.get("settings", {})
        if kind == "text" and settings.get("text") != text:
            return None
        return found
    _wait_for(f"the source {name} to be saved", saved, TIMEOUT * 2)
    return _checked("source_add", mode, {"name": name, "kind": kind, "scene": scene})
