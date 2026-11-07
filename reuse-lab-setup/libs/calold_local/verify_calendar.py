"""Verify calendar_app.py inside a clone: python3 verify_calendar.py <group> <seed> [function ...]

Every case: set up calendars and events with plain scripting (never calendar_app.py), put Calendar into a start
state, call the function with fresh values, read Calendar.sqlitedb, check every field, the distractors, that no
dialog or popover is left open, and the screen."""
import json
import os
import sys
import time
import traceback

sys.path.insert(0, os.path.expanduser("~/libs/calendar"))
import calendar_app as C  # noqa: E402
import calendar_db as D  # noqa: E402
from vcommon import Recorder, Values, osa, se, screenshot, rows_changed, sh, wait  # noqa: E402

GROUP, SEED = sys.argv[1], int(sys.argv[2])
ONLY = set(sys.argv[3:])
STATES = set(filter(None, os.environ.get("STATES", "").split(",")))
V = Values(SEED)
R = Recorder(GROUP, {"versions": C._versions(), "seed": SEED, "started": time.strftime("%Y-%m-%d %H:%M:%S")})
APP = "Calendar"
WIDE = "380,26,644,660"

PREP = r"""
function run(argv) {
  const Cal = Application("Calendar"), a = JSON.parse(argv[1]);
  const at = p => new Date(p[0], p[1] - 1, p[2], p[3], p[4]);
  switch (argv[0]) {
    case "calendar": Cal.calendars.push(Cal.Calendar({name: a.name})); return "ok";
    case "event": {
      const e = Cal.Event({summary: a.title, startDate: at(a.start), endDate: at(a.end), alldayEvent: a.all_day,
                           location: a.location, description: a.notes});
      Cal.calendars.byName(a.calendar).events.push(e);
      return e.uid();
    }
    case "show": {
      for (const c of Cal.calendars()) {
        const found = c.events.whose({uid: a.uid})();
        if (found.length) { Cal.show(found[0]); return "ok"; }
      }
      return "none";
    }
    case "view": Cal.switchView({to: a.view}); Cal.viewCalendar({at: at(a.at)}); return "ok";
  }
}"""


def prep(op, **args):
    return osa(PREP, op, json.dumps(args), lang="JavaScript")


def event(title, start, end, calendar="Calendar", all_day=False, location="", notes=""):
    return prep("event", title=title, start=start, end=end, calendar=calendar, all_day=all_day, location=location,
                notes=notes)


def quit_app():
    sh(f"osascript -e 'tell application \"{APP}\" to quit'")
    wait(lambda: not sh(f"pgrep -x {APP}"), 15)


def open_app():
    sh("open -b com.apple.iCal")
    wait(lambda: se("return (count of windows) > 0", APP) == "true", 20)
    time.sleep(1)


def escape_all():
    for _ in range(3):
        try:
            se("key code 53", APP)
        except RuntimeError:
            pass
    try:
        se('''repeat with x in windows
  repeat with s in sheets of x
    if exists button "Cancel" of s then click button "Cancel" of s
  end repeat
end repeat''', APP)
    except RuntimeError:
        pass


BASE = {}


def base():
    for name in ["Work", "Family"]:
        prep("calendar", name=name)
    time.sleep(1)
    event("Standup", [2026, 11, 18, 9, 0], [2026, 11, 18, 9, 15], "Work")
    event("Standup", [2026, 11, 18, 9, 30], [2026, 11, 18, 9, 45], "Family")
    event("Standup review", [2026, 11, 18, 10, 0], [2026, 11, 18, 10, 30], "Work")
    event("Dentist", [2026, 11, 19, 15, 0], [2026, 11, 19, 15, 45], "Calendar", location="Clinic 2")
    BASE["popover_uid"] = event("Book fair", [2026, 11, 20, 11, 0], [2026, 11, 20, 12, 0], "Family")


def start(state):
    if state in ("closed", "launching"):
        quit_app()
        if state == "launching":
            sh("open -b com.apple.iCal")
        return
    if not sh(f"pgrep -x {APP}"):
        open_app()
    escape_all()
    se("set frontmost to true", APP)
    if state in ("open", "other_view"):
        se('click menu item "By Month" of menu "View" of menu bar item "View" of menu bar 1', APP)
    elif state == "hidden":
        se("set visible to false", APP)
    elif state == "minimized":
        se('set value of attribute "AXMinimized" of window 1 to true', APP)
    elif state == "other_app":
        sh("open -a Calculator")
        wait(lambda: front() == "Calculator", 10)
    elif state == "popover_open":
        prep("show", uid=BASE["popover_uid"])
        time.sleep(0.7)
        se('click menu item "Edit Event" of menu "Edit" of menu bar item "Edit" of menu bar 1', APP)
        wait(lambda: popover_texts() is not None, 5)
    elif state == "alert_open":
        se('''if not (exists (first outline of scroll area 1 of splitter group 1 of splitter group 1 of window 1)) then
  click menu item "Show Calendar List" of menu "View" of menu bar item "View" of menu bar 1
end if''', APP)
        time.sleep(0.7)
        se('''set sidebar to first outline of scroll area 1 of splitter group 1 of splitter group 1 of window 1
repeat with r in rows of sidebar
  try
    repeat with e in (UI elements of UI element 1 of r)
      if value of e is "Family" then
        set selected of r to true
        set focused of sidebar to true
      end if
    end repeat
  end try
end repeat
click menu item "Delete" of menu "Edit" of menu bar item "Edit" of menu bar 1''', APP)
        wait(lambda: se("return (count of sheets of window 1) > 0", APP) == "true", 5)
    elif state == "search_text":
        se('keystroke "f" using command down', APP)
        time.sleep(0.7)
        se('keystroke "zq"', APP)
    elif state == "selected":
        prep("show", uid=BASE["popover_uid"])
    elif state == "blocked":
        se('click menu item "New Event or Reminder" of menu "File" of menu bar item "File" of menu bar 1', APP)
        wait(lambda: popover_texts() is not None, 5)
        se('keystroke "lunch with sam"', APP)
    time.sleep(0.8)


UI_STATES = ["closed", "other_view", "hidden", "minimized", "other_app", "alert_open", "popover_open", "search_text",
             "selected", "launching"]


def popover_texts():
    """The text fields' values of every popover in any Calendar window, or None when no popover is open."""
    found = se('''set out to ""
set seen to false
repeat with x in windows
  repeat with p in pop overs of x
    set seen to true
    repeat with f in text fields of p
      try
        set out to out & (value of f as text) & "|"
      end try
    end repeat
  end repeat
end repeat
if not seen then return "NONE"
return out''', APP)
    return None if found == "NONE" else found


def front():
    try:
        return osa('tell application "System Events" to return name of first process whose frontmost is true')
    except RuntimeError:
        return ""


def windows():
    try:
        return se('''set out to {}
repeat with x in windows
  set end of out to (count of sheets of x)
end repeat
return (count of windows) & out''', APP)
    except RuntimeError:
        return "not running"


def clean_screen():
    try:
        return se('''repeat with x in windows
  if (count of sheets of x) > 0 then return "sheet"
  if (count of pop overs of x) > 0 then return "popover"
end repeat
if exists menu 1 then return "menu"
return "clean"''', APP) == "clean"
    except RuntimeError:
        return True


CHANGED = []


def unchanged(before, after, targets):
    CHANGED.clear()
    for pk, item in before["events"].items():
        if pk not in targets and after["events"].get(pk) != item:
            CHANGED.append({"before": item, "after": after["events"].get(pk)})
    for pk, name in before["calendars"].items():
        if pk not in targets and after["calendars"].get(pk) != name:
            CHANGED.append({"calendar_before": name, "after": after["calendars"].get(pk)})
    return not CHANGED


def run_case(function, mode, state, setup, call, expect, kind="normal"):
    if ONLY and function not in ONLY:
        return
    if STATES and state not in STATES:
        return
    try:
        ctx = setup()
        start(state)
        time.sleep(0.5)
        before = D.snapshot()
        name = f"{function}-{mode}-{state}-{kind}"
        shot0 = screenshot(name + "-0")
        front0, windows0 = front(), windows()
        wide0 = screenshot(name + "-0w", WIDE) if mode == "background" else None
        began = time.monotonic()
        try:
            result, error = call(ctx), None
        except Exception as exc:  # noqa: BLE001
            result, error = None, exc
        seconds = round(time.monotonic() - began, 1)
        deadline = time.monotonic() + (150 if mode == "background" else 45)
        while True:
            time.sleep(1)
            after = D.snapshot()
            checks, targets = expect(ctx, result, error, before, after)
            if all(checks.values()) or time.monotonic() > deadline:
                break
        shot1 = screenshot(name + "-1")
        checks["distractors_unchanged"] = unchanged(before, after, targets)
        if kind != "blocked":
            checks["no_dialog_popover_or_menu_left"] = clean_screen()
        changed = rows_changed(shot0, shot1)
        if mode == "background":
            checks["front_app_unchanged"] = front0 == front()
            if state == "closed":
                checks["app_stayed_hidden"] = se("return visible", APP) == "false"
                checks["screen_unchanged"] = rows_changed(wide0, screenshot(name + "-1w", WIDE)) <= 40
            else:
                checks["no_new_window_or_dialog"] = windows0 == windows()
        elif kind == "normal":
            checks["screen_changed_by_ui"] = changed > 40
        detail = {"result": result, "error": repr(error) if error else None, "rows_changed": changed,
                  "changed_distractors": list(CHANGED)}
        R.case(function, mode, state, kind, checks, detail, seconds)
    except Exception:  # noqa: BLE001
        R.case(function, mode, state, kind, {"harness": False}, traceback.format_exc()[-1500:])
    finally:
        if state in ("blocked", "popover_open", "alert_open"):
            escape_all()


def new_events(before, after):
    return {pk: e for pk, e in after["events"].items() if pk not in before["events"]}


def day_time(day, hour, minute):
    return f"2026-{day[0]:02d}-{day[1]:02d} {hour:02d}:{minute:02d}"


def parts(text):
    date, clock = text.split(" ") if " " in text else (text, "00:00")
    y, m, d = (int(x) for x in date.split("-"))
    h, mi = (int(x) for x in clock.split(":"))
    return [y, m, d, h, mi]


SHAPES = [  # (start, end, all_day) — normal, across midnight, month end, all-day across a month end
    ("2026-11-21 14:45", "2026-11-21 15:30", False),
    ("2026-11-22 23:30", "2026-11-23 00:45", False),
    ("2026-11-30 22:00", "2026-12-01 01:15", False),
    ("2026-11-30", "2026-12-01", True),
]


def cases_create(state, index):
    begin, end, all_day = SHAPES[index % len(SHAPES)]
    special = index % 2 == 1

    def setup():
        return {"title": V.special() if special else V.word(), "location": V.special() if special else V.word(1),
                "notes": "line one\n" + V.special(), "calendar": "Work" if index % 3 == 0 else None}

    def expect(ctx, result, error, before, after):
        made = new_events(before, after)
        item = next(iter(made.values()), None)
        checks = {"no_error": error is None, "one_event_made": len(made) == 1}
        if item:
            checks.update(title=item["title"] == ctx["title"], start=item["start"] == begin, end=item["end"] == end,
                          all_day=item["all_day"] == all_day, location=item["location"] == ctx["location"],
                          notes=item["notes"] == ctx["notes"],
                          calendar=item["calendar"] == (ctx["calendar"] or "Calendar"),
                          return_matches=bool(result) and all(result[k] == item[k] for k in
                                                               ("title", "start", "end", "all_day", "location",
                                                                "notes", "calendar")))
        return checks, set(made)
    run_case("event_create", "background", state, setup,
             lambda c: C.event_create(title=c["title"], start=begin, end=end, location=c["location"],
                                      calendar=c["calendar"], all_day=all_day, notes=c["notes"],
                                      mode="background"), expect, f"shape{index % len(SHAPES)}")


def target_event(special=False, calendar="Calendar", day=(11, 25)):
    title = V.special() if special else V.word()
    event(title, [2026, day[0], day[1], 10, 0], [2026, day[0], day[1], 11, 0], calendar, location="Room 1",
          notes="old notes")
    time.sleep(1)
    return {"title": title, "date": f"2026-{day[0]:02d}-{day[1]:02d}"}


def cases_update(state, special):
    def setup():
        ctx = target_event(special)
        ctx.update(new=V.special() if special else V.word(), location=V.word(1), notes="new\nnotes " + V.word(1))
        return ctx

    def expect(ctx, result, error, before, after):
        old = [pk for pk, e in before["events"].items() if e["title"] == ctx["title"]]
        item = after["events"].get(old[0]) if old else None
        checks = {"no_error": error is None, "event_present": item is not None}
        if item:
            checks.update(title=item["title"] == ctx["new"], start=item["start"] == "2026-11-26 23:15",
                          end=item["end"] == "2026-11-27 00:20", location=item["location"] == ctx["location"],
                          notes=item["notes"] == ctx["notes"], calendar=item["calendar"] == "Calendar",
                          return_matches=bool(result) and result["start"] == item["start"]
                          and result["title"] == item["title"])
        return checks, set(old)
    run_case("event_update", "background", state, setup,
             lambda c: C.event_update(match=c["title"], date=c["date"], title=c["new"], start="2026-11-26 23:15",
                                      end="2026-11-27 00:20", location=c["location"], notes=c["notes"],
                                      mode="background"), expect)


def cases_delete(mode, state, special):
    def setup():
        return target_event(special, "Work", (11, 27))

    def expect(ctx, result, error, before, after):
        old = [pk for pk, e in before["events"].items() if e["title"] == ctx["title"]]
        return {"no_error": error is None, "deleted": bool(old) and all(pk not in after["events"] for pk in old),
                "return_matches": bool(result) and result["deleted"] and result["title"] == ctx["title"]}, set(old)
    run_case("event_delete", mode, state, setup,
             lambda c: C.event_delete(match=c["title"], date=c["date"], mode=mode), expect)


def cases_calendars(mode, state, special):
    def setup_create():
        return {"name": V.special() if special else V.word()}

    def expect_create(ctx, result, error, before, after):
        added = {pk: n for pk, n in after["calendars"].items() if pk not in before["calendars"]}
        return {"no_error": error is None, "one_calendar_made": list(added.values()) == [ctx["name"]],
                "return_matches": bool(result) and result["name"] == ctx["name"]}, set(added)
    run_case("calendar_create", mode, state, setup_create, lambda c: C.calendar_create(name=c["name"], mode=mode),
             expect_create)

    def setup_delete():
        name = V.special() if special else V.word()
        prep("calendar", name=name)
        time.sleep(1)
        event("Inside " + name, [2026, 11, 28, 9, 0], [2026, 11, 28, 10, 0], name)
        time.sleep(1)
        return {"name": name}

    def expect_delete(ctx, result, error, before, after):
        gone = [pk for pk, n in before["calendars"].items() if n == ctx["name"]]
        inside = [pk for pk, e in before["events"].items() if e["calendar"] == ctx["name"]]
        return {"no_error": error is None, "deleted": bool(gone) and all(pk not in after["calendars"] for pk in gone),
                "its_events_gone": all(pk not in after["events"] for pk in inside),
                "return_matches": bool(result) and result["deleted"]}, set(gone) | set(inside)
    run_case("calendar_delete", mode, state, setup_delete, lambda c: C.calendar_delete(name=c["name"], mode=mode),
             expect_delete)


def reads(state):
    def setup():
        title = V.special()
        event(title, [2026, 12, 2, 8, 0], [2026, 12, 2, 9, 30], "Family", location="Park ✨", notes="bring\nballs")
        event(title + " later", [2026, 12, 3, 8, 0], [2026, 12, 3, 9, 30], "Work")
        time.sleep(1)
        return {"title": title}

    def check_get(ctx, result, error, before, after):
        item = D.titled(after, ctx["title"])[0]
        return {"no_error": error is None, "fields": all(result[k] == item[k] for k in
                                                         ("title", "start", "end", "location", "notes", "calendar")),
                "only_fields_asked": set(result) == {"title", "start", "end", "location", "notes", "calendar"}}, set()
    run_case("event_get", "background", state, setup,
             lambda c: C.event_get(match=c["title"], date="2026-12-02",
                                   fields="title,start,end,location,notes,calendar"), check_get)

    def check_list(ctx, result, error, before, after):
        local = {"Calendar", "Work", "Family"} | {n for n in after["calendars"].values()}
        expected = sorted((e["title"], e["start"]) for e in after["events"].values()
                          if "2026-11-18" <= e["start"][:10] <= "2026-11-20"
                          and e["calendar"] not in ("US Holidays", "Birthdays", "Siri Suggestions",
                                                    "Scheduled Reminders", "Reminders", "Found in Mail",
                                                    "Found in Natural Language", "Facebook Birthdays", "Default")
                          and e["calendar"] in local)
        got = sorted((r["title"], r["start"]) for r in result)
        return {"no_error": error is None, "same_events": got == expected, "earliest_first":
                [r["start"] for r in result] == sorted(r["start"] for r in result)}, set()
    run_case("event_list", "background", state, lambda: {},
             lambda c: C.event_list(from_date="2026-11-18", to_date="2026-11-20", limit=100, fields="title,start"),
             check_list)

    def check_search(ctx, result, error, before, after):
        return {"no_error": error is None,
                "found": sorted(r["title"] for r in result) == ["Standup", "Standup", "Standup review"]}, set()
    run_case("event_search", "background", state, lambda: {},
             lambda c: C.event_search(query="standup", from_date="2026-11-17", to_date="2026-11-19",
                                      fields="title,calendar"), check_search)

    def check_calendars(ctx, result, error, before, after):
        names = sorted(r["name"] for r in result)
        return {"no_error": error is None, "has_local": {"Calendar", "Work", "Family"} <= set(names),
                "no_subscribed_or_reminders": not {"US Holidays", "Birthdays", "Scheduled Reminders"} & set(names)}, set()
    run_case("calendar_list", "background", state, lambda: {}, lambda c: C.calendar_list(), check_calendars)


def error_case(function, mode, call, expected, state, kind):
    def expect(ctx, result, error, before, after):
        return {"raised_" + expected.__name__: isinstance(error, expected),
                "nothing_changed": before == after}, set()
    run_case(function, mode, state, lambda: {}, call, expect, kind)


def main():
    open_app()
    base()
    time.sleep(2)
    index = 0
    for state in ("closed", "open"):
        for special in (False, True):
            for _ in range(2):
                cases_create(state, index)
                index += 1
            cases_update(state, special)
            cases_delete("background", state, special)
            cases_calendars("background", state, special)
        reads(state)
    for i, state in enumerate(UI_STATES):
        cases_delete("ui", state, i % 2 == 1)
        cases_calendars("ui", state, i % 2 == 1)
    for mode in ("ui", "background"):
        st = "other_view" if mode == "ui" else "open"
        error_case("event_delete", mode, lambda c: C.event_delete(match="Standup", date="2026-11-18", mode=mode),
                   C.Ambiguous, st, "ambiguous")
        error_case("event_delete", mode, lambda c: C.event_delete(match="Nope 3", date="2026-11-18", mode=mode),
                   C.NotFound, st, "not_found")
        error_case("calendar_delete", mode, lambda c: C.calendar_delete(name="No Such Cal", mode=mode),
                   C.NotFound, st, "not_found")
        error_case("calendar_create", mode, lambda c: C.calendar_create(name="Work", mode=mode),
                   C.AlreadyExists, st, "exists")
    error_case("event_update", "background",
               lambda c: C.event_update(match="Standup", date="2026-11-18", title="x", mode="background"),
               C.Ambiguous, "open", "ambiguous")
    error_case("event_get", "background", lambda c: C.event_get(match="Dentist", date="2026-11-20"),
               C.NotFound, "open", "not_found")
    for function, call in [("event_delete", lambda c: C.event_delete(match="Dentist", date="2026-11-19")),
                           ("calendar_create", lambda c: C.calendar_create(name=V.word()))]:
        def expect(ctx, result, error, before, after):
            return {"raised_StateBlocked": isinstance(error, C.StateBlocked), "nothing_changed": before == after,
                    "popover_left_with_its_text": "lunch with sam" in (popover_texts() or "")}, set()
        run_case(function, "ui", "blocked", lambda: {}, call, expect, "blocked")
    escape_all()
    R.data["meta"]["finished"] = time.strftime("%Y-%m-%d %H:%M:%S")
    R.save()


main()
