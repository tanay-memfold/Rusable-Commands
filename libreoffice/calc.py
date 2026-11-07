"""LibreOffice Calc commands for agents: plain functions with keyword arguments, to sort a CSV file.

mode="ui" works on screen: windows, menu items, dialogs, buttons and the Name Box are found by name or identifier through the macOS
Accessibility API; the cell cursor is moved with the keyboard and checked in Calc's Name Box; paths are pasted through the clipboard,
which is restored afterwards. The Sort dialog's checkbox and order buttons ignore the Accessibility press, so they are clicked at the
left end of the element's own frame when their value didn't change. No fixed screen positions.

Set CALC_ALLOWED_ROOT to a folder and every path is checked to be inside it, after following links, before anything happens.

Errors: NotFound, AlreadyExists, OutsideAllowedRoot, StateBlocked (the screen holds something the call won't destroy), UIError (an
element never appeared, or the result wasn't seen in time), NotSupported (the mode can't do it or wasn't verified)."""
from __future__ import annotations

import ctypes
import json
import os
import plistlib
import subprocess
import time
import re
import unicodedata
import urllib.parse
import warnings

APP = "soffice"
BUNDLE_ID = "org.libreoffice.script"
TIMEOUT = 10
SAVE_TIMEOUT = 15
ROOT_ENV = "CALC_ALLOWED_ROOT"
APP_PLIST = "/Applications/LibreOffice.app/Contents/Info.plist"

VERIFIED: dict = {
    "csv_convert": {
        "ui": {
            "macos": "15.6.1 (24G90)",
            "app": "26.8.1.1 (26.8.1.1)"
        }
    },
    "csv_sort": {
        "ui": {
            "macos": "15.6.1 (24G90)",
            "app": "26.8.1.1 (26.8.1.1)"
        }
    },
    "spreadsheet_to_csv": {
        "ui": {
            "macos": "15.6.1 (24G90)",
            "app": "26.8.1.1 (26.8.1.1)"
        }
    }
}
UNSUPPORTED: dict = {}


class CalcError(Exception):
    pass


class NotFound(CalcError):
    pass


class Ambiguous(CalcError):
    pass


class AlreadyExists(CalcError):
    pass


class OutsideAllowedRoot(CalcError):
    pass


class StateBlocked(CalcError):
    pass


class UIError(CalcError):
    pass


class NotSupported(CalcError):
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
        raise UIError("LibreOffice isn't running")
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
    _wait_for("LibreOffice in front", lambda: _system_events("return frontmost") == "true")




import csv as _csv
import io as _io


def _calc_windows() -> list:
    return [w for w in _windows() if _string(w, "AXSubrole") in ("AXStandardWindow", "AXDialog")]


def _window_titled(title: str):
    return next((w for w in _windows() if unicodedata.normalize("NFC", _string(w, "AXTitle")) == unicodedata.normalize("NFC", title)), None)


def _close_welcome() -> None:
    """LibreOffice's first-run "Welcome to LibreOffice!" window is closed with its close button (nothing in it is changed)."""
    window = _window_titled("Welcome to LibreOffice!")
    if window is not None:
        close = next((e for e in _children(window) if _string(e, "AXSubrole") == "AXCloseButton"), None)
        if close is not None:
            _press(close)
            _wait_for("the Welcome window to close", lambda: _window_titled("Welcome to LibreOffice!") is None)


def _letters(index: int) -> str:
    out = ""
    index += 1
    while index:
        index, rem = divmod(index - 1, 26)
        out = chr(65 + rem) + out
    return out


def _number_of(element):
    value = _attr(element, "AXValue")
    if not value:
        return None
    out = ctypes.c_long()
    _CF.CFNumberGetValue.restype, _CF.CFNumberGetValue.argtypes = ctypes.c_bool, [_P, ctypes.c_int, _P]
    return out.value if _CF.CFNumberGetValue(value, 4, ctypes.byref(out)) else None


def _in_order(key: list, descending: bool) -> bool:
    """Whether the column reads in order: as numbers when every cell is one, else as text ignoring case (and accents, as Calc does)."""
    def folded(x):
        return "".join(c for c in unicodedata.normalize("NFD", x) if not unicodedata.combining(c)).casefold()
    try:
        numbers = [float(x) for x in key]
        return numbers == sorted(numbers, reverse=descending)
    except ValueError:
        pass
    return any(key == sorted(key, key=k, reverse=descending) for k in (folded, str.casefold, None))


def _read_csv(full: str) -> list:
    with open(full, encoding="utf-8-sig", newline="") as handle:
        return list(_csv.reader(handle))


_CG = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics")


class _Point(ctypes.Structure):
    _fields_ = [("x", ctypes.c_double), ("y", ctypes.c_double)]


_CG.CGEventCreateMouseEvent.restype = _P
_CG.CGEventCreateMouseEvent.argtypes = [_P, ctypes.c_uint32, _Point, ctypes.c_uint32]
_CG.CGEventPost.argtypes = [ctypes.c_uint32, _P]
_AS.AXValueGetValue.restype = ctypes.c_bool
_AS.AXValueGetValue.argtypes = [_P, ctypes.c_int, _P]


def _click_box(element) -> None:
    """Click a checkbox or radio button at its box: the left end of the named element's own frame (LibreOffice ignores pressing it here)."""
    point, size = (ctypes.c_double * 2)(), (ctypes.c_double * 2)()
    if not (_AS.AXValueGetValue(_attr(element, "AXPosition"), 1, point) and _AS.AXValueGetValue(_attr(element, "AXSize"), 2, size)):
        raise UIError("the checkbox's frame couldn't be read")
    if _system_events("return frontmost") != "true":
        raise StateBlocked("another app came to the front; nothing more was done")
    x, y = point[0] + min(10, size[0] / 2), point[1] + size[1] / 2
    for kind in (5, 1, 2):
        _CG.CGEventPost(0, _CG.CGEventCreateMouseEvent(None, kind, _Point(x, y), 0))
        time.sleep(0.12)


def csv_sort(path: str, column: str, to: str, descending: bool = False, mode: str = "ui") -> dict:
    """Open a CSV file in Calc, sort its rows by the column whose header is column (the first row is kept as the header), and save
    the result as a new CSV file at to, then close it. The file at path isn't changed."""
    _mode("csv_sort", mode)
    full = _existing(path)
    if not full.lower().endswith(".csv"):
        raise ValueError("path must be a .csv file")
    target = _new_path(to)
    if not target.lower().endswith(".csv"):
        raise ValueError("to must end in .csv")
    rows = _read_csv(full)
    if not rows or column not in rows[0]:
        raise NotFound(f"no column {column!r} in the first row of {full}")
    if rows[0].count(column) > 1:
        raise ValueError(f"more than one column is named {column!r}")
    index = rows[0].index(column)
    cell = _letters(index) + "1"
    name = os.path.basename(full)
    if _running() and _window_titled(name) is not None:
        raise StateBlocked(f"{name} is already open in LibreOffice; close it first, nothing was done")
    if _running() and _window_titled(os.path.basename(target)) is not None:
        raise StateBlocked(f"a document named {os.path.basename(target)} is open in LibreOffice, so it can't be saved over; close it first, nothing was done")
    subprocess.run(["open", "-a", "LibreOffice", full], check=True)
    _wait_for("LibreOffice to start", _running, TIMEOUT * 3)
    def text_import():
        return next((w for w in _windows() if _string(w, "AXTitle").startswith("Text Import")), None)
    def import_or_recovery():
        if any("Document Recovery" in _string(w, "AXTitle") for w in _windows()):
            # Recovered documents from a crash are the user's: they are left for the user to decide.
            raise StateBlocked("LibreOffice is offering Document Recovery; nothing was done, so as not to lose recovered documents")
        return text_import() or _window_titled(name)
    importer = _wait_for("the Text Import dialog", import_or_recovery, TIMEOUT * 3)
    if _string(importer, "AXTitle").startswith("Text Import"):
        comma = _find(importer, "AXCheckBox", "Comma")
        if comma is not None and _number_of(comma) != 1:
            _press(comma)
        _press(_find(importer, "AXButton", "OK"))
    document = _wait_for(f"{name}'s window", lambda: _window_titled(name), TIMEOUT * 3)
    _close_welcome()
    _AS.AXUIElementSetAttributeValue(document, _cf("AXMain"), _TRUE)
    _AS.AXUIElementPerformAction(document, _cf("AXRaise"))
    _forward()
    # Keys must reach this document, not another LibreOffice window: wait until it is the focused window.
    _wait_for(f"{name}'s window to have the keyboard", lambda: unicodedata.normalize("NFC", _string(_attr(_app(), "AXFocusedWindow"), "AXTitle"))
              == unicodedata.normalize("NFC", name), TIMEOUT)
    box = _wait_for("the Name Box", lambda: next((e for e in _walk(document) if _role(e) == "AXComboBox" and
                                                   re.fullmatch(r"[A-Z]+[0-9]+(:[A-Z]+[0-9]+)?", _string(e, "AXValue") or "")), None))
    # The cursor goes to A1 (⌘Home) and right to the column; the Name Box (Calc's own address field) then has to read that cell.
    _key(115, "command down")
    time.sleep(0.3)
    for _ in range(index):
        _key(124)
        time.sleep(0.1)
    _wait_for(f"the cursor at {cell}", lambda: _string(box, "AXValue") == cell)
    _menu("Data", "Sort…")
    dialog = _wait_for("the Sort dialog", lambda: _window_titled("Sort"), TIMEOUT * 2)
    try:
        labels = _wait_for("Range contains column labels", lambda: _find(dialog, "AXCheckBox", "Range contains column labels"))
        if _number_of(labels) != 1:
            _press(labels)
            time.sleep(0.5)
        if _number_of(labels) != 1:
            _click_box(labels)
        _wait_for("the column labels box to be ticked", lambda: _number_of(labels) == 1)
        order = next((e for e in _walk(dialog) if _role(e) == "AXRadioButton" and _string(e, "AXTitle") == ("Descending" if descending else "Ascending")), None)
        if order is None:
            raise UIError("the Sort dialog's order wasn't found")
        if _number_of(order) != 1:
            _press(order)
            time.sleep(0.5)
        if _number_of(order) != 1:
            _click_box(order)
        _wait_for("the sort order to be chosen", lambda: _number_of(order) == 1)
        _press(_find(dialog, "AXButton", "OK"))
    except Exception:
        cancel = _find(dialog, "AXButton", "Cancel")
        if cancel is not None:
            _press(cancel)
        raise
    _wait_for("the Sort dialog to close", lambda: _window_titled("Sort") is None)
    _menu("File", "Save As…")
    panel = _wait_for("the Save dialog", lambda: _window_titled("Save"), TIMEOUT * 2)
    folder, new_name = os.path.split(target)
    try:
        _key(KEY_G, "{command down, shift down}")
        go = _wait_for("Go to Folder", lambda: _by_id(panel, "GoToWindow"))
        field = _wait_for("the folder field", lambda: _by_id(go, "PathTextField"))
        _key(KEY_A, "command down")
        _paste_text(folder, lambda: _string(field, "AXValue") == folder)
        _key(RETURN)
        _wait_for("Go to Folder to close", lambda: _by_id(panel, "GoToWindow") is None)
        name_box = _wait_for("the file name field", lambda: _by_id(panel, "saveAsNameTextField"))
        _focus(name_box)
        time.sleep(0.3)
        _key(KEY_A, "command down")
        _paste_text(new_name, lambda: unicodedata.normalize("NFC", _string(name_box, "AXValue")) == unicodedata.normalize("NFC", new_name))
        _press(_by_id(panel, "OKButton"))
    except Exception:
        cancel = _by_id(panel, "CancelButton") if panel is not None else None
        if cancel is not None:
            _press(cancel)
        raise

    def keep_or_done():
        # LibreOffice asks whether to keep the CSV format ("Use Text CSV Format"), then may show its Export Text File options.
        for window in _windows():
            keep = next((e for e in _walk(window) if _role(e) == "AXButton" and _string(e, "AXTitle").startswith("Use Text CSV Format")), None)
            if keep is not None:
                _press(keep)
                return None
            if _string(window, "AXTitle") == "Export Text File":
                _press(_find(window, "AXButton", "OK"))
                return None
        return os.path.isfile(target) or None
    _wait_for(f"{new_name} to be written", keep_or_done, SAVE_TIMEOUT * 2)
    time.sleep(1)
    written = _read_csv(target)
    body = written[1:]
    key = [r[index] if index < len(r) else "" for r in body]
    if written[:1] != rows[:1] or sorted(map(tuple, body)) != sorted(map(tuple, rows[1:])) or not _in_order(key, descending):
        raise UIError(f"{target} was written but isn't {rows[0][index]!r} sorted with the same rows")
    # The sorted file is on disk and checked, so its window is closed (File > Close), which also removes LibreOffice's lock file.
    # Calc may still ask to save in its own format; the CSV is already written, so that question is answered Don't Save.
    saved = _wait_for(f"{new_name}'s window", lambda: _window_titled(new_name), TIMEOUT)
    _AS.AXUIElementPerformAction(saved, _cf("AXRaise"))
    _wait_for(f"{new_name}'s window to have the keyboard", lambda: unicodedata.normalize("NFC", _string(_attr(_app(), "AXFocusedWindow"), "AXTitle"))
              == unicodedata.normalize("NFC", new_name), TIMEOUT)
    _menu("File", "Close")

    def closed():
        for window in _windows():
            dont = _find(window, "AXButton", "Don’t Save") or _find(window, "AXButton", "Don't Save")
            if dont is not None:
                _press(dont)
                return None
        return _window_titled(new_name) is None or None
    _wait_for(f"{new_name}'s window to close", closed, TIMEOUT)
    lock = os.path.join(os.path.dirname(target), f".~lock.{new_name}#")
    _wait_for("LibreOffice's lock file to go", lambda: not os.path.exists(lock), TIMEOUT)
    return _checked("csv_sort", mode, {"path": target, "column": column, "rows": len(body), "descending": descending})


# Convert (overnight, in its own section, tested on its own) ---------------------------------------------------------
# The CSV is opened as csv_sort opens it, then File > Save As… with the file type chosen by name in the save sheet's type menu,
# then LibreOffice's own "keep format" question if it asks. The saved spreadsheet is read back (its XML, inside the zip) and every
# cell must match the CSV. The new document is then closed.

import xml.etree.ElementTree as _ET
import zipfile as _zipfile

CONVERT_TYPES = {".xlsx": "Excel 2010–365 Spreadsheet (.xlsx)", ".ods": "ODF Spreadsheet (.ods)"}


def _xlsx_rows(full: str) -> list:
    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with _zipfile.ZipFile(full) as z:
        shared = []
        if "xl/sharedStrings.xml" in z.namelist():
            for si in _ET.fromstring(z.read("xl/sharedStrings.xml")).findall("m:si", ns):
                shared.append("".join(t.text or "" for t in si.iter(f"{{{ns['m']}}}t")))
        sheet = _ET.fromstring(z.read("xl/worksheets/sheet1.xml"))
    rows = []
    for row in sheet.iter(f"{{{ns['m']}}}row"):
        cells = {}
        for c in row.findall("m:c", ns):
            ref = re.match(r"([A-Z]+)", c.get("r", "")).group(1)
            col = sum((ord(ch) - 64) * 26 ** i for i, ch in enumerate(reversed(ref))) - 1
            v = c.find("m:v", ns)
            if c.get("t") == "s" and v is not None:
                cells[col] = shared[int(v.text)]
            elif c.get("t") == "inlineStr":
                cells[col] = "".join(t.text or "" for t in c.iter(f"{{{ns['m']}}}t"))
            else:
                cells[col] = v.text if v is not None and v.text is not None else ""
        rows.append([cells.get(i, "") for i in range(max(cells) + 1)] if cells else [])
    return rows


def _ods_rows(full: str) -> list:
    t = "urn:oasis:names:tc:opendocument:xmlns:table:1.0"
    tx = "urn:oasis:names:tc:opendocument:xmlns:text:1.0"
    with _zipfile.ZipFile(full) as z:
        root = _ET.fromstring(z.read("content.xml"))
    table = next(root.iter(f"{{{t}}}table"))
    rows = []
    for row in table.iter(f"{{{t}}}table-row"):
        repeat = int(row.get(f"{{{t}}}number-rows-repeated", "1"))
        cells = []
        for c in row:
            if c.tag not in (f"{{{t}}}table-cell", f"{{{t}}}covered-table-cell"):
                continue
            text = "\n".join("".join(p.itertext()) for p in c.findall(f"{{{tx}}}p"))
            cells += [text] * int(c.get(f"{{{t}}}number-columns-repeated", "1"))
        while cells and cells[-1] == "":
            cells.pop()
        if cells:
            rows += [cells] * (repeat if repeat < 1000 else 1)
    return rows


def csv_convert(path: str, to: str, mode: str = "ui") -> dict:
    """Save a CSV file as a new spreadsheet: an Excel .xlsx or an OpenDocument .ods file, by the suffix of to. The CSV isn't changed."""
    _mode("csv_convert", mode)
    full = _existing(path)
    if not full.lower().endswith(".csv"):
        raise ValueError("path must be a .csv file")
    target = _new_path(to)
    suffix = os.path.splitext(target)[1].lower()
    if suffix not in CONVERT_TYPES:
        raise ValueError("to must end in .xlsx or .ods")
    rows = [r for r in _read_csv(full) if r]
    if not rows:
        raise ValueError(f"{full} has no rows")
    name, new_name = os.path.basename(full), os.path.basename(target)
    if _running() and _window_titled(name) is not None:
        raise StateBlocked(f"{name} is already open in LibreOffice; close it first, nothing was done")
    if _running() and _window_titled(new_name) is not None:
        raise StateBlocked(f"a document named {new_name} is open in LibreOffice; close it first, nothing was done")
    subprocess.run(["open", "-a", "LibreOffice", full], check=True)
    _wait_for("LibreOffice to start", _running, TIMEOUT * 3)

    def import_or_recovery():
        if any("Document Recovery" in _string(w, "AXTitle") for w in _windows()):
            raise StateBlocked("LibreOffice is offering Document Recovery; nothing was done, so as not to lose recovered documents")
        return next((w for w in _windows() if _string(w, "AXTitle").startswith("Text Import")), None) or _window_titled(name)
    importer = _wait_for("the Text Import dialog", import_or_recovery, TIMEOUT * 3)
    if _string(importer, "AXTitle").startswith("Text Import"):
        comma = _find(importer, "AXCheckBox", "Comma")
        if comma is not None and _number_of(comma) != 1:
            _press(comma)
        _press(_find(importer, "AXButton", "OK"))
    document = _wait_for(f"{name}'s window", lambda: _window_titled(name), TIMEOUT * 3)
    _close_welcome()
    _AS.AXUIElementSetAttributeValue(document, _cf("AXMain"), _TRUE)
    _AS.AXUIElementPerformAction(document, _cf("AXRaise"))
    _forward()
    _wait_for(f"{name}'s window to have the keyboard", lambda: unicodedata.normalize("NFC", _string(_attr(_app(), "AXFocusedWindow"), "AXTitle"))
              == unicodedata.normalize("NFC", name), TIMEOUT)
    _menu("File", "Save As…")
    panel = _wait_for("the Save dialog", lambda: _window_titled("Save"), TIMEOUT * 2)
    folder = os.path.dirname(target)
    try:
        kind = next((e for e in _walk(panel) if _role(e) == "AXPopUpButton" and re.search(r"\(\.[a-z]+\)$", _string(e, "AXValue") or "")), None)
        if kind is None:
            raise UIError("the file type menu wasn't found")
        if _string(kind, "AXValue") != CONVERT_TYPES[suffix]:
            _press(kind)
            item = _wait_for(f"{CONVERT_TYPES[suffix]} in the type menu", lambda: next((e for e in _walk(kind) if _role(e) == "AXMenuItem"
                                                                                        and _string(e, "AXTitle") == CONVERT_TYPES[suffix]), None))
            _press(item)
            _wait_for("the file type to change", lambda: _string(kind, "AXValue") == CONVERT_TYPES[suffix])
        _key(KEY_G, "{command down, shift down}")
        go = _wait_for("Go to Folder", lambda: _by_id(panel, "GoToWindow"))
        field = _wait_for("the folder field", lambda: _by_id(go, "PathTextField"))
        _key(KEY_A, "command down")
        _paste_text(folder, lambda: _string(field, "AXValue") == folder)
        _key(RETURN)
        _wait_for("Go to Folder to close", lambda: _by_id(panel, "GoToWindow") is None)
        name_box = _wait_for("the file name field", lambda: _by_id(panel, "saveAsNameTextField"))
        _focus(name_box)
        time.sleep(0.3)
        _key(KEY_A, "command down")
        _paste_text(new_name, lambda: unicodedata.normalize("NFC", _string(name_box, "AXValue")) == unicodedata.normalize("NFC", new_name))
        _press(_by_id(panel, "OKButton"))
    except Exception:
        cancel = _by_id(panel, "CancelButton") if panel is not None else None
        if cancel is not None:
            _press(cancel)
        raise

    def keep_or_done():
        for window in _windows():
            keep = next((e for e in _walk(window) if _role(e) == "AXButton" and _string(e, "AXTitle").startswith("Use Excel")), None)
            if keep is not None and suffix == ".xlsx":
                _press(keep)
                return None
        return os.path.isfile(target) or None
    _wait_for(f"{new_name} to be written", keep_or_done, SAVE_TIMEOUT * 2)
    size = -1
    while os.path.getsize(target) != size:
        size = os.path.getsize(target)
        time.sleep(0.5)
    try:
        written = _xlsx_rows(target) if suffix == ".xlsx" else _ods_rows(target)
    except (KeyError, _zipfile.BadZipFile, _ET.ParseError, StopIteration) as error:
        raise UIError(f"{target} was written but couldn't be read back as a spreadsheet ({error})") from None
    if written != rows:
        raise UIError(f"{target} was written but its cells don't match the CSV")
    saved = _wait_for(f"{new_name}'s window", lambda: _window_titled(new_name), TIMEOUT)
    _AS.AXUIElementPerformAction(saved, _cf("AXRaise"))
    _wait_for(f"{new_name}'s window to have the keyboard", lambda: unicodedata.normalize("NFC", _string(_attr(_app(), "AXFocusedWindow"), "AXTitle"))
              == unicodedata.normalize("NFC", new_name), TIMEOUT)
    _menu("File", "Close")

    def closed():
        for window in _windows():
            dont = _find(window, "AXButton", "Don’t Save") or _find(window, "AXButton", "Don't Save")
            if dont is not None:
                _press(dont)
                return None
        return _window_titled(new_name) is None or None
    _wait_for(f"{new_name}'s window to close", closed, TIMEOUT)
    lock = os.path.join(folder, f".~lock.{new_name}#")
    _wait_for("LibreOffice's lock file to go", lambda: not os.path.exists(lock), TIMEOUT)
    return _checked("csv_convert", mode, {"path": target, "format": suffix[1:], "rows": len(rows)})


# Spreadsheet to CSV (overnight, in its own section, tested on its own) ---------------------------------------------
# The .xlsx or .ods file is opened in LibreOffice, then File > Save As… with Text CSV chosen by name in the type menu, then "Use Text
# CSV Format" and Export Text File's OK. The written CSV is read back and must hold the first sheet's cells.

def spreadsheet_to_csv(path: str, to: str, mode: str = "ui") -> dict:
    """Save the first sheet of an .xlsx or .ods spreadsheet as a new CSV file at to. The spreadsheet isn't changed."""
    _mode("spreadsheet_to_csv", mode)
    full = _existing(path)
    suffix = os.path.splitext(full)[1].lower()
    if suffix not in (".xlsx", ".ods"):
        raise ValueError("path must be an .xlsx or .ods file")
    target = _new_path(to)
    if not target.lower().endswith(".csv"):
        raise ValueError("to must end in .csv")
    try:
        cells = [r for r in (_xlsx_rows(full) if suffix == ".xlsx" else _ods_rows(full)) if r]
    except (KeyError, _zipfile.BadZipFile, _ET.ParseError, StopIteration) as error:
        raise ValueError(f"{full} couldn't be read as a spreadsheet ({error})") from None
    name, new_name = os.path.basename(full), os.path.basename(target)
    if _running() and (_window_titled(name) is not None or _window_titled(new_name) is not None):
        raise StateBlocked("a document with that name is already open in LibreOffice; close it first, nothing was done")
    subprocess.run(["open", "-a", "LibreOffice", full], check=True)
    _wait_for("LibreOffice to start", _running, TIMEOUT * 3)

    def opened():
        if any("Document Recovery" in _string(w, "AXTitle") for w in _windows()):
            raise StateBlocked("LibreOffice is offering Document Recovery; nothing was done, so as not to lose recovered documents")
        return _window_titled(name)
    document = _wait_for(f"{name}'s window", opened, TIMEOUT * 3)
    _close_welcome()
    _AS.AXUIElementSetAttributeValue(document, _cf("AXMain"), _TRUE)
    _AS.AXUIElementPerformAction(document, _cf("AXRaise"))
    _forward()
    _wait_for(f"{name}'s window to have the keyboard", lambda: unicodedata.normalize("NFC", _string(_attr(_app(), "AXFocusedWindow"), "AXTitle"))
              == unicodedata.normalize("NFC", name), TIMEOUT)
    _menu("File", "Save As…")
    panel = _wait_for("the Save dialog", lambda: _window_titled("Save"), TIMEOUT * 2)
    folder = os.path.dirname(target)
    try:
        kind = next((e for e in _walk(panel) if _role(e) == "AXPopUpButton" and re.search(r"\(\.[a-z]+\)$", _string(e, "AXValue") or "")), None)
        if kind is None:
            raise UIError("the file type menu wasn't found")
        if _string(kind, "AXValue") != "Text CSV (.csv)":
            _press(kind)
            item = _wait_for("Text CSV in the type menu", lambda: next((e for e in _walk(kind) if _role(e) == "AXMenuItem"
                                                                       and _string(e, "AXTitle") == "Text CSV (.csv)"), None))
            _press(item)
            _wait_for("the file type to change", lambda: _string(kind, "AXValue") == "Text CSV (.csv)")
        _key(KEY_G, "{command down, shift down}")
        go = _wait_for("Go to Folder", lambda: _by_id(panel, "GoToWindow"))
        field = _wait_for("the folder field", lambda: _by_id(go, "PathTextField"))
        _key(KEY_A, "command down")
        _paste_text(folder, lambda: _string(field, "AXValue") == folder)
        _key(RETURN)
        _wait_for("Go to Folder to close", lambda: _by_id(panel, "GoToWindow") is None)
        name_box = _wait_for("the file name field", lambda: _by_id(panel, "saveAsNameTextField"))
        _focus(name_box)
        time.sleep(0.3)
        _key(KEY_A, "command down")
        _paste_text(new_name, lambda: unicodedata.normalize("NFC", _string(name_box, "AXValue")) == unicodedata.normalize("NFC", new_name))
        _press(_by_id(panel, "OKButton"))
    except Exception:
        cancel = _by_id(panel, "CancelButton") if panel is not None else None
        if cancel is not None:
            _press(cancel)
        raise

    def keep_or_done():
        for window in _windows():
            keep = next((e for e in _walk(window) if _role(e) == "AXButton" and _string(e, "AXTitle").startswith("Use Text CSV Format")), None)
            if keep is not None:
                _press(keep)
                return None
            if _string(window, "AXTitle") == "Export Text File":
                _press(_find(window, "AXButton", "OK"))
                return None
        return os.path.isfile(target) or None
    _wait_for(f"{new_name} to be written", keep_or_done, SAVE_TIMEOUT * 2)
    size = -1
    while os.path.getsize(target) != size:
        size = os.path.getsize(target)
        time.sleep(0.5)
    written = [r for r in _read_csv(target) if r]
    if written != cells:
        raise UIError(f"{target} was written but its cells don't match the spreadsheet's first sheet")
    saved = _wait_for(f"{new_name}'s window", lambda: _window_titled(new_name), TIMEOUT)
    _AS.AXUIElementPerformAction(saved, _cf("AXRaise"))
    _wait_for(f"{new_name}'s window to have the keyboard", lambda: unicodedata.normalize("NFC", _string(_attr(_app(), "AXFocusedWindow"), "AXTitle"))
              == unicodedata.normalize("NFC", new_name), TIMEOUT)
    _menu("File", "Close")

    def closed():
        for window in _windows():
            dont = _find(window, "AXButton", "Don’t Save") or _find(window, "AXButton", "Don't Save")
            if dont is not None:
                _press(dont)
                return None
        return _window_titled(new_name) is None or None
    _wait_for(f"{new_name}'s window to close", closed, TIMEOUT)
    lock = os.path.join(folder, f".~lock.{new_name}#")
    _wait_for("LibreOffice's lock file to go", lambda: not os.path.exists(lock), TIMEOUT)
    return _checked("spreadsheet_to_csv", mode, {"path": target, "rows": len(written)})
