"""Preview commands for agents: plain functions with keyword arguments, for images and PDFs in Preview.

mode="ui" works on screen: elements are found by role and name through the macOS Accessibility API, menu items are clicked by name, and
text is pasted through the clipboard, which is restored afterwards. No screen coordinates.

Set PREVIEW_ALLOWED_ROOT to a folder and every path is checked to be inside it, after following links, before anything happens.

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

APP = "Preview"
BUNDLE_ID = "com.apple.Preview"
TIMEOUT = 10
SAVE_TIMEOUT = 15
ROOT_ENV = "PREVIEW_ALLOWED_ROOT"
APP_PLIST = "/System/Applications/Preview.app/Contents/Info.plist"

VERIFIED: dict = {
    "document_close": {
        "ui": {
            "macos": "15.6.1 (24G90)",
            "app": "11.0 (1069.7.1)"
        }
    },
    "document_export": {
        "ui": {
            "macos": "15.6.1 (24G90)",
            "app": "11.0 (1069.7.1)"
        }
    },
    "document_list": {
        "ui": {
            "macos": "15.6.1 (24G90)",
            "app": "11.0 (1069.7.1)"
        }
    },
    "document_open": {
        "ui": {
            "macos": "15.6.1 (24G90)",
            "app": "11.0 (1069.7.1)"
        }
    },
    "image_adjust": {
        "ui": {
            "macos": "15.6.1 (24G90)",
            "app": "11.0 (1069.7.1)"
        }
    },
    "image_crop": {
        "ui": {
            "macos": "15.6.1 (24G90)",
            "app": "11.0 (1069.7.1)"
        }
    },
    "image_flip": {
        "ui": {
            "macos": "15.6.1 (24G90)",
            "app": "11.0 (1069.7.1)"
        }
    },
    "image_resize": {
        "ui": {
            "macos": "15.6.1 (24G90)",
            "app": "11.0 (1069.7.1)"
        }
    },
    "image_rotate": {
        "ui": {
            "macos": "15.6.1 (24G90)",
            "app": "11.0 (1069.7.1)"
        }
    },
    "pdf_append_file": {
        "ui": {
            "macos": "15.6.1 (24G90)",
            "app": "11.0 (1069.7.1)"
        }
    },
    "pdf_delete_page": {
        "ui": {
            "macos": "15.6.1 (24G90)",
            "app": "11.0 (1069.7.1)"
        }
    },
    "pdf_insert_blank_page": {
        "ui": {
            "macos": "15.6.1 (24G90)",
            "app": "11.0 (1069.7.1)"
        }
    },
    "pdf_move_page": {
        "ui": {
            "macos": "15.6.1 (24G90)",
            "app": "11.0 (1069.7.1)"
        }
    },
    "pdf_rotate_page": {
        "ui": {
            "macos": "15.6.1 (24G90)",
            "app": "11.0 (1069.7.1)"
        }
    }
}
UNSUPPORTED: dict = {}


class PreviewError(Exception):
    pass


class NotFound(PreviewError):
    pass


class Ambiguous(PreviewError):
    pass


class AlreadyExists(PreviewError):
    pass


class OutsideAllowedRoot(PreviewError):
    pass


class StateBlocked(PreviewError):
    pass


class UIError(PreviewError):
    pass


class NotSupported(PreviewError):
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
        raise UIError("Preview isn't running")
    return _AS.AXUIElementCreateApplication(int(found[0]))


def _windows() -> list:
    return [e for e in _children(_app()) if _role(e) == "AXWindow"]


def _is_document(window) -> bool:
    """A document window. While minimized, or while Preview is hidden, it reports itself as a dialog."""
    subrole = _string(window, "AXSubrole")
    if subrole == "AXStandardWindow":
        return True
    return subrole == "AXDialog" and bool(_string(window, "AXDocument")) and \
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
    _wait_for("Preview in front", lambda: _system_events("return frontmost") == "true")


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


IMAGES = (".png", ".jpg", ".jpeg", ".heic", ".tif", ".tiff", ".gif", ".bmp")
FORMATS = {"png": "PNG", "jpeg": "JPEG", "heic": "HEIC", "tiff": "TIFF", "pdf": "PDF"}
SUFFIX = {"png": (".png",), "jpeg": (".jpg", ".jpeg"), "heic": (".heic",), "tiff": (".tif", ".tiff"), "pdf": (".pdf",)}


def _kind(full: str, allowed=IMAGES + (".pdf",)) -> str:
    if not full.lower().endswith(allowed):
        raise ValueError(f"{full} must end in one of {', '.join(allowed)}")
    return full


def _same(a: str, b: str) -> bool:
    return unicodedata.normalize("NFC", os.path.realpath(a)) == unicodedata.normalize("NFC", os.path.realpath(b))


def _clear_transient() -> None:
    """Close an open menu and an empty Open dialog. Dialogs on documents are never touched."""
    for _ in range(8):
        panel = next((w for w in _windows() if _string(w, "AXSubrole") in ("AXDialog", "AXFloatingWindow") and not _is_document(w)), None)
        if panel is None:
            return
        for element in _walk(panel):
            if _role(element) == "AXTextField" and _string(element, "AXValue"):
                raise StateBlocked("Preview shows a dialog with typed text; it was left as it is")
        cancel = _find(panel, "AXButton", "Cancel")
        if cancel is None:
            raise StateBlocked("Preview shows a dialog or panel it can't safely close; it was left as it is")
        _press(cancel)
        time.sleep(0.4)
    raise UIError("a dialog wouldn't close")


def _raise(window) -> None:
    if _sheet(window) is not None:
        raise StateBlocked(f"{_string(window, 'AXTitle')} has a dialog open; it was left as it is")
    _forward()
    if _attr(window, "AXMinimized") == _TRUE.value:
        _AS.AXUIElementSetAttributeValue(window, _cf("AXMinimized"), _FALSE)
        _wait_for("the window to come back", lambda: _attr(window, "AXMinimized") == _FALSE.value)
    target = _doc_path(window)

    def in_front():
        _AS.AXUIElementPerformAction(window, _cf("AXRaise"))
        main = _attr(_app(), "AXMainWindow")
        return main and _doc_path(main) == target
    _wait_for("the document in front", in_front)


def _opened(full: str):
    """The document's window in front, opening it if needed."""
    if _running():
        _forward()
        _clear_transient()
    window = _window_of(full) or _from_tab(full)
    if window is None:
        subprocess.run(["open", "-a", APP, full], check=True, capture_output=True)
        window = _wait_for("the document's window", lambda: _window_of(full) or _from_tab(full), SAVE_TIMEOUT)
    _raise(window)
    return window


def _from_tab(full: str):
    """Preview can open a document as a tab of another window; a tab in the background isn't a window, so its tab is chosen."""
    if not _running():
        return None
    name = unicodedata.normalize("NFC", os.path.basename(full))
    for window in _documents():
        for group in [e for e in _children(window) if _role(e) == "AXTabGroup"]:
            for tab in [e for e in _children(group) if _role(e) == "AXRadioButton"]:
                if unicodedata.normalize("NFC", _string(tab, "AXTitle")) == name:
                    _press(tab)
                    try:
                        return _wait_for("the tab to be chosen", lambda: _window_of(full), 3)
                    except UIError:
                        return None
    return None


def _stamp(full: str):
    st = os.stat(full)
    return (st.st_mtime_ns, st.st_size, st.st_ino)


def _save(window, full: str, before) -> None:
    """File > Save, then wait for the file to change on disk and settle."""
    _menu("File", "Save")
    _wait_for("the file to be written", lambda: os.path.exists(full) and _stamp(full) != before, SAVE_TIMEOUT)
    seen = []
    _wait_for("the file to settle", lambda: seen.append(_stamp(full)) or (len(seen) >= 3 and len(set(seen[-3:])) == 1), SAVE_TIMEOUT)
    if _sheet(window) is not None:
        raise StateBlocked(f"Preview asked something while saving {full}; the dialog was left open")


def _item(full: str) -> dict:
    return {"name": os.path.basename(full), "path": full}


def document_open(path: str, mode: str = "ui") -> dict:
    """Open an image or PDF in Preview, or bring it to the front if it's open."""
    _mode("document_open", mode)
    full = _kind(_existing(path))
    _opened(full)
    return _checked("document_open", mode, _item(full))


def document_list(mode: str = "ui") -> list:
    """The documents open in Preview: [{name, path}]. Doesn't start Preview."""
    _mode("document_list", mode)
    if not _running():
        return _checked("document_list", mode, [])
    return _checked("document_list", mode, [{"name": _string(w, "AXTitle"), "path": _doc_path(w)} for w in _documents()])


def document_close(path: str, mode: str = "ui") -> dict:
    """Close the document's window. Preview keeps changes by writing them to the file as it closes."""
    _mode("document_close", mode)
    full = _path(path)
    window = _window_of(full) if _running() else None
    if window is None:
        raise NotFound(f"{full} isn't open in Preview")
    _forward()
    _clear_transient()
    _raise(window)
    _menu("File", "Close Window")
    _wait_for("the window to close", lambda: _window_of(full) is None, SAVE_TIMEOUT)
    return _checked("document_close", mode, {**_item(full), "closed": True})


def _transform(function: str, path: str, item: str, mode: str) -> dict:
    full = _kind(_existing(path), IMAGES)
    before = _stamp(full)
    window = _opened(full)
    _menu("Tools", item)
    _save(window, full, before)
    return _checked(function, mode, _item(full))


def image_rotate(path: str, direction: str = "right", mode: str = "ui") -> dict:
    """Rotate an image a quarter turn (Tools > Rotate Left or Rotate Right) and save it."""
    _mode("image_rotate", mode)
    if direction not in ("left", "right"):
        raise ValueError("direction must be \"left\" or \"right\"")
    return _transform("image_rotate", path, f"Rotate {direction.title()}", mode)


def image_flip(path: str, axis: str = "horizontal", mode: str = "ui") -> dict:
    """Flip an image (Tools > Flip Horizontal or Flip Vertical) and save it."""
    _mode("image_flip", mode)
    if axis not in ("horizontal", "vertical"):
        raise ValueError("axis must be \"horizontal\" or \"vertical\"")
    return _transform("image_flip", path, f"Flip {axis.title()}", mode)


def _choose_format(panel, label: str) -> None:
    """Pick label in the dialog's Format pop-up, found as the pop-up whose menu has that item. The dialog fills in its
    controls after it appears, so this is tried until it works or the time runs out."""
    def pick():
        for popup in [e for e in _walk(panel) if _role(e) == "AXPopUpButton"]:
            if _string(popup, "AXValue") == label:
                return True
            _press(popup)
            try:
                menu = _wait_for("the pop-up's menu", lambda: next((e for e in _children(popup) if _role(e) == "AXMenu"), None), 2)
            except UIError:
                continue
            item = next((e for e in _children(menu) if _role(e) == "AXMenuItem" and _string(e, "AXTitle") == label), None)
            if item is not None:
                _press(item)
                return _wait_for(f"the format {label}", lambda: _string(popup, "AXValue") == label, 3)
            _key(ESCAPE)
        return False
    try:
        _wait_for(f"the format {label} in the Export dialog", pick, TIMEOUT)
    except UIError:
        raise UIError(f"the Export dialog has no format {label}") from None


def _go_to_folder(panel):
    """Open Go to Folder in the dialog, asking again once if it didn't open."""
    # The keystroke is ignored until the dialog has focus, so its name field is focused first.
    box = _by_id(panel, "saveAsNameTextField")  # a Save dialog has one; an Open dialog doesn't
    if box is not None:
        _AS.AXUIElementSetAttributeValue(box, _cf("AXFocused"), _TRUE)
        _wait_for("the name field to have focus", lambda: _string(_attr(_app(), "AXFocusedUIElement"), "AXIdentifier") == "saveAsNameTextField")
    for attempt in range(2):
        _key(KEY_G, "{command down, shift down}")
        try:
            return _wait_for("Go to Folder", lambda: _by_id(panel, "GoToWindow"), 5)
        except UIError:
            if attempt:
                raise


def document_export(path: str, to: str, format: str, mode: str = "ui") -> dict:
    """Save a copy of an image or PDF in another format at to (File > Export…). format: png, jpeg, heic, tiff or pdf.
    The original and its window stay as they were."""
    _mode("document_export", mode)
    if format not in FORMATS:
        raise ValueError(f"format must be one of {', '.join(FORMATS)}")
    full = _kind(_existing(path))
    target = _new_path(to)
    if not target.lower().endswith(SUFFIX[format]):
        raise ValueError(f"to must end in {' or '.join(SUFFIX[format])} for {format}")
    window = _opened(full)
    _menu("File", "Export…")
    panel = _wait_for("the Export dialog", lambda: _sheet(window))
    try:
        _choose_format(panel, FORMATS[format])
        folder, name = os.path.split(target)
        go = _go_to_folder(panel)
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
    except Exception:
        if _sheet(window) is not None:
            cancel = _find(_sheet(window), "AXButton", "Cancel")
            if cancel is not None:
                _press(cancel)
        raise
    _wait_for("the export to be written", lambda: os.path.isfile(target) and os.path.getsize(target) > 0, SAVE_TIMEOUT)
    seen = []
    _wait_for("the export to settle", lambda: seen.append(_stamp(target)) or (len(seen) >= 3 and len(set(seen[-3:])) == 1), SAVE_TIMEOUT)
    return _checked("document_export", mode, {**_item(target), "from": full, "format": format})


# PDF pages --------------------------------------------------------------------------------------------------------

UP, DOWN_ARROW = 126, 125


def _page_count(window) -> tuple:
    """(current page, number of pages) from the window title, such as "file.pdf – Page 2 of 3"."""
    title = _string(window, "AXTitle")
    if " – Page " not in title:
        return (1, 1)
    numbers = title.rsplit(" – Page ", 1)[1].split(" of ")
    return int(numbers[0]), int(numbers[1])


def _thumbs(window):
    """The sidebar's list of page thumbnails, showing thumbnails first if the sidebar shows something else."""
    def found():
        return next((e for e in _walk(window) if _role(e) == "AXList" and _string(e, "AXSubrole") == "AXCollectionList"
                     and any(_string(c, "AXSubrole") == "AXSectionList" for c in _children(e))), None)
    try:
        return _wait_for("the page thumbnails", found, 3)
    except UIError:
        _menu("View", "Thumbnails")
        return _wait_for("the page thumbnails", found)


def _select_page(window, page: int) -> int:
    """Select one page's thumbnail with the arrow keys, checked by the window title. Returns the number of pages."""
    pages = _page_count(window)[1]
    if not isinstance(page, int) or isinstance(page, bool) or not 1 <= page <= pages:
        raise ValueError(f"page must be a whole number from 1 to {pages}")
    thumbs = _thumbs(window)
    _AS.AXUIElementSetAttributeValue(thumbs, _cf("AXFocused"), _TRUE)
    _wait_for("the thumbnails to have focus", lambda: _string(_attr(_app(), "AXFocusedUIElement"), "AXSubrole") == "AXCollectionList")
    for _ in range(pages + 1):
        if _page_count(window)[0] == 1 and _has_enabled("Edit", "Delete"):
            break
        _key(UP)
        time.sleep(0.15)
    for k in range(2, page + 1):
        _key(DOWN_ARROW)
        _wait_for(f"page {k}", lambda k=k: _page_count(window)[0] == k)
    _wait_for(f"page {page} to be selected", lambda: _page_count(window)[0] == page and _has_enabled("Edit", "Delete"))
    return pages


def _has_enabled(title: str, item: str) -> bool:
    return _system_events(f'return enabled of menu item "{item}" of menu "{title}" of menu bar item "{title}" of menu bar 1') == "true"


def pdf_delete_page(path: str, page: int, mode: str = "ui") -> dict:
    """Delete one page (counting from 1) of a PDF with Edit > Delete, and save it."""
    _mode("pdf_delete_page", mode)
    full = _kind(_existing(path), (".pdf",))
    before = _stamp(full)
    window = _opened(full)
    pages = _select_page(window, page)
    if pages < 2:
        raise ValueError("a PDF's only page can't be deleted")
    _menu("Edit", "Delete")
    _wait_for("the page to go", lambda: _page_count(window)[1] == pages - 1)
    _save(window, full, before)
    return _checked("pdf_delete_page", mode, {**_item(full), "pages": pages - 1})


def pdf_move_page(path: str, page: int, to: int, mode: str = "ui") -> dict:
    """Move one page of a PDF so it becomes page to (both counted from 1), with Cut and then Paste before the page now at to,
    and save it. Moving a page to the very end isn't supported, because Paste goes before the selected page."""
    _mode("pdf_move_page", mode)
    full = _kind(_existing(path), (".pdf",))
    for name, value in (("page", page), ("to", to)):
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            raise ValueError(f"{name} must be a page number from 1")
    if to == page:
        raise ValueError("the page is already there")
    before = _stamp(full)
    window = _opened(full)
    pages = _page_count(window)[1]
    if page > pages or to >= pages:
        raise ValueError(f"page must be from 1 to {pages}, and to from 1 to {pages - 1} (not the end)")
    _select_page(window, page)
    saved = _jxa(CLIPBOARD, "save")
    try:
        _menu("Edit", "Cut")
        _wait_for("the page to be cut", lambda: _page_count(window)[1] == pages - 1)
        _select_page(window, to)
        _wait_for("Paste to be available", lambda: _has_enabled("Edit", "Paste"))
        _menu("Edit", "Paste")
        _wait_for("the page to be pasted", lambda: _page_count(window)[1] == pages, SAVE_TIMEOUT)
    finally:
        done = subprocess.run(["osascript", "-l", "JavaScript", "-e", CLIPBOARD, "restore"], input=saved, capture_output=True, text=True)
        if done.returncode:
            raise UIError(done.stderr.strip())
    _save(window, full, before)
    return _checked("pdf_move_page", mode, {**_item(full), "pages": pages, "page": page, "to": to})


def pdf_append_file(path: str, add: str, mode: str = "ui") -> dict:
    """Add every page of the PDF at add to the end of the PDF at path (Edit > Insert > Page from File…), and save it."""
    _mode("pdf_append_file", mode)
    full = _kind(_existing(path), (".pdf",))
    extra = _kind(_existing(add), (".pdf",))
    if _same(full, extra):
        raise ValueError("add must be another file")
    before = _stamp(full)
    window = _opened(full)
    pages = _page_count(window)[1]
    _select_page(window, pages)
    _system_events('click menu item "Page from File…" of menu 1 of menu item "Insert" of menu "Edit" of menu bar item "Edit" of menu bar 1')
    panel = _wait_for("the Insert dialog", lambda: _sheet(window) or next(
        (w for w in _windows() if _string(w, "AXSubrole") == "AXDialog" and not _is_document(w)), None))
    try:
        go = _go_to_folder(panel)
        field = _wait_for("the folder field", lambda: _by_id(go, "PathTextField"))
        _key(KEY_A, "command down")
        _paste_text(extra, lambda: unicodedata.normalize("NFC", _string(field, "AXValue")) == unicodedata.normalize("NFC", extra))
        _key(RETURN)
        _wait_for("Go to Folder to close", lambda: _by_id(panel, "GoToWindow") is None)
        button = _wait_for("the Open button", lambda: next((e for e in _walk(panel) if _role(e) == "AXButton" and
                                                           _string(e, "AXTitle") in ("Open", "Insert") and _attr(e, "AXEnabled") == _TRUE.value), None))
        _press(button)
    except Exception:
        cancel = _find(panel, "AXButton", "Cancel")
        if cancel is not None:
            _press(cancel)
        raise
    _wait_for("the pages to be added", lambda: _page_count(window)[1] > pages, SAVE_TIMEOUT)
    _save(window, full, before)
    return _checked("pdf_append_file", mode, {**_item(full), "pages": _page_count(window)[1], "from": extra})


# Crop and Adjust Color (day 4, in their own section, tested on their own) ----------------------------------------
# Cropping needs a dragged rectangle. Its corners are computed from the image element's own frame on screen (never from fixed
# screen positions), after View > Zoom to Fit, so the whole image is showing.

_CG = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics")


class _Point(ctypes.Structure):
    _fields_ = [("x", ctypes.c_double), ("y", ctypes.c_double)]


_CG.CGEventCreateMouseEvent.restype = _P
_CG.CGEventCreateMouseEvent.argtypes = [_P, ctypes.c_uint32, _Point, ctypes.c_uint32]
_CG.CGEventPost.argtypes = [ctypes.c_uint32, _P]
_AS.AXValueGetValue.restype = ctypes.c_bool
_AS.AXValueGetValue.argtypes = [_P, ctypes.c_int, _P]
_CF.CFNumberCreate.restype = _P
_CF.CFNumberCreate.argtypes = [_P, ctypes.c_int, _P]
_CF.CFNumberGetValue.restype = ctypes.c_bool
_CF.CFNumberGetValue.argtypes = [_P, ctypes.c_int, _P]
_CF.CFRelease.argtypes = [_P]
_MOVED, _DOWN, _UP, _DRAGGED = 5, 1, 2, 6
ADJUSTMENTS = {"exposure": "exposure", "contrast": "contrast", "saturation": "saturation"}


def _frame(element) -> tuple:
    point, size = (ctypes.c_double * 2)(), (ctypes.c_double * 2)()
    if not (_AS.AXValueGetValue(_attr(element, "AXPosition"), 1, point) and _AS.AXValueGetValue(_attr(element, "AXSize"), 2, size)):
        raise UIError("an element's frame couldn't be read")
    return point[0], point[1], size[0], size[1]


def _mouse(kind: int, x: float, y: float) -> None:
    event = _CG.CGEventCreateMouseEvent(None, kind, _Point(x, y), 0)
    _CG.CGEventPost(0, event)
    _CF.CFRelease(event)


def _drag(x1: float, y1: float, x2: float, y2: float) -> None:
    _mouse(_MOVED, x1, y1)
    time.sleep(0.1)
    _mouse(_DOWN, x1, y1)
    time.sleep(0.15)
    for step in range(1, 16):
        _mouse(_DRAGGED, x1 + (x2 - x1) * step / 15, y1 + (y2 - y1) * step / 15)
        time.sleep(0.03)
    _mouse(_UP, x2, y2)
    time.sleep(0.3)


def _number(element, name: str):
    value = _attr(element, name)
    out = ctypes.c_double()
    return out.value if value and _CF.CFNumberGetValue(value, 13, ctypes.byref(out)) else None


def image_crop(path: str, left: float, top: float, right: float, bottom: float, mode: str = "ui") -> dict:
    """Crop an image to the rectangle from (left, top) to (right, bottom), given as fractions of its width and height (0 to 1), and
    save it: View > Zoom to Fit, Tools > Rectangular Selection, a drag over the image, Tools > Crop, File > Save."""
    _mode("image_crop", mode)
    for name, value in (("left", left), ("top", top), ("right", right), ("bottom", bottom)):
        if not isinstance(value, (int, float)) or not 0 <= value <= 1:
            raise ValueError(f"{name} must be a fraction from 0 to 1")
    if right - left < 0.05 or bottom - top < 0.05:
        raise ValueError("the rectangle must be at least 5% of the image wide and high")
    full = _kind(_existing(path), IMAGES)
    before = _stamp(full)
    window = _opened(full)
    if _has_menu_item("View", "Zoom to Fit"):
        _menu("View", "Zoom to Fit")
        time.sleep(0.6)
    image = _wait_for("the image", lambda: next((e for e in _walk(window) if _role(e) == "AXImage"), None))

    def fits():
        x, y, w, h = _frame(image)
        wx, wy, ww, wh = _frame(window)
        return x >= wx - 1 and y >= wy - 1 and x + w <= wx + ww + 1 and y + h <= wy + wh + 1
    try:
        _wait_for("the whole image to show", fits, 3)
    except UIError:
        raise UIError("the whole image isn't showing in its window, so the rectangle can't be placed") from None
    x, y, w, h = _frame(image)
    _menu("Tools", "Rectangular Selection")
    time.sleep(0.3)
    if _system_events("return frontmost") != "true":
        raise StateBlocked("another app came to the front; nothing was cropped")
    _drag(x + left * w, y + top * h, x + right * w, y + bottom * h)
    _menu("Tools", "Crop")
    _save(window, full, before)
    return _checked("image_crop", mode, {**_item(full), "left": left, "top": top, "right": right, "bottom": bottom})


def _adjust_panel():
    return next((w for w in _windows() if _string(w, "AXTitle").startswith("Adjust Color")), None)


def _slider(panel, name: str):
    """Adjust Color's sliders have no names; each sits between its named icons, such as "hud icon exposure min"."""
    items = list(_walk(panel))
    for index, element in enumerate(items):
        if _string(element, "AXDescription") == f"hud icon {name} min":
            return next((e for e in items[index:] if _role(e) == "AXSlider"), None)
    return None


def image_adjust(path: str, exposure: float | None = None, contrast: float | None = None, saturation: float | None = None,
                 mode: str = "ui") -> dict:
    """Change an image's exposure, contrast or saturation in Tools > Adjust Color… and save it. Each value is set on its slider and
    must be inside that slider's own range (exposure -2 to 2 in testing; contrast and saturation as Preview shows them)."""
    _mode("image_adjust", mode)
    wanted = {k: v for k, v in (("exposure", exposure), ("contrast", contrast), ("saturation", saturation)) if v is not None}
    if not wanted:
        raise ValueError("give at least one of exposure, contrast or saturation")
    full = _kind(_existing(path), IMAGES)
    before = _stamp(full)
    window = _opened(full)
    if _adjust_panel() is None:
        _menu("Tools", "Adjust Color…")
    panel = _wait_for("the Adjust Color panel", _adjust_panel)
    done = {}
    try:
        for name, value in wanted.items():
            slider = _wait_for(f"the {name} slider", lambda name=name: _slider(panel, ADJUSTMENTS[name]))
            low, high = _number(slider, "AXMinValue"), _number(slider, "AXMaxValue")
            if low is None or high is None or not low <= value <= high:
                raise ValueError(f"{name} must be from {low} to {high}")
            number = ctypes.c_double(float(value))
            if _AS.AXUIElementSetAttributeValue(slider, _cf("AXValue"), _CF.CFNumberCreate(None, 13, ctypes.byref(number))):
                raise UIError(f"the {name} slider couldn't be set")
            _wait_for(f"{name} to be {value}", lambda slider=slider: abs((_number(slider, "AXValue") or 0) - value) < 1e-3)
            done[name] = value
    finally:
        close = next((e for e in _children(panel) if _string(e, "AXSubrole") == "AXCloseButton"), None) if panel is not None else None
        if close is not None:
            _press(close)
            _wait_for("the Adjust Color panel to close", lambda: _adjust_panel() is None)
    _raise(window)
    _save(window, full, before)
    return _checked("image_adjust", mode, {**_item(full), **done})


# Resize (overnight, in its own section, tested on its own) -------------------------------------------------------
# Tools > Adjust Size…'s fields have no names. Each is found on the row of its own label ("Width:", "Height:"): the text field whose
# frame overlaps the label's row, nearest to its right. Then it is checked by value (in pixels it must read the image's current
# width or height) before anything is typed.

def _pixels(full: str) -> tuple:
    out = _run(["sips", "-g", "pixelWidth", "-g", "pixelHeight", full])
    values = dict(line.split(": ") for line in (l.strip() for l in out.splitlines()) if ": " in line)
    return int(values["pixelWidth"]), int(values["pixelHeight"])


def _field_on_row(sheet, label: str):
    texts = list(_walk(sheet))
    name = next((e for e in texts if _role(e) == "AXStaticText" and _string(e, "AXValue") == label), None)
    if name is None:
        return None
    lx, ly, lw, lh = _frame(name)
    best = None
    for e in texts:
        if _role(e) != "AXTextField":
            continue
        x, y, w, h = _frame(e)
        if y < ly + lh and ly < y + h and x >= lx + lw - 1 and (best is None or x < _frame(best)[0]):
            best = e
    return best


def _type_number(field, value: int) -> None:
    _focus(field)
    _wait_for("the field to have the keyboard", lambda: _attr(field, "AXFocused") == _TRUE.value)
    _key(0, "command down")  # select all
    _system_events(f'keystroke "{int(value)}"')
    _key(48)  # Tab commits it, so Preview recomputes the other side
    time.sleep(0.4)


def image_resize(path: str, width: int | None = None, height: int | None = None, mode: str = "ui") -> dict:
    """Resize an image in pixels with Tools > Adjust Size… and save it. Give width or height to keep its proportions, or both to set
    both exactly."""
    _mode("image_resize", mode)
    for name, value in (("width", width), ("height", height)):
        if value is not None and (not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= 20000):
            raise ValueError(f"{name} must be a whole number of pixels from 1 to 20000")
    if width is None and height is None:
        raise ValueError("give width, height or both")
    full = _kind(_existing(path), IMAGES)
    old_w, old_h = _pixels(full)
    if (width or old_w, height or old_h) == (old_w, old_h) or (width is None and round(old_w * height / old_h) == old_w) or (
            height is None and round(old_h * width / old_w) == old_h):
        raise ValueError(f"the image is already {old_w}×{old_h}")
    before = _stamp(full)
    window = _opened(full)
    _raise(window)
    _menu("Tools", "Adjust Size…")
    sheet = _wait_for("the Adjust Size dialog", lambda: _sheet(window))
    try:
        resample = _wait_for("Resample image", lambda: _find(sheet, "AXCheckBox", "Resample image"))
        if _attr(resample, "AXValue") and _number(resample, "AXValue") == 0:
            _press(resample)
            _wait_for("Resample image to be on", lambda: _number(resample, "AXValue") == 1)
        units = next((e for e in _walk(sheet) if _role(e) == "AXPopUpButton" and _string(e, "AXValue") in
                      ("inches", "cm", "mm", "points", "pixels", "percent")), None)
        if units is None:
            raise UIError("the size units menu wasn't found")
        if _string(units, "AXValue") != "pixels":
            _press(units)
            item = _wait_for("pixels in the units menu", lambda: next((e for e in _walk(units) if _role(e) == "AXMenuItem" and _string(e, "AXTitle") == "pixels"), None))
            _press(item)
            _wait_for("the units to be pixels", lambda: _string(units, "AXValue") == "pixels")
        fields = {}
        for label, current in (("Width:", old_w), ("Height:", old_h)):
            field = _wait_for(f"the field beside {label}", lambda label=label: _field_on_row(sheet, label))
            try:
                _wait_for(f"the field beside {label} to read {current}", lambda field=field, current=current: _string(field, "AXValue").replace(",", "") == str(current), 3)
            except UIError:
                raise UIError(f"the field beside {label} reads {_string(field, 'AXValue')!r}, not the image's {current} pixels") from None
            fields[label] = field
        scale = _find(sheet, "AXCheckBox", "Scale proportionally")
        if scale is None:
            raise UIError("Scale proportionally wasn't found")
        keep = width is None or height is None
        if (_number(scale, "AXValue") == 1) != keep:
            _press(scale)
            _wait_for("Scale proportionally to change", lambda: (_number(scale, "AXValue") == 1) == keep)
        if width is not None:
            _type_number(fields["Width:"], width)
        if height is not None:
            _type_number(fields["Height:"], height)
        want_w = width if width is not None else max(1, round(old_w * height / old_h))
        want_h = height if height is not None else max(1, round(old_h * width / old_w))

        def reads():
            w, h = (_string(fields[k], "AXValue").replace(",", "") for k in ("Width:", "Height:"))
            return w.isdigit() and h.isdigit() and abs(int(w) - want_w) <= 1 and abs(int(h) - want_h) <= 1 and (int(w), int(h))
        shown = _wait_for("the new size in the dialog", reads)
        _press(_find(sheet, "AXButton", "OK"))
    except Exception:
        cancel = _find(sheet, "AXButton", "Cancel") if _sheet(window) is not None else None
        if cancel is not None:
            _press(cancel)
        raise
    _wait_for("the Adjust Size dialog to close", lambda: _sheet(window) is None)
    _save(window, full, before)
    new_w, new_h = _wait_for("the new size on disk", lambda: (lambda s: s if s != (old_w, old_h) else None)(_pixels(full)), SAVE_TIMEOUT)
    if (new_w, new_h) != shown:
        raise UIError(f"{full} was saved at {new_w}×{new_h}, not the {shown[0]}×{shown[1]} the dialog showed")
    return _checked("image_resize", mode, {**_item(full), "width": new_w, "height": new_h, "was": [old_w, old_h]})


# Blank page (overnight, in its own section, tested on its own) -----------------------------------------------------

def pdf_insert_blank_page(path: str, after: int, mode: str = "ui") -> dict:
    """Add a blank page to a PDF after page after (counting from 1) with Edit > Insert > Blank Page, and save it."""
    _mode("pdf_insert_blank_page", mode)
    full = _kind(_existing(path), (".pdf",))
    if not isinstance(after, int) or isinstance(after, bool) or after < 1:
        raise ValueError("after must be a page number from 1")
    before = _stamp(full)
    window = _opened(full)
    pages = _select_page(window, after)
    if _system_events('return enabled of menu item "Blank Page" of menu 1 of menu item "Insert" of menu "Edit" of menu bar item "Edit" of menu bar 1') != "true":
        raise UIError("Edit > Insert > Blank Page isn't available")
    _system_events('click menu item "Blank Page" of menu 1 of menu item "Insert" of menu "Edit" of menu bar item "Edit" of menu bar 1')
    _wait_for("the blank page", lambda: _page_count(window)[1] == pages + 1)
    _save(window, full, before)
    return _checked("pdf_insert_blank_page", mode, {**_item(full), "pages": pages + 1, "blank_page": after + 1})


# Rotate one PDF page (overnight, in its own section, tested on its own) ----------------------------------------------

ROTATIONS = r"""ObjC.import("Quartz"); function run(argv) { const d = $.PDFDocument.alloc.initWithURL($.NSURL.fileURLWithPath(argv[0]));
  if (d.isNil()) return "null"; const o = []; for (let i = 0; i < d.pageCount; i++) o.push(Number(d.pageAtIndex(i).rotation)); return JSON.stringify(o); }"""


def _rotations(full: str):
    return json.loads(_jxa(ROTATIONS, full)) or []


def pdf_rotate_page(path: str, page: int, direction: str = "right", mode: str = "ui") -> dict:
    """Rotate one page (counting from 1) of a PDF a quarter turn with Tools > Rotate Right or Rotate Left, and save it. The other
    pages aren't turned."""
    _mode("pdf_rotate_page", mode)
    item = {"right": "Rotate Right", "left": "Rotate Left"}.get(direction)
    if item is None:
        raise ValueError('direction must be "right" or "left"')
    full = _kind(_existing(path), (".pdf",))
    turns_before = _rotations(full)
    before = _stamp(full)
    window = _opened(full)
    pages = _select_page(window, page)
    if not _has_enabled("Tools", item):
        raise UIError(f"Tools > {item} isn't available")
    _menu("Tools", item)
    time.sleep(0.6)
    _save(window, full, before)
    # Read back from the file: only that page may have turned, by a quarter turn the asked way.
    want = list(turns_before)
    want[page - 1] = (want[page - 1] + (90 if direction == "right" else 270)) % 360
    got = _wait_for("the page to be turned in the file", lambda: (lambda r: r if r == want else None)(_rotations(full)), SAVE_TIMEOUT)
    if got != want:
        raise UIError(f"{full} was saved but its pages are turned {got}, not {want}")
    return _checked("pdf_rotate_page", mode, {**_item(full), "page": page, "direction": direction, "pages": pages})
