"""Record one UI-mode end-to-end run (delete_overlapping_holds) from a messy start state: python3 demo_calendar.py"""
import datetime
import json
import os
import subprocess
import sys
import time

from vcommon import osa, se, sh, wait

PREP = r"""
function run(argv) {
  const Cal = Application("Calendar"), a = JSON.parse(argv[0]);
  const at = p => new Date(p[0], p[1] - 1, p[2], p[3], p[4]);
  const e = Cal.Event({summary: a.title, startDate: at(a.start), endDate: at(a.end)});
  Cal.calendars.byName(a.calendar).events.push(e);
  if (a.show) Cal.show(e);
  return e.uid();
}"""
day = [2026, 11, 18]
for title, h1, m1, h2, m2, show in [("Design meeting", 15, 0, 16, 0, False), ("Hold: review prep", 14, 40, 15, 20, False),
                                    ("Hold - commute", 15, 50, 16, 40, False), ("Hold: gym", 18, 0, 19, 0, False),
                                    ("Tea", 10, 0, 10, 30, True)]:
    osa(PREP, json.dumps({"title": title, "start": day + [h1, m1], "end": day + [h2, m2], "calendar": "Calendar",
                          "show": show}), lang="JavaScript")
time.sleep(1)
se('keystroke "f" using command down', "Calendar")
time.sleep(0.5)
se('keystroke "zq"', "Calendar")
time.sleep(0.5)
se('click menu item "Edit Event" of menu "Edit" of menu bar item "Edit" of menu bar 1', "Calendar")
time.sleep(1)
recorder = subprocess.Popen(["screencapture", "-x", "-V", "45", os.path.expanduser("~/verify-out/calendar-demo.mov")])
time.sleep(2)
examples = os.path.expanduser("~/libs/calendar/examples")
done = subprocess.run([sys.executable, os.path.join(examples, "delete_overlapping_holds.py")], cwd=examples,
                      env={**os.environ, "PYTHONPATH": os.path.expanduser("~/libs/calendar")}, capture_output=True,
                      text=True)
print(done.returncode, done.stderr[-500:])
recorder.wait()
print("recorded")
