"""Contacts commands for agents: plain functions with keyword arguments, for the cards in Apple Contacts on this Mac.

mode="ui" makes the change on screen: elements are found by role and name through the macOS Accessibility API and pressed,
menu items are clicked by name, and text is pasted through the clipboard (restored afterwards). The card to act on is found
by exact name through Contacts' own scripting and its row is selected, so the edit lands on that card only.
mode="background" uses Contacts' own scripting and shows nothing.

Errors: NotFound, Ambiguous (nothing changed), AlreadyExists, StateBlocked (the screen holds something the call won't
destroy), UIError (an element never appeared), NotSupported (the mode can't do it)."""
from __future__ import annotations

import ctypes
import datetime as _dt
import json
import os
import plistlib
import subprocess
import time
import warnings

APP = "Contacts"
BUNDLE_ID = "com.apple.AddressBook"
TIMEOUT = 10
SAVE_TIMEOUT = 25
FIELDS = ("id", "name", "first", "last", "company", "emails", "phones", "note", "groups")
DEFAULT_FIELDS = "name,first,last,company,emails,phones,note,groups"

VERIFIED: dict = {
    "contact_add_address": {
        "background": {
            "macos": "15.6.1 (24G90)",
            "app": "14.0 (2695.500.71)"
        }
    },
    "contact_add_email": {
        "background": {
            "macos": "15.6.1 (24G90)",
            "app": "14.0 (2695.500.71)"
        }
    },
    "contact_add_phone": {
        "background": {
            "macos": "15.6.1 (24G90)",
            "app": "14.0 (2695.500.71)"
        }
    },
    "contact_create": {
        "background": {
            "macos": "15.6.1 (24G90)",
            "app": "14.0 (2695.500.71)"
        },
        "ui": {
            "macos": "15.6.1 (24G90)",
            "app": "14.0 (2695.500.71)"
        }
    },
    "contact_delete": {
        "background": {
            "macos": "15.6.1 (24G90)",
            "app": "14.0 (2695.500.71)"
        },
        "ui": {
            "macos": "15.6.1 (24G90)",
            "app": "14.0 (2695.500.71)"
        }
    },
    "contact_details": {
        "background": {
            "macos": "15.6.1 (24G90)",
            "app": "14.0 (2695.500.71)"
        }
    },
    "contact_export_vcard": {
        "background": {
            "macos": "15.6.1 (24G90)",
            "app": "14.0 (2695.500.71)"
        }
    },
    "contact_get": {
        "background": {
            "macos": "15.6.1 (24G90)",
            "app": "14.0 (2695.500.71)"
        }
    },
    "contact_list": {
        "background": {
            "macos": "15.6.1 (24G90)",
            "app": "14.0 (2695.500.71)"
        }
    },
    "contact_merge": {
        "ui": {
            "macos": "15.6.1 (24G90)",
            "app": "14.0 (2695.500.71)"
        }
    },
    "contact_remove_email": {
        "background": {
            "macos": "15.6.1 (24G90)",
            "app": "14.0 (2695.500.71)"
        }
    },
    "contact_remove_phone": {
        "background": {
            "macos": "15.6.1 (24G90)",
            "app": "14.0 (2695.500.71)"
        }
    },
    "contact_search": {
        "background": {
            "macos": "15.6.1 (24G90)",
            "app": "14.0 (2695.500.71)"
        }
    },
    "contact_set_birthday": {
        "background": {
            "macos": "15.6.1 (24G90)",
            "app": "14.0 (2695.500.71)"
        }
    },
    "contact_set_job_title": {
        "background": {
            "macos": "15.6.1 (24G90)",
            "app": "14.0 (2695.500.71)"
        }
    },
    "contact_set_phone": {
        "background": {
            "macos": "15.6.1 (24G90)",
            "app": "14.0 (2695.500.71)"
        }
    },
    "contact_update": {
        "background": {
            "macos": "15.6.1 (24G90)",
            "app": "14.0 (2695.500.71)"
        },
        "ui": {
            "macos": "15.6.1 (24G90)",
            "app": "14.0 (2695.500.71)"
        }
    },
    "group_add": {
        "background": {
            "macos": "15.6.1 (24G90)",
            "app": "14.0 (2695.500.71)"
        }
    },
    "group_create": {
        "background": {
            "macos": "15.6.1 (24G90)",
            "app": "14.0 (2695.500.71)"
        },
        "ui": {
            "macos": "15.6.1 (24G90)",
            "app": "14.0 (2695.500.71)"
        }
    },
    "group_delete": {
        "background": {
            "macos": "15.6.1 (24G90)",
            "app": "14.0 (2695.500.71)"
        },
        "ui": {
            "macos": "15.6.1 (24G90)",
            "app": "14.0 (2695.500.71)"
        }
    },
    "group_list": {
        "background": {
            "macos": "15.6.1 (24G90)",
            "app": "14.0 (2695.500.71)"
        }
    },
    "group_remove": {
        "background": {
            "macos": "15.6.1 (24G90)",
            "app": "14.0 (2695.500.71)"
        }
    },
    "group_rename": {
        "background": {
            "macos": "15.6.1 (24G90)",
            "app": "14.0 (2695.500.71)"
        },
        "ui": {
            "macos": "15.6.1 (24G90)",
            "app": "14.0 (2695.500.71)"
        }
    }
}


class ContactsError(Exception):
    pass


class NotFound(ContactsError):
    pass


class Ambiguous(ContactsError):
    pass


class AlreadyExists(ContactsError):
    pass


class StateBlocked(ContactsError):
    pass


class UIError(ContactsError):
    pass


class NotSupported(ContactsError):
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
    with open("/System/Applications/Contacts.app/Contents/Info.plist", "rb") as handle:
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


MEMBERSHIP = "adding to a list on screen means dragging a card, and these commands use no screen coordinates"
HIDDEN = "these fields can be added on screen only through menus and labels that weren't verified; use background"
UNSUPPORTED = {("group_add", "ui"): MEMBERSHIP, ("group_remove", "ui"): MEMBERSHIP,
               **{(name, "ui"): HIDDEN for name in ("contact_details", "contact_set_job_title", "contact_add_phone", "contact_set_phone",
                                                    "contact_remove_phone", "contact_add_email", "contact_remove_email", "contact_export_vcard")},
               ("contact_merge", "background"): "Contacts' scripting can't merge cards"}


def _mode(function: str, mode: str, supported: tuple = ("ui", "background")) -> None:
    if mode not in ("ui", "background"):
        raise ValueError(f"mode must be 'ui' or 'background', not {mode!r}")
    if VERIFIED and mode not in VERIFIED.get(function, {}):
        raise NotSupported(f"{function} has no verified {mode} mode: "
                           f"{UNSUPPORTED.get((function, mode), 'it did not pass verification')}")
    if mode not in supported:
        raise NotSupported(f"{function} has no {mode} mode: "
                           f"{UNSUPPORTED.get((function, mode), 'it reads data, which the background mode does')}")


def _fields(fields) -> list:
    chosen = [part.strip() for part in (fields or DEFAULT_FIELDS).split(",")] if isinstance(fields, (str, type(None))) \
        else list(fields)
    unknown = [name for name in chosen if name not in FIELDS]
    if unknown:
        raise ValueError(f"unknown fields {unknown}; choose from {', '.join(FIELDS)}")
    return chosen


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


# Contacts' own scripting -----------------------------------------------------------------------------------------

DATA = r"""
function run(argv) {
  const C = Application("Contacts");
  const op = argv[0], a = JSON.parse(argv[1]);
  const str = v => (v === null || v === undefined) ? "" : v;
  const groupsOf = C.groups().map(g => [g.name(), g.people().map(p => p.id())]);
  const info = p => ({id: p.id(), name: p.name(), first: str(p.firstName()), last: str(p.lastName()), company: str(p.organization()),
                      emails: p.emails().map(e => e.value()), phones: p.phones().map(e => e.value()), note: str(p.note()),
                      groups: groupsOf.filter(g => g[1].includes(p.id())).map(g => g[0])});
  const byId = id => C.people.byId(id);
  const named = name => C.groups().filter(g => g.name() === name);
  const setValues = p => {
    if (a.first !== null) p.firstName = a.first;
    if (a.last !== null) p.lastName = a.last;
    if (a.company !== null) p.organization = a.company;
    if (a.note !== null) p.note = a.note;
    if (a.email !== null) { if (p.emails().length) p.emails()[0].value = a.email; else p.emails.push(C.Email({label: "work", value: a.email})); }
    if (a.phone !== null) { if (p.phones().length) p.phones()[0].value = a.phone; else p.phones.push(C.Phone({label: "mobile", value: a.phone})); }
  };
  switch (op) {
    case "all": {
      const people = a.group === null ? C.people() : named(a.group)[0].people();
      return JSON.stringify(people.map(info));
    }
    case "find": return JSON.stringify(C.people().filter(p => p.name() === a.name).map(info));
    case "get": return JSON.stringify(info(byId(a.id)));
    case "create": { const p = C.Person({}); C.people.push(p); setValues(p); C.save(); return JSON.stringify(p.id()); }
    case "update": { setValues(byId(a.id)); C.save(); return "true"; }
    case "delete": { C.delete(byId(a.id)); C.save(); return "true"; }
    case "details": {
      const p = byId(a.id), lab = e => ({label: str(e.label()), value: e.value()});
      return JSON.stringify({job_title: str(p.jobTitle()), phones: p.phones().map(lab), emails: p.emails().map(lab)});
    }
    case "job": byId(a.id).jobTitle = a.value; C.save(); return "true";
    case "add_entry": { const p = byId(a.id); (a.kind === "phone" ? p.phones : p.emails).push((a.kind === "phone" ? C.Phone : C.Email)({label: a.label, value: a.value})); C.save(); return "true"; }
    case "set_entry": { for (const e of (a.kind === "phone" ? byId(a.id).phones() : byId(a.id).emails())) if (e.label() === a.label) e.value = a.value; C.save(); return "true"; }
    case "remove_entry": { for (const e of (a.kind === "phone" ? byId(a.id).phones() : byId(a.id).emails()).reverse()) if (e.label() === a.label) C.delete(e); C.save(); return "true"; }
    case "vcards": return JSON.stringify((a.id === null ? C.people() : [byId(a.id)]).map(p => p.vcard()));
    case "groups": return JSON.stringify(C.groups().map(g => ({name: g.name(), count: g.people().length})));
    case "group_create": C.groups.push(C.Group({name: a.name})); C.save(); return "true";
    case "group_rename": named(a.name)[0].name = a.to; C.save(); return "true";
    case "group_delete": C.delete(named(a.name)[0]); C.save(); return "true";
    case "group_add": C.add(byId(a.id), {to: named(a.name)[0]}); C.save(); return "true";
    case "group_remove": C.remove(byId(a.id), {from: named(a.name)[0]}); C.save(); return "true";
  }
  throw new Error("unknown op " + op);
}
"""


def _running() -> bool:
    return subprocess.run(["pgrep", "-x", APP], capture_output=True).returncode == 0


def _data(op: str, **args):
    return json.loads(_jxa(DATA, op, json.dumps(args)))


def _launch_hidden() -> None:
    """Start Contacts hidden and in the background when it isn't running, so nothing shows on screen."""
    if _running():
        return
    subprocess.run(["open", "-g", "-j", "-b", BUNDLE_ID], check=True)
    _wait_for("Contacts to start", lambda: _data("groups") is not None, TIMEOUT * 3, 2)


def _shape(item: dict, fields) -> dict:
    return {name: item[name] for name in _fields(fields)}


def _one(match: str) -> dict:
    found = _data("find", name=match)
    if not found:
        raise NotFound(f"no contact named {match!r}")
    if len(found) > 1:
        raise Ambiguous(f"{len(found)} contacts are named {match!r}; nothing was changed")
    return found[0]


def _group(name: str) -> dict:
    found = [g for g in _data("groups") if g["name"] == name]
    if not found:
        raise NotFound(f"no list named {name!r}")
    if len(found) > 1:
        raise Ambiguous(f"{len(found)} lists are named {name!r}; nothing was changed")
    return found[0]


def _saved(item_id: str, test) -> dict:
    return _wait_for("the change being saved", lambda: (lambda r: r if test(r) else None)(_data("get", id=item_id)),
                     SAVE_TIMEOUT, 2)


def _line(label: str, value) -> None:
    if value is not None and "\n" in value:
        raise ValueError(f"{label} must be one line")


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
        raise UIError("Contacts isn't running")
    return _AS.AXUIElementCreateApplication(int(found[0]))


def _window():
    return next((e for e in _children(_app()) if _role(e) == "AXWindow"), None)


def _sheets() -> list:
    window = _window()
    return [e for e in _children(window) if _role(e) == "AXSheet"] if window else []


def _system_events(body: str) -> str:
    return _osascript(f'tell application "System Events" to tell process "{APP}"\n{body}\nend tell')


def _key(code: int, modifier: str = "") -> None:
    if _system_events("return frontmost") != "true":
        raise StateBlocked("another app came to the front; nothing more was typed")
    _system_events(f"key code {code}" + (f" using {modifier} down" if modifier else ""))


ESCAPE, TAB = 53, 48


def _menu(title: str, item: str) -> None:
    _system_events(f'click menu item "{item}" of menu "{title}" of menu bar item "{title}" of menu bar 1')


def _has_menu_item(title: str, item: str) -> bool:
    return _system_events(f'exists menu item "{item}" of menu "{title}" of menu bar item "{title}" of menu bar 1') == "true"


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


def _focused():
    return _attr(_app(), "AXFocusedUIElement")


def _paste(text: str) -> None:
    """Paste into the focused field, replacing its text; wait until it shows; restore the clipboard."""
    saved = _jxa(CLIPBOARD, "save")
    try:
        _jxa(CLIPBOARD, "text", text)
        _key(0, "command")
        _key(9, "command")
        _wait_for("the pasted text to appear", lambda: _string(_focused(), "AXValue") == text)
    finally:
        # What was on the clipboard can be too large for an argument, so it goes through standard input.
        done = subprocess.run(["osascript", "-l", "JavaScript", "-e", CLIPBOARD, "restore"], input=saved,
                              capture_output=True, text=True)
        if done.returncode:
            raise UIError(done.stderr.strip())


def _clear_transients() -> None:
    """Close only Contacts' passing UI. A card or list name being edited, or a dialog with typed text, is left alone."""
    for _ in range(6):
        window = _window()
        if window is None:
            return
        if any(_role(e) == "AXMenu" for e in _walk(window)):
            _key(ESCAPE)
            time.sleep(0.3)
            continue
        sheets = _sheets()
        if sheets:
            fields = [e for e in _walk(sheets[0]) if _role(e) == "AXTextField"]
            cancel = _find(sheets[0], "AXButton", "Cancel")
            if any(_string(f, "AXValue").strip() for f in fields):
                raise StateBlocked("Contacts has a dialog with typed text in it; it was left as it is")
            if not cancel:
                raise StateBlocked("Contacts shows a dialog without a Cancel button; it was left as it is")
            _press(cancel)
            time.sleep(0.8)
            continue
        if _find(window, "AXButton", "Done"):
            raise StateBlocked("Contacts has a card being edited; it was left as it is")
        focused = _focused()
        if focused and _role(focused) == "AXTextField" and _string(focused, "AXSubrole") != "AXSearchField":
            raise StateBlocked("Contacts has a list name being edited; it was left as it is")
        search = next((e for e in _walk(window) if _string(e, "AXSubrole") == "AXSearchField"), None)
        if search and _string(search, "AXValue"):
            # The clear button can act yet report an error, so the field itself is what's checked next time round.
            cancel = _find(search, "AXButton", "cancel")
            if cancel:
                _AS.AXUIElementPerformAction(cancel, _cf("AXPress"))
                time.sleep(0.3)
            if _string(search, "AXValue"):
                _focus(search)
                _key(0, "command")
                _key(51)
            _key(ESCAPE)
            time.sleep(0.5)
            continue
        return
    raise UIError("Contacts still shows a menu, dialog or search")


def _ready() -> None:
    """Contacts in front, its main window showing, with no menu, dialog or search left open."""
    if _running() and _window():
        # Checked before anything is raised, because the screen holds someone's edit.
        window = _window()
        if _find(window, "AXButton", "Done"):
            raise StateBlocked("Contacts has a card being edited; it was left as it is")
    if not _running():
        subprocess.run(["open", "-b", BUNDLE_ID], check=True)
        _wait_for("Contacts to start", _running, TIMEOUT * 3)
    _osascript(f'tell application "{APP}" to activate')
    _system_events("set visible to true")
    for window in [e for e in _children(_app()) if _role(e) == "AXWindow"]:
        if _attr(window, "AXMinimized") == _TRUE.value:
            _AS.AXUIElementSetAttributeValue(window, _cf("AXMinimized"), _FALSE)
    try:
        _wait_for("a window", _window, 2)
    except UIError:
        subprocess.run(["open", "-b", BUNDLE_ID], check=True)
    _wait_for("the Contacts window in front", lambda: _window() and _system_events("return frontmost") == "true", SAVE_TIMEOUT)
    time.sleep(0.5)
    _clear_transients()


def _ready_for(mode: str) -> None:
    if mode == "ui":
        _ready()
    else:
        _launch_hidden()


def _outline(title: str):
    return _wait_for(f"the {title}", lambda: next((e for e in _walk(_window()) if _role(e) == "AXOutline"
                                                   and _string(e, "AXTitle") == title), None))


LISTS, CARDS = "Contact Lists List", "Contact List"


def _row_named(outline, name: str):
    for row in _children(outline):
        if _role(row) == "AXRow" and any(_string(e, "AXValue") == name for e in _walk(row)
                                         if _role(e) in ("AXStaticText", "AXTextField")):
            return row
    return None


def _select_in(title: str, name: str):
    """Focus this column and select the row showing exactly this name; nothing else is left selected."""
    outline = _outline(title)
    _focus(outline)
    time.sleep(0.2)
    row = _wait_for(f"the row {name!r}", lambda: _row_named(_outline(title), name))
    _AS.AXUIElementSetAttributeValue(row, _cf("AXSelected"), _TRUE)
    _wait_for("the row to be selected", lambda: _attr(row, "AXSelected") == _TRUE.value)
    selected = [r for r in _children(_outline(title)) if _role(r) == "AXRow" and _attr(r, "AXSelected") == _TRUE.value]
    if len(selected) != 1:
        raise UIError("more than one row is selected; nothing was changed")
    time.sleep(0.3)


def _select_card(name: str) -> None:
    _select_in(LISTS, "All Contacts")
    time.sleep(0.4)
    try:
        _wait_for("the card's row", lambda: _row_named(_outline(CARDS), name), 4)
    except UIError:
        # The card list can lag behind a search that was just cleared; choosing the list again refreshes it.
        groups = [g["name"] for g in _data("groups")]
        if groups:
            _select_in(LISTS, groups[0])
            time.sleep(0.5)
        _select_in(LISTS, "All Contacts")
        time.sleep(0.5)
    _select_in(CARDS, name)


def _menu_item_starting(title: str, start: str) -> str:
    names = _system_events(f'name of menu items of menu "{title}" of menu bar item "{title}" of menu bar 1').split(", ")
    return next((n for n in names if n.startswith(start)), "")


def _confirm_delete(name: str) -> None:
    """Press Delete in Contacts' alert only if it names what is meant to go; otherwise cancel and stop."""
    sheet = _sheets()[0]
    text = " ".join(_string(e, "AXValue") for e in _walk(sheet) if _role(e) == "AXStaticText")
    if name not in text:
        _press(_find(sheet, "AXButton", "Cancel"))
        raise UIError("Contacts' delete alert doesn't name the item; nothing was deleted")
    _press(_find(sheet, "AXButton", "Delete"))


def _field(description: str = "", placeholder: str = "", empty: bool = False):
    for element in _walk(_window()):
        if _role(element) in ("AXTextField", "AXTextArea") and _string(element, "AXSubrole") != "AXSearchField":
            if description and _string(element, "AXDescription") == description:
                return element
            if placeholder and _string(element, "AXPlaceholderValue") == placeholder and (not empty or not _string(element, "AXValue")):
                return element
    return None


def _put(field, text: str) -> None:
    _focus(field)
    time.sleep(0.3)
    _paste(text)


def _edit_values(first, last, company, email, phone, note, item=None) -> None:
    for label, value in (("First", first), ("Last", last), ("Company", company)):
        if value is not None:
            _put(_wait_for(f"the {label} field", lambda: _field(description=label)), value)
    if email is not None:
        if item and item["emails"]:
            field = next(e for e in _walk(_window()) if _role(e) == "AXTextField" and _string(e, "AXValue") == item["emails"][0])
        else:
            field = _wait_for("the Email field", lambda: _field(placeholder="Email", empty=True))
        _put(field, email)
    if phone is not None:
        if item and item["phones"]:
            field = _wait_for("the Phone field", lambda: _field(placeholder="Phone"))
        else:
            field = _wait_for("the Phone field", lambda: _field(placeholder="Phone", empty=True))
        _put(field, phone)
    if note is not None:
        _put(_wait_for("the Note field", lambda: _field(description="Note")), note)
    # This button acts but reports an error from AXPress, so what's checked is that the card left edit mode.
    _AS.AXUIElementPerformAction(_find(_window(), "AXButton", "Done"), _cf("AXPress"))
    _wait_for("the card to be saved", lambda: not _find(_window(), "AXButton", "Done"))


# Contacts ---------------------------------------------------------------------------------------------------------

def contact_create(first: str | None = None, last: str | None = None, company: str | None = None, email: str | None = None,
                   phone: str | None = None, note: str | None = None, mode: str = "ui") -> dict:
    """Add a card. It needs a first name, last name or company."""
    _mode("contact_create", mode)
    if not any(v and v.strip() for v in (first, last, company)):
        raise ValueError("a contact needs a first name, last name or company")
    for label, value in (("first", first), ("last", last), ("company", company), ("email", email), ("phone", phone)):
        _line(label, value)
    _ready_for(mode)
    before = {p["id"] for p in _data("all", group=None)}
    if mode == "background":
        item_id = _data("create", first=first, last=last, company=company, email=email, phone=phone, note=note)
    else:
        _select_in(LISTS, "All Contacts")
        _menu("File", "New Card")
        _wait_for("the new card", lambda: _field(description="First"))
        _edit_values(first, last, company, email, phone, note)
        item_id = _wait_for("the new card to be saved", lambda: next(iter({p["id"] for p in _data("all", group=None)} - before), None),
                            SAVE_TIMEOUT, 2)
    return _checked("contact_create", mode, _shape(_data("get", id=item_id), "id," + DEFAULT_FIELDS))


def contact_list(group: str | None = None, limit: int = 100, fields=None, mode: str = "background") -> list:
    """Every card, or the cards in one list, by name."""
    _mode("contact_list", mode, ("background",))
    _ready_for(mode)
    if group is not None:
        _group(group)
    found = sorted(_data("all", group=group), key=lambda p: p["name"].lower())[:limit]
    return _checked("contact_list", mode, [_shape(p, fields) for p in found])


def contact_search(query: str, limit: int = 100, fields=None, mode: str = "background") -> list:
    """Cards whose name, company, email, phone or note contain query, ignoring case."""
    _mode("contact_search", mode, ("background",))
    _ready_for(mode)
    q = query.lower()
    found = [p for p in _data("all", group=None)
             if q in " ".join([p["name"], p["company"], p["note"], *p["emails"], *p["phones"]]).lower()]
    return _checked("contact_search", mode, [_shape(p, fields) for p in sorted(found, key=lambda p: p["name"].lower())[:limit]])


def contact_get(match: str, fields=None, mode: str = "background") -> dict:
    """The card with exactly this name."""
    _mode("contact_get", mode, ("background",))
    _ready_for(mode)
    return _checked("contact_get", mode, _shape(_one(match), fields))


def contact_update(match: str, first: str | None = None, last: str | None = None, company: str | None = None,
                   email: str | None = None, phone: str | None = None, note: str | None = None, mode: str = "ui") -> dict:
    """Change the card named match; only the values given change. email and phone replace its first one, or add one."""
    _mode("contact_update", mode)
    for label, value in (("first", first), ("last", last), ("company", company), ("email", email), ("phone", phone)):
        _line(label, value)
    _ready_for(mode)
    item = _one(match)
    if mode == "background":
        _data("update", id=item["id"], first=first, last=last, company=company, email=email, phone=phone, note=note)
    else:
        _select_card(match)
        _press(_wait_for("the Edit button", lambda: _find(_window(), "AXButton", "Edit")))
        _wait_for("the card in edit mode", lambda: _field(description="First"))
        _edit_values(first, last, company, email, phone, note, item)

    def changed(p):
        return ((first is None or p["first"] == first) and (last is None or p["last"] == last)
                and (company is None or p["company"] == company) and (note is None or p["note"] == note)
                and (email is None or email in p["emails"]) and (phone is None or any(_digits(phone) == _digits(x) for x in p["phones"])))
    return _checked("contact_update", mode, _shape(_saved(item["id"], changed), "id," + DEFAULT_FIELDS))


def _digits(text: str) -> str:
    return "".join(c for c in text if c.isdigit())


def contact_delete(match: str, mode: str = "ui") -> dict:
    """Delete the card named match. Returns it as it was, with "deleted": True."""
    _mode("contact_delete", mode)
    _ready_for(mode)
    item = _one(match)
    if mode == "background":
        _data("delete", id=item["id"])
    else:
        _select_card(match)
        _wait_for("Delete Card in the Edit menu", lambda: _menu_item_starting("Edit", "Delete Card"))
        _menu("Edit", "Delete Card")
        _wait_for("the delete alert", _sheets)
        _confirm_delete(match)
    _wait_for("the card to go", lambda: item["id"] not in {p["id"] for p in _data("all", group=None)}, SAVE_TIMEOUT, 2)
    return _checked("contact_delete", mode, {**_shape(item, "id," + DEFAULT_FIELDS), "deleted": True})


# Lists ------------------------------------------------------------------------------------------------------------

def group_create(name: str, mode: str = "ui") -> dict:
    """Make a new list of contacts. Contacts' scripting calls these groups."""
    _mode("group_create", mode)
    if not name.strip() or "\n" in name:
        raise ValueError("name must be one non-empty line")
    _ready_for(mode)
    if any(g["name"] == name for g in _data("groups")):
        raise AlreadyExists(f"a list named {name!r} already exists")
    if mode == "background":
        _data("group_create", name=name)
    else:
        _menu("File", "New List")
        _wait_for("the new list's name field", lambda: _role(_focused()) == "AXTextField" and _string(_focused(), "AXSubrole") != "AXSearchField")
        _paste(name)
        _key(36)
    _wait_for("the list to be saved", lambda: [g for g in _data("groups") if g["name"] == name], SAVE_TIMEOUT, 2)
    return _checked("group_create", mode, {"name": name, "count": 0})


def group_list(mode: str = "background") -> list:
    """Every list with how many cards it holds."""
    _mode("group_list", mode, ("background",))
    _ready_for(mode)
    return _checked("group_list", mode, _data("groups"))


def group_rename(name: str, to: str, mode: str = "ui") -> dict:
    """Rename the list named name to to; its cards stay in it."""
    _mode("group_rename", mode)
    if not to.strip() or "\n" in to:
        raise ValueError("to must be one non-empty line")
    _ready_for(mode)
    _group(name)
    if any(g["name"] == to for g in _data("groups")):
        raise AlreadyExists(f"a list named {to!r} already exists")
    if mode == "background":
        _data("group_rename", name=name, to=to)
    else:
        _select_in(LISTS, name)
        item = _wait_for("Rename in the Edit menu", lambda: _menu_item_starting("Edit", "Rename"))
        _menu("Edit", item)
        _wait_for("the list's name field", lambda: _role(_focused()) == "AXTextField" and _string(_focused(), "AXValue") == name)
        _paste(to)
        _key(36)
    found = _wait_for("the rename to be saved", lambda: [g for g in _data("groups") if g["name"] == to], SAVE_TIMEOUT, 2)
    return _checked("group_rename", mode, found[0])


def group_delete(name: str, mode: str = "ui") -> dict:
    """Delete the list named name. Its cards stay in Contacts."""
    _mode("group_delete", mode)
    _ready_for(mode)
    found = _group(name)
    if mode == "background":
        _data("group_delete", name=name)
    else:
        _select_in(LISTS, name)
        item = _wait_for("Delete in the Edit menu", lambda: _menu_item_starting("Edit", "Delete List") or _menu_item_starting("Edit", "Delete Group"))
        _menu("Edit", item)
        time.sleep(1)
        if _sheets():
            _confirm_delete(name)
    _wait_for("the list to go", lambda: not [g for g in _data("groups") if g["name"] == name], SAVE_TIMEOUT, 2)
    return _checked("group_delete", mode, {**found, "deleted": True})


def group_add(match: str, group: str, mode: str = "background") -> dict:
    """Add the card named match to the list named group."""
    _mode("group_add", mode, ("background",))
    _ready_for(mode)
    _group(group)
    item = _one(match)
    if group not in item["groups"]:
        _data("group_add", id=item["id"], name=group)
    return _checked("group_add", mode, _shape(_saved(item["id"], lambda p: group in p["groups"]), "id," + DEFAULT_FIELDS))


def group_remove(match: str, group: str, mode: str = "background") -> dict:
    """Take the card named match out of the list named group. The card stays in Contacts."""
    _mode("group_remove", mode, ("background",))
    _ready_for(mode)
    _group(group)
    item = _one(match)
    if group in item["groups"]:
        _data("group_remove", id=item["id"], name=group)
    return _checked("group_remove", mode, _shape(_saved(item["id"], lambda p: group not in p["groups"]), "id," + DEFAULT_FIELDS))


# Details ----------------------------------------------------------------------------------------------------------

def _details(item: dict) -> dict:
    return {"id": item["id"], "name": item["name"], **_data("details", id=item["id"])}


def _entry_saved(item: dict, kind: str, test) -> dict:
    _wait_for("the change to be saved", lambda: test(_data("details", id=item["id"])[kind + "s"]), SAVE_TIMEOUT, 1)
    return _details(item)


def _label(label: str) -> str:
    if not label.strip() or "\n" in label:
        raise ValueError("label must be one non-empty line")
    return label


def contact_details(match: str, mode: str = "background") -> dict:
    """The job title, and each phone number and email with its label, of the card named match."""
    _mode("contact_details", mode, ("background",))
    _ready_for(mode)
    return _checked("contact_details", mode, _details(_one(match)))


def contact_set_job_title(match: str, job_title: str, mode: str = "background") -> dict:
    """Set the job title of the card named match. Empty clears it."""
    _mode("contact_set_job_title", mode, ("background",))
    _ready_for(mode)
    _line("job_title", job_title)
    item = _one(match)
    _data("job", id=item["id"], value=job_title)
    _wait_for("the change to be saved", lambda: _data("details", id=item["id"])["job_title"] == job_title, SAVE_TIMEOUT, 1)
    return _checked("contact_set_job_title", mode, _details(item))


def contact_add_phone(match: str, number: str, label: str = "mobile", mode: str = "background") -> dict:
    """Add a phone number with a label such as mobile, home or work. Numbers already there stay."""
    _mode("contact_add_phone", mode, ("background",))
    _ready_for(mode)
    _line("number", number)
    item = _one(match)
    _data("add_entry", id=item["id"], kind="phone", label=_label(label), value=number)
    return _checked("contact_add_phone", mode, _entry_saved(item, "phone", lambda e: {"label": label, "value": number} in e))


def contact_set_phone(match: str, label: str, number: str, mode: str = "background") -> dict:
    """Change the number under this label. Raises NotFound if the card has none with that label."""
    _mode("contact_set_phone", mode, ("background",))
    _ready_for(mode)
    _line("number", number)
    item = _one(match)
    if not [e for e in _data("details", id=item["id"])["phones"] if e["label"] == label]:
        raise NotFound(f"{match} has no phone labelled {label!r}")
    _data("set_entry", id=item["id"], kind="phone", label=label, value=number)
    return _checked("contact_set_phone", mode, _entry_saved(
        item, "phone", lambda e: all(x["value"] == number for x in e if x["label"] == label)))


def contact_remove_phone(match: str, label: str, mode: str = "background") -> dict:
    """Remove every number under this label. Raises NotFound if the card has none with that label."""
    _mode("contact_remove_phone", mode, ("background",))
    _ready_for(mode)
    item = _one(match)
    if not [e for e in _data("details", id=item["id"])["phones"] if e["label"] == label]:
        raise NotFound(f"{match} has no phone labelled {label!r}")
    _data("remove_entry", id=item["id"], kind="phone", label=label)
    return _checked("contact_remove_phone", mode, _entry_saved(item, "phone", lambda e: not [x for x in e if x["label"] == label]))


def contact_add_email(match: str, address: str, label: str = "work", mode: str = "background") -> dict:
    """Add an email with a label such as home or work. Addresses already there stay."""
    _mode("contact_add_email", mode, ("background",))
    _ready_for(mode)
    _line("address", address)
    item = _one(match)
    _data("add_entry", id=item["id"], kind="email", label=_label(label), value=address)
    return _checked("contact_add_email", mode, _entry_saved(item, "email", lambda e: {"label": label, "value": address} in e))


def contact_remove_email(match: str, label: str, mode: str = "background") -> dict:
    """Remove every address under this label. Raises NotFound if the card has none with that label."""
    _mode("contact_remove_email", mode, ("background",))
    _ready_for(mode)
    item = _one(match)
    if not [e for e in _data("details", id=item["id"])["emails"] if e["label"] == label]:
        raise NotFound(f"{match} has no email labelled {label!r}")
    _data("remove_entry", id=item["id"], kind="email", label=label)
    return _checked("contact_remove_email", mode, _entry_saved(item, "email", lambda e: not [x for x in e if x["label"] == label]))


def contact_export_vcard(path: str, match: str | None = None, mode: str = "background") -> dict:
    """Write one card, or with no match every card, to a new .vcf file. Nothing is overwritten."""
    _mode("contact_export_vcard", mode, ("background",))
    full = os.path.abspath(os.path.expanduser(path))
    if not full.lower().endswith(".vcf"):
        raise ValueError("path must end in .vcf")
    if os.path.lexists(full):
        raise AlreadyExists(f"{full} already exists; nothing is overwritten")
    if not os.path.isdir(os.path.dirname(full)):
        raise NotFound(f"the folder {os.path.dirname(full)} doesn't exist")
    _launch_hidden()
    item = _one(match) if match is not None else None
    cards = _data("vcards", id=item["id"] if item else None)
    with open(full, "x", encoding="utf-8", newline="") as handle:
        handle.write("".join(card if card.endswith("\n") else card + "\n" for card in cards))
    return _checked("contact_export_vcard", mode, {"path": full, "count": len(cards)})


def contact_merge(match: str, mode: str = "ui") -> dict:
    """Merge all the cards with exactly this name into one, with Card > Merge Selected Cards. Their numbers and emails are combined."""
    _mode("contact_merge", mode, ("ui",))
    _ready_for(mode)
    found = _data("find", name=match)
    if not found:
        raise NotFound(f"no contact named {match!r}")
    if len(found) < 2:
        raise ValueError(f"only one contact is named {match!r}; there is nothing to merge")
    _select_card(match)
    outline = _outline(CARDS)
    rows = [r for r in _children(outline) if _role(r) == "AXRow" and any(
        _string(e, "AXValue") == match for e in _walk(r) if _role(e) in ("AXStaticText", "AXTextField"))]
    if len(rows) != len(found):
        raise UIError(f"found {len(rows)} rows for {len(found)} cards; nothing was changed")
    # Selecting rows one by one replaces the selection, so all of them are set at once as the list's selected rows.
    create = _CF.CFArrayCreate
    create.restype, create.argtypes = _P, [_P, _P, ctypes.c_long, _P]
    items = (_P * len(rows))(*rows)
    array = create(None, ctypes.cast(items, _P), len(rows), ctypes.addressof(ctypes.c_char.in_dll(_CF, "kCFTypeArrayCallBacks")))
    _AS.AXUIElementSetAttributeValue(outline, _cf("AXSelectedRows"), array)
    _wait_for("the cards to be selected", lambda: sum(_attr(r, "AXSelected") == _TRUE.value for r in rows) == len(rows)
              and sum(_role(r) == "AXRow" and _attr(r, "AXSelected") == _TRUE.value for r in _children(outline)) == len(rows))
    _menu("Card", "Merge Selected Cards")
    _wait_for("the cards to merge", lambda: len(_data("find", name=match)) == 1, SAVE_TIMEOUT, 1)
    return _checked("contact_merge", mode, _shape(_one(match), "id," + DEFAULT_FIELDS))


# Birthday and addresses -------------------------------------------------------------------------------------------
# Added later with their own script, so the code above is unchanged.

MORE = r"""
function run(argv) {
  const C = Application("Contacts"), a = JSON.parse(argv[1]);
  const p = C.people.byId(a.id);
  const pad = n => String(n).padStart(2, "0");
  const read = () => {
    const b = p.birthDate();
    return JSON.stringify({birthday: b ? `${b.getFullYear()}-${pad(b.getMonth() + 1)}-${pad(b.getDate())}` : null,
      addresses: p.addresses().map(x => ({label: x.label(), street: x.street() || "", city: x.city() || "", zip: x.zip() || "", country: x.country() || ""}))});
  };
  if (argv[0] === "birthday") { p.birthDate = new Date(a.y, a.m - 1, a.d, 12, 0, 0); C.save(); }
  if (argv[0] === "address") {
    const props = {label: a.label, street: a.street, city: a.city};
    if (a.zip) props.zip = a.zip;
    if (a.country) props.country = a.country;
    p.addresses.push(C.Address(props)); C.save();
  }
  return read();
}"""


def _more(op: str, **args):
    return json.loads(_jxa(MORE, op, json.dumps(args)))


def contact_set_birthday(match: str, date: str, mode: str = "background") -> dict:
    """Set the birthday ("YYYY-MM-DD") of the card named match."""
    import datetime as _dt
    _mode("contact_set_birthday", mode, ("background",))
    try:
        day = _dt.date.fromisoformat(date)
    except (TypeError, ValueError):
        raise ValueError("date must be YYYY-MM-DD") from None
    _ready_for(mode)
    item = _one(match)
    _more("birthday", id=item["id"], y=day.year, m=day.month, d=day.day)
    got = _wait_for("the birthday to be saved", lambda: (lambda r: r if r["birthday"] == day.isoformat() else None)(_more("read", id=item["id"])), SAVE_TIMEOUT, 1)
    return _checked("contact_set_birthday", mode, {"id": item["id"], "name": item["name"], "birthday": got["birthday"]})


def contact_add_address(match: str, street: str, city: str, zip: str | None = None, country: str | None = None,
                        label: str = "home", mode: str = "background") -> dict:
    """Add a postal address with a label such as home or work to the card named match. Addresses already there stay."""
    _mode("contact_add_address", mode, ("background",))
    for name, value in (("street", street), ("city", city)):
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} must be non-empty text")
    _label(label)
    _ready_for(mode)
    item = _one(match)
    before = len(_more("read", id=item["id"])["addresses"])
    _more("address", id=item["id"], label=label, street=street, city=city, zip=zip, country=country)
    got = _wait_for("the address to be saved", lambda: (lambda r: r if len(r["addresses"]) == before + 1 else None)(_more("read", id=item["id"])), SAVE_TIMEOUT, 1)
    return _checked("contact_add_address", mode, {"id": item["id"], "name": item["name"], "addresses": got["addresses"]})
