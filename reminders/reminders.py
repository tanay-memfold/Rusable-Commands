"""Reminders commands for agents: plain functions with keyword arguments, on the local account (no iCloud, no sign-in).

mode="ui" makes the change on screen: elements are found by role and name through the macOS Accessibility API and
pressed, menu items are clicked by name, and text is pasted through the clipboard (restored afterwards). The reminder
to act on is found by exact title (and list) through Reminders' own scripting, and its list is shown, so the edit lands
on that row only. Due dates and priority have no ui mode: see UNSUPPORTED.
mode="background" uses Reminders' own scripting and shows nothing.

Dates are "YYYY-MM-DD HH:MM" in local time, or "YYYY-MM-DD" for a due day without a time. Midnight can't be told apart
from a day without a time, so a due time of 00:00 is refused. Priority is "high", "medium", "low" or None.

Errors: NotFound, Ambiguous (nothing changed), AlreadyExists, StateBlocked (the screen holds something the call
won't destroy), UIError (an element never appeared), NotSupported (the mode can't do it)."""
from __future__ import annotations

import ctypes
import datetime as _dt
import json
import plistlib
import subprocess
import time
import warnings

APP = "Reminders"
BUNDLE_ID = "com.apple.reminders"
ACCOUNTS = ("Local", "On My Mac")
TIMEOUT = 10
SAVE_TIMEOUT = 25
FIELDS = ("id", "title", "notes", "list", "due", "priority", "completed", "completed_date")
DEFAULT_FIELDS = "title,notes,list,due,priority,completed"
PRIORITIES = ("high", "medium", "low")

VERIFIED: dict = {
    "list_create": {
        "background": {
            "macos": "15.6.1 (24G90)",
            "app": "7.0 (3740)"
        },
        "ui": {
            "macos": "15.6.1 (24G90)",
            "app": "7.0 (3740)"
        }
    },
    "list_delete": {
        "background": {
            "macos": "15.6.1 (24G90)",
            "app": "7.0 (3740)"
        },
        "ui": {
            "macos": "15.6.1 (24G90)",
            "app": "7.0 (3740)"
        }
    },
    "list_list": {
        "background": {
            "macos": "15.6.1 (24G90)",
            "app": "7.0 (3740)"
        }
    },
    "list_rename": {
        "background": {
            "macos": "15.6.1 (24G90)",
            "app": "7.0 (3740)"
        },
        "ui": {
            "macos": "15.6.1 (24G90)",
            "app": "7.0 (3740)"
        }
    },
    "reminder_complete": {
        "background": {
            "macos": "15.6.1 (24G90)",
            "app": "7.0 (3740)"
        },
        "ui": {
            "macos": "15.6.1 (24G90)",
            "app": "7.0 (3740)"
        }
    },
    "reminder_create": {
        "background": {
            "macos": "15.6.1 (24G90)",
            "app": "7.0 (3740)"
        },
        "ui": {
            "macos": "15.6.1 (24G90)",
            "app": "7.0 (3740)"
        }
    },
    "reminder_delete": {
        "background": {
            "macos": "15.6.1 (24G90)",
            "app": "7.0 (3740)"
        },
        "ui": {
            "macos": "15.6.1 (24G90)",
            "app": "7.0 (3740)"
        }
    },
    "reminder_get": {
        "background": {
            "macos": "15.6.1 (24G90)",
            "app": "7.0 (3740)"
        }
    },
    "reminder_list": {
        "background": {
            "macos": "15.6.1 (24G90)",
            "app": "7.0 (3740)"
        }
    },
    "reminder_move": {
        "background": {
            "macos": "15.6.1 (24G90)",
            "app": "7.0 (3740)"
        }
    },
    "reminder_reopen": {
        "background": {
            "macos": "15.6.1 (24G90)",
            "app": "7.0 (3740)"
        }
    },
    "reminder_search": {
        "background": {
            "macos": "15.6.1 (24G90)",
            "app": "7.0 (3740)"
        }
    },
    "reminder_update": {
        "background": {
            "macos": "15.6.1 (24G90)",
            "app": "7.0 (3740)"
        },
        "ui": {
            "macos": "15.6.1 (24G90)",
            "app": "7.0 (3740)"
        }
    }
}


class RemindersError(Exception):
    pass


class NotFound(RemindersError):
    pass


class Ambiguous(RemindersError):
    pass


class AlreadyExists(RemindersError):
    pass


class StateBlocked(RemindersError):
    pass


class UIError(RemindersError):
    pass


class NotSupported(RemindersError):
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
    with open("/System/Applications/Reminders.app/Contents/Info.plist", "rb") as handle:
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


DATES = ("Reminders' date field exposes no parts to Accessibility, and pressing On a Day set nothing in testing, so a due "
         "date can't be set on screen safely; use mode=\"background\"")
UNSUPPORTED = {
    ("reminder_create", "ui"): DATES + "; the same goes for priority",
    ("reminder_update", "ui"): DATES + "; the same goes for priority",
    ("reminder_move", "ui"): "moving a reminder on screen means dragging it, and these commands use no screen coordinates",
}


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


# Reminders' own scripting ----------------------------------------------------------------------------------------

DATA = r"""
function run(argv) {
  const Rem = Application("Reminders");
  const op = argv[0], a = JSON.parse(argv[1]);
  const pad = n => String(n).padStart(2, "0");
  const day = d => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  const when = d => `${day(d)} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
  const at = p => new Date(p[0], p[1] - 1, p[2], p[3], p[4]);
  const account = Rem.accounts().find(x => %ACCOUNTS%.includes(x.name()));
  if (!account) throw new Error("no local Reminders account");
  const lists = () => account.lists();
  const named = name => lists().filter(l => l.name() === name);
  const scope = name => name === null ? lists() : named(name);
  const info = (r, l) => {
    const due = r.dueDate();
    const dayOnly = due && due.getHours() === 0 && due.getMinutes() === 0;
    const done = r.completionDate();
    return {id: r.id(), title: r.name(), notes: r.body() || "", list: l.name(),
            due: due ? (dayOnly ? day(due) : when(due)) : null, priority: PRIORITY[r.priority()] || null,
            completed: r.completed(), completed_date: done ? when(done) : null,
            sort: r.creationDate().getTime()};
  };
  const PRIORITY = {1: "high", 5: "medium", 9: "low"};
  const LEVEL = {high: 1, medium: 5, low: 9, null: 0};
  const byId = id => {
    for (const l of lists()) {
      const found = l.reminders.whose({id: id})();
      if (found.length) return [found[0], l];
    }
    throw new Error("no reminder " + id);
  };
  switch (op) {
    case "find": return JSON.stringify(scope(a.list).flatMap(l =>
      l.reminders.whose({name: a.title})().map(r => info(r, l))));
    case "all": return JSON.stringify(scope(a.list).flatMap(l => {
      const rs = a.completed === null ? l.reminders() : l.reminders.whose({completed: a.completed})();
      return rs.map(r => info(r, l));
    }).sort((x, y) => y.sort - x.sort));
    case "get": { const [r, l] = byId(a.id); return JSON.stringify(info(r, l)); }
    case "create": {
      const l = a.list === null ? named(Rem.defaultList().name())[0] : named(a.list)[0];
      const props = {name: a.title};
      if (a.notes !== null) props.body = a.notes;
      if (a.priority !== null) props.priority = LEVEL[a.priority];
      const r = Rem.Reminder(props);
      l.reminders.push(r);
      if (a.due !== null) {
        if (a.all_day) r.alldayDueDate = at(a.due); else r.dueDate = at(a.due);
      }
      return JSON.stringify(r.id());
    }
    case "update": {
      const [r] = byId(a.id);
      if (a.title !== null) r.name = a.title;
      if (a.notes !== null) r.body = a.notes;
      if (a.priority !== null) r.priority = LEVEL[a.priority];
      if (a.due !== null) {
        if (a.all_day) r.alldayDueDate = at(a.due); else r.dueDate = at(a.due);
      }
      if (a.clear_due) r.dueDate = null;
      return "true";
    }
    case "complete": { const [r] = byId(a.id); r.completed = true; return "true"; }
    case "move": { const [r] = byId(a.id); Rem.move(r, {to: named(a.to)[0]}); return "true"; }
    case "delete": { const [r] = byId(a.id); Rem.delete(r); return "true"; }
    case "show": { const [r] = byId(a.id); Rem.show(r); return "true"; }
    case "lists": return JSON.stringify(lists().map(l => ({name: l.name(), id: l.id(),
                                                          open: l.reminders.whose({completed: false}).length})));
    case "list_create": account.lists.push(Rem.List({name: a.name})); return "true";
    case "list_rename": named(a.name)[0].name = a.to; return "true";
    case "list_delete":
      try { Rem.delete(named(a.name)[0]); } catch (error) { if (named(a.name).length) throw error; }
      return "true";
    case "list_show": Rem.show(named(a.name)[0]); return "true";
    case "default_list": return JSON.stringify(Rem.defaultList().name());
  }
  throw new Error("unknown op " + op);
}
""".replace("%ACCOUNTS%", json.dumps(ACCOUNTS))


def _running() -> bool:
    return subprocess.run(["pgrep", "-x", APP], capture_output=True).returncode == 0


def _data(op: str, **args):
    return json.loads(_jxa(DATA, op, json.dumps(args)))


def _launch_hidden() -> None:
    """Start Reminders hidden and in the background when it isn't running, so nothing shows on screen."""
    if _running():
        return
    subprocess.run(["open", "-g", "-j", "-b", BUNDLE_ID], check=True)
    _wait_for("Reminders to start", lambda: _data("lists") is not None, TIMEOUT * 3)


def _shape(item: dict, fields) -> dict:
    return {name: item[name] for name in _fields(fields)}


def _one(match: str, list: str | None = None) -> dict:
    found = _data("find", title=match, list=list)
    where = f" in the list {list!r}" if list else ""
    if not found:
        raise NotFound(f"no reminder titled {match!r}{where}")
    if len(found) > 1:
        raise Ambiguous(f"{len(found)} reminders are titled {match!r}{where}; nothing was changed")
    return found[0]


def _list(name: str) -> None:
    found = [item for item in _data("lists") if item["name"] == name]
    if not found:
        raise NotFound(f"no list named {name!r}")
    if len(found) > 1:
        raise Ambiguous(f"{len(found)} lists are named {name!r}; nothing was changed")


def _due(due: str | None) -> tuple:
    """(parts, all_day) for "YYYY-MM-DD HH:MM" or "YYYY-MM-DD"."""
    if due is None:
        return None, False
    text = due.strip()
    try:
        if len(text) == 10:
            moment = _dt.datetime.strptime(text, "%Y-%m-%d")
            return [moment.year, moment.month, moment.day, 0, 0], True
        moment = _dt.datetime.strptime(text, "%Y-%m-%d %H:%M")
        if moment.hour == 0 and moment.minute == 0:
            raise ValueError(f"due {due!r}: 00:00 can't be told apart from a day without a time; give just the day")
        return [moment.year, moment.month, moment.day, moment.hour, moment.minute], False
    except ValueError as error:
        if "00:00" in str(error):
            raise
        raise ValueError(f"due {due!r} is not YYYY-MM-DD or YYYY-MM-DD HH:MM") from None


def _priority(priority: str | None) -> None:
    if priority is not None and priority not in PRIORITIES:
        raise ValueError(f"priority must be one of {PRIORITIES} or None")


def _saved(item_id: str, test) -> dict:
    return _wait_for("the change being saved", lambda: (lambda r: r if test(r) else None)(_data("get", id=item_id)),
                     SAVE_TIMEOUT, 2)


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
        raise UIError("Reminders isn't running")
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


FIRST_RUN = (("Not Now",), ("Continue",))


def _clear_transients() -> None:
    """Close only Reminders' passing UI. A sheet or new row holding typed text is left alone: StateBlocked."""
    for _ in range(6):
        window = _window()
        if window is None:
            return
        if any(_role(e) == "AXMenu" for e in _walk(window)):
            _key(ESCAPE)
            time.sleep(0.3)
            continue
        welcome = None if _sheets() else _find(window, "AXButton", "Continue")
        if welcome:
            _press(welcome)
            time.sleep(1.5)
            continue
        sheets = _sheets()
        if sheets:
            fields = [e for e in _walk(sheets[0]) if _role(e) == "AXTextField"]
            cancel = _find(sheets[0], "AXButton", "Cancel")
            if fields and cancel and _string(fields[0], "AXValue").strip():
                creating = any(_string(e, "AXValue") == "New List" for e in _walk(sheets[0]))
                if creating:
                    raise StateBlocked("Reminders has a dialog with typed text in it; it was left as it is")
            first_run = next((b for names in FIRST_RUN for b in [_find(sheets[0], "AXButton", names[0])] if b), None)
            target = cancel or first_run
            if not target:
                raise StateBlocked("Reminders shows a dialog without a Cancel button; it was left as it is")
            _press(target)
            time.sleep(1.5)
            continue
        if any(_role(e) == "AXPopover" for e in _walk(window)):
            _key(ESCAPE)
            time.sleep(0.5)
            continue
        focused = _focused()
        if focused and _role(focused) == "AXTextField" and _string(focused, "AXSubrole") != "AXSearchField":
            typed = _string(focused, "AXValue")
            if typed.strip() and typed not in {r["title"] for r in _data("all", list=None, completed=None)} | \
                    {r["notes"] for r in _data("all", list=None, completed=None)}:
                raise StateBlocked("Reminders has a new reminder with typed text in it; it was left as it is")
        search = next((e for e in _walk(window) if _string(e, "AXSubrole") == "AXSearchField"), None)
        if search and _string(search, "AXValue"):
            cancel = _find(search, "AXButton", "cancel")
            if cancel:
                _press(cancel)
            else:
                _focus(search)
                _key(0, "command")
                _key(51)
            _key(ESCAPE)
            time.sleep(0.5)
            continue
        return
    raise UIError("Reminders still shows a menu, dialog, popover or search")


def _ready() -> None:
    """Reminders in front, its main window showing, with no menu, dialog, popover or search left open."""
    if not _running():
        subprocess.run(["open", "-b", BUNDLE_ID], check=True)
        _wait_for("Reminders to start", _running, TIMEOUT * 3)
    _osascript(f'tell application "{APP}" to activate')
    _system_events("set visible to true")
    for window in [e for e in _children(_app()) if _role(e) == "AXWindow"]:
        if _attr(window, "AXMinimized") == _TRUE.value:
            _AS.AXUIElementSetAttributeValue(window, _cf("AXMinimized"), _FALSE)
    if not _wait_for_window():
        subprocess.run(["open", "-b", BUNDLE_ID], check=True)
    _wait_for("the Reminders window in front",
              lambda: _window() and _system_events("return frontmost") == "true", SAVE_TIMEOUT)
    time.sleep(0.5)
    _clear_transients()
    if _has_menu_item("View", "Show Sidebar"):
        _menu("View", "Show Sidebar")
        time.sleep(0.5)


def _wait_for_window() -> bool:
    try:
        _wait_for("a window", _window, 2)
        return True
    except UIError:
        return False


def _ready_for(mode: str) -> None:
    if mode == "ui":
        _ready()
    else:
        _launch_hidden()


def _pane():
    """The list pane on the right: everything but the sidebar."""
    return next((e for e in _walk(_window()) if _role(e) == "AXLayoutArea"
                 and _string(e, "AXDescription") != "Reminder lists"), None)


def _show_list(name: str) -> None:
    _data("list_show", name=name)
    _wait_for(f"the list {name!r} on screen", lambda: (lambda p: p and _string(p, "AXDescription") == name)(_pane()))


def _default_list() -> str:
    return _data("default_list")


def _rows() -> list:
    pane = _pane()
    return [e for e in _walk(pane) if _role(e) == "AXRow"] if pane else []


def _row(title: str):
    for row in _rows():
        for element in _walk(row):
            if _role(element) == "AXTextField" and _string(element, "AXValue") == title:
                return row
    return None


def _show_completed() -> bool:
    show = _find(_pane(), "AXButton", "Show")
    if show:
        _press(show)
        time.sleep(0.6)
        return True
    return False


def _hide_completed() -> None:
    hide = _find(_pane(), "AXButton", "Hide")
    if hide:
        _press(hide)


def _select(row) -> None:
    _AS.AXUIElementSetAttributeValue(row, _cf("AXSelected"), _TRUE)
    _wait_for("the row to be selected", lambda: _attr(row, "AXSelected") == _TRUE.value)


def _confirm_delete(name: str) -> None:
    """Press Delete in Reminders' alert only if it names what is meant to go; otherwise cancel and stop."""
    sheet = _sheets()[0]
    text = " ".join(_string(e, "AXValue") for e in _walk(sheet) if _role(e) == "AXStaticText")
    if name not in text:
        _press(_find(sheet, "AXButton", "Cancel"))
        raise UIError("Reminders' delete alert doesn't name the item; nothing was deleted")
    _press(_find(sheet, "AXButton", "Delete"))


def _commit() -> None:
    """A row being edited saves only when focus leaves it; Escape doesn't do that. So focus moves to the sidebar."""
    _focus(_wait_for("the sidebar", lambda: _find(_window(), "AXOutline", "Account Lists")))


def _ui_create(title: str, list_name: str | None, notes: str | None) -> None:
    _show_list(list_name if list_name is not None else _default_list())
    _press(_wait_for("Add Reminder", lambda: _find(_window(), "AXButton", "Add Reminder")))
    _wait_for("the new row", lambda: _role(_focused()) == "AXTextField" and not _string(_focused(), "AXValue"))
    _paste(title)
    if notes:
        _key(TAB)
        _wait_for("the notes field", lambda: _role(_focused()) == "AXTextField" and not _string(_focused(), "AXValue"))
        _paste(notes)
    _commit()


def _ui_complete(item: dict) -> None:
    _show_list(item["list"])
    if item["completed"]:
        return
    row = _wait_for("the reminder's row", lambda: _row(item["title"]))
    _press(next(e for e in _walk(row) if _role(e) == "AXCheckBox"))


def _ui_delete(item: dict) -> None:
    _show_list(item["list"])
    shown = _row(item["title"])
    opened = False
    if not shown:
        opened = _show_completed()
    row = _wait_for("the reminder's row", lambda: _row(item["title"]))
    # With focus in the sidebar, Edit > Delete means the whole list. So focus moves to the rows first, and any alert
    # means the menu isn't acting on this reminder: a reminder is deleted without one.
    _focus(_wait_for("the reminder rows", lambda: next((e for e in _walk(_pane()) if _role(e) == "AXOutline"), None)))
    time.sleep(0.3)
    _select(row)
    if _role(_focused()) not in ("AXOutline", "AXRow", "AXCell", "AXGroup"):
        raise UIError("focus isn't on the reminder rows; nothing was deleted")
    _menu("Edit", "Delete")
    time.sleep(1)
    if _sheets():
        _press(_find(_sheets()[0], "AXButton", "Cancel"))
        raise UIError("Reminders asked to delete something other than this reminder; nothing was deleted")
    if opened:
        time.sleep(0.5)
        _hide_completed()


def _ui_update(item: dict, title: str | None, notes: str | None) -> None:
    _show_list(item["list"])
    row = _wait_for("the reminder's row", lambda: _row(item["title"]))
    _focus(next(e for e in _walk(row) if _role(e) == "AXTextField"))
    _wait_for("the title field", lambda: _string(_focused(), "AXValue") == item["title"])
    if title is not None:
        _paste(title)
        row = _wait_for("the renamed row", lambda: _row(title))
    if notes is not None:
        # The row shows its notes field once its title is being edited.
        field = _wait_for("the notes field", lambda: [e for e in _walk(row) if _role(e) == "AXTextField"][1:2])[0]
        _focus(field)
        time.sleep(0.3)
        _paste(notes)
    _commit()


def _ui_list_create(name: str) -> None:
    _menu("File", "New List")
    sheet = _wait_for("the New List dialog", lambda: next(iter(_sheets()), None))
    field = next(e for e in _walk(sheet) if _role(e) == "AXTextField")
    _focus(field)
    time.sleep(0.3)
    _paste(name)
    _press(_find(sheet, "AXButton", "OK"))


def _ui_list_rename(name: str, to: str) -> None:
    _show_list(name)
    # The menu item is missing while a text field is being edited, so focus moves to the sidebar first.
    _commit()
    _wait_for("Show List Info", lambda: _has_menu_item("View", "Show List Info"))
    _menu("View", "Show List Info")
    sheet = _wait_for("the list's info dialog", lambda: next(iter(_sheets()), None))
    field = next(e for e in _walk(sheet) if _role(e) == "AXTextField")
    if _string(field, "AXValue") != name:
        _press(_find(sheet, "AXButton", "Cancel"))
        raise UIError("the info dialog doesn't show this list; nothing was changed")
    _focus(field)
    time.sleep(0.3)
    _paste(to)
    _press(_find(sheet, "AXButton", "OK"))


def _ui_list_delete(name: str) -> None:
    _show_list(name)
    sidebar = _wait_for("the sidebar", lambda: _find(_window(), "AXOutline", "Account Lists"))
    # The sidebar can catch up with the list on screen a moment later.
    try:
        _wait_for("the list to be selected", lambda: any(_find(r, "AXTextField", name) for r in _children(sidebar)
                                                         if _role(r) == "AXRow" and _attr(r, "AXSelected") == _TRUE.value))
    except UIError:
        raise UIError("the list isn't the one selected in the sidebar; nothing was deleted") from None
    _focus(sidebar)
    time.sleep(0.3)
    _menu("Edit", "Delete")
    time.sleep(1)
    if _sheets():
        _confirm_delete(name)


# Reminders --------------------------------------------------------------------------------------------------------

def reminder_create(title: str, list: str | None = None, due: str | None = None, notes: str | None = None,
                    priority: str | None = None, mode: str = "ui") -> dict:
    """Add a reminder to list (default: the default list). due: "YYYY-MM-DD HH:MM" or "YYYY-MM-DD"."""
    _mode("reminder_create", mode)
    if not title.strip() or "\n" in title:
        raise ValueError("title must be one non-empty line")
    _priority(priority)
    parts, all_day = _due(due)
    if mode == "ui" and (due is not None or priority is not None):
        raise NotSupported(UNSUPPORTED[("reminder_create", "ui")])
    _ready_for(mode)
    if list is not None:
        _list(list)
    before = {r["id"] for r in _data("find", title=title, list=list)}
    if mode == "background":
        item_id = _data("create", title=title, list=list, due=parts, all_day=all_day, notes=notes, priority=priority)
    else:
        _ui_create(title, list, notes)
        item_id = _wait_for("the new reminder to be saved",
                            lambda: next(iter({r["id"] for r in _data("find", title=title, list=list)} - before),
                                         None), SAVE_TIMEOUT, 2)
    item = _saved(item_id, lambda r: r["title"] == title and (notes is None or r["notes"] == notes))
    return _checked("reminder_create", mode, _shape(item, "id," + DEFAULT_FIELDS))


def reminder_list(list: str | None = None, completed: bool | None = False, limit: int = 100, fields=None,
                  mode: str = "background") -> list:
    """Reminders in list (default: every list); completed=False open ones, True done ones, None both. Newest first."""
    _mode("reminder_list", mode, ("background",))
    _ready_for(mode)
    if list is not None:
        _list(list)
    found = _data("all", list=list, completed=completed)[:limit]
    return _checked("reminder_list", mode, [_shape(r, fields) for r in found])


def reminder_search(query: str, fields=None, completed: bool | None = None, mode: str = "background") -> list:
    """Reminders whose title or notes contain query (any case), newest first."""
    _mode("reminder_search", mode, ("background",))
    _ready_for(mode)
    q = query.lower()
    found = [r for r in _data("all", list=None, completed=completed)
             if q in r["title"].lower() or q in r["notes"].lower()]
    return _checked("reminder_search", mode, [_shape(r, fields) for r in found])


def reminder_get(match: str, list: str | None = None, fields=None, mode: str = "background") -> dict:
    """The reminder titled exactly match (optionally only in list)."""
    _mode("reminder_get", mode, ("background",))
    _ready_for(mode)
    return _checked("reminder_get", mode, _shape(_one(match, list), fields))


def reminder_update(match: str, list: str | None = None, title: str | None = None, due: str | None = None,
                    notes: str | None = None, priority: str | None = None, mode: str = "background") -> dict:
    """Change the reminder titled match; only the values given change."""
    _mode("reminder_update", mode)
    if title is not None and (not title.strip() or "\n" in title):
        raise ValueError("title must be one non-empty line")
    _priority(priority)
    parts, all_day = _due(due)
    if mode == "ui" and (due is not None or priority is not None):
        raise NotSupported(UNSUPPORTED[("reminder_update", "ui")])
    _ready_for(mode)
    item = _one(match, list)
    if mode == "background":
        _data("update", id=item["id"], title=title, notes=notes, priority=priority, due=parts, all_day=all_day,
              clear_due=False)
    else:
        _ui_update(item, title, notes)

    def changed(r):
        return ((title is None or r["title"] == title) and (notes is None or r["notes"] == notes)
                and (priority is None or r["priority"] == priority) and (due is None or r["due"] == due.strip()))
    return _checked("reminder_update", mode, _shape(_saved(item["id"], changed), "id," + DEFAULT_FIELDS))


def reminder_complete(match: str, list: str | None = None, mode: str = "ui") -> dict:
    """Mark the reminder titled match as completed."""
    _mode("reminder_complete", mode)
    _ready_for(mode)
    item = _one(match, list)
    if mode == "background":
        _data("complete", id=item["id"])
    else:
        _ui_complete(item)
    return _checked("reminder_complete", mode,
                    _shape(_saved(item["id"], lambda r: r["completed"]), "id," + DEFAULT_FIELDS))


def reminder_delete(match: str, list: str | None = None, mode: str = "ui") -> dict:
    """Delete the reminder titled match. Returns it as it was, with "deleted": True."""
    _mode("reminder_delete", mode)
    _ready_for(mode)
    item = _one(match, list)
    if mode == "background":
        _data("delete", id=item["id"])
    else:
        _ui_delete(item)
    _wait_for("the reminder to go", lambda: item["id"] not in {r["id"] for r in _data("find", title=match, list=None)},
              SAVE_TIMEOUT)
    return _checked("reminder_delete", mode, {**_shape(item, "id," + DEFAULT_FIELDS), "deleted": True})


# Lists ------------------------------------------------------------------------------------------------------------

def list_create(name: str, mode: str = "ui") -> dict:
    """Make a list named name in the local account."""
    _mode("list_create", mode)
    if not name.strip() or "\n" in name:
        raise ValueError("name must be one non-empty line")
    _ready_for(mode)
    if any(item["name"] == name for item in _data("lists")):
        raise AlreadyExists(f"a list named {name!r} already exists")
    if mode == "background":
        _data("list_create", name=name)
    else:
        _ui_list_create(name)
    _wait_for("the list to be saved", lambda: [i for i in _data("lists") if i["name"] == name], SAVE_TIMEOUT, 2)
    return _checked("list_create", mode, {"name": name, "open": 0})


def list_list(mode: str = "background") -> list:
    """Every list in the local account with its number of open reminders."""
    _mode("list_list", mode, ("background",))
    _ready_for(mode)
    return _checked("list_list", mode, [{"name": i["name"], "open": i["open"]} for i in _data("lists")])


def list_rename(name: str, to: str, mode: str = "ui") -> dict:
    """Rename the list named name to to."""
    _mode("list_rename", mode)
    if not to.strip() or "\n" in to:
        raise ValueError("to must be one non-empty line")
    _ready_for(mode)
    _list(name)
    if any(item["name"] == to for item in _data("lists")):
        raise AlreadyExists(f"a list named {to!r} already exists")
    if mode == "background":
        _data("list_rename", name=name, to=to)
    else:
        _ui_list_rename(name, to)
    found = _wait_for("the rename to be saved", lambda: [i for i in _data("lists") if i["name"] == to], SAVE_TIMEOUT, 2)
    return _checked("list_rename", mode, {"name": to, "open": found[0]["open"]})


def list_delete(name: str, mode: str = "ui") -> dict:
    """Delete the list named name and its reminders."""
    _mode("list_delete", mode)
    _ready_for(mode)
    _list(name)
    found = next(i for i in _data("lists") if i["name"] == name)
    if mode == "background":
        _data("list_delete", name=name)
    else:
        _ui_list_delete(name)
    _wait_for("the list to go", lambda: not [i for i in _data("lists") if i["name"] == name], SAVE_TIMEOUT)
    return _checked("list_delete", mode, {"name": name, "open": found["open"], "deleted": True})


def reminder_move(match: str, to_list: str, list: str | None = None, mode: str = "background") -> dict:
    """Move the reminder titled match to the list to_list. Its title, notes, due date and priority stay."""
    _mode("reminder_move", mode, ("background",))
    _ready_for(mode)
    item = _one(match, list)
    _list(to_list)
    if item["list"] != to_list:
        _data("move", id=item["id"], to=to_list)

    def moved():
        now = [r for r in _data("find", title=match, list=to_list)]
        return now[0] if len(now) == 1 and not [r for r in _data("find", title=match, list=item["list"])
                                                if item["list"] != to_list and r["id"] == item["id"]] else None
    return _checked("reminder_move", mode, _wait_for("the reminder to move", moved, SAVE_TIMEOUT))


# Reopen ----------------------------------------------------------------------------------------------------------
# Added later with their own script, so the code above is unchanged.

MORE = r"""
function run(argv) {
  const Rem = Application("Reminders"), a = JSON.parse(argv[1]);
  for (const l of Rem.lists()) {
    const found = l.reminders.whose({id: a.id})();
    if (!found.length) continue;
    const r = found[0];
    if (argv[0] === "reopen") r.completed = false;
    return JSON.stringify({flagged: r.flagged(), completed: r.completed()});
  }
  throw new Error("no reminder " + a.id);
}"""


def _more(op: str, **args):
    return json.loads(_jxa(MORE, op, json.dumps(args)))


def reminder_reopen(match: str, list: str | None = None, mode: str = "background") -> dict:
    """Mark the completed reminder titled match as not completed again."""
    _mode("reminder_reopen", mode, ("background",))
    _ready_for(mode)
    item = _one(match, list)
    if not item["completed"]:
        raise ValueError(f"{match!r} isn't completed")
    _more("reopen", id=item["id"])
    return _checked("reminder_reopen", mode, _shape(_saved(item["id"], lambda r: not r["completed"]), "id," + DEFAULT_FIELDS))
