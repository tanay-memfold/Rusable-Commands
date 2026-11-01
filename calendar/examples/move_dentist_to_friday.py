# Request: move my dentist appointment next week to the same time on Friday.
import datetime
import calendar_app as calendar

today = datetime.date.today()
next_monday = today + datetime.timedelta(days=7 - today.weekday())
next_sunday = next_monday + datetime.timedelta(days=6)
friday = next_monday + datetime.timedelta(days=4)

found = calendar.event_search(query="dentist", from_date=str(next_monday), to_date=str(next_sunday),
                              fields="title,start,end")
if len(found) == 1:
    dentist = found[0]
    start = datetime.datetime.strptime(dentist["start"], "%Y-%m-%d %H:%M")
    end = datetime.datetime.strptime(dentist["end"], "%Y-%m-%d %H:%M")
    new_start = datetime.datetime.combine(friday, start.time())
    calendar.event_update(match=dentist["title"], date=dentist["start"][:10],
                          start=new_start.strftime("%Y-%m-%d %H:%M"),
                          end=(new_start + (end - start)).strftime("%Y-%m-%d %H:%M"))
