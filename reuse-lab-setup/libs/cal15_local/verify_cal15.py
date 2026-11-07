"""verify_cal15.py <group> <seed> <states...>: Calendar's repeat and alert commands, read back from Calendar.sqlitedb."""
import os, sys, time, json, subprocess
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import calendar_app as C, cal_more_db as DB, vkit
from vcommon import osa, sh, se
group, seed, states = sys.argv[1], int(sys.argv[2]), sys.argv[3:]
APP = "Calendar"
SETUP = r"""
function run(argv) {
  const Cal = Application("Calendar"); const a = JSON.parse(argv[1]);
  const cal = () => Cal.calendars().filter(c => c.name() === a.cal);
  if (argv[0] === "calendar") { if (!cal().length) Cal.calendars.push(Cal.Calendar({name: a.cal})); return "true"; }
  if (argv[0] === "event") {
    const at = p => new Date(p[0], p[1] - 1, p[2], p[3], p[4]);
    const e = Cal.Event({summary: a.title, startDate: at(a.start), endDate: at(a.end)}); cal()[0].events.push(e);
    if (a.rule) e.recurrence = a.rule;
    (a.alerts || []).forEach(m => e.displayAlarms.push(Cal.DisplayAlarm({triggerInterval: -m})));
    return JSON.stringify(e.uid());
  }
}"""
def setup_js(op, **a): return json.loads(osa(SETUP, op, json.dumps(a), lang="JavaScript"))
def running(): return bool(sh("pgrep -x Calendar"))
def quit_app():
    if running(): osa('tell application "Calendar" to quit'); [time.sleep(0.5) for _ in range(30) if running()]
def front_app():
    try: return osa('tell application "System Events" to return name of first process whose frontmost is true')
    except RuntimeError: return ""
def start(state):
    if state == "closed": quit_app(); return
    if not running(): sh("open -b com.apple.iCal"); [time.sleep(0.5) for _ in range(40) if not running()]; time.sleep(2)
    se("set visible to true\nset frontmost to true", APP); time.sleep(0.6)
    if state == "hidden": se("set visible to false", APP); time.sleep(0.6)
    elif state == "other_app": sh("open -a Calculator"); [time.sleep(0.3) for _ in range(20) if front_app() == APP]
K = vkit.Kit("cal15", C, APP, group, seed, C.CalendarError, start)
# calendar_export_ics saves into the folder Calendar's save sheet shows, then moves the file out, so those folders' times change.
# The kit's whole-home check leaves them out; each export case checks instead that their contents end up exactly as before.
SHEET_FOLDERS = ("Documents", "Desktop", "Downloads")
_ov = K.outside_view
def _outside_view():
    v = _ov()
    for f in SHEET_FOLDERS: v.pop(f, None)
    return v
K.outside_view = _outside_view; K.outside0 = _outside_view()
def sheet_folders(): return {f: sorted(os.listdir(os.path.join(os.path.expanduser("~"), f))) for f in SHEET_FOLDERS if os.path.isdir(os.path.join(os.path.expanduser("~"), f))}
CAL = f"Rusable Cal {K.V.rng.randint(1000, 9999)}"
DAY = [2027, 3, 1]
n = {"i": 0}
def ev(rule=None, alerts=()):
    n["i"] += 1; d = 1 + n["i"] % 27; m = 3 + (n["i"] // 27) % 9
    title = (K.V.special() if n["i"] % 2 else K.V.word())
    if not running(): sh("open -g -j -b com.apple.iCal"); [time.sleep(0.5) for _ in range(40) if not running()]; time.sleep(2)
    setup_js("calendar", cal=CAL)
    uid = setup_js("event", cal=CAL, title=title, start=[2027, m, d, 10, 0], end=[2027, m, d, 11, 0], rule=rule, alerts=list(alerts))
    for _ in range(40):
        if DB.item(title): break
        time.sleep(0.25)
    return {"title": title, "date": f"2027-{m:02d}-{d:02d}", "uid": uid, "snap": DB.snapshot()}
def others_same(c):
    now = DB.snapshot(); return {k: v for k, v in now.items() if v[0] != c["title"]} == {k: v for k, v in c["snap"].items() if v[0] != c["title"]}
def has(c, freq, interval=1, count=None, until=False):
    r = DB.repeat(c["title"])
    return bool(r) and r != "missing" and r["freq"] == freq and r["interval"] == interval and r["count"] == count and (bool(r["until"]) == until) and r["rows"] == 1
RULES = [("weekly_count", "FREQ=WEEKLY;COUNT=5", ("WEEKLY", 1, 5, False)), ("daily_interval", "freq=daily;interval=3", ("DAILY", 3, None, False)),
         ("monthly_until", "FREQ=MONTHLY;UNTIL=20271231T000000Z", ("MONTHLY", 1, None, True)), ("yearly", "RRULE:FREQ=YEARLY", ("YEARLY", 1, None, False)),
         ("weekly_days", "FREQ=WEEKLY;INTERVAL=2;BYDAY=MO,WE", ("WEEKLY", 2, None, False))]
def state_cases(state):
    m = "background"
    for kind, rule, want in RULES:
        K.case("event_set_repeat", m, state, kind, lambda: ev(), lambda c, rule=rule: C.event_set_repeat(match=c["title"], date=c["date"], rule=rule, mode=m),
               lambda c, b, a, r, e, want=want: {"no_error": e is None, "db_repeat": has(c, *want), "return": bool(r) and r["uid"] == c["uid"] and bool(r["repeat"]), "others_same": others_same(c)})
    K.case("event_set_repeat", m, state, "stop_refused", lambda: ev(rule="FREQ=DAILY;COUNT=4"), lambda c: C.event_set_repeat(match=c["title"], date=c["date"], rule=None, mode=m),
           lambda c, b, a, r, e: {"raised_NotSupported": isinstance(e, C.NotSupported), "repeat_kept": has(c, "DAILY", 1, 4), "others_same": others_same(c)})
    K.case("event_set_repeat", m, state, "replace", lambda: ev(rule="FREQ=DAILY;COUNT=4"), lambda c: C.event_set_repeat(match=c["title"], date=c["date"], rule="FREQ=WEEKLY;COUNT=2", mode=m),
           lambda c, b, a, r, e: {"no_error": e is None, "db_repeat": has(c, "WEEKLY", 1, 2), "others_same": others_same(c)})
    for kind, mins in (("15", 15), ("at_start", 0), ("day", 1440)):
        K.case("event_add_alert", m, state, kind, lambda: ev(), lambda c, mins=mins: C.event_add_alert(match=c["title"], date=c["date"], minutes_before=mins, mode=m),
               lambda c, b, a, r, e, mins=mins: {"no_error": e is None, "db_alerts": DB.alerts(c["title"]) == [mins], "return": bool(r) and r["alerts"] == [mins], "others_same": others_same(c)})
    K.case("event_add_alert", m, state, "second", lambda: ev(alerts=[30]), lambda c: C.event_add_alert(match=c["title"], date=c["date"], minutes_before=5, mode=m),
           lambda c, b, a, r, e: {"no_error": e is None, "db_alerts": DB.alerts(c["title"]) == [5, 30], "return": bool(r) and r["alerts"] == [5, 30], "others_same": others_same(c)})
    K.case("event_details", m, state, "both", lambda: ev(rule="FREQ=MONTHLY;COUNT=6", alerts=[45, 15]), lambda c: C.event_details(match=c["title"], date=c["date"], mode=m),
           lambda c, b, a, r, e: {"no_error": e is None, "alerts_match_db": bool(r) and r["alerts"] == DB.alerts(c["title"]) == [15, 45], "repeat_match_db": bool(r) and "MONTHLY" in (r["repeat"] or "") and "COUNT=6" in r["repeat"] and has(c, "MONTHLY", 1, 6), "title": bool(r) and r["title"] == c["title"], "others_same": others_same(c)})
    K.case("event_details", m, state, "plain", lambda: ev(), lambda c: C.event_details(match=c["title"], date=c["date"], mode=m),
           lambda c, b, a, r, e: {"no_error": e is None, "empty": bool(r) and r["alerts"] == [] and r["repeat"] is None and DB.repeat(c["title"]) is None and DB.alerts(c["title"]) == []})
def errors():
    m, st = "background", "open"
    for kind, rule in (("no_freq", "INTERVAL=2"), ("bad_freq", "FREQ=HOURLY"), ("bad_key", "FREQ=DAILY;BYHOUR=3"), ("count_and_until", "FREQ=DAILY;COUNT=2;UNTIL=20270101T000000Z"), ("zero", "FREQ=DAILY;INTERVAL=0")):
        K.case("event_set_repeat", m, st, kind, lambda: ev(), lambda c, rule=rule: C.event_set_repeat(match=c["title"], date=c["date"], rule=rule, mode=m),
               lambda c, b, a, r, e: {"raised_ValueError": isinstance(e, ValueError), "db_unchanged": DB.repeat(c["title"]) is None, "others_same": others_same(c)})
    for kind, mins in (("negative", -5), ("too_big", 50000), ("not_int", 2.5), ("bool", True)):
        K.case("event_add_alert", m, st, kind, lambda: ev(), lambda c, mins=mins: C.event_add_alert(match=c["title"], date=c["date"], minutes_before=mins, mode=m),
               lambda c, b, a, r, e: {"raised_ValueError": isinstance(e, ValueError), "db_unchanged": DB.alerts(c["title"]) == []})
    K.case("event_add_alert", m, st, "already_exists", lambda: ev(alerts=[15]), lambda c: C.event_add_alert(match=c["title"], date=c["date"], minutes_before=15, mode=m),
           lambda c, b, a, r, e: {"raised_AlreadyExists": isinstance(e, C.AlreadyExists), "db_unchanged": DB.alerts(c["title"]) == [15]})
    for fn, call in (("event_set_repeat", lambda c: C.event_set_repeat(match="No such event 4242", date=c["date"], rule="FREQ=DAILY", mode=m)),
                     ("event_add_alert", lambda c: C.event_add_alert(match="No such event 4242", date=c["date"], minutes_before=5, mode=m)),
                     ("event_details", lambda c: C.event_details(match="No such event 4242", date=c["date"], mode=m)),
                     ("event_set_repeat", lambda c: C.event_set_repeat(match=c["title"], date="2027-12-30", rule="FREQ=DAILY", mode=m))):
        K.case(fn, m, st, "not_found", lambda: ev(), call, lambda c, b, a, r, e: {"raised_NotFound": isinstance(e, C.NotFound), "db_unchanged": DB.repeat(c["title"]) is None and DB.alerts(c["title"]) == [], "others_same": others_same(c)})
    def twins():
        c = ev(); uid2 = setup_js("event", cal=CAL, title=c["title"], start=[int(x) for x in c["date"].split("-")] + [15, 0], end=[int(x) for x in c["date"].split("-")] + [16, 0])
        time.sleep(1); c["uid2"] = uid2; c["snap"] = DB.snapshot(); return c
    K.case("event_set_repeat", m, st, "ambiguous", twins, lambda c: C.event_set_repeat(match=c["title"], date=c["date"], rule="FREQ=DAILY", mode=m),
           lambda c, b, a, r, e: {"raised_Ambiguous": isinstance(e, C.Ambiguous), "neither": DB.repeat_rows(c["title"]) == 0})
    for fn in ("event_set_repeat", "event_add_alert", "event_details"):
        args = {"event_set_repeat": {"rule": "FREQ=DAILY"}, "event_add_alert": {"minutes_before": 5}}.get(fn, {})
        K.case(fn, "ui", st, "ui_not_supported", lambda: ev(), lambda c, fn=fn, args=args: getattr(C, fn)(match=c["title"], date=c["date"], mode="ui", **args),
               lambda c, b, a, r, e: {"raised_NotSupported": isinstance(e, C.NotSupported), "db_unchanged": DB.repeat(c["title"]) is None and DB.alerts(c["title"]) == []}, clip=False)
def large_clipboard():
    m = "background"
    K.case("event_set_repeat", m, "open", "large_clipboard", lambda: ev(), lambda c: C.event_set_repeat(match=c["title"], date=c["date"], rule="FREQ=DAILY;COUNT=2", mode=m), lambda c, b, a, r, e: {"no_error": e is None, "db_repeat": has(c, "DAILY", 1, 2)}, big=True)
    K.case("event_add_alert", m, "open", "large_clipboard", lambda: ev(), lambda c: C.event_add_alert(match=c["title"], date=c["date"], minutes_before=7, mode=m), lambda c, b, a, r, e: {"no_error": e is None, "db_alerts": DB.alerts(c["title"]) == [7]}, big=True)
    K.case("event_details", m, "open", "large_clipboard", lambda: ev(alerts=[9]), lambda c: C.event_details(match=c["title"], date=c["date"], mode=m), lambda c, b, a, r, e: {"no_error": e is None, "alerts": bool(r) and r["alerts"] == [9]}, big=True)
ICS = f"{K.DATA}/ics"; os.makedirs(ICS, exist_ok=True)
def export_setup():
    cal = f"Rusable Export {K.V.rng.randint(1000, 99999)}"; titles = [K.V.special(), K.V.word()]
    if not running(): sh("open -g -j -b com.apple.iCal"); [time.sleep(0.5) for _ in range(40) if not running()]; time.sleep(2)
    setup_js("calendar", cal=cal)
    for k, t in enumerate(titles): setup_js("event", cal=cal, title=t, start=[2027, 6, 3 + k, 9, 0], end=[2027, 6, 3 + k, 10, 0])
    time.sleep(1.5); return {"cal": cal, "titles": titles, "p": f"{ICS}/{cal}.ics", "files": sorted(os.listdir(ICS)), "sheet0": sheet_folders()}
def ics_ok(c):
    try: t = open(c["p"], encoding="utf-8").read().replace("\r\n ", "").replace("\n ", "")
    except OSError: return False
    def unescape(x): return x.replace("\\,", ",").replace("\\;", ";").replace("\\\\", "\\")
    summaries = sorted(unescape(l.split(":", 1)[1].strip()) for l in t.splitlines() if l.startswith("SUMMARY"))
    return t.startswith("BEGIN:VCALENDAR") and t.count("BEGIN:VEVENT") == 2 and summaries == sorted(c["titles"])
def export_cases(state):
    K.case("calendar_export_ics", "ui", state, "two_events", export_setup, lambda c: C.calendar_export_ics(name=c["cal"], path=c["p"]),
           lambda c, b, a, r, e: {"no_error": e is None, "ics_has_both": ics_ok(c), "only_it": sorted(os.listdir(ICS)) == sorted(c["files"] + [os.path.basename(c["p"])]), "return": bool(r) and r["events"] == 2 and r["path"] == c["p"],
                                      "sheet_folders_as_before": sheet_folders() == c["sheet0"]}, lambda c: {c["p"]})
def export_group():
    for st in ("closed", "open", "other_app", "hidden"): export_cases(st)
    K.case("calendar_export_ics", "ui", "open", "large_clipboard", export_setup, lambda c: C.calendar_export_ics(name=c["cal"], path=c["p"]), lambda c, b, a, r, e: {"no_error": e is None, "ics_has_both": ics_ok(c)}, lambda c: {c["p"]}, big=True)
    def taken():
        c = export_setup(); open(c["p"], "w").write("keep"); c["files"] = sorted(os.listdir(ICS)); return c
    K.case("calendar_export_ics", "ui", "open", "already_exists", taken, lambda c: C.calendar_export_ics(name=c["cal"], path=c["p"]), lambda c, b, a, r, e: {"raised": isinstance(e, C.AlreadyExists), "kept": open(c["p"]).read() == "keep"})
    K.case("calendar_export_ics", "ui", "open", "not_found", lambda: {}, lambda c: C.calendar_export_ics(name="No Such Calendar 4242", path=f"{ICS}/none.ics"), lambda c, b, a, r, e: {"raised": isinstance(e, C.NotFound), "none": not os.path.exists(f"{ICS}/none.ics")})
    K.case("calendar_export_ics", "ui", "open", "bad_type", lambda: {}, lambda c: C.calendar_export_ics(name="Calendar", path=f"{ICS}/x.txt"), lambda c, b, a, r, e: {"raised": isinstance(e, ValueError)})
    K.case("calendar_export_ics", "ui", "open", "no_folder", lambda: {}, lambda c: C.calendar_export_ics(name="Calendar", path=f"{ICS}/none/x.ics"), lambda c, b, a, r, e: {"raised": isinstance(e, C.NotFound)})
    K.case("calendar_export_ics", "background", "open", "not_supported", lambda: {}, lambda c: C.calendar_export_ics(name="Calendar", path=f"{ICS}/bg.ics", mode="background"), lambda c, b, a, r, e: {"raised": isinstance(e, C.NotSupported)})
CAL_DB = DB.PATH  # Calendar.sqlitedb, where cal_more_db reads it on this macOS
def calendar_rows(name):
    import sqlite3
    d = sqlite3.connect(f"file:{CAL_DB}?mode=ro", uri=True)
    try: return d.execute("select count(*) from Calendar where title = ?", (name,)).fetchone()[0]
    finally: d.close()
def large_clipboard_old():
    """Day 3b: the old UI paste (calendar_create) with a very large clipboard; the calendar is read back from Calendar.sqlitedb."""
    def setup(): return {"name": f"Big clipboard {K.word()} {K.V.rng.randint(100, 999)}"}
    K.case("calendar_create", "ui", "open", "large_clipboard", setup, lambda c: C.calendar_create(name=c["name"], mode="ui"),
           lambda c, b, a, r, e: {"no_error": e is None, "db_one_calendar": calendar_rows(c["name"]) == 1}, big=True)
# Import (overnight): made-up .ics files; the events are read back from Calendar.sqlitedb by title, calendar and start time.
def in_calendar(cal):
    import sqlite3
    d = sqlite3.connect(f"file:{CAL_DB}?mode=ro", uri=True)
    try: return sorted((t, round(st)) for t, st in d.execute("select i.summary, i.start_date from CalendarItem i join Calendar c on c.ROWID = i.calendar_id where c.title = ?", (cal,)))
    finally: d.close()
def ics_text(events):
    def esc(x): return x.replace("\\", "\\\\").replace(",", "\\,").replace(";", "\\;")
    out = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//rusable//verify//EN"]
    for k, (title, day, hour) in enumerate(events):
        out += ["BEGIN:VEVENT", f"UID:{K.V.rng.randint(10**8, 10**9)}-{k}@rusable.test", "DTSTAMP:20261101T090000Z", f"DTSTART:2027{day}T{hour:02d}0000Z", f"DTEND:2027{day}T{hour + 1:02d}0000Z", f"SUMMARY:{esc(title)}", "END:VEVENT"]
    return "\r\n".join(out + ["END:VCALENDAR", ""])
def import_setup(count=2):
    cal = f"Rusable Import {K.V.rng.randint(1000, 99999)}"
    if not running(): sh("open -g -j -b com.apple.iCal"); [time.sleep(0.5) for _ in range(40) if not running()]; time.sleep(2)
    setup_js("calendar", cal=cal); time.sleep(1)
    events = [(K.V.special() if k % 2 else K.V.word(), f"0{4 + k % 5}{10 + k:02d}", 8 + k) for k in range(count)]
    n["i"] += 1; p = f"{ICS}/{(K.V.special() if n['i'] % 2 else K.V.word()).replace('/', '-')} {n['i']}.ics"
    open(p, "w", encoding="utf-8").write(ics_text(events))
    return {"cal": cal, "p": p, "titles": sorted(t for t, _, _ in events), "before": in_calendar(cal), "snap": DB.snapshot()}
def imported(c, b, a, r, e):
    now = in_calendar(c["cal"]); other = {k: v for k, v in DB.snapshot().items() if v[0] not in c["titles"]}
    return {"no_error": e is None, "events_in_calendar": sorted(t for t, _ in now) == c["titles"], "others_same": other == {k: v for k, v in c["snap"].items() if v[0] not in c["titles"]},
            "return": bool(r) and r["calendar"] == c["cal"] and r["events"] == len(c["titles"]) and r["path"] == c["p"]}
def import_group():
    for st in ("closed", "open", "other_app", "hidden"):
        K.case("calendar_import_ics", "ui", st, "two_events", import_setup, lambda c: C.calendar_import_ics(path=c["p"], calendar=c["cal"]), imported)
    K.case("calendar_import_ics", "ui", "open", "five_events", lambda: import_setup(5), lambda c: C.calendar_import_ics(path=c["p"], calendar=c["cal"]), imported)
    K.case("calendar_import_ics", "ui", "open", "one_event", lambda: import_setup(1), lambda c: C.calendar_import_ics(path=c["p"], calendar=c["cal"]), imported)
    K.case("calendar_import_ics", "ui", "open", "large_clipboard", import_setup, lambda c: C.calendar_import_ics(path=c["p"], calendar=c["cal"]), imported, big=True)
    def twice():
        c = import_setup(); C.calendar_import_ics(path=c["p"], calendar=c["cal"]); c["before"] = in_calendar(c["cal"]); c["snap"] = DB.snapshot(); return c
    K.case("calendar_import_ics", "ui", "open", "already_imported", twice, lambda c: C.calendar_import_ics(path=c["p"], calendar=c["cal"]),
           lambda c, b, a, r, e: {"raised": isinstance(e, C.UIError), "no_duplicates": in_calendar(c["cal"]) == c["before"], "no_window_left": not C._import_windows(C._AS.AXUIElementCreateApplication(int(sh("pgrep -x Calendar").split()[0])))})
    K.case("calendar_import_ics", "ui", "open", "no_calendar", import_setup, lambda c: C.calendar_import_ics(path=c["p"], calendar="No Such Calendar 5151"), lambda c, b, a, r, e: {"raised": isinstance(e, C.NotFound), "nothing_added": in_calendar(c["cal"]) == c["before"]})
    K.case("calendar_import_ics", "ui", "open", "no_file", lambda: {}, lambda c: C.calendar_import_ics(path=f"{ICS}/none.ics", calendar="Calendar"), lambda c, b, a, r, e: {"raised": isinstance(e, C.NotFound)})
    def empty():
        p = f"{ICS}/empty {K.word()}.ics"; open(p, "w").write("BEGIN:VCALENDAR\r\nVERSION:2.0\r\nEND:VCALENDAR\r\n"); return {"p": p}
    K.case("calendar_import_ics", "ui", "open", "no_events", empty, lambda c: C.calendar_import_ics(path=c["p"], calendar="Calendar"), lambda c, b, a, r, e: {"raised": isinstance(e, ValueError)})
    K.case("calendar_import_ics", "ui", "open", "bad_type", lambda: {}, lambda c: C.calendar_import_ics(path=f"{ICS}/x.txt", calendar="Calendar"), lambda c, b, a, r, e: {"raised": isinstance(e, ValueError)})
    K.case("calendar_import_ics", "background", "open", "not_supported", lambda: {}, lambda c: C.calendar_import_ics(path=f"{ICS}/x.ics", calendar="Calendar", mode="background"), lambda c, b, a, r, e: {"raised": isinstance(e, C.NotSupported)})
# Rename (overnight): read back from Calendar.sqlitedb: the old title gone, the new one there, and the calendar's events kept.
def titles():
    import sqlite3
    d = sqlite3.connect(f"file:{CAL_DB}?mode=ro", uri=True)
    try: return sorted(t for (t,) in d.execute("select title from Calendar"))
    finally: d.close()
def rn_setup():
    c = import_setup(2); C.calendar_import_ics(path=c["p"], calendar=c["cal"]); time.sleep(1)
    c["events"] = in_calendar(c["cal"]); c["to"] = f"{K.V.special()} {K.V.rng.randint(100, 9999)}"; c["titles"] = titles(); return c
SELF_MADE = {"Scheduled Reminders"}  # Calendar adds this one by itself when it starts
def renamed(c, b, a, r, e):
    now = [t for t in titles() if t not in SELF_MADE]; want = sorted([t for t in c["titles"] if t != c["cal"] and t not in SELF_MADE] + [c["to"]])
    return {"no_error": e is None, "titles": now == want, "events_kept": [t for t, _ in in_calendar(c["to"])] == [t for t, _ in c["events"]],
            "return": bool(r) and r["name"] == c["to"] and r["was"] == c["cal"]}
def rename_group():
    for st in ("closed", "open", "other_app", "hidden"):
        # With Calendar quit, the VM can be left with no app in front at all, which a real Mac never has; Finder is brought forward.
        K.case("calendar_rename", "background", st, "two_events", rn_setup, lambda c: C.calendar_rename(name=c["cal"], to=c["to"]), renamed,
               before=(lambda c: (sh("open -a Finder"), time.sleep(1.5))) if st == "closed" else None)
    m, st = "background", "open"
    def taken():
        c = rn_setup(); setup_js("calendar", cal=c["to"]); time.sleep(1); c["titles"] = titles(); return c
    K.case("calendar_rename", m, st, "taken", taken, lambda c: C.calendar_rename(name=c["cal"], to=c["to"]), lambda c, b, a, r, e: {"raised": isinstance(e, C.AlreadyExists), "unchanged": [t for t in titles() if t not in SELF_MADE] == [t for t in c["titles"] if t not in SELF_MADE]})
    K.case("calendar_rename", m, st, "no_calendar", lambda: {"titles": titles()}, lambda c: C.calendar_rename(name="No Such Calendar 8181", to="X 1"), lambda c, b, a, r, e: {"raised": isinstance(e, C.NotFound), "unchanged": [t for t in titles() if t not in SELF_MADE] == [t for t in c["titles"] if t not in SELF_MADE]})
    K.case("calendar_rename", m, st, "empty", lambda: {}, lambda c: C.calendar_rename(name="Calendar", to=" "), lambda c, b, a, r, e: {"raised": isinstance(e, ValueError)})
    K.case("calendar_rename", m, st, "same", lambda: {}, lambda c: C.calendar_rename(name="Calendar", to="Calendar"), lambda c, b, a, r, e: {"raised": isinstance(e, ValueError)})
    K.case("calendar_rename", "ui", st, "not_supported", lambda: {}, lambda c: C.calendar_rename(name="Calendar", to="X 2", mode="ui"), lambda c, b, a, r, e: {"raised": isinstance(e, C.NotSupported)}, clip=False)
    K.case("calendar_rename", m, st, "large_clipboard", rn_setup, lambda c: C.calendar_rename(name=c["cal"], to=c["to"]), renamed, big=True)
def tidy_cal():
    try: osa('on run argv\ntell application "Calendar" to delete (every calendar whose name is (item 1 of argv))\nend run', CAL)
    except RuntimeError: pass
groups = [(s, (lambda s=s: state_cases(s))) for s in ("closed", "open", "other_app", "hidden")] + [("errors", errors), ("large_clipboard", large_clipboard), ("export", export_group), ("large_clipboard_old", large_clipboard_old), ("import", import_group), ("rename", rename_group)]
try: K.run(states, groups)
finally: tidy_cal()
