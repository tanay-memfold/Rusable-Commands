"""Anaconda Navigator commands for agents: plain functions with keyword arguments, to remove conda environments.

mode="ui" works on screen: elements are found by role and name through the macOS Accessibility API and pressed. No screen
coordinates. Navigator's own offers (to update itself, or to sign in for AI help) are declined; nothing is signed in or updated.

Errors: AlreadyExists, StateBlocked (the screen holds something the call won't destroy), UIError (an element never appeared, or the
environment didn't appear in time), NotSupported (the mode can't do it or wasn't verified)."""
from __future__ import annotations

import ctypes
import json
import os
import plistlib
import re
import subprocess
import time
import warnings

APP = "Anaconda-Navigator"
BUNDLE_ID = "com.anaconda.io"
CONDA = "/opt/homebrew/anaconda3"
ENVS = CONDA + "/envs"
COMMAND = f"{CONDA}/bin/python {CONDA}/bin/anaconda-navigator"
APP_PLIST = f"{CONDA}/Anaconda-Navigator.app/Contents/Info.plist"
ENV_LIST = os.path.expanduser("~/.conda/environments.txt")
TIMEOUT = 10
START_TIMEOUT = 150
CREATE_TIMEOUT = 900
ESCAPE, SPACE, KEY_A, KEY_V = 53, 49, 0, 9

VERIFIED: dict = {
    "environment_remove": {
        "ui": {
            "macos": "15.6.1 (24G90)",
            "app": "2.6.6"
        }
    }
}
UNSUPPORTED: dict = {}


class AnacondaError(Exception):
    pass


class AlreadyExists(AnacondaError):
    pass


class NotFound(AnacondaError):
    pass


class StateBlocked(AnacondaError):
    pass


class UIError(AnacondaError):
    pass


class NotSupported(AnacondaError):
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




def _pid():
    found = subprocess.run(["pgrep", "-f", "-x", COMMAND], capture_output=True, text=True).stdout.split()
    return int(found[0]) if found else None


def _app():
    pid = _pid()
    if pid is None:
        raise UIError("Anaconda Navigator isn't running")
    return _AS.AXUIElementCreateApplication(pid)


def _windows() -> list:
    return [e for e in _children(_app()) if _role(e) == "AXWindow"]


def _main():
    return next((w for w in _windows() if _string(w, "AXTitle") == "Anaconda Navigator" and _find(w, "AXCheckBox", "Environments")), None)


def _dialogs() -> list:
    return [w for w in _windows() if _string(w, "AXTitle") != "Anaconda Navigator"]


def _texts(root) -> list:
    return [_string(e, "AXValue") or _string(e, "AXTitle") for e in _walk(root) if _role(e) in ("AXStaticText", "AXButton")]


def _system_events(body: str) -> str:
    return _run(["osascript", "-e", f'tell application "System Events" to tell (first process whose unix id is {_pid()})\n{body}\nend tell'])


def _front() -> bool:
    return _system_events("return frontmost") == "true"


def _key(code: int, modifier: str = "") -> None:
    if not _front():
        raise StateBlocked("another app came to the front; nothing more was done")
    _system_events(f"key code {code}" + (f" using {modifier}" if modifier else ""))


def _forward() -> None:
    _system_events("set visible to true\nset frontmost to true")
    _wait_for("Anaconda Navigator in front", _front)


def _press(element) -> None:
    # Navigator's Qt buttons often answer "cannot complete" (-25204) while doing what was asked; the caller checks the outcome.
    if _AS.AXUIElementPerformAction(element, _cf("AXPress")) not in (0, -25204):
        raise UIError("an element couldn't be pressed")


def _decline_offers() -> bool:
    """Decline Navigator's own offers: "Update Application" (No, remind me later) and "Sign in for AI Coding Help" (Escape)."""
    declined = False
    for window in _dialogs():
        later = _find(window, "AXButton", "No, remind me later")
        if later is not None:
            _press(later)
            declined = True
        elif _find(window, "AXButton", "Sign In") is not None and "Sign in for AI Coding Help" in _texts(window):
            _forward()
            _key(ESCAPE)
            declined = True
    if declined:
        time.sleep(1)
    return declined


def _clear() -> None:
    """Close Navigator's passing dialogs; refuse one holding a typed name."""
    for window in _dialogs():
        field = _find(window, "AXTextField", "New environment name")
        if field is not None and _string(field, "AXValue"):
            raise StateBlocked("a Navigator dialog holds a typed name; nothing was done")
        cancel = _find(window, "AXButton", "Cancel")
        if cancel is not None:
            _press(cancel)
        else:
            raise StateBlocked(f"a Navigator dialog is open ({' '.join(t for t in _texts(window) if t)[:80]}); nothing was done")
    _wait_for("Navigator's dialogs to close", lambda: not _dialogs())


def _start() -> None:
    if _pid() is None:
        _run(["open", "-b", BUNDLE_ID])
        _wait_for("Anaconda Navigator to start", lambda: _pid() is not None and _main() is not None, START_TIMEOUT, 1)
        # Its offers come up a few seconds after the window.
        end = time.monotonic() + 15
        while time.monotonic() < end:
            _decline_offers()
            time.sleep(1)
    _forward()
    _decline_offers()
    _clear()


def _environments_page():
    main = _main()
    if main is None:
        raise UIError("Navigator's window isn't showing")
    if _find(main, "AXButton", "Create") is None or _find(main, "AXTextField", "Search Environments") is None:
        # The sidebar's Environments answers to focus and Space, not to AXPress.
        _AS.AXUIElementSetAttributeValue(_find(main, "AXCheckBox", "Environments"), _cf("AXFocused"), _TRUE)
        time.sleep(0.4)
        _key(SPACE)
    _wait_for("the Environments page", lambda: _find(main, "AXButton", "Create") and _find(main, "AXTextField", "Search Environments"), TIMEOUT * 2)
    return main


def _known_names() -> set:
    names = set(os.listdir(ENVS)) if os.path.isdir(ENVS) else set()
    try:
        names |= {os.path.basename(line.strip().rstrip("/")) for line in open(ENV_LIST) if line.strip()}
    except OSError:
        pass
    return names | {"base", "root"}


def _made(path: str) -> bool:
    return os.path.isfile(f"{path}/conda-meta/history") and os.path.exists(f"{path}/bin/python")


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


def _paste_text(text: str, landed) -> None:
    """Put text on the clipboard, paste it with Command-V where the cursor is, wait for landed(), and restore the clipboard."""
    saved = _run(["osascript", "-l", "JavaScript", "-e", CLIPBOARD, "save"])
    try:
        _run(["osascript", "-l", "JavaScript", "-e", CLIPBOARD, "text", text])
        _key(KEY_V, "command down")
        _wait_for("the pasted text to appear", landed)
    finally:
        # What was on the clipboard can be too large for an argument, so it goes through standard input.
        done = subprocess.run(["osascript", "-l", "JavaScript", "-e", CLIPBOARD, "restore"], input=saved, capture_output=True, text=True)
        if done.returncode:
            raise UIError(done.stderr.strip())


# Commands ---------------------------------------------------------------------------------------------------------


# Removing environments (day 4, in its own section, tested on its own) ------------------
# Navigator's environment rows have no names. A row is pressed in the middle of its own frame only after the named search has left
# just the rows for that name, and the selection is checked by name before anything happens: Navigator's Remove dialog names the
# selected environment (it is opened and, when only checking, cancelled), and the root environment is the only one with the
# _anaconda_depends package (looked for with Search Packages).

_CG = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics")


class _Point(ctypes.Structure):
    _fields_ = [("x", ctypes.c_double), ("y", ctypes.c_double)]


_CG.CGEventCreateMouseEvent.restype = _P
_CG.CGEventCreateMouseEvent.argtypes = [_P, ctypes.c_uint32, _Point, ctypes.c_uint32]
_CG.CGEventPost.argtypes = [ctypes.c_uint32, _P]
_AS.AXValueGetValue.restype = ctypes.c_bool
_AS.AXValueGetValue.argtypes = [_P, ctypes.c_int, _P]


def _frame(element):
    point, size = (ctypes.c_double * 2)(), (ctypes.c_double * 2)()
    if not (_AS.AXValueGetValue(_attr(element, "AXPosition"), 1, point) and _AS.AXValueGetValue(_attr(element, "AXSize"), 2, size)):
        return None
    return point[0], point[1], size[0], size[1]


def _click(x: float, y: float) -> None:
    if not _front():
        raise StateBlocked("another app came to the front; nothing more was done")
    for kind in (5, 1, 2):  # move, down, up
        _CG.CGEventPost(0, _CG.CGEventCreateMouseEvent(None, kind, _Point(x, y), 0))
        time.sleep(0.12)


def _env_rows(main) -> list:
    """The environment list's rows: the list beside the Search Environments field."""
    search = _find(main, "AXTextField", "Search Environments")
    box = _frame(search) if search is not None else None
    for element in _walk(main):
        if _role(element) == "AXList" and box is not None:
            frame = _frame(element)
            if frame and abs(frame[0] - (box[0] - 12)) < 30 and frame[1] > box[1]:
                return [r for r in _children(element) if _frame(r)]
    return []


def _search_envs(main, text: str) -> None:
    search = _find(main, "AXTextField", "Search Environments")
    _AS.AXUIElementSetAttributeValue(search, _cf("AXFocused"), _TRUE)
    time.sleep(0.3)
    _key(KEY_A, "command down")
    if text:
        _paste_text(text, lambda: _string(search, "AXValue") == text)
    else:
        _key(51)  # delete
        _wait_for("the search to be empty", lambda: _string(search, "AXValue") == "")
    time.sleep(1.5)


def _remove_dialog():
    return next((w for w in _dialogs() if "Remove environment" in _texts(w)), None)


def _idle(main) -> None:
    """Wait until Navigator has finished loading (no "Loading packages" line, no progress bar); it ignores presses while busy."""
    def quiet():
        return not any(_role(e) == "AXStaticText" and _string(e, "AXValue").startswith("Loading packages") for e in _walk(main))
    try:
        _wait_for("Navigator to finish loading", quiet, CREATE_TIMEOUT // 15, 0.5)
    except UIError:
        pass
    time.sleep(0.5)


def _open_remove(main):
    """Press Remove and return its dialog; pressed once more if the dialog hasn't come in 6 s."""
    for attempt in range(2):
        _press(_find(main, "AXButton", "Remove"))
        try:
            return _wait_for("the Remove environment dialog", _remove_dialog, 6)
        except UIError:
            if attempt == 1:
                raise
            _idle(main)


def _is_root(main) -> bool:
    """The root environment is the only one with the _anaconda_depends package (the Anaconda distribution): it is looked for with Search Packages."""
    field = _find(main, "AXTextField", "Search Packages")
    _AS.AXUIElementSetAttributeValue(field, _cf("AXFocused"), _TRUE)
    time.sleep(0.3)
    _key(KEY_A, "command down")
    _paste_text("_anaconda_depends", lambda: _string(field, "AXValue") == "_anaconda_depends")

    def matches():
        # Navigator's status line: "N packages available matching "_anaconda_depends"".
        line = next((_string(e, "AXValue") for e in _walk(main) if _role(e) == "AXStaticText" and "matching \"_anaconda_depends\"" in _string(e, "AXValue")), "")
        count = line.split(" ", 1)[0]
        return int(count) if count.isdigit() else None
    try:
        found = (_wait_for("the package search", lambda: matches() is not None and (matches() > 0 or time.sleep(1.5) or matches() is not None), 6) and (matches() or 0) > 0)
    except UIError:
        found = False
    _AS.AXUIElementSetAttributeValue(field, _cf("AXFocused"), _TRUE)
    _key(KEY_A, "command down")
    _key(51)
    time.sleep(0.5)
    return found


def _selected_name(main):
    """The selected environment's name, as Navigator's Remove dialog shows it (opened and cancelled)."""
    dialog = _open_remove(main)
    texts = [t for t in _texts(dialog) if t]
    name = texts[texts.index("Name:") + 1] if "Name:" in texts and texts.index("Name:") + 1 < len(texts) else None
    _press(_find(dialog, "AXButton", "Cancel"))
    _wait_for("the Remove dialog to close", lambda: _remove_dialog() is None)
    return name


def _select_env(main, name: str | None) -> None:
    """Select the environment named name (None: the root one, always listed first), checked by name as above."""
    _idle(main)
    _search_envs(main, name or "")
    rows = _wait_for(f"{name or 'the root environment'} in the list", lambda: _env_rows(main), TIMEOUT)
    for row in (rows if name else rows[:1]):
        x, y, w, h = _frame(row)
        _click(x + w * 0.4, y + h / 2)
        time.sleep(1.5)
        _idle(main)
        if (name is None and _is_root(main)) or (name is not None and _selected_name(main) == name):
            return
    raise NotFound(f"no environment named {name} could be selected; nothing was done")


def environment_remove(name: str, mode: str = "ui") -> dict:
    """Remove the conda environment named name and everything in it (Environments page: the environment, Remove, Remove). Navigator's
    dialog must name it before Remove is pressed."""
    _mode("environment_remove", mode)
    if not isinstance(name, str) or not name or name in ("base", "root"):
        raise ValueError("name must be an environment's name; the root environment can't be removed")
    path = f"{ENVS}/{name}"
    if not os.path.isdir(path):
        raise NotFound(f"no environment named {name} in {ENVS}; nothing was done")
    _start()
    main = _environments_page()
    _select_env(main, name)
    dialog = _open_remove(main)
    texts = [t for t in _texts(dialog) if t]
    if name not in texts or path not in texts:
        _press(_find(dialog, "AXButton", "Cancel"))
        raise UIError(f"Navigator's Remove dialog didn't name {name} at {path}; it was cancelled")
    _press(next(e for e in _walk(dialog) if _role(e) == "AXButton" and _string(e, "AXTitle") == "Remove"))
    _wait_for(f"{name} to be removed", lambda: not os.path.exists(os.path.join(path, "conda-meta")), CREATE_TIMEOUT, 2)
    return _checked("environment_remove", mode, {"name": name, "path": path, "removed": True})
