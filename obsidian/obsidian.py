"""Obsidian commands for agents: plain functions with keyword arguments, for vaults and notes.

mode="ui" works on screen: elements are found by role and name through the macOS Accessibility API, menu items are clicked by name, and
text is pasted through the clipboard, which is restored afterwards. No screen coordinates.

Set OBSIDIAN_ALLOWED_ROOT to a folder and every path is checked to be inside it, after following links, before anything happens.

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

APP = "Obsidian"
BUNDLE_ID = "md.obsidian"
TIMEOUT = 10
SAVE_TIMEOUT = 15
ROOT_ENV = "OBSIDIAN_ALLOWED_ROOT"
APP_PLIST = "/Applications/Obsidian.app/Contents/Info.plist"

VERIFIED: dict = {
    "note_create": {
        "ui": {
            "macos": "15.6.1 (24G90)",
            "app": "1.9.14 (0.14.8)"
        }
    },
    "vault_create": {
        "ui": {
            "macos": "15.6.1 (24G90)",
            "app": "1.9.14 (0.14.8)"
        }
    },
    "vault_list": {
        "ui": {
            "macos": "15.6.1 (24G90)",
            "app": "1.9.14 (0.14.8)"
        }
    }
}
UNSUPPORTED: dict = {}


class ObsidianError(Exception):
    pass


class NotFound(ObsidianError):
    pass


class Ambiguous(ObsidianError):
    pass


class AlreadyExists(ObsidianError):
    pass


class OutsideAllowedRoot(ObsidianError):
    pass


class StateBlocked(ObsidianError):
    pass


class UIError(ObsidianError):
    pass


class NotSupported(ObsidianError):
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
        raise UIError("Obsidian isn't running")
    return _AS.AXUIElementCreateApplication(int(found[0]))


def _windows() -> list:
    return [e for e in _children(_app()) if _role(e) == "AXWindow"]


def _is_document(window) -> bool:
    """A document window. While minimized, or while Obsidian is hidden, it reports itself as a dialog."""
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
    _wait_for("Obsidian in front", lambda: _system_events("return frontmost") == "true")


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


REGISTRY = os.path.expanduser("~/Library/Application Support/obsidian/obsidian.json")


def _accessible() -> None:
    """Obsidian (Electron) shows its window's contents to Accessibility only when asked."""
    _AS.AXUIElementSetAttributeValue(_app(), _cf("AXManualAccessibility"), _TRUE)


_ASKED = [0.0]


def _readable() -> bool:
    """A window whose contents Accessibility can see. A window Obsidian opens after the request (as while it starts) can stay
    unreadable, so the request is made again, but only after 3 seconds: asking each time rebuilds what Obsidian shows."""
    if any(sum(1 for _ in _walk(w)) > 10 for w in _windows()):
        return True
    if time.monotonic() - _ASKED[0] > 3:
        _accessible()
        _ASKED[0] = time.monotonic()
    return False


def _start() -> None:
    if not _running():
        subprocess.run(["open", "-b", BUNDLE_ID], check=True)
        _wait_for("Obsidian to start", _running, TIMEOUT * 3)
    _wait_for("Obsidian's window", _readable, TIMEOUT * 3)
    _forward()


def _button(root, title: str):
    return next((e for e in _walk(root) if _role(e) == "AXButton" and _string(e, "AXTitle") == title), None)


def _picker():
    """Obsidian's vault picker window (the one with Create and Open folder as vault)."""
    for window in _windows():
        texts = {_string(e, "AXValue") for e in _walk(window) if _role(e) == "AXStaticText"}
        if "Create new vault" in texts or "Create local vault" in texts:
            return window
    return None


def _vaults() -> dict:
    """Vault folders Obsidian knows, from its own registry file."""
    try:
        with open(REGISTRY) as handle:
            return {v["path"]: k for k, v in json.load(handle).get("vaults", {}).items()}
    except (OSError, ValueError):
        return {}


def vault_create(name: str, folder: str, mode: str = "ui") -> dict:
    """Make a new vault called name inside folder (Create new vault in Obsidian's vault picker). Obsidian then opens it."""
    _mode("vault_create", mode)
    if not name.strip() or "/" in name or "\n" in name or name.startswith("."):
        raise ValueError("name must be a single folder name")
    parent = _path(folder)
    if not os.path.isdir(parent):
        raise NotFound(f"no folder {parent}")
    target = os.path.join(parent, name)
    if os.path.lexists(target):
        raise AlreadyExists(f"{target} already exists; nothing was made")
    _start()
    if _picker() is None:
        _menu("File", "Open Vault…")
    picker = _wait_for("Obsidian's vault picker", lambda: _readable() and _picker(), TIMEOUT * 2)
    if _button(picker, "Browse") is None:
        _press(_wait_for("Create in the vault picker", lambda: _button(picker, "Create")))
    browse = _wait_for("Browse", lambda: _button(picker, "Browse"))
    field = next(e for e in _walk(picker) if _role(e) == "AXTextField" and _string(e, "AXPlaceholderValue") == "Vault name")
    _AS.AXUIElementSetAttributeValue(field, _cf("AXFocused"), _TRUE)
    _key(KEY_A, "command down")
    _paste_text(name, lambda: unicodedata.normalize("NFC", _string(field, "AXValue")) == unicodedata.normalize("NFC", name))
    _press(browse)
    panel = _wait_for("the folder dialog", lambda: next((w for w in _windows() if _by_id(w, "OKButton") is not None), None), TIMEOUT)
    try:
        _key(KEY_G, "{command down, shift down}")
        go = _wait_for("Go to Folder", lambda: _by_id(panel, "GoToWindow"))
        path_field = _wait_for("the folder field", lambda: _by_id(go, "PathTextField"))
        _key(KEY_A, "command down")
        _paste_text(parent, lambda: _string(path_field, "AXValue") == parent)
        _key(RETURN)
        _wait_for("Go to Folder to close", lambda: _by_id(panel, "GoToWindow") is None)
        _press(_by_id(panel, "OKButton"))
    except Exception:
        cancel = _by_id(panel, "CancelButton")
        if cancel is not None:
            _press(cancel)
        raise
    _wait_for("the folder dialog to close", lambda: not any(_by_id(w, "OKButton") is not None for w in _windows()))
    _press(_wait_for("Create", lambda: [b for b in _walk(picker) if _role(b) == "AXButton" and _string(b, "AXTitle") == "Create"][-1]))
    _wait_for("the vault to be made", lambda: os.path.isdir(os.path.join(target, ".obsidian")) and target in _vaults(), SAVE_TIMEOUT * 2)
    return _checked("vault_create", mode, {"name": name, "path": target})


def vault_list(mode: str = "ui") -> list:
    """The vaults Obsidian knows, read from its own registry file: [{name, path}]."""
    _mode("vault_list", mode)
    return _checked("vault_list", mode, [{"name": os.path.basename(p), "path": p} for p in sorted(_vaults())])


def note_create(vault: str, title: str, text: str = "", mode: str = "ui") -> dict:
    """Make a note in a vault Obsidian knows, through Obsidian's own obsidian://new link. Links such as [[Other note]] in text are
    kept as written. vault is the vault's folder."""
    _mode("note_create", mode)
    full = _path(vault)
    if full not in _vaults():
        raise NotFound(f"Obsidian doesn't know a vault at {full}")
    if not title.strip() or "/" in title or "\n" in title or title.startswith("."):
        raise ValueError("title must be one line without /")
    note = os.path.join(full, title + ".md")
    if os.path.lexists(note):
        raise AlreadyExists(f"{note} already exists; nothing was changed")
    _start()
    query = urllib.parse.urlencode({"vault": os.path.basename(full), "name": title, "content": text}, quote_via=urllib.parse.quote)
    subprocess.run(["open", f"obsidian://new?{query}"], check=True)
    _wait_for("the note to be written", lambda: os.path.isfile(note) and open(note, encoding="utf-8").read() == text, SAVE_TIMEOUT)
    return _checked("note_create", mode, {"vault": full, "title": title, "path": note})

