"""Calendar commands for agents: plain functions with keyword arguments, on the local calendars (On My Mac).
Import it as `import calendar_app as calendar` (Python has its own calendar module).

mode="ui" (the default) makes the change on screen: System Events clicks menu items, buttons, popover fields and
sidebar rows found by name and role; text is pasted through the clipboard (restored afterwards) and dates and
times are typed into Calendar's date fields. The event to act on is found by exact title and day through
Calendar's own scripting, then shown, so the edit lands on that event only.
mode="background" uses Calendar's own scripting and shows nothing.

Dates are "YYYY-MM-DD HH:MM" in local time, or "YYYY-MM-DD" for all-day events (end = the last day, inclusive).
UI mode types dates as MM/DD/YYYY and times as h:MMAM/PM: it needs the macOS region set to United States.
Repeating events: only the first occurrence is seen (Calendar's scripting doesn't expand repeats).

Errors: NotFound, Ambiguous (nothing changed), AlreadyExists, StateBlocked (the screen holds something the call
won't destroy), UIError (an element never appeared), NotSupported (the mode can't do it)."""
from __future__ import annotations

import datetime as _dt
import json
import plistlib
import subprocess
import time
import warnings

APP = "Calendar"
BUNDLE_ID = "com.apple.iCal"
NOT_LOCAL = ("Scheduled Reminders",)
TIMEOUT = 10
SAVE_TIMEOUT = 25
FIELDS = ("uid", "title", "start", "end", "all_day", "location", "notes", "calendar")
DEFAULT_FIELDS = "title,start,end,all_day,location,notes,calendar"

VERIFIED: dict = {
    "calendar_create": {
        "background": {
            "macos": "26.6.2 (25G83)",
            "app": "16.0 (3036.4.14)"
        },
        "ui": {
            "macos": "26.6.2 (25G83)",
            "app": "16.0 (3036.4.14)"
        }
    },
    "calendar_delete": {
        "background": {
            "macos": "26.6.2 (25G83)",
            "app": "16.0 (3036.4.14)"
        },
        "ui": {
            "macos": "26.6.2 (25G83)",
            "app": "16.0 (3036.4.14)"
        }
    },
    "calendar_list": {
        "background": {
            "macos": "26.6.2 (25G83)",
            "app": "16.0 (3036.4.14)"
        }
    },
    "event_create": {
        "background": {
            "macos": "26.6.2 (25G83)",
            "app": "16.0 (3036.4.14)"
        }
    },
    "event_delete": {
        "background": {
            "macos": "26.6.2 (25G83)",
            "app": "16.0 (3036.4.14)"
        },
        "ui": {
            "macos": "26.6.2 (25G83)",
            "app": "16.0 (3036.4.14)"
        }
    },
    "event_get": {
        "background": {
            "macos": "26.6.2 (25G83)",
            "app": "16.0 (3036.4.14)"
        }
    },
    "event_list": {
        "background": {
            "macos": "26.6.2 (25G83)",
            "app": "16.0 (3036.4.14)"
        }
    },
    "event_search": {
        "background": {
            "macos": "26.6.2 (25G83)",
            "app": "16.0 (3036.4.14)"
        }
    },
    "event_update": {
        "background": {
            "macos": "26.6.2 (25G83)",
            "app": "16.0 (3036.4.14)"
        }
    }
}


class CalendarError(Exception):
    pass


class NotFound(CalendarError):
    pass


class Ambiguous(CalendarError):
    pass


class AlreadyExists(CalendarError):
    pass


class StateBlocked(CalendarError):
    pass


class UIError(CalendarError):
    pass


class NotSupported(CalendarError):
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
    with open("/System/Applications/Calendar.app/Contents/Info.plist", "rb") as handle:
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


UNSUPPORTED = {
    ("event_create", "ui"): "typing into Calendar's date fields through System Events is not reliable: the same "
                            "keystrokes set 12/30/2026 once and moved the event to the year 12 the next time, and "
                            "a new event's title was replaced by an autocomplete suggestion; an event on the wrong "
                            "day breaks the never-the-wrong-item rule",
    ("event_update", "ui"): "it needs the same date fields as event_create (see there)",
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


def _shape(event: dict, fields) -> dict:
    return {name: event[name] for name in _fields(fields)}


def _when(text: str, all_day: bool = False) -> _dt.datetime:
    """Parse "YYYY-MM-DD HH:MM" (or "YYYY-MM-DD" when all_day)."""
    try:
        if all_day:
            return _dt.datetime.strptime(text.strip()[:10], "%Y-%m-%d")
        return _dt.datetime.strptime(text.strip(), "%Y-%m-%d %H:%M")
    except ValueError:
        raise ValueError(f"{text!r} is not {'YYYY-MM-DD' if all_day else 'YYYY-MM-DD HH:MM'}") from None


def _day(text: str) -> _dt.date:
    try:
        return _dt.datetime.strptime(text.strip()[:10], "%Y-%m-%d").date()
    except ValueError:
        raise ValueError(f"{text!r} is not YYYY-MM-DD") from None


def _parts(moment: _dt.datetime) -> list:
    return [moment.year, moment.month, moment.day, moment.hour, moment.minute]


def _wait_for(what: str, test, timeout: float = TIMEOUT):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            value = test()
        except UIError:
            value = None
        if value:
            return value
        time.sleep(0.2)
    raise UIError(f"{what} did not happen within {timeout}s")


# Calendar's own scripting -----------------------------------------------------------------------------------------

DATA = r"""
function run(argv) {
  const Cal = Application("Calendar");
  const op = argv[0], a = JSON.parse(argv[1]);
  const pad = n => String(n).padStart(2, "0");
  const day = d => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  const when = d => `${day(d)} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
  const at = p => new Date(p[0], p[1] - 1, p[2], p[3], p[4]);
  const notLocal = %NOT_LOCAL%;
  const local = () => Cal.calendars().filter(c => c.writable() && !notLocal.includes(c.name()));
  const named = name => local().filter(c => c.name() === name);
  const scope = name => name === null ? local() : named(name);
  const info = (e, c) => {
    const allDay = e.alldayEvent(), start = e.startDate(), end = e.endDate();
    const last = new Date(end.getTime() - 1000);
    return {uid: e.uid(), title: e.summary(), all_day: allDay, start: allDay ? day(start) : when(start),
            end: allDay ? day(last) : when(end), location: e.location() || "", notes: e.description() || "",
            calendar: c.name(), sort: start.getTime()};
  };
  const between = (c, from, to, title) => {
    const range = [{startDate: {_greaterThanEquals: at(from)}}, {startDate: {_lessThan: at(to)}}];
    if (title !== null) range.push({summary: title});
    return c.events.whose({_and: range})().map(e => info(e, c));
  };
  const fixEnd = (e, end) => {
    // Some calendars store an all-day end one day later than asked; read it back and correct it.
    if (!e.alldayEvent()) return;
    const want = at(end); want.setDate(want.getDate() - 1);
    for (let i = 0; i < 3; i++) {
      const last = new Date(e.endDate().getTime() - 1000);
      const days = Math.round((new Date(day(last)) - new Date(day(want))) / 86400000);
      if (days === 0) return;
      const moved = new Date(e.endDate().getTime()); moved.setDate(moved.getDate() - days);
      e.endDate = moved;
    }
    throw new Error("Calendar would not store the all-day end " + day(want));
  };
  const byUid = uid => {
    for (const c of local()) {
      const found = c.events.whose({uid: uid})();
      if (found.length) return [found[0], c];
    }
    throw new Error("no event " + uid);
  };
  switch (op) {
    case "events": {
      const out = scope(a.calendar).flatMap(c => between(c, a.from, a.to, a.title));
      return JSON.stringify(out.sort((x, y) => x.sort - y.sort));
    }
    case "get": { const [e, c] = byUid(a.uid); return JSON.stringify(info(e, c)); }
    case "create": {
      const c = a.calendar === null ? local()[0] : named(a.calendar)[0];
      const e = Cal.Event({summary: a.title, startDate: at(a.start), endDate: at(a.end), alldayEvent: a.all_day});
      c.events.push(e);
      if (a.location !== null) e.location = a.location;
      if (a.notes !== null) e.description = a.notes;
      fixEnd(e, a.end);
      return JSON.stringify(e.uid());
    }
    case "update": {
      const [e] = byUid(a.uid);
      if (a.title !== null) e.summary = a.title;
      if (a.all_day !== null) e.alldayEvent = a.all_day;
      if (a.end !== null) e.endDate = at(a.end);
      if (a.start !== null) e.startDate = at(a.start);
      if (a.end !== null) e.endDate = at(a.end);
      if (a.location !== null) e.location = a.location;
      if (a.notes !== null) e.description = a.notes;
      if (a.end !== null) fixEnd(e, a.end);
      return "true";
    }
    case "delete": { const [e] = byUid(a.uid); Cal.delete(e); return "true"; }
    case "show": { const [e] = byUid(a.uid); Cal.show(e); return "true"; }
    case "calendars": return JSON.stringify(local().map(c => ({name: c.name()})));
    case "calendar_create": Cal.calendars.push(Cal.Calendar({name: a.name})); return "true";
  }
  throw new Error("unknown op " + op);
}""".replace("%NOT_LOCAL%", json.dumps(list(NOT_LOCAL)))


def _running() -> bool:
    return subprocess.run(["pgrep", "-x", APP], capture_output=True).returncode == 0


def _data(op: str, **args):
    return json.loads(_jxa(DATA, op, json.dumps(args)))


def _launch_hidden() -> None:
    """Start Calendar hidden and in the background when it isn't running, so nothing shows on screen."""
    if _running():
        return
    subprocess.run(["open", "-g", "-j", "-b", BUNDLE_ID], check=True)
    _wait_for("Calendar to start", lambda: _data("calendars") is not None, TIMEOUT * 3)


def _range(from_day: _dt.date, to_day: _dt.date) -> tuple:
    start = _dt.datetime.combine(from_day, _dt.time())
    end = _dt.datetime.combine(to_day + _dt.timedelta(days=1), _dt.time())
    return _parts(start), _parts(end)


def _events(from_day: _dt.date, to_day: _dt.date, title: str | None = None, calendar: str | None = None) -> list:
    start, end = _range(from_day, to_day)
    return _data("events", **{"from": start, "to": end, "title": title, "calendar": calendar})


def _one(match: str, date: str, calendar: str | None = None) -> dict:
    day = _day(date)
    found = _events(day, day, match, calendar)
    if not found:
        raise NotFound(f"no event titled {match!r} on {day}")
    if len(found) > 1:
        raise Ambiguous(f"{len(found)} events are titled {match!r} on {day}; nothing was changed")
    return found[0]


def _calendar(name: str) -> None:
    found = [c for c in _data("calendars") if c["name"] == name]
    if not found:
        raise NotFound(f"no local calendar named {name!r}")
    if len(found) > 1:
        raise Ambiguous(f"{len(found)} calendars are named {name!r}; nothing was changed")


def _times(start: str, end: str, all_day: bool) -> tuple:
    first, last = _when(start, all_day), _when(end, all_day)
    if all_day:
        last = last + _dt.timedelta(days=1)
    if last <= first:
        raise ValueError("end must be after start")
    return first, last


def _public(event: dict) -> dict:
    return {key: value for key, value in event.items() if key != "sort"}


# The screen -------------------------------------------------------------------------------------------------------

UI = """on run argv
  tell application "System Events" to tell process "Calendar"
    try
      set w to missing value
      repeat with x in windows
        try
          if exists (first button of toolbar 1 of x whose description is "Add Event") then
            set w to x
            exit repeat
          end if
        end try
      end repeat
%s
    end try
  end tell
  return "no"
end run"""


def _ui(body: str, *args: str) -> str:
    return _osascript(UI % body, *args)


def _until(what: str, body: str, *args: str) -> str:
    deadline = time.monotonic() + TIMEOUT
    while time.monotonic() < deadline:
        answer = _ui(body, *args)
        if answer.startswith("blocked:"):
            raise StateBlocked(f"Calendar shows {answer[8:]}; it was left as it is")
        if answer != "no":
            return answer
        time.sleep(0.1)
    raise UIError(f"{what} not found within {TIMEOUT}s")


FRONT = """      tell application "Calendar" to activate
      set visible to true
      repeat with x in windows
        try
          if value of attribute "AXMinimized" of x is true then set value of attribute "AXMinimized" of x to false
        end try
      end repeat
      if w is missing value then
        tell application "Calendar" to reopen
        return "no"
      end if
      perform action "AXRaise" of w
      if frontmost and (value of attribute "AXMinimized" of w) is false then return "ok\""""

TRANSIENT = """      repeat with b in menu bar items of menu bar 1
        if selected of b then
          key code 53
          return "no"
        end if
      end repeat
      if exists menu 1 then
        key code 53
        return "no"
      end if
      repeat with x in windows
        set extra to {}
        if x is not w and subrole of x is in {"AXDialog", "AXSystemDialog"} then set extra to {x}
        repeat with s in (sheets of x) & extra
          repeat with f in text fields of s
            if value of f is not "" then return "blocked:a dialog with typed text in it"
          end repeat
          if exists button "Cancel" of s then
            click button "Cancel" of s
            return "no"
          end if
          return "blocked:a dialog without a Cancel button"
        end repeat
      end repeat
      if exists pop over 1 of w then
        repeat with f in text fields of pop over 1 of w
          if description of f is "New Quick Event" and value of f is not "" then return "blocked:a quick event with typed text"
        end repeat
        try
          set focused of text field 1 of pop over 1 of w to true
        end try
        key code 53
        return "no"
      end if
      repeat with g in {toolbar 1 of w} & (groups of toolbar 1 of w)
        repeat with f in text fields of g
          if subrole of f is "AXSearchField" and value of f is not missing value and value of f is not "" then
            if exists (first button of f whose description is "cancel") then
              click (first button of f whose description is "cancel")
            else
              set value of f to ""
            end if
            key code 53
            return "no"
          end if
        end repeat
      end repeat
      return "ok\""""


def _ready() -> None:
    """Calendar in front, its main window showing, with no menu, dialog, popover or search left open."""
    if not _running():
        subprocess.run(["open", "-b", BUNDLE_ID], check=True)
    _until("the Calendar window in front", FRONT)
    _until("Calendar with no menu, dialog, popover or search open", TRANSIENT)


def _ready_for(mode: str) -> None:
    if mode == "ui":
        _ready()
    else:
        _launch_hidden()


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
  const items = JSON.parse(argv[1]).map(pairs => {
    const item = $.NSPasteboardItem.alloc.init;
    pairs.forEach(([type, data]) => item.setDataForType($.NSData.alloc.initWithBase64EncodedStringOptions(data, 0), type));
    return item;
  });
  if (items.length) pb.writeObjects($(items));
  return "restored";
}"""

KEYS = """      if not frontmost then return "blocked:another app in front"
      repeat with k in argv
        set k to k as text
        if k starts with "type:" then
          keystroke (text 6 thru -1 of k)
        else if k starts with "cmd+" then
          key code ((text 5 thru -1 of k) as integer) using command down
        else
          key code (k as integer)
        end if
      end repeat
      return "ok\""""

RETURN, TAB, ESCAPE, SELECT_ALL, PASTE, DELETE = "36", "48", "53", "cmd+0", "cmd+9", "51"


def _keys(*keys: str) -> None:
    _until("the keys", KEYS, *keys)


FOCUSED = """      set f to value of attribute "AXFocusedUIElement"
      if role of f is in {"AXTextField", "AXTextArea"} then
        if value of f is missing value then return ""
        return value of f
      end if"""


def _focused_text() -> str:
    return _ui(FOCUSED)


def _paste(text: str, replace: bool = True) -> None:
    """Paste text into the focused field (replacing its text), wait until it shows, restore the clipboard."""
    saved = _jxa(CLIPBOARD, "save")
    try:
        _jxa(CLIPBOARD, "text", text)
        _keys(*((SELECT_ALL,) if replace else ()), PASTE)
        _wait_for("the pasted text to appear", lambda: _focused_text() == text or None)
    finally:
        _jxa(CLIPBOARD, "restore", saved)


MENU_ITEM = """      if (count of argv) is 2 then
        click menu item (item 2 of argv) of menu (item 1 of argv) of menu bar item (item 1 of argv) of menu bar 1
      else
        click menu item (item 3 of argv) of menu 1 of menu item (item 2 of argv) of menu (item 1 of argv) of menu bar item (item 1 of argv) of menu bar 1
      end if
      return "ok\""""

SELECTED = """      if exists pop over 1 of w then
        key code 53
        return "no"
      end if
      repeat with g in groups of splitter group 1 of w
        if description of g ends with "Calendar Area" then
          repeat with t in text fields of g
            if value of t is item 1 of argv then return "ok"
          end repeat
        end if
      end repeat"""

SIDEBAR = """      if not (exists (first outline of scroll area 1 of splitter group 1 of splitter group 1 of w whose description is "Calendar Sources")) then
        click menu item "Show Calendar List" of menu "View" of menu bar item "View" of menu bar 1
        return "no"
      end if
      return "ok\""""

CALENDAR_ROW = """      set sidebar to first outline of scroll area 1 of splitter group 1 of splitter group 1 of w whose description is "Calendar Sources"
      repeat with r in rows of sidebar
        try
          repeat with e in (UI elements of UI element 1 of r)
            if role of e is in {"AXTextField", "AXStaticText"} and value of e is item 1 of argv then
              set selected of r to true
              set focused of sidebar to true
              return "ok"
            end if
          end repeat
        end try
      end repeat"""

NAME_FIELD = """      set f to value of attribute "AXFocusedUIElement"
      if role of f is "AXTextField" and subrole of f is not "AXSearchField" then return "ok\""""

ALERT = """      repeat with x in windows
        repeat with s in sheets of x
          if exists button (item 1 of argv) of s then
            click button (item 1 of argv) of s
            set clicked to true
            return "no"
          end if
        end repeat
      end repeat
      if (count of argv) > 1 then return "ok\""""

ALERT_SHOWN = """      repeat with x in windows
        repeat with s in sheets of x
          if exists button (item 1 of argv) of s then return "ok"
        end repeat
      end repeat"""

CLEAN = """      repeat with x in windows
        if (count of sheets of x) > 0 then return "no"
      end repeat
      if exists pop over 1 of w then return "no"
      if exists menu 1 then return "no"
      return "ok\""""


def _done() -> None:
    _until("Calendar with no popover, dialog or menu left open", CLEAN)


# Events -----------------------------------------------------------------------------------------------------------

def event_create(title: str, start: str, end: str, location: str | None = None, calendar: str | None = None,
                 all_day: bool = False, notes: str | None = None, mode: str = "background") -> dict:
    """Make an event. start/end: "YYYY-MM-DD HH:MM", or "YYYY-MM-DD" with all_day=True (end = last day)."""
    _mode("event_create", mode, ("background",))
    if not title.strip() or "\n" in title:
        raise ValueError("title must be one non-empty line")
    first, last = _times(start, end, all_day)
    _ready_for(mode)
    if calendar is not None:
        _calendar(calendar)
    uid = _data("create", title=title, start=_parts(first), end=_parts(last), all_day=all_day,
                location=location, notes=notes, calendar=calendar)
    event = _saved(uid, lambda e: e["title"] == title)
    return _checked("event_create", mode, _shape(event, "uid," + DEFAULT_FIELDS))


def _saved(uid: str, test) -> dict:
    return _wait_for("the change being saved", lambda: (lambda e: e if test(e) else None)(_data("get", uid=uid)),
                     SAVE_TIMEOUT)


def event_list(from_date: str, to_date: str, limit: int = 50, fields=None, calendar: str | None = None,
               mode: str = "background") -> list:
    """Events starting between from_date and to_date (YYYY-MM-DD, both included), earliest first."""
    _mode("event_list", mode, ("background",))
    _ready_for(mode)
    if calendar is not None:
        _calendar(calendar)
    found = _events(_day(from_date), _day(to_date), None, calendar)[:limit]
    return _checked("event_list", mode, [_shape(e, fields) for e in found])


def event_search(query: str, from_date: str, to_date: str, fields=None, mode: str = "background") -> list:
    """Events between the dates whose title, location or notes contain query (any case)."""
    _mode("event_search", mode, ("background",))
    _ready_for(mode)
    q = query.lower()
    found = [e for e in _events(_day(from_date), _day(to_date))
             if q in e["title"].lower() or q in e["location"].lower() or q in e["notes"].lower()]
    return _checked("event_search", mode, [_shape(e, fields) for e in found])


def event_get(match: str, date: str, fields=None, calendar: str | None = None, mode: str = "background") -> dict:
    """The event titled exactly match that starts on date (YYYY-MM-DD)."""
    _mode("event_get", mode, ("background",))
    _ready_for(mode)
    return _checked("event_get", mode, _shape(_one(match, date, calendar), fields))


def event_update(match: str, date: str, title: str | None = None, start: str | None = None, end: str | None = None,
                 location: str | None = None, notes: str | None = None, all_day: bool | None = None,
                 calendar: str | None = None, mode: str = "background") -> dict:
    """Change the event titled match on date. Only the given values change; start and end go together."""
    _mode("event_update", mode, ("background",))
    if title is not None and (not title.strip() or "\n" in title):
        raise ValueError("title must be one non-empty line")
    _ready_for(mode)
    event = _one(match, date, calendar)
    day_kind = event["all_day"] if all_day is None else all_day
    first = last = None
    if start is not None or end is not None or all_day is not None:
        first, last = _times(start or event["start"], end or event["end"], day_kind)
    _data("update", uid=event["uid"], title=title, location=location, notes=notes,
          all_day=all_day, start=_parts(first) if first else None, end=_parts(last) if last else None)

    def changed(e):
        return ((title is None or e["title"] == title) and (location is None or e["location"] == location)
                and (notes is None or e["notes"] == notes) and (all_day is None or e["all_day"] == all_day)
                and (first is None or e["start"] == (first.strftime("%Y-%m-%d") if day_kind
                                                     else first.strftime("%Y-%m-%d %H:%M"))))
    return _checked("event_update", mode, _shape(_saved(event["uid"], changed), "uid," + DEFAULT_FIELDS))


def event_delete(match: str, date: str, calendar: str | None = None, mode: str = "ui") -> dict:
    """Delete the event titled match on date. Returns the event as it was."""
    _mode("event_delete", mode)
    _ready_for(mode)
    event = _one(match, date, calendar)
    if mode == "background":
        _data("delete", uid=event["uid"])
    else:
        _until("By Day in the View menu", MENU_ITEM, "View", "By Day")
        _data("show", uid=event["uid"])
        _until(f"the event {match!r} selected", SELECTED, match)
        _until("Delete in the Edit menu", MENU_ITEM, "Edit", "Delete")
        _done()
    day = _day(date)
    _wait_for("the event to go", lambda: event["uid"] not in {e["uid"] for e in _events(day, day, match)})
    return _checked("event_delete", mode, {**_shape(event, "uid," + DEFAULT_FIELDS), "deleted": True})


# Calendars --------------------------------------------------------------------------------------------------------

def calendar_create(name: str, mode: str = "ui") -> dict:
    """Make a local calendar (On My Mac) named name."""
    _mode("calendar_create", mode)
    if not name.strip() or "\n" in name:
        raise ValueError("name must be one non-empty line")
    _ready_for(mode)
    if any(c["name"] == name for c in _data("calendars")):
        raise AlreadyExists(f"a calendar named {name!r} already exists")
    if mode == "background":
        _data("calendar_create", name=name)
    else:
        _until("the calendar list", SIDEBAR)
        _until("New Calendar > On My Mac in the File menu", MENU_ITEM, "File", "New Calendar ", "On My Mac")
        _until("the new calendar's name field", NAME_FIELD)
        _paste(name)
        _keys(RETURN)
        _done()
    _wait_for("the calendar to be saved", lambda: [c for c in _data("calendars") if c["name"] == name])
    return _checked("calendar_create", mode, {"name": name})


def calendar_list(mode: str = "background") -> list:
    """The local calendars (On My Mac) that can hold events."""
    _mode("calendar_list", mode, ("background",))
    _ready_for(mode)
    return _checked("calendar_list", mode, _data("calendars"))


def calendar_delete(name: str, mode: str = "ui") -> dict:
    """Delete the local calendar named name and its events."""
    _mode("calendar_delete", mode)
    _ready_for(mode)
    _calendar(name)
    if mode == "background":
        _osascript('on run argv\ntell application "Calendar" to delete calendar (item 1 of argv)\nend run', name)
    else:
        _until("the calendar list", SIDEBAR)
        _until(f"the calendar row {name!r}", CALENDAR_ROW, name)
        _until("Delete in the Edit menu", MENU_ITEM, "Edit", "Delete")
        _until("the Delete button of the confirmation", ALERT_SHOWN, "Delete")
        _until("the confirmation to close", ALERT, "Delete", "until gone")
        _done()
    _wait_for("the calendar to go", lambda: not [c for c in _data("calendars") if c["name"] == name])
    return _checked("calendar_delete", mode, {"name": name, "deleted": True})
