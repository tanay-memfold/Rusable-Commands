"""Read-only view of Calendar.sqlitedb for repeats and alerts, by event uid. Never writes."""
import os, sqlite3
PATH = os.path.expanduser("~/Library/Group Containers/group.com.apple.calendar/Calendar.sqlitedb")
FREQ = {1: "DAILY", 2: "WEEKLY", 3: "MONTHLY", 4: "YEARLY"}
def _db(): return sqlite3.connect(f"file:{PATH}?mode=ro", uri=True)
def tables():
    with _db() as db: return {t: [c[1] for c in db.execute(f"pragma table_info({t})")] for (t,) in db.execute("select name from sqlite_master where type='table'")}
def item(title):
    """By title: the test's titles are unique, and Calendar's scripting uid isn't the database's unique_identifier."""
    with _db() as db:
        r = db.execute("select ROWID, summary from CalendarItem where summary = ?", (title,)).fetchall()
        return r[0] if len(r) == 1 else None
def repeat(title):
    """(FREQ, interval, count, end_date or None, specifier) or None."""
    found = item(title)
    if not found: return "missing"
    with _db() as db:
        rows = db.execute("select frequency, interval, count, end_date, specifier from Recurrence where owner_id = ?", (found[0],)).fetchall()
    if not rows: return None
    f, i, c, e, s = rows[0]
    return {"freq": FREQ.get(f, f), "interval": i, "count": c or None, "until": e, "specifier": s or "", "rows": len(rows)}
def alerts(title):
    """Minutes before the start, from each alarm's trigger interval. Calendar's own default alert is left out."""
    found = item(title)
    if not found: return "missing"
    with _db() as db:
        return sorted(-round(t / 60) for (t,) in db.execute("select trigger_interval from Alarm where calendaritem_owner_id = ? and default_alarm = 0", (found[0],)))
def snapshot():
    """Everything but these two tables, to see nothing else changed: events by uid with their basic fields."""
    with _db() as db:
        return {k: (s, st, en) for k, s, st, en in db.execute("select ROWID, summary, start_date, end_date from CalendarItem")}
def repeat_rows(title):
    """Repeat rows of every event with this title."""
    with _db() as db:
        return db.execute("select count(*) from Recurrence r join CalendarItem i on i.ROWID = r.owner_id where i.summary = ?", (title,)).fetchone()[0]
