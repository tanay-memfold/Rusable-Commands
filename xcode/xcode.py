"""Xcode commands for agents: plain functions with keyword arguments, to make and open projects.

mode="ui" works on screen: elements are found by role and name through the macOS Accessibility API, menu items are clicked by name,
and text is pasted through the clipboard, which is restored afterwards. No screen coordinates. Opening a project through Xcode's
own scripting brought Xcode to the front, so it isn't offered as a background mode.

Set XCODE_ALLOWED_ROOT to a folder and every path is checked to be inside it, after following links, before anything happens.

Errors: NotFound, AlreadyExists, OutsideAllowedRoot, StateBlocked (the screen holds something the call won't destroy), UIError (an
element never appeared), NotSupported (the mode can't do it or wasn't verified)."""
from __future__ import annotations

import ctypes
import json
import os
import plistlib
import subprocess
import time
import unicodedata
import warnings

APP = "Xcode"
BUNDLE_ID = "com.apple.dt.Xcode"
TIMEOUT = 10
SAVE_TIMEOUT = 20
START_TIMEOUT = 90
ROOT_ENV = "XCODE_ALLOWED_ROOT"
APP_PLIST = "/Applications/Xcode.app/Contents/Info.plist"
KEY_A, KEY_G, KEY_V, RETURN, ESCAPE = 0, 5, 9, 36, 53
PLATFORMS = ("iOS", "macOS")

VERIFIED: dict = {
    "project_build": {
        "ui": {
            "macos": "15.6.1 (24G90)",
            "app": "16.4 (23792)"
        }
    },
    "project_new": {
        "ui": {
            "macos": "15.6.1 (24G90)",
            "app": "16.4 (23792)"
        }
    },
    "project_open": {
        "ui": {
            "macos": "15.6.1 (24G90)",
            "app": "16.4 (23792)"
        }
    }
}
UNSUPPORTED: dict = {}


class XcodeError(Exception):
    pass


class NotFound(XcodeError):
    pass


class Ambiguous(XcodeError):
    pass


class AlreadyExists(XcodeError):
    pass


class OutsideAllowedRoot(XcodeError):
    pass


class StateBlocked(XcodeError):
    pass


class UIError(XcodeError):
    pass


class NotSupported(XcodeError):
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
        raise UIError("Xcode isn't running")
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
    _wait_for("Xcode in front", lambda: _system_events("return frontmost") == "true")




_CF.CFNumberGetValue.restype, _CF.CFNumberGetValue.argtypes = ctypes.c_bool, [_P, ctypes.c_int, _P]


def _number(element, name: str):
    value = _attr(element, name)
    if not value:
        return None
    out = ctypes.c_long()
    return out.value if _CF.CFNumberGetValue(value, 4, ctypes.byref(out)) else None  # 4: kCFNumberSInt64Type


def _is_true(element, name: str) -> bool:
    return _attr(element, name) == _TRUE.value


def _submenu(title: str, parent: str, item: str) -> None:
    if _system_events("return frontmost") != "true":
        raise StateBlocked("another app came to the front; nothing more was done")
    _system_events(f'click menu item "{item}" of menu 1 of menu item "{parent}" of menu "{title}" of menu bar item "{title}" of menu bar 1')


def _sheets() -> list:
    return [s for w in _windows() for s in _children(w) if _role(s) == "AXSheet"]


def _chooser():
    return next((s for s in _sheets() if _string(s, "AXIdentifier") == "Xcode.ProjectTemplateChooserAssistant"), None)


def _start() -> None:
    if not _running():
        _run(["open", "-b", BUNDLE_ID])
        _wait_for("Xcode to start", lambda: _running() and _windows(), START_TIMEOUT, 0.5)
        time.sleep(2)
    _forward()
    for sheet in _sheets():
        # A sheet holding typed text is left alone; an untouched template chooser is cancelled.
        if sheet is _chooser() or _string(sheet, "AXIdentifier") == "Xcode.ProjectTemplateChooserAssistant":
            name = _by_id(sheet, "productName")
            if name is not None and _string(name, "AXValue"):
                raise StateBlocked("Xcode's new-project sheet holds a typed name; nothing was done")
            cancel = _find(sheet, "AXButton", "Cancel")
            if cancel is not None:
                _press(cancel)
                continue
        raise StateBlocked("an Xcode sheet is open; nothing was done")
    _wait_for("Xcode's sheets to close", lambda: not _sheets())


def _full(path: str) -> str:
    return unicodedata.normalize("NFC", _path(path))


def _go_to_folder(panel, folder: str) -> None:
    _key(KEY_G, "{command down, shift down}")
    go = _wait_for("Go to Folder", lambda: _by_id(panel, "GoToWindow"))
    field = _wait_for("the folder field", lambda: _by_id(go, "PathTextField"))
    _key(KEY_A, "command down")
    _paste_text(folder, lambda: unicodedata.normalize("NFC", _string(field, "AXValue")) == unicodedata.normalize("NFC", folder))
    _key(RETURN)
    _wait_for("Go to Folder to close", lambda: _by_id(panel, "GoToWindow") is None)


def _project_windows() -> list:
    return [w for w in _windows() if _string(w, "AXIdentifier") == "Xcode.WorkspaceWindow"]


def _shows(name: str) -> bool:
    want = unicodedata.normalize("NFC", name)
    return any(unicodedata.normalize("NFC", _string(w, "AXTitle")).split(" — ")[0] == want for w in _project_windows())


# Commands ---------------------------------------------------------------------------------------------------------


def project_new(name: str, folder: str, platform: str = "iOS", template: str = "App", organization: str = "com.example",
                git: bool = False, mode: str = "ui") -> dict:
    """Make a new project from a template (File > New > Project…): platform tab, template, Product Name, Organization Identifier,
    then the folder in the save sheet and Create. Xcode makes folder/name/name.xcodeproj. The other options keep Xcode's defaults."""
    _mode("project_new", mode)
    if not isinstance(name, str) or not name.strip() or any(c in name for c in "/:") or name.startswith("."):
        raise ValueError("name must not be empty, start with a dot, or contain / or :")
    if platform not in PLATFORMS:
        raise ValueError(f"platform must be one of {PLATFORMS}")
    if not organization or any(c in organization for c in " /:"):
        raise ValueError("organization must be a reverse-DNS prefix such as com.example")
    where = _full(folder)
    if not os.path.isdir(where):
        raise NotFound(f"no folder at {where}")
    target = os.path.join(where, name)
    if os.path.exists(target):
        raise AlreadyExists(f"{target} already exists; nothing is overwritten")
    _start()
    _submenu("File", "New", "Project…")
    sheet = _wait_for("the template chooser", _chooser, TIMEOUT * 2)
    try:
        tab = _wait_for(f"the {platform} tab", lambda: _find(sheet, "AXRadioButton", platform))
        _press(tab)
        _wait_for(f"the {platform} tab to be chosen", lambda: _number(tab, "AXValue") == 1)
        chooser = _wait_for("the template list", lambda: _find(sheet, "AXList", "template chooser"))
        tile = next((e for e in _walk(chooser) if _role(e) == "AXGroup" and _string(e, "AXDescription") == template), None)
        if tile is None:
            raise NotFound(f"no {platform} template named {template}")
        _AS.AXUIElementSetAttributeValue(tile, _cf("AXSelected"), _TRUE)
        _wait_for(f"the {template} template to be chosen", lambda: _is_true(tile, "AXSelected"))
        _press(_find(sheet, "AXButton", "Next"))
        product = _wait_for("the Product Name field", lambda: _by_id(sheet, "productName"))
        for identifier, value in (("productName", name), ("bundleIdentifierPrefix", organization)):
            field = _wait_for(f"the {identifier} field", lambda identifier=identifier: _by_id(sheet, identifier))
            _focus(field)
            _AS.AXUIElementSetAttributeValue(field, _cf("AXValue"), _cf(value))
            _wait_for(f"{identifier} to read {value}", lambda field=field, value=value: _string(field, "AXValue") == value)
        time.sleep(0.5)
        nxt = _find(sheet, "AXButton", "Next")
        if nxt is None or not _is_true(nxt, "AXEnabled"):
            raise UIError("Xcode didn't take the name and organization (Next is off)")
        _press(nxt)
        panel = _wait_for("the save sheet", lambda: next((e for e in _walk(sheet) if _string(e, "AXIdentifier") == "open-panel"), None), TIMEOUT * 2)
        _go_to_folder(panel, where)
        box = _by_id(panel, "create git repository")
        if box is not None and (_number(box, "AXValue") == 1) != git:
            _press(box)
            _wait_for("the Git choice", lambda: (_number(box, "AXValue") == 1) == git)
        _press(_by_id(panel, "OKButton"))
    except Exception:
        if _chooser() is not None:
            cancel = _by_id(_chooser(), "CancelButton") or _find(_chooser(), "AXButton", "Cancel")
            if cancel is not None:
                _press(cancel)
        raise
    project = os.path.join(target, name + ".xcodeproj")
    _wait_for("the project to be written", lambda: os.path.isfile(os.path.join(project, "project.pbxproj")) and _chooser() is None, SAVE_TIMEOUT)
    _wait_for(f"Xcode's window to show {name}", lambda: _shows(name), SAVE_TIMEOUT)
    return _checked("project_new", mode, {"name": name, "path": project, "folder": target, "platform": platform, "template": template})


def project_open(path: str, mode: str = "ui") -> dict:
    """Open an .xcodeproj or .xcworkspace (File > Open…, going to it in the dialog)."""
    _mode("project_open", mode)
    full = _full(path)
    if not full.endswith((".xcodeproj", ".xcworkspace")):
        raise ValueError("path must be an .xcodeproj or .xcworkspace")
    if not os.path.isdir(full):
        raise NotFound(f"nothing at {full}")
    name = os.path.splitext(os.path.basename(full))[0]
    _start()
    _menu("File", "Open…")
    panel = _wait_for("the Open dialog", lambda: next((w for w in _windows() if _by_id(w, "OKButton") is not None), None), TIMEOUT * 2)
    try:
        _go_to_folder(panel, full)
        _press(_by_id(panel, "OKButton"))
    except Exception:
        cancel = _by_id(panel, "CancelButton")
        if cancel is not None:
            _press(cancel)
        raise
    _wait_for(f"Xcode's window to show {name}", lambda: _shows(name), SAVE_TIMEOUT)
    return _checked("project_open", mode, {"name": name, "path": full})


# Building (added on day 3 in its own section, tested on its own) ---------------------------------------------------

DERIVED = os.path.expanduser("~/Library/Developer/Xcode/DerivedData")


def _activity() -> str:
    """The text in the toolbar's activity view, such as "Build Succeeded"."""
    for window in _project_windows():
        if _is_true(window, "AXMain"):
            for element in _walk(window):
                if _string(element, "AXIdentifier") == "Activity Text":
                    return _string(element, "AXValue")
    return ""


def _window_for(name: str):
    want = unicodedata.normalize("NFC", name)
    return next((w for w in _project_windows() if unicodedata.normalize("NFC", _string(w, "AXTitle")).split(" — ")[0] == want), None)


def _products(name: str) -> list:
    """Built apps for this project in Xcode's DerivedData (folders are named <project>-<hash>)."""
    out = []
    if os.path.isdir(DERIVED):
        for folder in os.listdir(DERIVED):
            if folder.rsplit("-", 1)[0] == name.replace(" ", "_"):
                products = os.path.join(DERIVED, folder, "Build", "Products")
                for base, dirs, _ in os.walk(products):
                    out += [os.path.join(base, d) for d in dirs if d.endswith(".app")]
                    dirs[:] = [d for d in dirs if not d.endswith(".app")]
    return out


def project_build(path: str, mode: str = "ui") -> dict:
    """Build an open-able .xcodeproj with Product > Build for its current scheme and destination, and wait for Build Succeeded
    or Build Failed. It is opened first if Xcode doesn't show it."""
    _mode("project_build", mode)
    full = _full(path)
    if not full.endswith((".xcodeproj", ".xcworkspace")):
        raise ValueError("path must be an .xcodeproj or .xcworkspace")
    if not os.path.isdir(full):
        raise NotFound(f"nothing at {full}")
    name = os.path.splitext(os.path.basename(full))[0]
    if not (_running() and _window_for(name) is not None):
        project_open(path=full)
    _start()
    window = _wait_for(f"Xcode's window for {name}", lambda: _window_for(name))
    _AS.AXUIElementSetAttributeValue(window, _cf("AXMain"), _TRUE)
    _wait_for(f"{name} in front", lambda: _is_true(window, "AXMain"))
    before = _activity()
    began = time.time()
    _menu("Product", "Build")

    def fresh():
        return [p for p in _products(name) if os.path.getmtime(p) >= began - 1]
    # The activity text may still show the last build's result, so wait for it to change (or for a new product) first.
    _wait_for("the build to start", lambda: _activity() != before or fresh(), TIMEOUT * 3, 0.3)

    def finished():
        # A scheme whose platform isn't installed makes Xcode offer to download it ("Download & Install"). Nothing is downloaded:
        # Cancel is pressed and the build is reported as not possible.
        for window in _windows():
            for element in _walk(window):
                if _role(element) == "AXButton" and _string(element, "AXTitle") == "Download & Install":
                    cancel = next((e for e in _walk(window) if _role(e) == "AXButton" and _string(e, "AXTitle") == "Cancel"), None)
                    if cancel is not None:
                        _press(cancel)
                    raise NotSupported("Xcode would have to download platform support to build this scheme; it was declined (Cancel)")
        text = _activity()
        if text.startswith("Build Failed"):
            return "failed"
        if text.startswith("Build Succeeded") and fresh():
            return "succeeded"
        return None
    result = _wait_for("the build to finish", finished, 600, 1)
    # A failed build can leave a partly built .app behind, so products are listed only for a build that succeeded.
    return _checked("project_build", mode, {"name": name, "succeeded": result == "succeeded", "products": sorted(fresh()) if result == "succeeded" else []})
