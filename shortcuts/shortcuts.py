"""Shortcuts commands for agents: plain functions with keyword arguments, for the Shortcuts app on this Mac.

mode="background" uses "Shortcuts Events", the app's own scripting, and shows nothing: listing, running, folders and moving.
It needs the one-time macOS Automation permission for whatever process calls it ("… wants access to control Shortcuts
Events"); a person must allow that, and nothing here answers it.
mode="ui" works on screen: elements are found by role and name through the macOS Accessibility API and pressed, menu items
are clicked by name, and text is set straight into named fields (the clipboard isn't used). Two things can't be pressed
through Accessibility, a file or folder parameter in an action and its Open panel's Go To: there the call clicks the middle
of that named element's own frame, and types a key with System Events.

Running a shortcut that reads or saves files makes Shortcuts ask, once per shortcut, "Allow '<name>' to …?". Nothing here
answers that: shortcut_run raises PermissionNeeded and leaves the question on screen for a person.

Errors: NotFound, Ambiguous (nothing changed), AlreadyExists, StateBlocked (the screen holds something the call won't
destroy, or another app came to the front), PermissionNeeded, UIError (an element never appeared, or the result wasn't seen
in time), NotSupported (the mode can't do it or wasn't verified)."""
from __future__ import annotations

import ctypes
import os
import plistlib
import subprocess
import time
import warnings

APP = "Shortcuts"
EVENTS = "Shortcuts Events"
BUNDLE_ID = "com.apple.shortcuts"
APP_PLIST = "/System/Applications/Shortcuts.app/Contents/Info.plist"
VIEW_SERVICE = "ShortcutsViewService"
TIMEOUT = 10
RUN_TIMEOUT = 60

VERIFIED: dict = {
    "folder_create": {
        "background": {
            "macos": "15.6.1 (24G90)",
            "app": "7.0 (3612.0.2.1)"
        }
    },
    "shortcut_delete": {
        "ui": {
            "macos": "15.6.1 (24G90)",
            "app": "7.0 (3612.0.2.1)"
        }
    },
    "shortcut_list": {
        "background": {
            "macos": "15.6.1 (24G90)",
            "app": "7.0 (3612.0.2.1)"
        }
    },
    "shortcut_move": {
        "background": {
            "macos": "15.6.1 (24G90)",
            "app": "7.0 (3612.0.2.1)"
        }
    },
    "shortcut_run": {
        "background": {
            "macos": "15.6.1 (24G90)",
            "app": "7.0 (3612.0.2.1)"
        }
    }
}
UNSUPPORTED = {
    ("shortcut_list", "ui"): "it reads data, which the background mode does",
    ("shortcut_run", "ui"): "running is done through Shortcuts Events, which shows nothing",
    ("folder_create", "ui"): "folders are made through Shortcuts Events",
    ("shortcut_move", "ui"): "moving a shortcut on screen means dragging it, and these commands use no screen coordinates",
    ("shortcut_create", "background"): "Shortcuts Events can't make shortcuts or add actions",
    ("shortcut_delete", "background"): "Shortcuts Events accepts delete but nothing is deleted",
}


class ShortcutsError(Exception):
    pass


class NotFound(ShortcutsError):
    pass


class Ambiguous(ShortcutsError):
    pass


class AlreadyExists(ShortcutsError):
    pass


class StateBlocked(ShortcutsError):
    pass


class PermissionNeeded(ShortcutsError):
    pass


class UIError(ShortcutsError):
    pass


class NotSupported(ShortcutsError):
    pass


def _run(args: list, input_text: str | None = None) -> str:
    done = subprocess.run(args, capture_output=True, text=True, input=input_text)
    if done.returncode:
        raise UIError(done.stderr.strip())
    return done.stdout.rstrip("\n")


def _events(body: str, *args: str) -> str:
    """A Shortcuts Events step; values go in as argv, never into the script text."""
    return _run(["osascript", "-e", "on run argv\nwith timeout of 30 seconds\ntell application \"Shortcuts Events\"\n" + body +
                 "\nend tell\nend timeout\nend run", *args])


def _versions() -> dict:
    macos = f"{_run(['sw_vers', '-productVersion'])} ({_run(['sw_vers', '-buildVersion'])})"
    with open(APP_PLIST, "rb") as handle:
        info = plistlib.load(handle)
    return {"macos": macos, "app": f"{info['CFBundleShortVersionString']} ({info['CFBundleVersion']})"}


def _checked(function: str, mode: str, result):
    verified = VERIFIED.get(function, {}).get(mode)
    if verified is None:
        return result
    now = _versions()
    if now == verified:
        return result
    flag = {"unverified_version": True, "verified_on": verified, "running_on": now}
    warnings.warn(f"{function} ({mode}) was verified on {verified}, running on {now}")
    if isinstance(result, dict):
        return {**result, **flag}
    if isinstance(result, list):
        return [{**item, **flag} if isinstance(item, dict) else item for item in result]
    return result


def _mode(function: str, mode: str, supported: tuple) -> None:
    if mode not in ("ui", "background"):
        raise ValueError(f"mode must be 'ui' or 'background', not {mode!r}")
    if VERIFIED and mode not in VERIFIED.get(function, {}):
        raise NotSupported(f"{function} has no verified {mode} mode: "
                           f"{UNSUPPORTED.get((function, mode), 'it did not pass verification')}")
    if mode not in supported:
        raise NotSupported(f"{function} has no {mode} mode: {UNSUPPORTED.get((function, mode), '')}")


def _name(value, what: str = "name") -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{what} must not be empty")
    if value != value.strip() or "\n" in value:
        raise ValueError(f"{what} must not start or end with spaces or hold line breaks")
    return value


def _wait_for(what: str, test, timeout: float = TIMEOUT, every: float = 0.25):
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


# --- Shortcuts Events (background) ---------------------------------------------------------------------------------

_SEP = "␞"


def _all() -> list:
    """Every shortcut, top level and in folders: name, folder, action count, accepts input."""
    out = _events('set AppleScript\'s text item delimiters to "' + _SEP + '"\nset rows to {}\n'
                  'repeat with s in (every shortcut)\nset end of rows to (name of s) & "' + _SEP + '" & "" & "' + _SEP +
                  '" & (action count of s) & "' + _SEP + '" & (accepts input of s)\nend repeat\n'
                  'repeat with f in (every folder)\nrepeat with s in (every shortcut of f)\n'
                  'set end of rows to (name of s) & "' + _SEP + '" & (name of f) & "' + _SEP + '" & (action count of s) & "' +
                  _SEP + '" & (accepts input of s)\nend repeat\nend repeat\n'
                  'set AppleScript\'s text item delimiters to linefeed\nreturn rows as text')
    found = []
    for line in out.split("\n"):
        if not line:
            continue
        name, folder, count, accepts = line.split(_SEP)
        found.append({"name": name, "folder": folder or None, "action_count": int(count), "accepts_input": accepts == "true"})
    return found


def _folders() -> list:
    out = _events('set AppleScript\'s text item delimiters to linefeed\nreturn (name of every folder) as text')
    return [n for n in out.split("\n") if n]


def _one(name: str) -> dict:
    found = [s for s in _all() if s["name"] == name]
    if not found:
        raise NotFound(f"no shortcut named {name}")
    if len(found) > 1:
        raise Ambiguous(f"{len(found)} shortcuts are named {name}; nothing was done")
    return found[0]


def shortcut_list(mode: str = "background") -> list:
    """Every shortcut: [{name, folder (None at the top level), action_count, accepts_input}], sorted by name."""
    _mode("shortcut_list", mode, ("background",))
    return _checked("shortcut_list", mode, sorted(_all(), key=lambda s: (s["name"], s["folder"] or "")))


def folder_create(name: str, mode: str = "background") -> dict:
    """A new, empty shortcut folder."""
    _mode("folder_create", mode, ("background",))
    _name(name)
    if name in _folders():
        raise AlreadyExists(f"a folder named {name} already exists; nothing was done")
    _events('make new folder with properties {name:(item 1 of argv)}', name)
    _wait_for(f"the folder {name}", lambda: name in _folders())
    return _checked("folder_create", mode, {"name": name})


def shortcut_move(name: str, folder: str, mode: str = "background") -> dict:
    """Move a shortcut into an existing folder."""
    _mode("shortcut_move", mode, ("background",))
    _name(name)
    _name(folder, "folder")
    if folder not in _folders():
        raise NotFound(f"no folder named {folder}")
    found = _one(name)
    if found["folder"] == folder:
        return _checked("shortcut_move", mode, {"name": name, "folder": folder, "moved": False})
    where = "shortcut (item 1 of argv)" if found["folder"] is None else "shortcut (item 1 of argv) of folder (item 3 of argv)"
    _events(f'set folder of {where} to folder (item 2 of argv)', name, folder, found["folder"] or "")
    _wait_for(f"{name} in {folder}", lambda: _one(name)["folder"] == folder)
    return _checked("shortcut_move", mode, {"name": name, "folder": folder, "moved": True})


def _privacy_prompt() -> str:
    """The text of Shortcuts' own "Allow … ?" question, if one is showing."""
    for pid in subprocess.run(["pgrep", "-f", VIEW_SERVICE], capture_output=True, text=True).stdout.split():
        app = _AS.AXUIElementCreateApplication(int(pid))
        for window in _children(app):
            if _role(window) == "AXWindow" and _string(window, "AXTitle").startswith("Privacy"):
                texts = [_string(e, "AXValue") for e in _walk(window) if _role(e) == "AXStaticText"]
                return next((t for t in texts if t.startswith("Allow")), "a privacy question")
    return ""


def shortcut_run(name: str, input: str | None = None, timeout: float = RUN_TIMEOUT, mode: str = "background") -> dict:
    """Run a shortcut by name, optionally with text input. Returns {name, output}: the shortcut's output as text, or None.
    If Shortcuts asks to allow the shortcut access (files, for example), raises PermissionNeeded and leaves the question
    on screen for a person."""
    _mode("shortcut_run", mode, ("background",))
    _name(name)
    if input is not None and not isinstance(input, str):
        raise ValueError("input must be text or None")
    if not (isinstance(timeout, (int, float)) and 1 <= timeout <= 600):
        raise ValueError("timeout must be between 1 and 600 seconds")
    found = _one(name)
    if _privacy_prompt():
        raise PermissionNeeded("a Shortcuts privacy question is already on screen, waiting for a person; nothing was run")
    target = "shortcut (item 1 of argv)" if found["folder"] is None else "shortcut (item 1 of argv) of folder (item 3 of argv)"
    run = f"run {target}" + (" with input (item 2 of argv)" if input is not None else "")
    script = ("on run argv\nwith timeout of " + str(int(timeout) + 5) + " seconds\ntell application \"Shortcuts Events\"\n"
              "set r to " + run + "\nend tell\nend timeout\nif r is missing value then return \"␟none\"\n"
              "try\nreturn r as text\non error\nreturn \"␟not text\"\nend try\nend run")
    proc = subprocess.Popen(["osascript", "-e", script, name, input or "", found["folder"] or ""],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    deadline = time.monotonic() + timeout
    while proc.poll() is None:
        prompt = _privacy_prompt()
        if prompt:
            proc.kill()
            raise PermissionNeeded(f"Shortcuts asks: {prompt} A person must answer it; it was left on screen")
        if time.monotonic() > deadline:
            proc.kill()
            raise UIError(f"{name} didn't finish within {timeout}s")
        time.sleep(0.3)
    out, err = proc.communicate()
    if proc.returncode:
        raise UIError(f"{name} failed: {err.strip()}")
    out = out.rstrip("\n")
    output = None if out == "␟none" else out
    return _checked("shortcut_run", mode, {"name": name, "output": output})


# --- Accessibility (ui) ---------------------------------------------------------------------------------------------

_AS = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices")
_CF = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
_CG = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics")
_P = ctypes.c_void_p


class _Point(ctypes.Structure):
    _fields_ = [("x", ctypes.c_double), ("y", ctypes.c_double)]


for _f, _res, _args in [(_AS.AXUIElementCreateApplication, _P, [ctypes.c_int]),
                        (_AS.AXUIElementCopyAttributeValue, ctypes.c_int, [_P, _P, ctypes.POINTER(_P)]),
                        (_AS.AXUIElementSetAttributeValue, ctypes.c_int, [_P, _P, _P]),
                        (_AS.AXUIElementPerformAction, ctypes.c_int, [_P, _P]),
                        (_AS.AXValueGetValue, ctypes.c_bool, [_P, ctypes.c_int, _P]),
                        (_CF.CFStringCreateWithCString, _P, [_P, ctypes.c_char_p, ctypes.c_uint32]),
                        (_CF.CFStringGetLength, ctypes.c_long, [_P]),
                        (_CF.CFStringGetMaximumSizeForEncoding, ctypes.c_long, [ctypes.c_long, ctypes.c_uint32]),
                        (_CF.CFStringGetCString, ctypes.c_bool, [_P, ctypes.c_char_p, ctypes.c_long, ctypes.c_uint32]),
                        (_CF.CFGetTypeID, ctypes.c_ulong, [_P]), (_CF.CFStringGetTypeID, ctypes.c_ulong, []),
                        (_CF.CFArrayGetTypeID, ctypes.c_ulong, []), (_CF.CFArrayGetCount, ctypes.c_long, [_P]),
                        (_CF.CFArrayGetValueAtIndex, _P, [_P, ctypes.c_long]),
                        (_CF.CFNumberGetTypeID, ctypes.c_ulong, []), (_CF.CFNumberGetValue, ctypes.c_bool, [_P, ctypes.c_int, _P]),
                        (_CG.CGEventCreateMouseEvent, _P, [_P, ctypes.c_uint32, _Point, ctypes.c_uint32]),
                        (_CG.CGEventPost, None, [ctypes.c_uint32, _P])]:
    _f.restype, _f.argtypes = _res, _args
_UTF8 = 0x08000100
_TRUE = _P.in_dll(_CF, "kCFBooleanTrue")
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


def _number(element, name: str):
    value = _attr(element, name)
    if not value or _CF.CFGetTypeID(value) != _CF.CFNumberGetTypeID():
        return None
    out = ctypes.c_long()
    return out.value if _CF.CFNumberGetValue(value, 4, ctypes.byref(out)) else None


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


def _label(element) -> str:
    """A parameter button's name without the quote marks Shortcuts puts around it."""
    return "".join(ch for ch in (_string(element, "AXDescription") or _string(element, "AXTitle"))
                   if ch not in "\x91⁨⁩").strip()


def _press(element) -> None:
    if element is None or _AS.AXUIElementPerformAction(element, _cf("AXPress")):
        raise UIError("an element couldn't be pressed")


def _set_value(element, text: str) -> None:
    _AS.AXUIElementSetAttributeValue(element, _cf("AXFocused"), _TRUE)
    _AS.AXUIElementSetAttributeValue(element, _cf("AXValue"), _cf(text))
    _wait_for("the text to be set", lambda: _string(element, "AXValue") == text, 3)


def _frame(element) -> tuple:
    point, size = (ctypes.c_double * 2)(), (ctypes.c_double * 2)()
    if not (_AS.AXValueGetValue(_attr(element, "AXPosition"), 1, point) and _AS.AXValueGetValue(_attr(element, "AXSize"), 2, size)):
        raise UIError("an element's frame couldn't be read")
    return point[0], point[1], size[0], size[1]


def _running() -> bool:
    return subprocess.run(["pgrep", "-x", APP], capture_output=True).returncode == 0


def _app():
    found = subprocess.run(["pgrep", "-x", APP], capture_output=True, text=True).stdout.split()
    if not found:
        raise UIError("Shortcuts isn't running")
    return _AS.AXUIElementCreateApplication(int(found[0]))


def _windows() -> list:
    return [e for e in _children(_app()) if _role(e) == "AXWindow"]


def _focused():
    return _attr(_app(), "AXFocusedWindow")


def _by_id(root, identifier: str):
    return next((e for e in _walk(root) if _string(e, "AXIdentifier") == identifier), None)


def _system_events(body: str, *args: str) -> str:
    return _run(["osascript", "-e", "on run argv\ntell application \"System Events\" to tell process \"Shortcuts\"\n" + body +
                 "\nend tell\nend run", *args])


def _menu(menu: str, item: str) -> None:
    _system_events("click menu item (item 2 of argv) of menu (item 1 of argv) of menu bar 1", menu, item)


def _menu_enabled(menu: str, item: str) -> bool:
    return _system_events("return enabled of menu item (item 2 of argv) of menu (item 1 of argv) of menu bar 1", menu, item) == "true"


def _front() -> bool:
    return _system_events("return frontmost") == "true"


def _key(code: int, modifiers: str = "") -> None:
    if not _front():
        raise StateBlocked("another app came to the front; nothing more was done")
    using = f" using {{{modifiers}}}" if modifiers else ""
    _run(["osascript", "-e", f'tell application "System Events" to key code {code}{using}'])


def _keystroke(char: str, modifiers: str) -> None:
    if not _front():
        raise StateBlocked("another app came to the front; nothing more was done")
    _run(["osascript", "-e", f'tell application "System Events" to keystroke "{char}" using {{{modifiers}}}'])


def _click_middle(element, window) -> None:
    """One click in the middle of a named element's own frame, only if that point is inside its window and Shortcuts is in front."""
    x, y, w, h = _frame(element)
    wx, wy, ww, wh = _frame(window)
    cx, cy = x + w / 2, y + h / 2
    if not (w > 0 and h > 0 and wx < cx < wx + ww and wy < cy < wy + wh):
        raise UIError("a parameter isn't showing inside the editor")
    if not _front():
        raise StateBlocked("another app came to the front; nothing more was done")
    for kind in (5, 1, 2):
        _CG.CGEventPost(0, _CG.CGEventCreateMouseEvent(None, kind, _Point(cx, cy), 0))
        time.sleep(0.12)


def _sheet(window):
    return next((c for c in _children(window) if _role(c) == "AXSheet"), None)


def _start() -> None:
    """Shortcuts running and in front, with nothing modal showing."""
    if not _running():
        _run(["open", "-b", BUNDLE_ID])
        _wait_for("Shortcuts to start", lambda: _running() and _windows(), 30)
    _system_events("set visible to true\nset frontmost to true")
    _wait_for("Shortcuts in front", _front)
    for window in _windows():
        if _sheet(window) is not None or _string(window, "AXIdentifier") in ("open-panel", "save-panel"):
            raise StateBlocked("a Shortcuts sheet or file panel is open; nothing was done")
    if _privacy_prompt():
        raise StateBlocked("a Shortcuts privacy question is on screen; nothing was done")


def _editor(window):
    return _by_id(window, "actions.list")


def _actions(window) -> list:
    """The action groups in an editor, as Accessibility lists them."""
    found = _editor(window)
    return [c for c in _children(found) if _role(c) == "AXGroup"] if found is not None else []


def _library_rows(window, name: str) -> list:
    """Action library rows whose own text is exactly name."""
    return [e for e in _walk(window) if _role(e) == "AXRow"
            and any(_role(t) == "AXStaticText" and _string(t, "AXValue") == name for t in _walk(e))]


def _search_field(window):
    """The action library's search field: the text field that holds a Search button, outside the toolbar."""
    return next((e for e in _walk(window) if _role(e) == "AXTextField" and _role(_attr(e, "AXParent")) != "AXToolbar"
                 and any(_role(c) == "AXButton" and _string(c, "AXDescription") == "Search" for c in _children(e))), None)


def _open_panel_go(path: str) -> None:
    """Choose path in the Open panel in front: Go To (Shift-Cmd-G), the path, Return, then Open."""
    panel = _wait_for("the Open panel", lambda: (lambda w: w if w is not None and _string(w, "AXIdentifier") == "open-panel" else None)(_focused()))
    _keystroke("g", "command down, shift down")
    field = _wait_for("Go To's path field", lambda: _by_id(_focused(), "PathTextField"))
    _set_value(field, path)
    _key(36)
    want = os.path.basename(path.rstrip("/"))
    _wait_for(f"the panel at {want}", lambda: _string(_by_id(_focused(), "where popup") or panel, "AXValue") == want
              and _by_id(_focused(), "PathTextField") is None)
    _press(_by_id(_focused(), "OKButton"))
    _wait_for("the Open panel to close", lambda: _string(_focused(), "AXIdentifier") != "open-panel")


def _cancel_panel() -> None:
    try:
        window = _focused()
        if _string(window, "AXIdentifier") == "open-panel":
            _key(53)
            time.sleep(0.4)
            if _string(_focused(), "AXIdentifier") == "open-panel":
                _press(_by_id(_focused(), "CancelButton"))
    except (UIError, StateBlocked):
        pass


def _add_action(window, step: dict) -> None:
    name = step["action"]
    before = len(_actions(window))
    field = _search_field(window)
    if field is None:
        raise UIError("the action library's search field wasn't found")
    _set_value(field, name)
    try:
        _wait_for(f"the action {name} in the library", lambda: _library_rows(window, name), 6)
    except UIError:
        raise NotFound(f"the action library has no action named {name}") from None
    time.sleep(0.8)  # the filtered list redraws once more after the first matching row shows up
    rows = _library_rows(window, name)
    if len(rows) > 1:
        raise Ambiguous(f"{len(rows)} library actions are named {name}; the shortcut was left as it is")
    if not rows:
        raise UIError(f"the action {name} went away from the library")
    # Fix 1: Return goes to whatever has keyboard focus, which after an earlier action can be one of that action's own
    # fields; so the library's table takes focus first, and the key is sent only once it has it.
    table = _attr(rows[0], "AXParent")
    _AS.AXUIElementSetAttributeValue(table, _cf("AXFocused"), _TRUE)
    _AS.AXUIElementSetAttributeValue(rows[0], _cf("AXSelected"), _TRUE)
    _wait_for(f"{name} selected", lambda: _attr(rows[0], "AXSelected") == _TRUE.value, 3)
    _wait_for("the action library focused", lambda: _role(_attr(_app(), "AXFocusedUIElement")) in ("AXTable", "AXOutline", "AXRow"), 3)
    time.sleep(0.3)
    _key(36)
    group = _wait_for(f"{name} added", lambda: len(_actions(window)) > before and next(
        (g for g in _actions(window) if _string(g, "AXDescription") == name and _added(g)), None))
    tokens = lambda: [e for e in _children(group) if _role(e) == "AXButton" and "⁨" in (_string(e, "AXDescription") or _string(e, "AXTitle"))]
    if "path" in step:
        _wait_for(f"{name}'s file parameter", tokens, 5)
        _click_middle(tokens()[0], window)
        _open_panel_go(step["path"])
        want = step["path"].strip("/").split("/")
        _wait_for(f"{name} set to {step['path']}", lambda: bool(tokens()) and _label(tokens()[0]).split("  ") == want)
    if "save_to" in step:
        ask = lambda: next((e for e in _walk(group) if _role(e) == "AXCheckBox" and _string(e, "AXDescription") == "Ask Where To Save"), None)
        if ask() is None:
            _press(next(e for e in _children(group) if _role(e) == "AXButton" and _string(e, "AXDescription") == "Show More"))
            _wait_for("Save File's options", ask)
        if _number(ask(), "AXValue") == 1:
            _press(ask())
            _wait_for("Ask Where To Save off", lambda: _number(ask(), "AXValue") == 0)
        _wait_for("Save File's destination", lambda: len(tokens()) == 2)
        _click_middle(tokens()[1], window)
        _open_panel_go(step["save_to"])
        want = os.path.basename(step["save_to"].rstrip("/"))  # the destination shows only its folder's name
        _wait_for(f"Save File set to {step['save_to']}", lambda: len(tokens()) == 2 and _label(tokens()[1]) == want)


_seen_groups: set = set()


def _added(group) -> bool:
    """True once for each action group: the one just added is the group not seen before."""
    key = _string(group, "AXIdentifier") + str(_frame(group))
    return key not in _seen_groups


def _steps(actions) -> list:
    if not isinstance(actions, (list, tuple)) or not actions:
        raise ValueError("actions must be a non-empty list")
    steps = []
    for item in actions:
        step = {"action": item} if isinstance(item, str) else dict(item) if isinstance(item, dict) else None
        if step is None or set(step) - {"action", "path", "save_to"}:
            raise ValueError("each action is a name, or {'action': name, 'path': …} or {'action': 'Save File', 'save_to': folder}")
        _name(step.get("action"), "action")
        if "path" in step:
            if step["action"] != "File":
                raise ValueError("path is only for the File action")
            step["path"] = os.path.abspath(os.path.expanduser(step["path"]))
            if not os.path.exists(step["path"]):
                raise NotFound(f"{step['path']} doesn't exist")
        if "save_to" in step:
            if step["action"] != "Save File":
                raise ValueError("save_to is only for the Save File action")
            step["save_to"] = os.path.abspath(os.path.expanduser(step["save_to"]))
            if not os.path.isdir(step["save_to"]):
                raise NotFound(f"{step['save_to']} isn't a folder")
        steps.append(step)
    return steps


def shortcut_create(name: str, actions: list, mode: str = "ui") -> dict:
    """A new shortcut with these actions, in order. Each action is its name in the action library (exactly, e.g. "Comment",
    "Make Archive"), or a dict: {"action": "File", "path": file or folder} or {"action": "Save File", "save_to": folder}
    (Ask Where To Save is turned off). Actions keep Shortcuts' defaults otherwise. The editor is closed afterwards.
    Returns {name, actions, action_count} (Shortcuts' own count, which can be larger: If adds Otherwise and End If)."""
    _mode("shortcut_create", mode, ("ui",))
    _name(name)
    steps = _steps(actions)
    names = {s["name"] for s in _all()}
    if name in names:
        raise AlreadyExists(f"a shortcut named {name} already exists; nothing was done")
    _start()
    titles = {_string(w, "AXTitle") for w in _windows()}
    _menu("File", "New Shortcut")
    window = _wait_for("the new shortcut's editor", lambda: next(
        (w for w in _windows() if _string(w, "AXTitle") not in titles and _editor(w) is not None), None), 15)
    _seen_groups.clear()
    try:
        for step in steps:
            for g in _actions(window):
                _seen_groups.add(_string(g, "AXIdentifier") + str(_frame(g)))
            _add_action(window, step)
        field = _by_id(window, "editor.shortcutname")
        _set_value(field, name)
        _key(36)
        # Fix 1: the name is confirmed in Shortcuts' own list, not the window title (which can differ for some names).
        _wait_for(f"{name} saved", lambda: any(s["name"] == name and s["action_count"] >= len(steps) for s in _all()), 15)
    except Exception as error:
        _cancel_panel()
        try:
            _close(window)
        except (UIError, StateBlocked):
            pass
        left = sorted({s["name"] for s in _all()} - names)
        error.args = (f"{error.args[0] if error.args else error}; " +
                      (f"the unfinished shortcut was left as {', '.join(left)}" if left else "no shortcut was left"),)
        raise
    _close(window)
    found = _one(name)
    return _checked("shortcut_create", mode, {"name": name, "actions": [s["action"] for s in steps], "action_count": found["action_count"]})


def _close(window) -> None:
    """Close an editor window with its own close button; Shortcuts keeps what it holds."""
    title = _string(window, "AXTitle")
    button = _attr(window, "AXCloseButton")
    if button is None:
        raise UIError("the editor's close button wasn't found")
    _press(button)
    _wait_for("the editor to close", lambda: all(_string(w, "AXTitle") != title or _editor(w) is None for w in _windows()), 8)


def _library():
    """The library window, showing All Shortcuts."""
    found = next((w for w in _windows() if _by_id(w, "library.grid") is not None), None)
    if found is None:
        _run(["open", "-b", BUNDLE_ID])
        found = _wait_for("the library window", lambda: next((w for w in _windows() if _by_id(w, "library.grid") is not None), None))
    _AS.AXUIElementPerformAction(found, _cf("AXRaise"))
    sidebar = _by_id(found, "library.sidebar")
    row = next((r for r in _children(sidebar) if _role(r) == "AXRow"
                and any(_string(t, "AXValue") == "All Shortcuts" for t in _walk(r))), None)
    if row is None:
        raise UIError("All Shortcuts wasn't found in the sidebar")
    _AS.AXUIElementSetAttributeValue(row, _cf("AXSelected"), _TRUE)
    return found


def _tiles(window) -> list:
    grid = _by_id(window, "library.grid")
    return [_string(e, "AXDescription") for e in _walk(grid) if _role(e) == "AXButton"] if grid is not None else []


def shortcut_delete(name: str, mode: str = "ui") -> dict:
    """Delete a shortcut (Shortcuts asks first; the call checks the name it asks about). Refused when the library's search
    for the name also shows other shortcuts (their names contain it), since Delete acts on everything shown."""
    _mode("shortcut_delete", mode, ("ui",))
    _name(name)
    _one(name)
    _start()
    window = _library()
    toolbar = next((c for c in _children(window) if _role(c) == "AXToolbar"), None)
    field = next((e for e in _walk(toolbar) if _role(e) == "AXTextField"), None) if toolbar is not None else None
    if field is None:
        raise UIError("the library's search field wasn't found")
    _set_value(field, name)
    try:
        shown = _wait_for(f"{name} in the library", lambda: (lambda t: t if name in t else None)(_tiles(window)))
        time.sleep(0.6)
        shown = _tiles(window)
        if shown != [name]:
            raise Ambiguous(f"searching for {name} also shows {sorted(set(shown) - {name}) or 'it twice'}; nothing was deleted")
        grid = _by_id(window, "library.grid")
        _AS.AXUIElementSetAttributeValue(grid, _cf("AXFocused"), _TRUE)
        _wait_for("the grid focused", lambda: _string(_attr(_app(), "AXFocusedUIElement"), "AXIdentifier") == "library.grid", 3)
        _menu("Edit", "Select All")
        _wait_for("the shortcut selected", lambda: _menu_enabled("Edit", "Duplicate"), 3)
        _menu("Edit", "Delete")
        sheet = _wait_for("Shortcuts' question", lambda: _sheet(window))
        asked = [_string(e, "AXValue") for e in _walk(sheet) if _role(e) == "AXStaticText"]
        if f"Delete shortcut “{name}”?" not in asked:
            _press(next((e for e in _walk(sheet) if _role(e) == "AXButton" and _string(e, "AXTitle") == "Cancel"), None))
            raise UIError(f"Shortcuts asked {asked[:1]}, not about {name}; cancelled, nothing was deleted")
        _press(next((e for e in _walk(sheet) if _role(e) == "AXButton" and _string(e, "AXTitle") == "Delete"), None))
        _wait_for(f"{name} deleted", lambda: not any(s["name"] == name for s in _all()), 15)
    finally:
        try:
            _set_value(field, "")
        except UIError:
            pass
    return _checked("shortcut_delete", mode, {"name": name, "deleted": True})
