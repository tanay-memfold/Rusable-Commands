"""Keka commands for agents: plain functions with keyword arguments, to make and open archives with Keka.

mode="ui" works on screen: elements are found by role and name through the macOS Accessibility API, menu items are clicked by name, and
text is pasted through the clipboard, which is restored afterwards. No screen coordinates.

Set KEKA_ALLOWED_ROOT to a folder and every path is checked to be inside it, after following links, before anything happens.

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

APP = "Keka"
BUNDLE_ID = "com.aone.keka"
TIMEOUT = 10
SAVE_TIMEOUT = 15
ROOT_ENV = "KEKA_ALLOWED_ROOT"
APP_PLIST = "/Applications/Keka.app/Contents/Info.plist"

VERIFIED: dict = {
    "archive_create": {
        "ui": {
            "macos": "15.6.1 (24G90)",
            "app": "1.6.0 (5638)"
        }
    },
    "archive_format": {
        "ui": {
            "macos": "15.6.1 (24G90)",
            "app": "1.6.0 (5638)"
        }
    },
    "archive_set_format": {
        "ui": {
            "macos": "15.6.1 (24G90)",
            "app": "1.6.0 (5638)"
        }
    }
}
UNSUPPORTED: dict = {}


class KekaError(Exception):
    pass


class NotFound(KekaError):
    pass


class Ambiguous(KekaError):
    pass


class AlreadyExists(KekaError):
    pass


class OutsideAllowedRoot(KekaError):
    pass


class StateBlocked(KekaError):
    pass


class UIError(KekaError):
    pass


class NotSupported(KekaError):
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
        raise UIError("Keka isn't running")
    return _AS.AXUIElementCreateApplication(int(found[0]))


def _windows() -> list:
    return [e for e in _children(_app()) if _role(e) == "AXWindow"]


def _is_document(window) -> bool:
    """A document window. While minimized, or while Keka is hidden, it reports itself as a dialog."""
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
    _wait_for("Keka in front", lambda: _system_events("return frontmost") == "true")


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


FORMATS = {"zip": "ZIP", "tar": "TAR", "7z": "7Z", "gzip": "GZIP", "bzip2": "BZIP2", "xz": "XZ", "dmg": "DMG", "iso": "ISO"}
SUFFIX = {"zip": ".zip", "tar": ".tar", "7z": ".7z", "gzip": ".gz", "bzip2": ".bz2", "xz": ".xz", "dmg": ".dmg", "iso": ".iso"}
ARCHIVES = (".zip", ".tar", ".7z", ".gz", ".tgz", ".bz2", ".xz", ".rar")

def _clear_transient() -> None:
    """Cancel an Open or Save dialog Keka left showing, unless someone typed in it."""
    for _ in range(4):
        panel = next((w for w in _windows() if not _is_main(w) and (_string(w, "AXIdentifier") in ("save-panel", "open-panel") or
                      _string(w, "AXSubrole") == "AXDialog")), None)
        if panel is None:
            return
        tags = [e for e in _walk(panel) if _role(e) == "AXTextField" and _string(e, "AXIdentifier") != "saveAsNameTextField" and _string(e, "AXValue")]
        if tags:
            raise StateBlocked("Keka shows a dialog with typed text; it was left as it is")
        cancel = _by_id(panel, "CancelButton") or _find(panel, "AXButton", "Cancel")
        if cancel is None:
            raise StateBlocked("Keka shows a dialog it can't safely close; it was left as it is")
        _press(cancel)
        time.sleep(0.5)
    raise UIError("a dialog wouldn't close")


def _is_main(window) -> bool:
    return any(_role(e) == "AXPopUpButton" and _string(e, "AXDescription") == "Format Selector" for e in _walk(window))


def _main_window():
    """The window with the Format pop-up. While minimized, or while Keka is hidden, it doesn't report itself as a standard window."""
    return next((w for w in _windows() if _is_main(w)), None)


def _format_popup(show: bool = False):
    window = _wait_for("Keka's window", _main_window)
    if show and _attr(window, "AXMinimized") == _TRUE.value:
        _AS.AXUIElementSetAttributeValue(window, _cf("AXMinimized"), _FALSE)
        _wait_for("Keka's window to come back", lambda: _attr(window, "AXMinimized") == _FALSE.value)
    return next(e for e in _walk(window) if _role(e) == "AXPopUpButton" and _string(e, "AXDescription") == "Format Selector")


def _current_format() -> str:
    label = _string(_format_popup(), "AXValue")
    return next((k for k, v in FORMATS.items() if v == label), label)


def _start(hidden: bool = False) -> bool:
    """Start Keka if it's closed, and wait until its window is there. True if it was started here."""
    if _running():
        return False
    subprocess.run(["open", *(["-g", "-j"] if hidden else []), "-b", BUNDLE_ID], check=True)
    _wait_for("Keka to start", _running, TIMEOUT * 2)
    _wait_for("Keka's window", _main_window, TIMEOUT * 2)
    return True


def archive_set_format(format: str, mode: str = "ui") -> dict:
    """Choose the format Keka makes archives in, with the Format pop-up in Keka's window: zip, tar, 7z, gzip, bzip2, xz, dmg or iso."""
    _mode("archive_set_format", mode)
    if format not in FORMATS:
        raise ValueError(f"format must be one of {', '.join(FORMATS)}")
    _start()
    _forward()
    popup = _format_popup(show=True)
    if _string(popup, "AXValue") != FORMATS[format]:
        _press(popup)
        menu = _wait_for("the Format menu", lambda: next((e for e in _walk(popup) if _role(e) == "AXMenu"), None))
        item = next((e for e in _walk(menu) if _role(e) == "AXMenuItem" and _string(e, "AXTitle") == FORMATS[format]), None)
        if item is None:
            _key(ESCAPE)
            raise UIError(f"the Format menu has no {FORMATS[format]}")
        _press(item)
        _wait_for(f"the format {FORMATS[format]}", lambda: _string(_format_popup(show=True), "AXValue") == FORMATS[format])
    return _checked("archive_set_format", mode, {"format": format})


def archive_format(mode: str = "ui") -> dict:
    """The format Keka makes archives in, read from its window."""
    _mode("archive_format", mode)
    _start()
    return _checked("archive_format", mode, {"format": _current_format()})


def _new_items(folder: str, before: set, test, timeout: float) -> list:
    def made():
        now = sorted(n for n in set(os.listdir(folder)) - before if not n.startswith(".") and test(n))
        return now or None
    found = _wait_for("Keka's result", made, timeout)
    seen = []
    _wait_for("Keka to finish writing", lambda: seen.append([_stamp(os.path.join(folder, n)) for n in found]) or
              (len(seen) >= 3 and seen[-1] == seen[-2] == seen[-3]), timeout)
    return found


def _stamp(path: str):
    if os.path.isdir(path):
        return sorted((os.path.relpath(os.path.join(b, f), path), os.path.getsize(os.path.join(b, f))) for b, _, fs in os.walk(path) for f in fs)
    return os.path.getsize(path)


def _same_folder(paths: list) -> tuple:
    if not paths:
        raise ValueError("give at least one path")
    full = [_existing(p) for p in paths]
    folders = {os.path.dirname(p) for p in full}
    if len(folders) != 1:
        raise ValueError("all the items must be in the same folder")
    return full, folders.pop()


def archive_create(paths: list, mode: str = "ui") -> dict:
    """Make an archive of items in the same folder in the format set in Keka: the items are opened with Keka, which asks where to
    save, and the archive is saved next to them under Keka's own name for it. The items stay."""
    _mode("archive_create", mode)
    full, folder = _same_folder(paths)
    if not _running() or _attr(_app(), "AXHidden") == _TRUE.value:
        raise NotSupported("archive_create needs Keka open and not hidden: items handed to a closed or hidden Keka were dropped "
                           "in testing, even after two fixes. Open Keka first; nothing was done")
    _forward()
    _clear_transient()
    fmt = _current_format()
    suffix = SUFFIX.get(fmt, "")
    before = set(os.listdir(folder))
    subprocess.run(["open", "-a", APP, *full], check=True, capture_output=True)
    panel = _wait_for("Keka's save dialog", lambda: next((w for w in _windows() if _string(w, "AXIdentifier") == "save-panel"
                                                          and _string(w, "AXTitle").startswith("Compress")), None), SAVE_TIMEOUT * 2)
    try:
        name = _string(_by_id(panel, "saveAsNameTextField"), "AXValue")
        if not name.lower().endswith(suffix) or os.path.lexists(os.path.join(folder, name)):
            raise AlreadyExists(f"Keka would save {name} in {folder}, which isn't a new {suffix} file; nothing was made")
        where = _by_id(panel, "where popup")
        if _string(where, "AXValue") != os.path.basename(folder):
            _AS.AXUIElementSetAttributeValue(_by_id(panel, "saveAsNameTextField"), _cf("AXFocused"), _TRUE)
            _key(KEY_G, "{command down, shift down}")
            go = _wait_for("Go to Folder", lambda: _by_id(panel, "GoToWindow"))
            field = _wait_for("the folder field", lambda: _by_id(go, "PathTextField"))
            _key(KEY_A, "command down")
            _paste_text(folder, lambda: _string(field, "AXValue") == folder)
            _key(RETURN)
            _wait_for("the folder to be chosen", lambda: _string(where, "AXValue") == os.path.basename(folder))
        _press(_by_id(panel, "OKButton"))
    except Exception:
        cancel = _by_id(panel, "CancelButton")
        if cancel is not None:
            _press(cancel)
        raise
    made = _new_items(folder, before, lambda n: n.lower().endswith(suffix), SAVE_TIMEOUT * 4)
    if [unicodedata.normalize("NFC", n) for n in made] != [unicodedata.normalize("NFC", name)]:
        raise UIError(f"expected {name}, found {made}")
    name = made[0]
    return _checked("archive_create", mode, {"name": name, "path": os.path.join(folder, name), "format": fmt, "from": full})
