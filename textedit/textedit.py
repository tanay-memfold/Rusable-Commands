"""TextEdit commands for agents: plain functions with keyword arguments, for plain text (.txt) and rich text (.rtf) documents.

mode="ui" works on screen: elements are found by role and name through the macOS Accessibility API and pressed, menu items are
clicked by name, and text is pasted through the clipboard, which is restored afterwards. No screen coordinates.
mode="background" uses TextEdit's own scripting and leaves the front app alone. A closed TextEdit is started hidden.

A document is named by its path. Set TEXTEDIT_ALLOWED_ROOT to a folder and every path is checked to be inside it, after following
links, before anything happens: a path outside raises OutsideAllowedRoot.

TextEdit keeps changes by itself: it can write an edited document to its file when it loses focus, and when the window closes.

Errors: NotFound, AlreadyExists, OutsideAllowedRoot, StateBlocked (the document has a dialog open, which the call won't destroy),
UIError (an element never appeared), NotSupported (the mode wasn't verified)."""
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

APP = "TextEdit"
BUNDLE_ID = "com.apple.TextEdit"
TIMEOUT = 10
SAVE_TIMEOUT = 15
ROOT_ENV = "TEXTEDIT_ALLOWED_ROOT"
SUFFIXES = (".txt", ".rtf")
APP_PLIST = "/System/Applications/TextEdit.app/Contents/Info.plist"

VERIFIED: dict = {
    "document_append": {
        "background": {
            "macos": "15.6.1 (24G90)",
            "app": "1.20 (409)"
        },
        "ui": {
            "macos": "15.6.1 (24G90)",
            "app": "1.20 (409)"
        }
    },
    "document_close": {
        "background": {
            "macos": "15.6.1 (24G90)",
            "app": "1.20 (409)"
        },
        "ui": {
            "macos": "15.6.1 (24G90)",
            "app": "1.20 (409)"
        }
    },
    "document_copy_to_new": {
        "background": {
            "macos": "15.6.1 (24G90)",
            "app": "1.20 (409)"
        },
        "ui": {
            "macos": "15.6.1 (24G90)",
            "app": "1.20 (409)"
        }
    },
    "document_create": {
        "background": {
            "macos": "15.6.1 (24G90)",
            "app": "1.20 (409)"
        },
        "ui": {
            "macos": "15.6.1 (24G90)",
            "app": "1.20 (409)"
        }
    },
    "document_export_pdf": {
        "ui": {
            "macos": "15.6.1 (24G90)",
            "app": "1.20 (409)"
        }
    },
    "document_list": {
        "background": {
            "macos": "15.6.1 (24G90)",
            "app": "1.20 (409)"
        },
        "ui": {
            "macos": "15.6.1 (24G90)",
            "app": "1.20 (409)"
        }
    },
    "document_open": {
        "background": {
            "macos": "15.6.1 (24G90)",
            "app": "1.20 (409)"
        },
        "ui": {
            "macos": "15.6.1 (24G90)",
            "app": "1.20 (409)"
        }
    },
    "document_read": {
        "background": {
            "macos": "15.6.1 (24G90)",
            "app": "1.20 (409)"
        },
        "ui": {
            "macos": "15.6.1 (24G90)",
            "app": "1.20 (409)"
        }
    },
    "document_replace_text": {
        "background": {
            "macos": "15.6.1 (24G90)",
            "app": "1.20 (409)"
        },
        "ui": {
            "macos": "15.6.1 (24G90)",
            "app": "1.20 (409)"
        }
    },
    "document_save": {
        "background": {
            "macos": "15.6.1 (24G90)",
            "app": "1.20 (409)"
        },
        "ui": {
            "macos": "15.6.1 (24G90)",
            "app": "1.20 (409)"
        }
    },
    "document_save_as": {
        "background": {
            "macos": "15.6.1 (24G90)",
            "app": "1.20 (409)"
        },
        "ui": {
            "macos": "15.6.1 (24G90)",
            "app": "1.20 (409)"
        }
    }
}


class TextEditError(Exception):
    pass


class NotFound(TextEditError):
    pass


class AlreadyExists(TextEditError):
    pass


class OutsideAllowedRoot(TextEditError):
    pass


class StateBlocked(TextEditError):
    pass


class UIError(TextEditError):
    pass


class NotSupported(TextEditError):
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


def _mode(function: str, mode: str) -> None:
    if mode not in ("ui", "background"):
        raise ValueError(f"mode must be 'ui' or 'background', not {mode!r}")
    if VERIFIED and mode not in VERIFIED.get(function, {}):
        raise NotSupported(f"{function} has no verified {mode} mode: it did not pass verification")


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


# Paths ------------------------------------------------------------------------------------------------------------

def _path(path: str) -> str:
    full = os.path.abspath(os.path.expanduser(path))
    root = os.environ.get(ROOT_ENV)
    if root:
        allowed, real = os.path.realpath(os.path.expanduser(root)), os.path.realpath(full)
        if real != allowed and not real.startswith(allowed + os.sep):
            raise OutsideAllowedRoot(f"{full} is outside {ROOT_ENV}; nothing was done")
    if not full.lower().endswith(SUFFIXES):
        raise ValueError(f"only .txt and .rtf documents are supported, not {os.path.basename(full)!r}")
    return full


def _existing(path: str) -> str:
    full = _path(path)
    if not os.path.isfile(full):
        raise NotFound(f"no document at {full}")
    return full


def _new_path(path: str) -> str:
    full = _path(path)
    if os.path.lexists(full):
        raise AlreadyExists(f"{full} already exists; nothing is overwritten")
    if not os.path.isdir(os.path.dirname(full)):
        raise NotFound(f"the folder {os.path.dirname(full)} doesn't exist")
    return full


def _same(first: str, second: str) -> bool:
    return unicodedata.normalize("NFC", os.path.realpath(first)) == unicodedata.normalize("NFC", os.path.realpath(second))


def _on_disk(full: str):
    """The file's text as a program would read it; None if it can't be read as text."""
    try:
        if full.lower().endswith(".rtf"):
            done = subprocess.run(["textutil", "-convert", "txt", "-stdout", full], capture_output=True, text=True)
            return done.stdout if done.returncode == 0 else None
        with open(full, encoding="utf-8", newline="") as handle:
            return handle.read()
    except (OSError, UnicodeDecodeError):
        return None


def _matches_disk(full: str, text: str) -> bool:
    disk = _on_disk(full)
    if disk is None:
        return False
    return unicodedata.normalize("NFC", disk).rstrip("\n") == unicodedata.normalize("NFC", text).rstrip("\n") \
        if full.lower().endswith(".rtf") else unicodedata.normalize("NFC", disk) == unicodedata.normalize("NFC", text)


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
        raise UIError("TextEdit isn't running")
    return _AS.AXUIElementCreateApplication(int(found[0]))


def _windows() -> list:
    return [e for e in _children(_app()) if _role(e) == "AXWindow"]


def _is_document(window) -> bool:
    """A document window. While minimized, or while TextEdit is hidden, it reports itself as a dialog."""
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


MENU_OPEN = """repeat with b in menu bar items of menu bar 1
  if selected of b then return "true"
end repeat
return "false\""""


def _clear_transient() -> None:
    """Close an open menu, and an Open dialog with nothing typed in it. Dialogs on documents are never touched here."""
    for _ in range(12):
        if _system_events(MENU_OPEN) == "true":
            _key(ESCAPE)
            time.sleep(0.2)
            continue
        panel = next((w for w in _windows() if _string(w, "AXSubrole") == "AXDialog" and not _is_document(w)), None)
        if panel is None:
            return
        for element in _walk(panel):
            if _role(element) == "AXTextField" and _string(element, "AXValue"):
                raise StateBlocked("TextEdit shows a dialog with typed text; it was left as it is")
        cancel = _find(panel, "AXButton", "Cancel")
        if cancel is None:
            raise StateBlocked("TextEdit shows a dialog it can't safely close; it was left as it is")
        _press(cancel)
        time.sleep(0.4)
    raise UIError("a menu or dialog wouldn't close")


def _launch() -> bool:
    """Start TextEdit if it's closed. It opens an empty document by itself."""
    if _running():
        return False
    subprocess.run(["open", "-b", BUNDLE_ID], check=True)
    _wait_for("TextEdit to start", _running)
    _wait_for("TextEdit's first window", lambda: _windows())
    return True


def _forward() -> None:
    _system_events("set visible to true\nset frontmost to true")
    _wait_for("TextEdit in front", lambda: _system_events("return frontmost") == "true")


def _raise(window) -> None:
    """The document in front, with no dialog on it."""
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
        return main and _doc_path(main) == target and _string(main, "AXTitle") == _string(window, "AXTitle")
    _wait_for("the document in front", in_front)


def _open_doc(full: str):
    window = _window_of(full)
    if window is None:
        subprocess.run(["open", "-a", APP, full], check=True, capture_output=True)
        window = _wait_for("the document's window", lambda: _window_of(full))
        _wait_for("the document's text", lambda: _text_area(window) is not None)
    return window


def _opened(full: str):
    if _running():
        _forward()
        _clear_transient()
    return _open_doc(full)


def _open_window(full: str):
    """The window of a document that must be open already."""
    window = _window_of(full)
    if window is None:
        raise NotFound(f"{full} isn't open in TextEdit")
    return window


def _wait_for_quietly(test) -> bool:
    try:
        return bool(_wait_for("it", test, 2))
    except UIError:
        return False


def _fresh_window():
    window = _attr(_app(), "AXMainWindow")
    return window if window and not _doc_path(window) and not _sheet(window) and _text_area(window) is not None \
        and not _string(_text_area(window), "AXValue") else None


CLIPBOARD_COUNT = 'ObjC.import("AppKit"); String($.NSPasteboard.generalPasteboard.changeCount)'


def _item(full: str) -> dict:
    return {"name": os.path.basename(full), "path": full}


def _editing(window) -> object:
    _raise(window)
    area = _text_area(window)
    _AS.AXUIElementSetAttributeValue(area, _cf("AXFocused"), _TRUE)
    _wait_for("the text to have focus", lambda: _string(_attr(_app(), "AXFocusedUIElement"), "AXIdentifier") == "First Text View")
    return area


def _is(area, text: str) -> bool:
    return unicodedata.normalize("NFC", _string(area, "AXValue")) == unicodedata.normalize("NFC", text)


def _set_text(window, text: str) -> None:
    area = _editing(window)
    if _is(area, text):
        return
    _menu("Edit", "Select All")
    if text:
        _paste_text(text, lambda: _is(area, text))
    else:
        _key(DELETE)
        _wait_for("the text to go", lambda: _is(area, ""))


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


def _saved_at(full: str, area) -> None:
    window = _wait_for("the document to be saved", lambda: _window_of(full), SAVE_TIMEOUT)
    if _sheet(window) is not None:
        raise StateBlocked(f"TextEdit asked something while saving {full}; the dialog was left open")
    _wait_for("the file to match the document", lambda: _matches_disk(full, _string(area, "AXValue")), SAVE_TIMEOUT)


# Scripting --------------------------------------------------------------------------------------------------------

SCRIPT = r"""
ObjC.import("Foundation");
function run() {
  const a = JSON.parse(ObjC.unwrap($.NSString.alloc.initWithDataEncoding($.NSFileHandle.fileHandleWithStandardInput.readDataToEndOfFile, $.NSUTF8StringEncoding)));
  const T = Application("TextEdit");
  const same = (x, y) => !!x && x.normalize("NFC") === y.normalize("NFC");
  const doc = p => T.documents().find(d => same(d.path(), p));
  const out = v => JSON.stringify(v === undefined ? null : v);
  switch (a.op) {
    case "list": return out(T.documents().map(d => ({name: d.name(), path: d.path() || null})));
    case "has": return out(!!doc(a.path));
    case "text": return out(doc(a.path).text());
    case "set": doc(a.path).text = a.text; return out(doc(a.path).text());
    case "save": doc(a.path).save(); return out(true);
    case "save_as": { const d = doc(a.path); if (d.modified()) d.save(); d.save({in: Path(a.to)}); T.open(Path(a.to)); doc(a.path).close({saving: "yes"}); return out(true); }
    case "close": doc(a.path).close({saving: "yes"}); return out(true);
    case "create": {
      const names = T.documents().map(d => d.name());
      T.documents.push(T.Document({text: a.text}));
      const made = T.documents().find(d => !names.includes(d.name())), name = made.name();
      made.save({in: Path(a.path)});
      // A rich text document becomes the new file; one saved as plain text stays untitled, with the file written beside it.
      (doc(a.path) || T.documents.byName(name)).close({saving: "no"});
      return out(true);
    }
    case "tidy": for (const d of T.documents()) if (!d.path() && !d.text()) d.close({saving: "no"}); return out(true);
  }
}"""


def _script(op: str, **args):
    try:
        done = subprocess.run(["osascript", "-l", "JavaScript", "-e", SCRIPT], input=json.dumps({"op": op, **args}),
                              capture_output=True, text=True, timeout=SAVE_TIMEOUT + 15)
    except subprocess.TimeoutExpired:
        raise UIError(f"TextEdit didn't answer ({op}); it may be showing a dialog") from None
    if done.returncode:
        raise UIError(done.stderr.strip())
    return json.loads(done.stdout)


def _start_hidden() -> None:
    if _running():
        return
    subprocess.run(["open", "-g", "-j", "-b", BUNDLE_ID], check=True)
    _wait_for("TextEdit to start", _running)
    _wait_for("TextEdit to answer", lambda: _script("list") is not None)
    time.sleep(0.5)
    _script("tidy")


def _script_open(full: str) -> None:
    if not _running():
        raise NotSupported("background mode can't open a document while TextEdit is closed: TextEdit came to the front in "
                           "testing. Use mode=\"ui\", or start TextEdit first; nothing was done")
    if not _script("has", path=full):
        subprocess.run(["open", "-g", "-a", APP, full], check=True, capture_output=True)
    _wait_for("the document to open", lambda: _script("has", path=full))


def _script_opened(full: str) -> None:
    if not _running() or not _script("has", path=full):
        raise NotFound(f"{full} isn't open in TextEdit")


def _script_saved(full: str) -> None:
    _wait_for("the file to match the document", lambda: _matches_disk(full, _script("text", path=full)), SAVE_TIMEOUT)


# Commands ---------------------------------------------------------------------------------------------------------

def document_list(mode: str = "background") -> list:
    """The documents open in TextEdit, front to back. path is None for one that has never been saved."""
    _mode("document_list", mode)
    if not _running():
        return _checked("document_list", mode, [])
    if mode == "background":
        return _checked("document_list", mode, _script("list"))
    out = []
    for window in _documents():
        path = _doc_path(window)
        out.append({"name": _string(window, "AXTitle"), "path": path})
    return _checked("document_list", mode, out)


def document_create(path: str, text: str = "", mode: str = "ui") -> dict:
    """Make a new document with text and save it at path, which must not exist. .txt is plain text, .rtf is rich text."""
    _mode("document_create", mode)
    full = _new_path(path)
    if mode == "background":
        _start_hidden()
        _script("create", path=full, text=text)
        _wait_for("the file to match the text", lambda: _matches_disk(full, text), SAVE_TIMEOUT)
        return _checked("document_create", mode, _item(full))
    started = _launch()
    _forward()
    _clear_transient()

    if not (started and _wait_for_quietly(_fresh_window)):
        _menu("File", "New")
    window = _wait_for("the new document", _fresh_window)
    plain = full.lower().endswith(".txt")
    change = "Make Plain Text" if plain else "Make Rich Text"
    if _has_menu_item("Format", change):
        _menu("Format", change)
        _wait_for("the document's format", lambda: not _has_menu_item("Format", change))
    area = _text_area(window)
    if text:
        _AS.AXUIElementSetAttributeValue(area, _cf("AXFocused"), _TRUE)
        _paste_text(text, lambda: _is(area, text))
    _key(KEY_S, "command down")
    _fill_save_panel(window, full)
    _saved_at(full, area)
    return _checked("document_create", mode, _item(full))


def document_open(path: str, mode: str = "ui") -> dict:
    """Open the document at path in TextEdit and bring it to the front."""
    _mode("document_open", mode)
    full = _existing(path)
    if mode == "background":
        _script_open(full)
        return _checked("document_open", mode, _item(full))
    _raise(_opened(full))
    return _checked("document_open", mode, _item(full))


def document_read(path: str, mode: str = "background") -> dict:
    """The document's text as TextEdit shows it, including changes not yet written to the file. Opens it if it isn't open."""
    _mode("document_read", mode)
    full = _existing(path)
    if mode == "background":
        _script_open(full)
        return _checked("document_read", mode, {**_item(full), "text": _script("text", path=full)})
    window = _window_of(full) or _opened(full)
    area = _wait_for("the document's text", lambda: _text_area(window))
    return _checked("document_read", mode, {**_item(full), "text": _string(area, "AXValue")})


def document_replace_text(path: str, text: str, mode: str = "ui") -> dict:
    """Replace all of the document's text. Opens it if it isn't open. Call document_save to be sure it's written to the file."""
    _mode("document_replace_text", mode)
    full = _existing(path)
    if mode == "background":
        _script_open(full)
        _script("set", path=full, text=text)
        return _checked("document_replace_text", mode, {**_item(full), "text": text})
    _set_text(_opened(full), text)
    return _checked("document_replace_text", mode, {**_item(full), "text": text})


def document_append(path: str, text: str, mode: str = "ui") -> dict:
    """Add text at the end of the document, with nothing between. Opens it if it isn't open. Call document_save to be sure it's written."""
    _mode("document_append", mode)
    if not text:
        raise ValueError("text must not be empty")
    full = _existing(path)
    if mode == "background":
        _script_open(full)
        whole = _script("text", path=full) + text
        _script("set", path=full, text=whole)
        return _checked("document_append", mode, {**_item(full), "text": whole})
    area = _editing(_opened(full))
    before = _string(area, "AXValue")
    _key(DOWN, "command down")
    _paste_text(text, lambda: _is(area, before + text))
    return _checked("document_append", mode, {**_item(full), "text": before + text})


def document_copy_to_new(path: str, to: str, mode: str = "ui") -> dict:
    """Copy all of a document's text, paste it into a new document, and save that at to, which must not exist. Both stay open in UI mode."""
    _mode("document_copy_to_new", mode)
    full, target = _existing(path), _new_path(to)
    if mode == "background":
        _script_open(full)
        text = _script("text", path=full)
        if not text:
            raise ValueError(f"{full} is empty; there is nothing to copy")
        _script("create", path=target, text=text)
        _wait_for("the file to match the text", lambda: _matches_disk(target, text), SAVE_TIMEOUT)
        return _checked("document_copy_to_new", mode, {**_item(target), "from": full})
    window = _opened(full)
    area = _editing(window)
    text = _string(area, "AXValue")
    if not text:
        raise ValueError(f"{full} is empty; there is nothing to copy")
    saved = _jxa(CLIPBOARD, "save")
    try:
        _menu("Edit", "Select All")
        _wait_for("all the text to be selected", lambda: unicodedata.normalize("NFC", _string(area, "AXSelectedText")) == unicodedata.normalize("NFC", text))
        before = _jxa(CLIPBOARD_COUNT)
        for _ in range(3):
            # Copy was sometimes ignored just after Select All, so it is asked again while the clipboard hasn't changed.
            _menu("Edit", "Copy")
            if _wait_for_quietly(lambda: _jxa(CLIPBOARD_COUNT) != before):
                break
        else:
            raise UIError("the text wasn't copied")
        _menu("File", "New")
        new = _wait_for("the new document", _fresh_window)
        plain = target.lower().endswith(".txt")
        change = "Make Plain Text" if plain else "Make Rich Text"
        if _has_menu_item("Format", change):
            _menu("Format", change)
            _wait_for("the document's format", lambda: not _has_menu_item("Format", change))
        box = _text_area(new)
        _AS.AXUIElementSetAttributeValue(box, _cf("AXFocused"), _TRUE)
        _paste()
        _wait_for("the pasted text to appear", lambda: _is(box, text))
    finally:
        done = subprocess.run(["osascript", "-l", "JavaScript", "-e", CLIPBOARD, "restore"], input=saved,
                              capture_output=True, text=True)
        if done.returncode:
            raise UIError(done.stderr.strip())
    _key(KEY_S, "command down")
    _fill_save_panel(new, target)
    _saved_at(target, box)
    return _checked("document_copy_to_new", mode, {**_item(target), "from": full})


def document_save(path: str, mode: str = "ui") -> dict:
    """Write the open document to its file, and wait until the file holds its text."""
    _mode("document_save", mode)
    full = _path(path)
    if mode == "background":
        _script_opened(full)
        _script("save", path=full)
        _script_saved(full)
        return _checked("document_save", mode, {**_item(full), "saved": True})
    if _running():
        _forward()
        _clear_transient()
    window = _open_window(full)
    _raise(window)
    _menu("File", "Save")
    _saved_at(full, _text_area(window))
    return _checked("document_save", mode, {**_item(full), "saved": True})


def document_save_as(path: str, to: str, mode: str = "ui") -> dict:
    """Save the open document at a new path of the same type. The window then shows the new file, and the old file stays."""
    _mode("document_save_as", mode)
    full, target = _path(path), _new_path(to)
    if os.path.splitext(full)[1].lower() != os.path.splitext(target)[1].lower():
        raise ValueError("the new path must have the same type as the document: .txt or .rtf")
    if mode == "background":
        _script_opened(full)
        _script("save_as", path=full, to=target)
        _wait_for("the document to move", lambda: _script("has", path=target), SAVE_TIMEOUT)
        _script_saved(target)
        return _checked("document_save_as", mode, {**_item(target), "from": full})
    if _running():
        _forward()
        _clear_transient()
    window = _open_window(full)
    _raise(window)
    area = _text_area(window)
    _menu("File", "Save As…")
    _fill_save_panel(window, target)
    _saved_at(target, area)
    return _checked("document_save_as", mode, {**_item(target), "from": full})


def document_close(path: str, mode: str = "ui") -> dict:
    """Close the open document. TextEdit keeps its changes: it writes them to the file as the window closes."""
    _mode("document_close", mode)
    full = _path(path)
    if mode == "background":
        _script_opened(full)
        text = _script("text", path=full)
        _script("close", path=full)
        _wait_for("the document to close", lambda: not _script("has", path=full))
        _wait_for("the file to match the document", lambda: _matches_disk(full, text), SAVE_TIMEOUT)
        return _checked("document_close", mode, {**_item(full), "closed": True})
    if _running():
        _forward()
        _clear_transient()
    window = _open_window(full)
    _raise(window)
    text = _string(_text_area(window), "AXValue")
    _menu("File", "Close")

    def gone():
        now = _window_of(full)
        if now is not None and _sheet(now) is not None:
            raise StateBlocked(f"TextEdit asked something while closing {full}; the dialog was left open")
        return now is None
    _wait_for("the document to close", gone)
    _wait_for("the file to match the document", lambda: _matches_disk(full, text), SAVE_TIMEOUT)
    return _checked("document_close", mode, {**_item(full), "closed": True})


def document_export_pdf(path: str, to: str, mode: str = "ui") -> dict:
    """Save a PDF of a .txt or .rtf document at to (File > Export as PDF…), opening it if needed. The document is unchanged."""
    _mode("document_export_pdf", mode)
    if mode != "ui":
        raise NotSupported("document_export_pdf has no background mode: TextEdit's scripting has no PDF export")
    full = _existing(path)
    target = os.path.abspath(os.path.expanduser(to))
    if not target.lower().endswith(".pdf"):
        raise ValueError("to must end in .pdf")
    root = os.environ.get(ROOT_ENV)
    if root:
        allowed, real = os.path.realpath(os.path.expanduser(root)), os.path.realpath(os.path.dirname(target))
        if real != allowed and not real.startswith(allowed + os.sep):
            raise OutsideAllowedRoot(f"{target} is outside {ROOT_ENV}; nothing was done")
    if os.path.lexists(target):
        raise AlreadyExists(f"{target} already exists; nothing is overwritten")
    if not os.path.isdir(os.path.dirname(target)):
        raise NotFound(f"the folder {os.path.dirname(target)} doesn't exist")
    window = _opened(full)
    _raise(window)
    _menu("File", "Export as PDF…")
    try:
        _fill_save_panel(window, target)
    except Exception:
        sheet = _sheet(window)
        if sheet is not None and _find(sheet, "AXButton", "Cancel") is not None:
            _press(_find(sheet, "AXButton", "Cancel"))
        raise
    _wait_for("the PDF to be written", lambda: os.path.isfile(target) and os.path.getsize(target) > 0, SAVE_TIMEOUT)
    seen = []
    _wait_for("the PDF to finish", lambda: seen.append(os.path.getsize(target)) or (len(seen) >= 3 and len(set(seen[-3:])) == 1), SAVE_TIMEOUT)
    return _checked("document_export_pdf", mode, {"name": os.path.basename(target), "path": target, "from": full})
