"""Automator commands for agents: plain functions with keyword arguments, to build and save workflows.

mode="ui" works on screen: elements are found by role and name through the macOS Accessibility API, menu items are clicked by name, and
text is pasted through the clipboard, which is restored afterwards. No screen coordinates.

Set AUTOMATOR_ALLOWED_ROOT to a folder and every path is checked to be inside it, after following links, before anything happens.

Errors: NotFound, Ambiguous, AlreadyExists, OutsideAllowedRoot, StateBlocked (the screen holds something the call won't destroy),
UIError (an element never appeared), NotSupported (the mode can't do it or wasn't verified)."""
from __future__ import annotations

import ctypes
import json
import os
import plistlib
import subprocess
import time
import unicodedata
import urllib.parse
import warnings

APP = "Automator"
BUNDLE_ID = "com.apple.Automator"
TIMEOUT = 10
SAVE_TIMEOUT = 15
ROOT_ENV = "AUTOMATOR_ALLOWED_ROOT"
APP_PLIST = "/System/Applications/Automator.app/Contents/Info.plist"

VERIFIED: dict = {
    "action_add_items": {
        "ui": {
            "macos": "15.6.1 (24G90)",
            "app": "2.10 (528)"
        }
    },
    "action_set_filter": {
        "ui": {
            "macos": "15.6.1 (24G90)",
            "app": "2.10 (528)"
        }
    },
    "action_set_folder": {
        "ui": {
            "macos": "15.6.1 (24G90)",
            "app": "2.10 (528)"
        }
    },
    "action_set_option": {
        "ui": {
            "macos": "15.6.1 (24G90)",
            "app": "2.10 (528)"
        }
    },
    "workflow_actions": {
        "ui": {
            "macos": "15.6.1 (24G90)",
            "app": "2.10 (528)"
        }
    },
    "workflow_add_action": {
        "ui": {
            "macos": "15.6.1 (24G90)",
            "app": "2.10 (528)"
        }
    },
    "workflow_new": {
        "ui": {
            "macos": "15.6.1 (24G90)",
            "app": "2.10 (528)"
        }
    },
    "workflow_open": {
        "ui": {
            "macos": "15.6.1 (24G90)",
            "app": "2.10 (528)"
        }
    },
    "workflow_run": {
        "ui": {
            "macos": "15.6.1 (24G90)",
            "app": "2.10 (528)"
        }
    },
    "workflow_save": {
        "ui": {
            "macos": "15.6.1 (24G90)",
            "app": "2.10 (528)"
        }
    }
}
UNSUPPORTED: dict = {}


class AutomatorError(Exception):
    pass


class NotFound(AutomatorError):
    pass


class Ambiguous(AutomatorError):
    pass


class AlreadyExists(AutomatorError):
    pass


class OutsideAllowedRoot(AutomatorError):
    pass


class StateBlocked(AutomatorError):
    pass


class UIError(AutomatorError):
    pass


class NotSupported(AutomatorError):
    pass


def _run(args: list) -> str:
    done = subprocess.run(args, capture_output=True, text=True)
    if done.returncode:
        raise UIError(done.stderr.strip())
    return done.stdout.strip()


def _osascript(script: str, *args: str) -> str:
    return _run(["osascript", "-e", script, *args])


def _jxa(script: str, *args: str) -> str:
    return _run(["osascript", "-l", "JavaScript", "-e", script, *args])


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


def _mode(function: str, mode: str, supported: tuple = ("ui",)) -> None:
    if mode not in ("ui", "background"):
        raise ValueError(f"mode must be 'ui' or 'background', not {mode!r}")
    if mode not in supported or (VERIFIED and mode not in VERIFIED.get(function, {})):
        raise NotSupported(f"{function} has no verified {mode} mode: {UNSUPPORTED.get((function, mode), 'it did not pass verification')}")


def _wait_for(what: str, test, timeout: float = TIMEOUT, every: float = 0.2):
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


def _running() -> bool:
    return subprocess.run(["pgrep", "-x", APP], capture_output=True).returncode == 0


def _path(path: str) -> str:
    full = os.path.abspath(os.path.expanduser(path))
    root = os.environ.get(ROOT_ENV)
    if root:
        allowed, real = os.path.realpath(os.path.expanduser(root)), os.path.realpath(full)
        if real != allowed and not real.startswith(allowed + os.sep):
            raise OutsideAllowedRoot(f"{full} is outside {ROOT_ENV}; nothing was done")
    return full


def _existing(path: str) -> str:
    full = _path(path)
    if not os.path.exists(full):
        raise NotFound(f"nothing at {full}")
    return full


def _new_path(path: str) -> str:
    full = _path(path)
    if os.path.lexists(full):
        raise AlreadyExists(f"{full} already exists; nothing is overwritten")
    if not os.path.isdir(os.path.dirname(full)):
        raise NotFound(f"the folder {os.path.dirname(full)} doesn't exist")
    return full


# The screen -------------------------------------------------------------------------------------------------------

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


def _app():
    found = subprocess.run(["pgrep", "-x", APP], capture_output=True, text=True).stdout.split()
    if not found:
        raise UIError("Automator isn't running")
    return _AS.AXUIElementCreateApplication(int(found[0]))


def _windows() -> list:
    return [e for e in _children(_app()) if _role(e) == "AXWindow"]


def _is_document(window) -> bool:
    """A document window. While minimized, or while Automator is hidden, it reports itself as a dialog."""
    subrole = _string(window, "AXSubrole")
    if subrole == "AXStandardWindow":
        return True
    return subrole == "AXDialog" and _text_area(window) is not None and \
        (_attr(window, "AXMinimized") == _TRUE.value or _attr(_app(), "AXHidden") == _TRUE.value)


def _documents() -> list:
    return [w for w in _windows() if _is_document(w)]


def _doc_path(window):
    url = _string(window, "AXDocument")
    return urllib.parse.unquote(urllib.parse.urlparse(url).path) if url else None


def _window_of(full: str):
    if not _running():
        return None
    for window in _documents():
        path = _doc_path(window)
        if path and _same(path, full):
            return window
    return None


def _sheet(window):
    return next((e for e in _children(window) if _role(e) == "AXSheet"), None)


def _by_id(root, identifier: str):
    return next((e for e in _walk(root) if _string(e, "AXIdentifier") == identifier), None)


def _text_area(window):
    return next((e for e in _walk(window) if _role(e) == "AXTextArea"), None)


def _system_events(body: str) -> str:
    return _osascript(f'tell application "System Events" to tell process "{APP}"\n{body}\nend tell')


def _key(code: int, modifier: str = "") -> None:
    if _system_events("return frontmost") != "true":
        raise StateBlocked("another app came to the front; nothing more was typed")
    _system_events(f"key code {code}" + (f" using {modifier}" if modifier else ""))


def _menu(title: str, item: str) -> None:
    if _system_events("return frontmost") != "true":
        raise StateBlocked("another app came to the front; nothing more was done")
    _system_events(f'click menu item "{item}" of menu "{title}" of menu bar item "{title}" of menu bar 1')


def _has_menu_item(title: str, item: str) -> bool:
    return _system_events(f'exists menu item "{item}" of menu "{title}" of menu bar item "{title}" of menu bar 1') == "true"


RETURN, ESCAPE, DOWN, DELETE, KEY_A, KEY_G, KEY_S, KEY_V = 36, 53, 125, 51, 0, 5, 1, 9


CLIPBOARD = r"""
ObjC.import("AppKit");
function run(argv) {
  const pb = $.NSPasteboard.generalPasteboard;
  if (argv[0] === "save") {
    const items = ObjC.unwrap(pb.pasteboardItems) || [];
    return JSON.stringify(items.map(item => ObjC.unwrap(item.types).map(t => {
      const type = ObjC.unwrap(t);
      return [type, ObjC.unwrap(item.dataForType(type).base64EncodedStringWithOptions(0))];
    })));
  }
  pb.clearContents;
  if (argv[0] === "text") {
    pb.setStringForType($(argv[1]), "public.utf8-plain-text");
    return String(pb.changeCount);
  }
  const input = $.NSFileHandle.fileHandleWithStandardInput.readDataToEndOfFile;
  const items = JSON.parse(ObjC.unwrap($.NSString.alloc.initWithDataEncoding(input, $.NSUTF8StringEncoding))).map(pairs => {
    const item = $.NSPasteboardItem.alloc.init;
    pairs.forEach(([type, data]) => item.setDataForType($.NSData.alloc.initWithBase64EncodedStringOptions(data, 0), type));
    return item;
  });
  if (items.length) pb.writeObjects($(items));
  return "restored";
}"""



def _paste() -> None:
    _key(KEY_V, "command down")


def _paste_text(text: str, landed) -> None:
    """Put text on the clipboard, paste it where the cursor is, wait for landed(), and restore the clipboard."""
    saved = _jxa(CLIPBOARD, "save")
    try:
        _jxa(CLIPBOARD, "text", text)
        _paste()
        _wait_for("the pasted text to appear", landed)
    finally:
        # What was on the clipboard can be too large for an argument, so it goes through standard input.
        done = subprocess.run(["osascript", "-l", "JavaScript", "-e", CLIPBOARD, "restore"], input=saved,
                              capture_output=True, text=True)
        if done.returncode:
            raise UIError(done.stderr.strip())


def _forward() -> None:
    _system_events("set visible to true\nset frontmost to true")
    _wait_for("Automator in front", lambda: _system_events("return frontmost") == "true")


def _fill_save_panel(window, full: str) -> None:
    """Choose the folder and name in the Save dialog, check them, and press Save."""
    panel = _wait_for("the Save dialog", lambda: _sheet(window))
    folder, name = os.path.split(full)
    _key(KEY_G, "{command down, shift down}")
    go = _wait_for("Go to Folder", lambda: _by_id(panel, "GoToWindow"))
    field = _wait_for("the folder field", lambda: _by_id(go, "PathTextField"))
    _key(KEY_A, "command down")
    _paste_text(folder, lambda: _string(field, "AXValue") == folder)
    _key(RETURN)
    _wait_for("Go to Folder to close", lambda: _by_id(panel, "GoToWindow") is None)
    where = _by_id(panel, "where popup")
    _wait_for("the folder to be chosen", lambda: _string(where, "AXValue") == os.path.basename(folder))
    box = _by_id(panel, "saveAsNameTextField")
    _AS.AXUIElementSetAttributeValue(box, _cf("AXFocused"), _TRUE)
    time.sleep(0.3)
    _key(KEY_A, "command down")
    _paste_text(name, lambda: unicodedata.normalize("NFC", _string(box, "AXValue")) == unicodedata.normalize("NFC", name))
    _press(_find(panel, "AXButton", "Save"))


# Commands ---------------------------------------------------------------------------------------------------------



def _wait_for_quietly(test, timeout: float = 2):
    try:
        return _wait_for("it", test, timeout)
    except UIError:
        return None


def _start() -> None:
    if not _running():
        subprocess.run(["open", "-b", BUNDLE_ID], check=True)
        _wait_for("Automator to start", _running, TIMEOUT * 2)
    _forward()


def _chooser():
    """Automator's "Choose a type for your document" dialog."""
    return next((w for w in _windows() for e in _walk(w) if _role(e) == "AXStaticText" and _string(e, "AXValue") == "Choose a type for your document:"), None)


def _workflow_view(window):
    return next((e for e in _walk(window) if _role(e) == "AXList" and _string(e, "AXIdentifier") == "workflowView"), None)


def _front_workflow():
    main = _attr(_app(), "AXMainWindow")
    if main is None or _workflow_view(main) is None:
        raise NotFound("no workflow window is in front in Automator")
    if _sheet(main) is not None:
        raise StateBlocked("the workflow has a dialog open; it was left as it is")
    return main


def _action_titles(window) -> list:
    view = _workflow_view(window)
    out = []
    for item in _children(view):
        title = next((_string(e, "AXValue") for e in _walk(item) if _role(e) == "AXStaticText" and _string(e, "AXValue")), None)
        if title:
            out.append(title)
    return out


def workflow_new(mode: str = "ui") -> dict:
    """Start a new, empty workflow window (File > New, then Workflow in Automator's type chooser)."""
    _mode("workflow_new", mode)
    _start()
    before = {_string(w, "AXTitle") for w in _windows()}
    if _chooser() is None:
        _menu("File", "New")
    chooser = _wait_for("Automator's type chooser", _chooser)
    workflow = next((e for e in _walk(chooser) if _role(e) in ("AXStaticText", "AXCell", "AXImage") and _string(e, "AXValue") == "Workflow"), None)
    if workflow is not None:
        _AS.AXUIElementPerformAction(_attr(workflow, "AXParent"), _cf("AXPress"))
    _press(_wait_for("Choose", lambda: _find(chooser, "AXButton", "Choose")))
    window = _wait_for("the new workflow", lambda: next((w for w in _windows() if _workflow_view(w) is not None and not _action_titles(w)
                                                          and _chooser() is None), None))
    return _checked("workflow_new", mode, {"name": _string(window, "AXTitle"), "actions": []})


def workflow_add_action(name: str, copy_first: bool = False, mode: str = "ui") -> dict:
    """Add the library action with exactly this name to the end of the workflow in front (select it, then Return). If Automator
    offers to add a Copy Finder Items action first (for actions that change files), copy_first says whether to accept."""
    _mode("workflow_add_action", mode)
    if not name.strip():
        raise ValueError("name must be an action's name")
    _start()
    window = _front_workflow()
    before = _action_titles(window)
    search = next((e for e in _walk(window) if _role(e) == "AXTextField" and _string(e, "AXSubrole") == "AXSearchField"), None)
    if search is not None and _string(search, "AXValue"):
        _AS.AXUIElementSetAttributeValue(search, _cf("AXFocused"), _TRUE)
        _key(KEY_A, "command down")
        _key(DELETE)
    table = _wait_for("the action list", lambda: next((e for e in _walk(window) if _role(e) == "AXTable" and _string(e, "AXDescription") == "actions"), None))
    row = next((r for r in _children(table) if _role(r) == "AXRow" and any(_string(c, "AXValue") == name for c in _walk(r))), None)
    if row is None:
        raise NotFound(f"no action named {name!r} in Automator's library")
    _AS.AXUIElementSetAttributeValue(row, _cf("AXSelected"), _TRUE)
    _AS.AXUIElementSetAttributeValue(table, _cf("AXFocused"), _TRUE)
    _wait_for(f"{name!r} to be selected", lambda: _attr(row, "AXSelected") == _TRUE.value)
    _key(RETURN)
    sheet = _wait_for_quietly(lambda: _sheet(window))
    if sheet:
        _press(_find(_sheet(window), "AXButton", "Add" if copy_first else "Don't Add"))
    want = len(before) + (2 if (sheet and copy_first) else 1)
    _wait_for(f"{name!r} in the workflow", lambda: len(_action_titles(window)) == want and _action_titles(window)[-1] == name)
    return _checked("workflow_add_action", mode, {"workflow": _string(window, "AXTitle"), "actions": _action_titles(window)})


def workflow_actions(mode: str = "ui") -> dict:
    """The actions of the workflow in front, in order."""
    _mode("workflow_actions", mode)
    window = _front_workflow()
    return _checked("workflow_actions", mode, {"workflow": _string(window, "AXTitle"), "actions": _action_titles(window)})


def workflow_save(path: str, mode: str = "ui") -> dict:
    """Save the workflow in front as a new .workflow file at path (File > Save…)."""
    _mode("workflow_save", mode)
    full = _new_path(path)
    if not full.lower().endswith(".workflow"):
        raise ValueError("path must end in .workflow")
    _start()
    window = _front_workflow()
    _menu("File", "Save…")
    _fill_save_panel(window, full)
    _wait_for("the workflow to be saved", lambda: os.path.isfile(os.path.join(full, "Contents", "document.wflow")), SAVE_TIMEOUT)
    return _checked("workflow_save", mode, {"name": os.path.basename(full), "path": full, "actions": _action_titles(window)})


# Action options and running (day 4, in their own section, tested on their own) -----------------------------------

RUN_TIMEOUT = 300


def _action_group(name: str, index: int = 1):
    """The index-th action named name in the workflow in front (1 is the first)."""
    window = _front_workflow()
    view = _workflow_view(window)
    found = []
    for item in _children(view):
        title = next((_string(e, "AXValue") for e in _children(item) if _role(e) == "AXStaticText" and _string(e, "AXValue")), None)
        if title == name:
            found.append(item)
    if len(found) < index or index < 1:
        raise NotFound(f"the workflow has no action {name!r} number {index}")
    return window, found[index - 1]


def _labelled(group, role: str, label: str):
    """The control of this role whose linked label reads label (with or without its colon)."""
    want = {label, label.rstrip(":") + ":", label.rstrip(":")}
    for element in _walk(group):
        if _role(element) == role:
            title = _attr(element, "AXTitleUIElement")
            if title is not None and _string(title, "AXValue") in want:
                return element
    return None


def _pick(popup, item: str) -> None:
    """Choose a menu item of a pop-up button by its title."""
    _AS.AXUIElementPerformAction(popup, _cf("AXPress"))
    menu_item = _wait_for(f"{item!r} in the pop-up", lambda: next((m for m in _walk(popup) if _role(m) == "AXMenuItem" and _string(m, "AXTitle") == item), None))
    if _attr(menu_item, "AXEnabled") == _FALSE.value:
        _key(ESCAPE)
        raise ValueError(f"{item!r} can't be chosen there")
    _press(menu_item)


def _choose_in_panel(window, folder: str, name: str | None) -> None:
    """In the Open sheet now on window: go to folder; select name in it if given; press the OK button (Choose, Add or Open)."""
    def open_panel():
        # A sheet on the workflow for Add…; its own window for a pop-up's Other….
        return _sheet(window) or next((w for w in _windows() if w is not window and _by_id(w, "OKButton") is not None), None)
    panel = _wait_for("the Open dialog", open_panel)
    try:
        _key(KEY_G, "{command down, shift down}")
        go = _wait_for("Go to Folder", lambda: _by_id(panel, "GoToWindow"))
        field = _wait_for("the folder field", lambda: _by_id(go, "PathTextField"))
        _key(KEY_A, "command down")
        _paste_text(folder, lambda: unicodedata.normalize("NFC", _string(field, "AXValue")) == unicodedata.normalize("NFC", folder))
        _key(RETURN)
        _wait_for("Go to Folder to close", lambda: _by_id(panel, "GoToWindow") is None)
        if name is not None:
            # Typing selects by name only once the folder's list has loaded, so wait until the dialog shows the item.
            want = unicodedata.normalize("NFC", name)
            _wait_for(f"{name} in the dialog", lambda: any(unicodedata.normalize("NFC", _string(e, "AXValue") or _string(e, "AXTitle")) == want
                                                          for e in _walk(panel) if _role(e) in ("AXTextField", "AXStaticText", "AXCell")), TIMEOUT)
            quoted = '"' + name.replace("\\", "\\\\").replace('"', '\\"') + '"'
            _system_events(f"keystroke {quoted}")
            time.sleep(0.8)
        _press(_wait_for("the dialog's OK button", lambda: _by_id(panel, "OKButton")))
    except Exception:
        cancel = _by_id(panel, "CancelButton")
        if cancel is not None:
            _press(cancel)
        raise
    _wait_for("the Open dialog to close", lambda: open_panel() is None)


def _item_paths(group) -> list:
    """The paths listed in Get Specified Finder Items' table (its Path column)."""
    table = next((e for e in _walk(group) if _role(e) == "AXTable"), None)
    out = []
    for row in (_children(table) if table is not None else []):
        if _role(row) == "AXRow":
            cells = [_string(e, "AXValue") for e in _walk(row) if _role(e) in ("AXTextField", "AXStaticText") and _string(e, "AXValue")]
            if cells:
                out.append(cells[-1])
    return out


def action_add_items(paths: list, action: str = "Get Specified Finder Items", index: int = 1, mode: str = "ui") -> dict:
    """Add files or folders to Get Specified Finder Items (its Add… button, then each item chosen in the Open dialog)."""
    _mode("action_add_items", mode)
    if isinstance(paths, str) or not paths:
        raise ValueError("paths must be a non-empty list")
    fulls = [_existing(p) for p in paths]
    _start()
    window, group = _action_group(action, index)
    for full in fulls:
        before = _item_paths(group)
        name = unicodedata.normalize("NFC", os.path.basename(full))
        _press(_find(group, "AXButton", "Add…"))
        _choose_in_panel(window, os.path.dirname(full), os.path.basename(full))
        _wait_for(f"{name} to be listed", lambda: len(_item_paths(group)) > len(before))
        added = [unicodedata.normalize("NFC", p) for p in _item_paths(group)[len(before):]]
        if added != [name]:
            # The Open dialog picked something else: take it out again and say so.
            table = next((e for e in _walk(group) if _role(e) == "AXTable"), None)
            rows = [r for r in _children(table) if _role(r) == "AXRow"] if table is not None else []
            for row in rows[len(before):]:
                _AS.AXUIElementSetAttributeValue(row, _cf("AXSelected"), _TRUE)
            _press(_find(group, "AXButton", "Remove"))
            _wait_for("the wrong item to be removed", lambda: len(_item_paths(group)) == len(before))
            raise UIError(f"the Open dialog picked {added} instead of {name}; it was removed again")
    return _checked("action_add_items", mode, {"action": action, "items": _item_paths(group)})


def action_set_folder(action: str, folder: str, option: str = "To", index: int = 1, mode: str = "ui") -> dict:
    """Set an action's folder pop-up (To: in Copy and Move Finder Items, Where: in New Text File) to folder, through Other…."""
    _mode("action_set_folder", mode)
    full = _existing(folder)
    if not os.path.isdir(full):
        raise ValueError("folder must be a folder")
    _start()
    window, group = _action_group(action, index)
    popup = _labelled(group, "AXPopUpButton", option)
    if popup is None:
        raise NotFound(f"{action} has no {option!r} pop-up")
    _pick(popup, "Other…")
    _choose_in_panel(window, full, None)
    want = " > ".join(p for p in full.strip("/").split("/"))
    _wait_for("the folder to be chosen", lambda: _string(popup, "AXHelp").endswith(want) or _string(popup, "AXValue") == os.path.basename(full))
    return _checked("action_set_folder", mode, {"action": action, "option": option, "folder": full})


def action_set_option(action: str, option: str, value: str | int | bool, index: int = 1, mode: str = "ui") -> dict:
    """Set one of an action's options by its label: a pop-up (To Type, Encoding, File Format, Scale's "By"), a text field
    (Save as, Scale's "Size") or a checkbox (Replacing existing files, Repeat for each subfolder found)."""
    _mode("action_set_option", mode)
    _start()
    window, group = _action_group(action, index)
    if option in ("Size", "By") and action == "Scale Images":
        popup = next((e for e in _children(group) if _role(e) == "AXPopUpButton"), None)
        field = next((e for e in _walk(group) if _role(e) == "AXTextField"), None)
        target = popup if option == "By" else field
        kind = "AXPopUpButton" if option == "By" else "AXTextField"
    else:
        target, kind = None, None
        for role in ("AXPopUpButton", "AXTextField"):
            target = _labelled(group, role, option)
            if target is not None:
                kind = role
                break
        if target is None:
            target = next((e for e in _walk(group) if _role(e) == "AXCheckBox" and _string(e, "AXTitle") == option), None)
            kind = "AXCheckBox" if target is not None else None
    if target is None:
        raise NotFound(f"{action} has no option {option!r}")
    if kind == "AXPopUpButton":
        _pick(target, str(value))
        _wait_for(f"{option} to read {value}", lambda: _string(target, "AXValue") == str(value))
    elif kind == "AXTextField":
        text = str(value)
        _focus(target)
        time.sleep(0.3)
        _key(KEY_A, "command down")
        _paste_text(text, lambda: _string(target, "AXValue") == text)
        _key(RETURN)
    else:
        if not isinstance(value, bool):
            raise ValueError(f"{option} takes True or False")
        if (_number_value(target) == 1) != value:
            _press(target)
        _wait_for(f"{option} to be {value}", lambda: (_number_value(target) == 1) == value)
    return _checked("action_set_option", mode, {"action": action, "option": option, "value": value})


def _number_value(element):
    value = _attr(element, "AXValue")
    if not value:
        return None
    out = ctypes.c_long()
    _CF.CFNumberGetValue.restype, _CF.CFNumberGetValue.argtypes = ctypes.c_bool, [_P, ctypes.c_int, _P]
    return out.value if _CF.CFNumberGetValue(value, 4, ctypes.byref(out)) else None


FILTER_ATTRIBUTES = ("Name", "Kind", "Date last opened", "Date last modified", "Date created", "Size", "Label", "File extension")


def action_set_filter(attribute: str, operator: str, value: str | int | None = None, unit: str | None = None,
                      action: str = "Filter Finder Items", index: int = 1, mode: str = "ui") -> dict:
    """Set Filter Finder Items' first rule: attribute (such as "Date last modified" or "File extension"), operator as Automator
    names it (such as "is not in the last", "is", "contains"), then the value and, for dates and sizes, the unit (days, KB…)."""
    _mode("action_set_filter", mode)
    if attribute not in FILTER_ATTRIBUTES:
        raise ValueError(f"attribute must be one of {FILTER_ATTRIBUTES}")
    _start()
    window, group = _action_group(action, index)

    def popups():
        return [e for e in _walk(group) if _role(e) == "AXPopUpButton"]
    if len(popups()) < 2:
        raise UIError("the filter's rule pop-ups weren't found")
    _pick(popups()[1], attribute)
    _wait_for(f"the rule to be on {attribute}", lambda: _string(popups()[1], "AXValue") == attribute and len(popups()) >= 3)
    _pick(popups()[2], operator)
    _wait_for(f"the rule to read {operator}", lambda: _string(popups()[2], "AXValue") == operator)
    if value is not None:
        field = _wait_for("the rule's value field", lambda: next((e for e in _walk(group) if _role(e) == "AXTextField"), None))
        text = str(value)
        _focus(field)
        time.sleep(0.3)
        _key(KEY_A, "command down")
        _paste_text(text, lambda: _string(field, "AXValue") == text)
        _key(RETURN)
    if unit is not None:
        if len(popups()) < 4:
            raise ValueError(f"{operator!r} takes no unit")
        _pick(popups()[3], unit)
        _wait_for(f"the unit to read {unit}", lambda: _string(popups()[3], "AXValue") == unit)
    return _checked("action_set_filter", mode, {"attribute": attribute, "operator": operator, "value": value, "unit": unit})


def workflow_run(mode: str = "ui") -> dict:
    """Run the workflow in front (Workflow > Run) and wait until it stops. Raises UIError with Automator's message if an action failed."""
    _mode("workflow_run", mode)
    if not _running():
        # Starting Automator here would only open its document chooser; with it closed there is no workflow to run.
        raise NotFound("Automator isn't running, so no workflow is open; nothing was started")
    _start()
    window = _front_workflow()

    def running():
        return _system_events('return enabled of menu item "Stop" of menu "Workflow" of menu bar item "Workflow" of menu bar 1') == "true"
    _menu("Workflow", "Run")
    started = time.monotonic()
    while time.monotonic() - started < 3 and not running():
        time.sleep(0.2)
    _wait_for("the workflow to finish", lambda: not running(), RUN_TIMEOUT, 0.5)
    time.sleep(0.5)

    def status():
        texts = [_string(e, "AXValue").strip() for e in _walk(window) if _role(e) == "AXStaticText" and _string(e, "AXValue")]
        return next((t for t in reversed(texts) if t.startswith(("Workflow completed", "The action", "Workflow failed"))), "")
    sheet = _sheet(window)
    if sheet is None and not status().startswith("Workflow completed"):
        raise UIError(f"the workflow didn't complete: {status() or 'Automator showed no result'}")
    if sheet is not None:
        text = " ".join(_string(e, "AXValue") for e in _walk(sheet) if _role(e) == "AXStaticText" and _string(e, "AXValue"))
        ok = _find(sheet, "AXButton", "OK")
        if ok is not None:
            _press(ok)
        raise UIError(f"the workflow stopped with: {text[:300]}")
    return _checked("workflow_run", mode, {"ran": True, "actions": _action_titles(window)})


# Opening a saved workflow (overnight, in its own section, tested on its own) ----------------------------------------

def _document_path(window) -> str:
    import urllib.parse as _up
    url = _string(window, "AXDocument")
    return unicodedata.normalize("NFC", _up.unquote(_up.urlparse(url).path).rstrip("/")) if url else ""


def workflow_open(path: str, mode: str = "ui") -> dict:
    """Open a saved .workflow in Automator (as a double-click on it would) and bring its window to the front, so the other workflow
    commands act on it. Returns its actions, in order."""
    _mode("workflow_open", mode)
    full = _existing(path)
    if not full.lower().endswith(".workflow") or not os.path.isfile(os.path.join(full, "Contents", "document.wflow")):
        raise ValueError("path must be a saved .workflow")
    want = unicodedata.normalize("NFC", os.path.realpath(full))

    def window():
        return next((w for w in _windows() if _workflow_view(w) is not None and _document_path(w) in (want, unicodedata.normalize("NFC", full))), None)
    started_here = not _running()
    if not (_running() and window() is not None):
        subprocess.run(["open", "-a", "Automator", full], check=True)
        _wait_for("Automator to start", _running, TIMEOUT * 2)
    shown = _wait_for(f"{os.path.basename(full)}'s window", window, TIMEOUT * 2)
    # A fresh Automator can also show its document chooser, a moment after the workflow's window; it is closed with its own
    # Close button, without choosing anything.
    deadline = time.monotonic() + (5 if started_here else 1)
    while time.monotonic() < deadline:
        chooser = _chooser()
        if chooser is not None:
            # The chooser's own buttons are Open an Existing Document…, Close and Choose; Close shuts it without choosing.
            close = _find(chooser, "AXButton", "Close") or _find(chooser, "AXButton", "Cancel")
            if close is not None:
                _press(close)
                time.sleep(0.5)
                continue
        time.sleep(0.3)
    if _chooser() is not None:
        raise UIError("Automator's document chooser didn't close")
    _AS.AXUIElementSetAttributeValue(shown, _cf("AXMain"), _TRUE)
    _AS.AXUIElementPerformAction(shown, _cf("AXRaise"))
    _forward()
    _wait_for(f"{os.path.basename(full)} in front", lambda: _document_path(_attr(_app(), "AXMainWindow")) in (want, unicodedata.normalize("NFC", full)))
    front = _front_workflow()
    _wait_for("its actions", lambda: _action_titles(front), TIMEOUT)
    return _checked("workflow_open", mode, {"name": os.path.basename(full), "path": full, "actions": _action_titles(front)})
