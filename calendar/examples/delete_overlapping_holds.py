# Request: list everything on 18 Nov and delete the holds that overlap the 3 pm meeting.
import datetime
import calendar_app as calendar

day = "2026-11-18"
events = calendar.event_list(from_date=day, to_date=day, fields="title,start,end,all_day,calendar")
for event in events:
    print(event["start"], "-", event["end"], event["title"], f"({event['calendar']})")

meetings = [e for e in events if not e["all_day"] and e["start"] == f"{day} 15:00" and "meeting" in e["title"].lower()]
if meetings:
    meeting_start = datetime.datetime.strptime(meetings[0]["start"], "%Y-%m-%d %H:%M")
    meeting_end = datetime.datetime.strptime(meetings[0]["end"], "%Y-%m-%d %H:%M")
    for event in events:
        if event["all_day"] or not event["title"].lower().startswith("hold"):
            continue
        start = datetime.datetime.strptime(event["start"], "%Y-%m-%d %H:%M")
        end = datetime.datetime.strptime(event["end"], "%Y-%m-%d %H:%M")
        if start < meeting_end and end > meeting_start:
            calendar.event_delete(match=event["title"], date=day, calendar=event["calendar"])
