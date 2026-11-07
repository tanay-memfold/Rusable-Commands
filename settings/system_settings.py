"""System Settings commands for agents: plain functions with keyword arguments, for the desktop wallpaper and the apps that open at
login.

mode="ui" works on screen: panes are opened by System Settings' own x-apple.systempreferences links, and buttons, rows and the Open
dialog are found by name or identifier through the macOS Accessibility API. Wallpaper buttons ignore the Accessibility press, so a
wallpaper is clicked in the middle of its own named button's frame, only once that frame is wholly inside the visible wallpaper list
(scrolled there with the wheel over the list's own frame). No fixed screen positions. Paths are pasted through the clipboard, which is
restored afterwards.

Errors: NotFound, AlreadyExists, StateBlocked (the screen holds something the call won't destroy, or the change needs something
the call won't do, like a download), UIError (an element never appeared, or the result wasn't seen in time), NotSupported (the mode
can't do it or wasn't verified)."""
from __future__ import annotations

import ctypes
import json
import os
import plistlib
import subprocess
import time
import unicodedata
import warnings

APP = "System Settings"
TIMEOUT = 10
SAVE_TIMEOUT = 15
ROOT_ENV = "SETTINGS_ALLOWED_ROOT"  # not used for app paths: apps are read, never written
APP_PLIST = "/System/Applications/System Settings.app/Contents/Info.plist"
WALLPAPER_PANE = "x-apple.systempreferences:com.apple.Wallpaper-Settings.extension"
LOGIN_PANE = "x-apple.systempreferences:com.apple.LoginItems-Settings.extension"
GENERAL_PANE = "x-apple.systempreferences:com.apple.systempreferences.GeneralSettings"
WALLPAPER_INDEX = os.path.expanduser("~/Library/Application Support/com.apple.wallpaper/Store/Index.plist")

VERIFIED: dict = {
    "appearance_set": {
        "ui": {
            "macos": "15.6.1 (24G90)",
            "app": "15.0 (15.0)"
        }
    },
    "dock_set": {
        "ui": {
            "macos": "15.6.1 (24G90)",
            "app": "15.0 (15.0)"
        }
    },
    "login_item_add": {
        "ui": {
            "macos": "15.6.1 (24G90)",
            "app": "15.0 (15.0)"
        }
    },
    "login_item_list": {
        "ui": {
            "macos": "15.6.1 (24G90)",
            "app": "15.0 (15.0)"
        }
    },
    "login_item_remove": {
        "ui": {
            "macos": "15.6.1 (24G90)",
            "app": "15.0 (15.0)"
        }
    },
    "wallpaper_list": {
        "ui": {
            "macos": "15.6.1 (24G90)",
            "app": "15.0 (15.0)"
        }
    },
    "wallpaper_set": {
        "ui": {
            "macos": "15.6.1 (24G90)",
            "app": "15.0 (15.0)"
        }
    }
}
UNSUPPORTED: dict = {}


class SettingsError(Exception):
    pass


class NotFound(SettingsError):
    pass


class Ambiguous(SettingsError):
    pass


class AlreadyExists(SettingsError):
    pass


class OutsideAllowedRoot(SettingsError):
    pass


class StateBlocked(SettingsError):
    pass


class UIError(SettingsError):
    pass


class NotSupported(SettingsError):
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
        raise UIError("System Settings isn't running")
    return _AS.AXUIElementCreateApplication(int(found[0]))


def _windows() -> list:
    return [e for e in _children(_app()) if _role(e) == "AXWindow"]


def _sheet(window):
    return next((e for e in _children(window) if _role(e) == "AXSheet"), None)


def _by_id(root, identifier: str):
    return next((e for e in _walk(root) if _string(e, "AXIdentifier") == identifier), None)


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
    _wait_for("System Settings in front", lambda: _system_events("return frontmost") == "true")





def _number_of(element):
    value = _attr(element, "AXValue")
    if not value:
        return None
    out = ctypes.c_long()
    _CF.CFNumberGetValue.restype, _CF.CFNumberGetValue.argtypes = ctypes.c_bool, [_P, ctypes.c_int, _P]
    return out.value if _CF.CFNumberGetValue(value, 4, ctypes.byref(out)) else None


_CG = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics")


class _Point(ctypes.Structure):
    _fields_ = [("x", ctypes.c_double), ("y", ctypes.c_double)]


_CG.CGEventCreateMouseEvent.restype = _P
_CG.CGEventCreateMouseEvent.argtypes = [_P, ctypes.c_uint32, _Point, ctypes.c_uint32]
_CG.CGEventPost.argtypes = [ctypes.c_uint32, _P]
_AS.AXValueGetValue.restype = ctypes.c_bool
_AS.AXValueGetValue.argtypes = [_P, ctypes.c_int, _P]




def _bool(element, name: str) -> bool:
    value = _attr(element, name)
    if not value:
        return False
    _CF.CFBooleanGetValue.restype, _CF.CFBooleanGetValue.argtypes = ctypes.c_bool, [_P]
    return bool(_CF.CFBooleanGetValue(value))


def _frame(element) -> tuple:
    point, size = (ctypes.c_double * 2)(), (ctypes.c_double * 2)()
    if not (_AS.AXValueGetValue(_attr(element, "AXPosition"), 1, point) and _AS.AXValueGetValue(_attr(element, "AXSize"), 2, size)):
        raise UIError("an element's frame couldn't be read")
    return point[0], point[1], size[0], size[1]


def _inside(inner: tuple, outer: tuple) -> bool:
    return (inner[0] >= outer[0] and inner[1] >= outer[1] and inner[0] + inner[2] <= outer[0] + outer[2]
            and inner[1] + inner[3] <= outer[1] + outer[3])


_CG.CGEventCreateScrollWheelEvent.restype = _P
_CG.CGEventCreateScrollWheelEvent.argtypes = [_P, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_int32]
_CG.CGEventSetLocation.argtypes = [_P, _Point]


def _front_check() -> None:
    if _system_events("return frontmost") != "true":
        raise StateBlocked("another app came to the front; nothing more was done")


def _click_middle(element) -> None:
    x, y, w, h = _frame(element)
    _front_check()
    for kind in (5, 1, 2):
        _CG.CGEventPost(0, _CG.CGEventCreateMouseEvent(None, kind, _Point(x + w / 2, y + h / 2), 0))
        time.sleep(0.12)


def _scroll_into(element, area) -> None:
    """Scroll area with the wheel (over the middle of its own frame) until element is wholly inside it."""
    for _ in range(40):
        box, inner = _frame(area), _frame(element)
        if _inside(inner, box):
            return
        if inner[0] < box[0] or inner[0] + inner[2] > box[0] + box[2]:
            raise UIError("the element is outside the list sideways, where the wheel doesn't reach")
        _front_check()
        event = _CG.CGEventCreateScrollWheelEvent(None, 0, 1, 60 if inner[1] < box[1] else -60)
        _CG.CGEventSetLocation(event, _Point(box[0] + box[2] / 2, box[1] + box[3] / 2))
        _CG.CGEventPost(0, event)
        time.sleep(0.35)
    raise UIError("the element couldn't be scrolled into view")


def _blocking_sheet():
    """A sheet (an Open dialog, a question) already on a System Settings window."""
    for window in _windows():
        sheet = _sheet(window)
        if sheet is not None:
            return sheet
    return None


def _open_pane(url: str, title: str):
    if _running() and _blocking_sheet() is not None:
        raise StateBlocked("System Settings has a dialog open; close it first, nothing was done")
    if _running() and any(_string(w, "AXTitle") == title for w in _windows()):
        # A pane that's already showing doesn't pick up changes made elsewhere (seen with Open at Login), so it's reloaded by
        # going to General first.
        subprocess.run(["open", GENERAL_PANE], check=True)
        _wait_for("another pane", lambda: not any(_string(w, "AXTitle") == title for w in _windows()), TIMEOUT)
    subprocess.run(["open", url], check=True)
    _wait_for("System Settings to start", _running, TIMEOUT * 2)
    window = _wait_for(f"the {title} pane", lambda: next((w for w in _windows() if _string(w, "AXTitle") == title), None), TIMEOUT * 2)
    _forward()
    return window


def _with_id_prefix(root, prefix: str):
    return next((e for e in _walk(root) if _string(e, "AXIdentifier").startswith(prefix)), None)


# Wallpaper --------------------------------------------------------------------------------------------------------

def _wallpaper_area(window):
    area = next((e for e in _walk(window) if _role(e) == "AXScrollArea" and _string(e, "AXDescription") == "Wallpapers"), None)
    if area is None:
        raise UIError("the Wallpapers list wasn't found")
    return area


def _wallpaper_buttons(area) -> list:
    """(group, button) for the wallpapers the list holds now, in screen order: each group's heading, then its buttons. A wallpaper
    button's identifier is its name followed by ";" (and "isRemote" when it isn't on this Mac)."""
    out, group = [], ""
    for element in _walk(area):
        identifier = _string(element, "AXIdentifier")
        if _role(element) == "AXStaticText" and _string(element, "AXValue"):
            group = _string(element, "AXValue")
        elif identifier.startswith(("Show All: ", "Show Less: ")):  # also names the group when its heading has scrolled out
            group = identifier.split(": ", 1)[1]
        elif _role(element) == "AXButton" and identifier.startswith(_string(element, "AXDescription") + ";"):
            out.append((group, element))
    return out


def _wheel(area, pixels: int) -> None:
    _front_check()
    box = _frame(area)
    event = _CG.CGEventCreateScrollWheelEvent(None, 0, 1, pixels)
    _CG.CGEventSetLocation(event, _Point(box[0] + box[2] / 2, box[1] + box[3] / 2))
    _CG.CGEventPost(0, event)
    time.sleep(0.35)


def _collapse_groups(window) -> None:
    """Any group opened with Show All is closed again (Show Less), so every group is one row."""
    for element in list(_walk(window)):
        if _string(element, "AXIdentifier").startswith("Show Less: "):
            _press(element)
            time.sleep(0.6)


def _scan(window, area, want=None):
    """Scroll the list from the top down (the wheel over the list's own frame), as it loads groups lazily, opening each group with
    its own Show All button so every wallpaper is listed. Returns {name: (group, remote)} for all, or stops at want and returns
    (group, button). Groups are closed again by the caller."""
    for _ in range(12):
        _wheel(area, 400)
    seen, opened, still = {}, set(), 0
    for _ in range(150):
        before = len(seen) + len(opened)
        for element in list(_walk(area)):
            identifier = _string(element, "AXIdentifier")
            if identifier.startswith("Show All: ") and identifier not in opened:
                opened.add(identifier)
                _press(element)
                time.sleep(0.6)
        for group, button in _wallpaper_buttons(area):
            name = _string(button, "AXDescription")
            if want is not None and name == want:
                return group, button
            if name not in seen or not seen[name][0]:
                seen[name] = (group, "isRemote" in _string(button, "AXIdentifier"))
        still = still + 1 if len(seen) + len(opened) == before else 0
        if still >= 3:
            break
        _wheel(area, -300)
    return None if want is not None else seen


def _selected_wallpaper(window) -> str:
    label = _with_id_prefix(window, "SelectedDesktop: ")
    return _string(label, "AXIdentifier")[len("SelectedDesktop: "):] if label is not None else ""


def wallpaper_list(mode: str = "ui") -> list:
    """Every wallpaper the Wallpaper pane offers: [{name, on_this_mac, current}]. Ones not on this Mac would be downloaded
    from Apple when chosen."""
    _mode("wallpaper_list", mode)
    window = _open_pane(WALLPAPER_PANE, "Wallpaper")
    area = _wait_for("the Wallpapers list", lambda: _wallpaper_area(window), TIMEOUT * 2)
    _wait_for("the wallpapers", lambda: _wallpaper_buttons(area), TIMEOUT * 2)
    _collapse_groups(window)
    current = _selected_wallpaper(window)
    out = [{"name": name, "on_this_mac": not remote, "current": name == current}
           for name, (group, remote) in _scan(window, area).items()]
    _collapse_groups(window)
    return _checked("wallpaper_list", mode, out)


def wallpaper_set(name: str, mode: str = "ui") -> dict:
    """Set the desktop picture of every display and Space to the named wallpaper from the Wallpaper pane (System Settings >
    Wallpaper). Only wallpapers already on this Mac: one that would be downloaded from Apple first raises StateBlocked."""
    _mode("wallpaper_set", mode)
    if not isinstance(name, str) or not name.strip():
        raise ValueError("name must be a wallpaper's name")
    window = _open_pane(WALLPAPER_PANE, "Wallpaper")
    area = _wait_for("the Wallpapers list", lambda: _wallpaper_area(window), TIMEOUT * 2)
    _wait_for("the wallpapers", lambda: _wallpaper_buttons(area), TIMEOUT * 2)
    all_spaces = _by_id(window, "ShowOnAllDisplays")
    if all_spaces is not None and _number_of(all_spaces) == 0:
        raise StateBlocked("Show on all Spaces is off, so this would change only the current Space; nothing was done")
    if _selected_wallpaper(window) == name:
        return _checked("wallpaper_set", mode, {"wallpaper": name, "changed": False})
    _collapse_groups(window)
    found = _scan(window, area, want=name)
    if found is None:
        _collapse_groups(window)
        raise NotFound(f"System Settings offers no wallpaper named {name!r}")
    group, button = found
    if "isRemote" in _string(button, "AXIdentifier"):
        _collapse_groups(window)
        raise StateBlocked(f"{name!r} isn't on this Mac; choosing it would download it from Apple, so nothing was done")
    _scroll_into(button, area)
    if not _inside(_frame(button), _frame(window)):
        raise UIError(f"{name!r} isn't inside the System Settings window")
    _click_middle(button)
    _wait_for(f"{name!r} to be the wallpaper", lambda: _selected_wallpaper(window) == name, SAVE_TIMEOUT)
    _collapse_groups(window)
    return _checked("wallpaper_set", mode, {"wallpaper": name, "changed": True})


# Login items ------------------------------------------------------------------------------------------------------

def _login_outline(window):
    """The Open at Login list: the pane's first outline after the sidebar."""
    return _wait_for("the Open at Login list", lambda: next((e for e in _walk(window) if _role(e) == "AXOutline"
                                                          and _string(e, "AXDescription") != "Sidebar"), None), TIMEOUT * 2)


def _login_rows(outline) -> list:
    out = []
    for row in _children(outline):
        if _role(row) == "AXRow":
            texts = [_string(e, "AXValue") for e in _walk(row) if _role(e) == "AXStaticText"]
            if texts:
                out.append((texts[0], texts[1] if len(texts) > 1 else "", row))
    return out


def login_item_list(mode: str = "ui") -> list:
    """The apps and items that open at login (System Settings > General > Login Items & Extensions > Open at Login): [{name, kind}],
    in the pane's order (by name)."""
    _mode("login_item_list", mode)
    window = _open_pane(LOGIN_PANE, "Login Items & Extensions")
    outline = _login_outline(window)
    time.sleep(0.5)
    return _checked("login_item_list", mode, [{"name": n, "kind": k} for n, k, _ in _login_rows(outline)])


def _app_name(full: str) -> str:
    try:
        with open(os.path.join(full, "Contents", "Info.plist"), "rb") as handle:
            info = plistlib.load(handle)
        return info.get("CFBundleDisplayName") or info.get("CFBundleName") or os.path.basename(full)[:-4]
    except (OSError, plistlib.InvalidFileException):
        return os.path.basename(full)[:-4]


def login_item_add(app_path: str, mode: str = "ui") -> dict:
    """Add an app to Open at Login: the pane's Add (+) button, then the app chosen in the Open dialog."""
    _mode("login_item_add", mode)
    full = os.path.abspath(os.path.expanduser(app_path)).rstrip("/")
    if not full.endswith(".app"):
        raise ValueError("app_path must be an .app")
    if not os.path.isdir(full):
        raise NotFound(f"no app at {full}")
    window = _open_pane(LOGIN_PANE, "Login Items & Extensions")
    outline = _login_outline(window)
    time.sleep(0.5)
    shown = os.path.basename(full)[:-4]
    if any(n in (shown, _app_name(full)) for n, _, _ in _login_rows(outline)):
        raise AlreadyExists(f"{shown} already opens at login")
    before = len(_login_rows(outline))
    add = _wait_for("the Add button", lambda: next((e for e in _walk(window) if _role(e) == "AXButton" and _string(e, "AXDescription") == "Add"), None))
    _press(add)
    panel = _wait_for("the Open dialog", lambda: _by_id(window, "open-panel"), TIMEOUT)
    try:
        _key(KEY_G, "{command down, shift down}")
        go = _wait_for("Go to Folder", lambda: _by_id(panel, "GoToWindow"))
        field = _wait_for("the folder field", lambda: _by_id(go, "PathTextField"))
        _key(KEY_A, "command down")
        _paste_text(full, lambda: _string(field, "AXValue") == full)
        _key(RETURN)
        _wait_for("Go to Folder to close", lambda: _by_id(panel, "GoToWindow") is None)
        ok = _wait_for("the Open button", lambda: _by_id(panel, "OKButton"))
        _press(ok)
    except Exception:
        cancel = _by_id(panel, "CancelButton") if _by_id(window, "open-panel") is not None else None
        if cancel is not None:
            _press(cancel)
        raise
    _wait_for("the Open dialog to close", lambda: _by_id(window, "open-panel") is None, TIMEOUT)
    row = _wait_for(f"{shown} in Open at Login", lambda: next(((n, k) for n, k, _ in _login_rows(outline) if n in (shown, _app_name(full))), None), SAVE_TIMEOUT)
    if len(_login_rows(outline)) != before + 1:
        raise UIError("Open at Login didn't gain exactly one item")
    return _checked("login_item_add", mode, {"name": row[0], "kind": row[1], "path": full})


def login_item_remove(name: str, mode: str = "ui") -> dict:
    """Stop an item opening at login: its row in Open at Login is selected (checked by name), then the pane's Remove (−) button.
    The app itself isn't touched."""
    _mode("login_item_remove", mode)
    if not isinstance(name, str) or not name.strip():
        raise ValueError("name must be an item's name")
    window = _open_pane(LOGIN_PANE, "Login Items & Extensions")
    outline = _login_outline(window)
    time.sleep(0.5)
    rows = [(n, r) for n, _, r in _login_rows(outline) if n == name]
    if not rows:
        raise NotFound(f"nothing named {name!r} opens at login")
    if len(rows) > 1:
        raise Ambiguous(f"more than one login item is named {name!r}")
    before = len(_login_rows(outline))
    _AS.AXUIElementSetAttributeValue(rows[0][1], _cf("AXSelected"), _TRUE)

    def only_it():
        selected = [n for n, _, r in _login_rows(outline) if _bool(r, "AXSelected")]
        return selected == [name]
    _wait_for(f"only {name!r} to be selected", only_it, TIMEOUT)
    remove = next((e for e in _walk(window) if _role(e) == "AXButton" and _string(e, "AXDescription") == "Remove"), None)
    if remove is None:
        raise UIError("the Remove button wasn't found")
    _press(remove)
    _wait_for(f"{name!r} to leave Open at Login", lambda: all(n != name for n, _, _ in _login_rows(outline)) and len(_login_rows(outline)) == before - 1, SAVE_TIMEOUT)
    return _checked("login_item_remove", mode, {"name": name, "removed": True})


# Appearance (overnight, in its own section, tested on its own) -----------------------------------------------------

APPEARANCE_PANE = "x-apple.systempreferences:com.apple.Appearance-Settings.extension"


def appearance_set(mode_name: str, mode: str = "ui") -> dict:
    """Set macOS's appearance to "light", "dark" or "auto" with System Settings > Appearance's own named buttons."""
    _mode("appearance_set", mode)
    title = {"light": "Light", "dark": "Dark", "auto": "Auto"}.get(mode_name if isinstance(mode_name, str) else None)
    if title is None:
        raise ValueError('mode_name must be "light", "dark" or "auto"')
    window = _open_pane(APPEARANCE_PANE, "Appearance")
    button = _wait_for(f"the {title} button", lambda: next((e for e in _walk(window) if _role(e) == "AXButton"
                                                             and _string(e, "AXDescription") == title), None), TIMEOUT * 2)
    if _bool(button, "AXSelected"):
        return _checked("appearance_set", mode, {"appearance": mode_name, "changed": False})
    _front_check()
    _press(button)
    _wait_for(f"{title} to be selected", lambda: _bool(button, "AXSelected"), TIMEOUT)
    return _checked("appearance_set", mode, {"appearance": mode_name, "changed": True})


# Dock (overnight, in its own section, tested on its own) ------------------------------------------------------------

DOCK_PANE = "x-apple.systempreferences:com.apple.Desktop-Settings.extension"


def dock_set(autohide: bool | None = None, position: str | None = None, show_recents: bool | None = None, mode: str = "ui") -> dict:
    """Change the Dock in System Settings > Desktop & Dock: autohide (Automatically hide and show the Dock), position ("left",
    "bottom" or "right") and show_recents (Show suggested and recent apps in Dock). Only the values given change."""
    _mode("dock_set", mode)
    for name, value in (("autohide", autohide), ("show_recents", show_recents)):
        if value is not None and not isinstance(value, bool):
            raise ValueError(f"{name} must be True, False or None")
    place = {"left": "Left", "bottom": "Bottom", "right": "Right"}.get(position) if position is not None else None
    if position is not None and place is None:
        raise ValueError('position must be "left", "bottom" or "right"')
    if autohide is None and position is None and show_recents is None:
        raise ValueError("give autohide, position or show_recents")
    window = _open_pane(DOCK_PANE, "Desktop & Dock")
    changed = []
    for identifier, value, label in (("auto-hide-dock", autohide, "autohide"), ("show-recents", show_recents, "show_recents")):
        if value is None:
            continue
        box = _wait_for(f"the {label} switch", lambda identifier=identifier: _by_id(window, identifier), TIMEOUT * 2)
        if (_number_of(box) == 1) != value:
            _front_check()
            _press(box)
            _wait_for(f"{label} to change", lambda box=box, value=value: (_number_of(box) == 1) == value, TIMEOUT)
            changed.append(label)
    if place is not None:
        menu = _wait_for("the Position on screen menu", lambda: _by_id(window, "position"), TIMEOUT * 2)
        if _string(menu, "AXValue") != place:
            _front_check()
            _press(menu)
            item = _wait_for(f"{place} in the menu", lambda: next((e for e in _walk(menu) if _role(e) == "AXMenuItem" and _string(e, "AXTitle") == place), None))
            _press(item)
            _wait_for(f"the Dock to move {position}", lambda: _string(menu, "AXValue") == place, TIMEOUT)
            changed.append("position")
    box_hide, box_recent, menu = _by_id(window, "auto-hide-dock"), _by_id(window, "show-recents"), _by_id(window, "position")
    return _checked("dock_set", mode, {"autohide": _number_of(box_hide) == 1, "position": _string(menu, "AXValue").lower(),
                                       "show_recents": _number_of(box_recent) == 1, "changed": changed})
