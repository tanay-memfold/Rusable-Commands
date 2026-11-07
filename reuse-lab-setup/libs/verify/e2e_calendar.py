"""End-to-end: run each Calendar example program from a messy start state (an event popover open and a search
with text), then check the exact outcome in Calendar.sqlitedb.   python3 e2e_calendar.py <group> [record]"""
import datetime
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.expanduser("~/libs/calendar"))
import calendar_app as C  # noqa: E402
import calendar_db as D  # noqa: E402
from vcommon import Recorder, osa, se, sh, wait  # noqa: E402

GROUP = sys.argv[1]
RECORD = len(sys.argv) > 2
R = Recorder(GROUP, {"versions": C._versions(), "started": time.strftime("%Y-%m-%d %H:%M:%S")})
EXAMPLES = os.path.expanduser("~/libs/calendar/examples")
PREP = r"""
function run(argv) {
  const Cal = Application("Calendar"), a = JSON.parse(argv[1]);
  const at = p => new Date(p[0], p[1] - 1, p[2], p[3], p[4]);
  if (argv[0] === "calendar") { Cal.calendars.push(Cal.Calendar({name: a.name})); return "ok"; }
  if (argv[0] === "show") {
    for (const c of Cal.calendars()) { const f = c.events.whose({uid: a.uid})(); if (f.length) Cal.show(f[0]); }
    return "ok";
  }
  const e = Cal.Event({summary: a.title, startDate: at(a.start), endDate: at(a.end)});
  Cal.calendars.byName(a.calendar).events.push(e);
  return e.uid();
}"""


def prep(op, **args):
    return osa(PREP, op, json.dumps(args), lang="JavaScript")


def event(title, start, end, calendar="Calendar"):
    return prep("event", title=title, start=start, end=end, calendar=calendar)


def parts(moment):
    return [moment.year, moment.month, moment.day, moment.hour, moment.minute]


def messy(uid):
    """An event's Edit Event popover open, after a search was typed."""
    sh("open -b com.apple.iCal")
    wait(lambda: se("return (count of windows) > 0", "Calendar") == "true", 20)
    time.sleep(1)
    se('keystroke "f" using command down', "Calendar")
    time.sleep(0.7)
    se('keystroke "zq"', "Calendar")
    time.sleep(0.5)
    prep("show", uid=uid)
    time.sleep(0.7)
    se('click menu item "Edit Event" of menu "Edit" of menu bar item "Edit" of menu bar 1', "Calendar")
    wait(lambda: se('''repeat with x in windows
  if (count of pop overs of x) > 0 then return "yes"
end repeat
return "no"''', "Calendar") == "yes", 5)


def run_program(name):
    recorder = None
    if RECORD:
        recorder = subprocess.Popen(["screencapture", "-x", "-V", "90", os.path.expanduser(f"~/verify-out/{name}.mov")])
        time.sleep(1.5)
    began = time.monotonic()
    done = subprocess.run([sys.executable, os.path.join(EXAMPLES, name + ".py")], capture_output=True, text=True,
                          cwd=EXAMPLES, env={**os.environ, "PYTHONPATH": os.path.expanduser("~/libs/calendar")})
    seconds = round(time.monotonic() - began, 1)
    if recorder:
        time.sleep(2)
        recorder.terminate()
        recorder.wait()
    return done, seconds


def settle(test, timeout=150):
    deadline = time.monotonic() + timeout
    while True:
        snap = D.snapshot()
        if test(snap) or time.monotonic() > deadline:
            return snap
        time.sleep(2)


def main():
    sh("open -g -j -b com.apple.iCal")
    time.sleep(4)
    prep("calendar", name="Work")
    time.sleep(1)
    today = datetime.date.today()
    monday = today + datetime.timedelta(days=7 - today.weekday())
    tuesday, friday = monday + datetime.timedelta(days=1), monday + datetime.timedelta(days=4)
    at = lambda day, h, m: datetime.datetime.combine(day, datetime.time(h, m))  # noqa: E731
    event("Dentist checkup", parts(at(tuesday, 16, 20)), parts(at(tuesday, 17, 5)))
    event("Dentist checkup", parts(at(today, 9, 0)), parts(at(today, 9, 30)))
    event("Team sync", parts(at(tuesday, 16, 0)), parts(at(tuesday, 16, 30)), "Work")
    popover = event("Gym", parts(at(friday, 7, 0)), parts(at(friday, 8, 0)))
    time.sleep(2)
    messy(popover)
    done, seconds = run_program("move_dentist_to_friday")
    want = (at(friday, 16, 20).strftime("%Y-%m-%d %H:%M"), at(friday, 17, 5).strftime("%Y-%m-%d %H:%M"))
    after = settle(lambda s: any((e["start"], e["end"]) == want for e in D.titled(s, "Dentist checkup")))
    dentists = sorted((e["start"], e["end"]) for e in D.titled(after, "Dentist checkup"))
    checks = {"program_ok": done.returncode == 0,
              "moved_to_friday_same_time": want in dentists,
              "this_weeks_dentist_untouched": (at(today, 9, 0).strftime("%Y-%m-%d %H:%M"),
                                               at(today, 9, 30).strftime("%Y-%m-%d %H:%M")) in dentists,
              "two_dentist_events": len(dentists) == 2,
              "team_sync_untouched": [e["start"] for e in D.titled(after, "Team sync")] ==
              [at(tuesday, 16, 0).strftime("%Y-%m-%d %H:%M")]}
    R.case("e2e move_dentist_to_friday", "ui", "popover_open+search_text", "e2e", checks,
           {"stdout": done.stdout[-500:], "stderr": done.stderr[-1500:]}, seconds)

    day = datetime.date(2026, 11, 18)
    event("Design meeting", parts(at(day, 15, 0)), parts(at(day, 16, 0)), "Work")
    event("Hold: focus", parts(at(day, 14, 30)), parts(at(day, 15, 15)))
    event("Hold - travel", parts(at(day, 15, 45)), parts(at(day, 17, 0)), "Work")
    event("Hold: lunch", parts(at(day, 12, 0)), parts(at(day, 13, 0)))
    event("Hold: late", parts(at(day, 16, 0)), parts(at(day, 16, 30)))
    event("Review", parts(at(day, 15, 0)), parts(at(day, 15, 30)))
    popover = event("Coffee", parts(at(day, 9, 0)), parts(at(day, 9, 30)))
    time.sleep(2)
    messy(popover)
    done, seconds = run_program("delete_overlapping_holds")
    gone = ("Hold: focus", "Hold - travel")
    after = settle(lambda s: not any(D.titled(s, t) for t in gone))
    checks = {"program_ok": done.returncode == 0,
              "overlapping_holds_deleted": not any(D.titled(after, t) for t in gone),
              "other_holds_kept": bool(D.titled(after, "Hold: lunch")) and bool(D.titled(after, "Hold: late")),
              "meeting_and_review_kept": bool(D.titled(after, "Design meeting")) and bool(D.titled(after, "Review")),
              "listed_everything": all(t in done.stdout for t in ("Design meeting", "Hold: lunch", "Review"))}
    R.case("e2e delete_overlapping_holds", "ui", "popover_open+search_text", "e2e", checks,
           {"stdout": done.stdout[-800:], "stderr": done.stderr[-1500:]}, seconds)
    R.save()


main()
