"""Read-only view of Calendar.sqlitedb: every event's title, local start/end, all-day, location, notes and calendar,
and every calendar's title. Never writes."""
import datetime
import os
import sqlite3
from zoneinfo import ZoneInfo

PATH = os.path.expanduser("~/Library/Group Containers/group.com.apple.calendar/Calendar.sqlitedb")
EPOCH = datetime.datetime(2001, 1, 1, tzinfo=datetime.timezone.utc)
NAMES = {"DEFAULT_CALENDAR_NAME": "Calendar", "DEFAULT_TASK_CALENDAR_NAME": "Reminders"}


def _local(seconds, zone):
    moment = EPOCH + datetime.timedelta(seconds=seconds)
    if zone in (None, "_float"):
        return moment.replace(tzinfo=None)
    return moment.astimezone(ZoneInfo(zone)).astimezone().replace(tzinfo=None)


def snapshot() -> dict:
    db = sqlite3.connect(f"file:{PATH}?mode=ro", uri=True)
    try:
        calendars = {pk: NAMES.get(title, title) for pk, title in db.execute("select ROWID, title from Calendar")}
        events = {}
        for pk, summary, start, start_tz, end, end_tz, all_day, cal, location, notes, uid in db.execute(
                "select i.ROWID, i.summary, i.start_date, i.start_tz, i.end_date, i.end_tz, i.all_day, i.calendar_id, "
                "l.title, i.description, i.unique_identifier from CalendarItem i "
                "left join Location l on l.ROWID = i.location_id where i.entity_type = 2 or i.entity_type is null"):
            first, last = _local(start, start_tz), _local(end, end_tz)
            if all_day:
                shown = (first.strftime("%Y-%m-%d"), last.strftime("%Y-%m-%d"))
            else:
                shown = (first.strftime("%Y-%m-%d %H:%M"), last.strftime("%Y-%m-%d %H:%M"))
            events[pk] = {"title": summary, "start": shown[0], "end": shown[1], "all_day": bool(all_day),
                          "location": location or "", "notes": notes or "", "calendar": calendars.get(cal),
                          "uid": uid}
        return {"events": events, "calendars": calendars}
    finally:
        db.close()


def titled(snap: dict, title: str) -> list:
    return [e for e in snap["events"].values() if e["title"] == title]


def calendar_names(snap: dict) -> list:
    return sorted(snap["calendars"].values())
