"""VS Code commands for agents: plain functions with keyword arguments, to open folders and files and make files in Visual Studio Code.

mode="ui" works on screen: elements are found by role and name through the macOS Accessibility API, menu items are clicked by name, and
text is pasted through the clipboard, which is restored afterwards. No screen coordinates.

Set VSCODE_ALLOWED_ROOT to a folder and every path is checked to be inside it, after following links, before anything happens.

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

APP = "Code"
BUNDLE_ID = "com.microsoft.VSCode"
TIMEOUT = 10
SAVE_TIMEOUT = 15
ROOT_ENV = "VSCODE_ALLOWED_ROOT"
APP_PLIST = "/Applications/Visual Studio Code.app/Contents/Info.plist"

VERIFIED: dict = {
    "extension_install": {
        "ui": {
            "macos": "15.6.1 (24G90)",
            "app": "1.105.1 (1.105.1)"
        }
    },
    "file_new": {
        "ui": {
            "macos": "15.6.1 (24G90)",
            "app": "1.105.1 (1.105.1)"
        }
    },
    "file_open": {
        "ui": {
            "macos": "15.6.1 (24G90)",
            "app": "1.105.1 (1.105.1)"
        }
    },
    "folder_open": {
        "ui": {
            "macos": "15.6.1 (24G90)",
            "app": "1.105.1 (1.105.1)"
        }
    }
}
UNSUPPORTED: dict = {}


class VscodeError(Exception):
    pass


class NotFound(VscodeError):
    pass


class Ambiguous(VscodeError):
    pass


class AlreadyExists(VscodeError):
    pass


class OutsideAllowedRoot(VscodeError):
    pass


class StateBlocked(VscodeError):
    pass


class UIError(VscodeError):
    pass


class NotSupported(VscodeError):
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


MAIN = "/Applications/Visual Studio Code.app/Contents/MacOS/Electron"


def _pid():
    """VS Code's main process: its executable is called Electron, and its helpers share the name, so it's found by path."""
    found = subprocess.run(["pgrep", "-f", "-x", MAIN], capture_output=True, text=True).stdout.split()
    return int(found[0]) if found else None


def _running() -> bool:
    return _pid() is not None


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
    pid = _pid()
    if pid is None:
        raise UIError("VS Code isn't running")
    return _AS.AXUIElementCreateApplication(pid)


def _windows() -> list:
    return [e for e in _children(_app()) if _role(e) == "AXWindow"]


def _is_document(window) -> bool:
    """A document window. While minimized, or while VS Code is hidden, it reports itself as a dialog."""
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
    _wait_for("VS Code in front", lambda: _system_events("return frontmost") == "true")


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



def _accessible() -> None:
    """VS Code (Electron) shows its window's contents to Accessibility only when asked."""
    _AS.AXUIElementSetAttributeValue(_app(), _cf("AXManualAccessibility"), _TRUE)


def _distrust() -> bool:
    """Answer VS Code's "Do you trust the authors of the files in this folder?" with No, which keeps Restricted Mode and grants
    nothing. True if the dialog was there."""
    _accessible()
    for window in _windows():
        button = next((e for e in _walk(window) if _role(e) == "AXButton" and _string(e, "AXTitle") == "No, I don't trust the authors"), None)
        if button is not None:
            _press(button)
            _wait_for("the trust dialog to close", lambda: not any(_string(e, "AXTitle") == "No, I don't trust the authors"
                                                                  for w in _windows() for e in _walk(w) if _role(e) == "AXButton"))
            return True
    return False


def _start() -> None:
    if not _running():
        subprocess.run(["open", "-b", BUNDLE_ID], check=True)
        _wait_for("VS Code to start", _running, TIMEOUT * 3)
    _wait_for("VS Code's window", lambda: _windows(), TIMEOUT * 3)
    _forward()
    _distrust()


def _main_title() -> str:
    return _string(_attr(_app(), "AXMainWindow") or _attr(_app(), "AXFocusedWindow"), "AXTitle")


def _dialog():
    return next((w for w in _windows() if _by_id(w, "OKButton") is not None), None)


def _choose_in_dialog(folder: str, name: str | None) -> None:
    """Go to folder in an Open or Save dialog, type name if it has a name field, and press its OK button."""
    panel = _wait_for("the dialog", _dialog, TIMEOUT * 2)
    try:
        _key(KEY_G, "{command down, shift down}")
        go = _wait_for("Go to Folder", lambda: _by_id(panel, "GoToWindow"))
        field = _wait_for("the folder field", lambda: _by_id(go, "PathTextField"))
        _key(KEY_A, "command down")
        _paste_text(folder, lambda: _string(field, "AXValue") == folder)
        _key(RETURN)
        _wait_for("Go to Folder to close", lambda: _by_id(panel, "GoToWindow") is None)
        if name is not None:
            box = _by_id(panel, "saveAsNameTextField")
            if box is not None:
                _AS.AXUIElementSetAttributeValue(box, _cf("AXFocused"), _TRUE)
                time.sleep(0.3)
                _key(KEY_A, "command down")
                _paste_text(name, lambda: unicodedata.normalize("NFC", _string(box, "AXValue")) == unicodedata.normalize("NFC", name))
            else:
                # An Open dialog: the item is picked by typing its name in the file list.
                _system_events(f'keystroke "{name}"')
                time.sleep(0.6)
        _press(_by_id(panel, "OKButton"))
    except Exception:
        cancel = _by_id(panel, "CancelButton")
        if cancel is not None:
            _press(cancel)
        raise
    _wait_for("the dialog to close", lambda: _dialog() is None, TIMEOUT * 2)


def folder_open(path: str, mode: str = "ui") -> dict:
    """Open a folder in VS Code (File > Open Folder…). The window then shows it."""
    _mode("folder_open", mode)
    full = _existing(path)
    if not os.path.isdir(full):
        raise ValueError("path must be a folder")
    _start()
    _menu("File", "Open Folder…")
    _choose_in_dialog(full, None)
    name = os.path.basename(full)
    _wait_for(f"the window to show {name}", lambda: name in unicodedata.normalize("NFC", _main_title()), TIMEOUT * 3)
    time.sleep(1.5)
    _distrust()
    return _checked("folder_open", mode, {"name": name, "path": full, "window": _main_title()})


def file_new(path: str, text: str = "", mode: str = "ui") -> dict:
    """Make a new file with text at a path that doesn't exist (File > New Text File, then Save As…). It stays open."""
    _mode("file_new", mode)
    full = _new_path(path)
    _start()
    _menu("File", "New Text File")
    _wait_for("the new Untitled file", lambda: _main_title().startswith("Untitled"), TIMEOUT * 2)
    time.sleep(0.8)
    _key(ESCAPE)  # VS Code's "Select a language" hint sits over a new file
    time.sleep(0.3)
    if text:
        saved = _jxa(CLIPBOARD, "save")
        try:
            _jxa(CLIPBOARD, "text", text)
            _paste()
            _wait_for("the text to land", lambda: _main_title().startswith("●") or "●" in _main_title() or "Untitled" in _main_title(), TIMEOUT)
            time.sleep(0.8)
        finally:
            done = subprocess.run(["osascript", "-l", "JavaScript", "-e", CLIPBOARD, "restore"], input=saved, capture_output=True, text=True)
            if done.returncode:
                raise UIError(done.stderr.strip())
    _menu("File", "Save As…")
    _choose_in_dialog(os.path.dirname(full), os.path.basename(full))
    _wait_for("the file to be written", lambda: os.path.isfile(full) and open(full, encoding="utf-8").read() == text, SAVE_TIMEOUT)
    return _checked("file_new", mode, {"name": os.path.basename(full), "path": full})


def file_open(path: str, mode: str = "ui") -> dict:
    """Open a file in VS Code (File > Open…), going to the file itself in the dialog. The window then shows it."""
    _mode("file_open", mode)
    full = _existing(path)
    if os.path.isdir(full):
        raise ValueError("path must be a file; use folder_open for a folder")
    _start()
    _menu("File", "Open…")
    _choose_in_dialog(full, None)
    name = os.path.basename(full)
    _wait_for(f"the window to show {name}", lambda: unicodedata.normalize("NFC", name) in unicodedata.normalize("NFC", _main_title()), TIMEOUT * 3)
    time.sleep(1.5)
    _distrust()
    return _checked("file_open", mode, {"name": name, "path": full, "window": _main_title()})


# Extensions (day 4, in their own section, tested on their own) --------------------------------------

EXTENSIONS = os.path.expanduser("~/.vscode/extensions")


def _installed() -> set:
    """Extension ids installed for this user, from VS Code's own extensions folder."""
    try:
        with open(os.path.join(EXTENSIONS, "extensions.json"), encoding="utf-8") as handle:
            return {e["identifier"]["id"].lower() for e in json.load(handle)}
    except (OSError, ValueError, KeyError, TypeError):
        return set()


def _button_named(name: str):
    return next((e for w in _windows() for e in _walk(w) if _role(e) == "AXButton" and name in (_string(e, "AXTitle"), _string(e, "AXDescription"))), None)


def extension_install(ext_id: str, mode: str = "ui") -> dict:
    """Install an extension from the Marketplace by its id (publisher.name, such as esbenp.prettier-vscode) in the Extensions view.
    The first extension from a publisher makes VS Code ask "Trust Publisher & Install"; that is pressed. A workspace-trust question
    gets plain Install, which doesn't trust the workspace."""
    _mode("extension_install", mode)
    if not ext_id or ext_id.count(".") != 1 or " " in ext_id:
        raise ValueError("ext_id must be publisher.name")
    if ext_id.lower() in _installed():
        raise AlreadyExists(f"{ext_id} is already installed")
    _start()
    _accessible()
    # Just after it starts, VS Code ignores the menu until its window is ready: wait for the sidebar's Extensions button first.
    _wait_for("VS Code's window to be ready", lambda: any(_role(e) in ("AXButton", "AXRadioButton", "AXTab", "AXGroup") and _string(e, "AXDescription").startswith("Extensions (")
                                                       for w in _windows() for e in _walk(w)), TIMEOUT * 3)
    def search_box():
        return next((e for w in _windows() for e in _walk(w) if _role(e) in ("AXTextArea", "AXTextField")
                     and "Search Extensions" in (_string(e, "AXDescription") + _string(e, "AXPlaceholderValue"))), None)
    search = None
    for attempt in range(3):
        # Soon after VS Code starts, the menu choice or its Accessibility can be lost: ask again, then choose the view again.
        _accessible()
        _menu("View", "Extensions")
        try:
            search = _wait_for("the extensions search", search_box, 8)
            break
        except UIError:
            if attempt == 2:
                raise
    _AS.AXUIElementSetAttributeValue(search, _cf("AXFocused"), _TRUE)
    _key(KEY_A, "command down")
    _paste_text("@id:" + ext_id, lambda: ("@id:" + ext_id) in _string(search, "AXValue"))
    def result():
        # Only the search results' list, and only once it holds just this one extension (not the lists shown before the search).
        lists = [e for w in _windows() for e in _walk(w) if _role(e) == "AXList" and _string(e, "AXDescription") == "Extensions"]
        if len(lists) != 1:
            return None
        items = [e for e in _children(lists[0]) if _role(e) in ("AXGroup", "AXRow")]
        if len(items) != 1:
            return None
        return next((b for b in _walk(items[0]) if _role(b) == "AXButton" and "Install" in (_string(b, "AXTitle"), _string(b, "AXDescription"))), None)
    before = _installed()
    install = _wait_for(f"{ext_id} alone in the search results", result, SAVE_TIMEOUT * 2)
    _press(install)

    def installed_or_asked():
        if ext_id.lower() in _installed():
            return True
        publisher = _button_named("Trust Publisher & Install")
        if publisher is not None:
            _press(publisher)
            return False
        for window in _windows():
            items = list(_walk(window))
            if any(_role(e) == "AXButton" and "Trust Workspace & Install" in (_string(e, "AXTitle"), _string(e, "AXDescription")) for e in items):
                plain = next((e for e in items if _role(e) == "AXButton" and _string(e, "AXTitle") == "Install"), None)
                if plain is not None:
                    _press(plain)
        return False
    _wait_for(f"{ext_id} to be installed", installed_or_asked, SAVE_TIMEOUT * 6)
    _distrust()
    extra = sorted(_installed() - before - {ext_id.lower()})
    return _checked("extension_install", mode, {"id": ext_id, "installed": True, **({"also_installed": extra} if extra else {})})
