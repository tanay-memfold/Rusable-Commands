# Calendar commands

`calendar_app.py`: plain Python functions for Apple Calendar, on the local calendars (On My Mac). Python 3.9+,
standard library only. The file is named so it doesn't clash with Python's own `calendar` module; import it like
this:

```python
import calendar_app as calendar

calendar.event_create(title="Dentist", start="2026-11-18 15:15", end="2026-11-18 16:00", location="Room 4")
```

## Modes

- `mode="background"`: Calendar's own scripting; nothing appears on screen. If Calendar isn't running, it is
  started hidden. Every function has this mode.
- `mode="ui"`: the change is made on screen. System Events selects the event or calendar, then clicks menu items
  and buttons by name. It is verified for `event_delete`, `calendar_create` and `calendar_delete`, and is their
  default. In UI mode the event is found by exact title and day through Calendar's scripting, shown, and checked
  to be the selected event before **Edit › Delete** is chosen.

**Left out of UI mode: `event_create` and `event_update`.** Typing into Calendar's date fields through System
Events wasn't reliable in testing:

- The same keystrokes set the date 12/30/2026 once, and the next time moved the event to the year 12.
- When a new event's title was typed, an autocomplete suggestion replaced it.

An event on the wrong day breaks the rule of never acting on the wrong item, so these two run in background mode
only. They default to background, and asking for `mode="ui"` raises `NotSupported` with this reason.

## Start states (UI mode)

Each UI call brings Calendar to the front first. It clears only Calendar's own transient UI: an open menu, an
event popover, a search, or a confirmation with a Cancel button. A Quick Event popover with typed text is left
alone: the call raises `StateBlocked` and changes nothing. It then works from Calendar closed, launching, hidden
or minimized, from another app in front, from another view or day, and with another event selected.

## Dates

- Timed events: `"YYYY-MM-DD HH:MM"`, local time. Events may cross midnight and month ends.
- All-day events: `"YYYY-MM-DD"` with `all_day=True`. `end` is the last day, inclusive (one day:
  `start == end`).
- Repeating events: only the first occurrence is seen, because Calendar's scripting doesn't expand repeats.

## Matching and errors

`match` is the exact title, and `date` (`YYYY-MM-DD`) the day the event starts. Add `calendar=` when the same
title exists twice that day in different calendars.

| Error | When |
|---|---|
| `NotFound` | no event with that title starts that day, or no such local calendar |
| `Ambiguous` | more than one event matches; nothing is changed |
| `AlreadyExists` | `calendar_create` with a name that is taken |
| `StateBlocked` | the screen holds something the call won't destroy |
| `UIError` | a named element never appeared within the timeout |
| `NotSupported` | the mode can't do this, or wasn't verified (the message gives the reason) |

## Fields

Events are dicts. `fields=` picks from `uid`, `title`, `start`, `end`, `all_day`, `location`, `notes`,
`calendar`. The default is all of them except `uid`; changes also return `uid`.

## Versions

`VERIFIED` at the top of `calendar_app.py` records the macOS and Calendar versions and builds each function and
mode was verified on. If the running versions differ, results gain `"unverified_version": true` and both
versions.

## Functions

### event_create(title, start, end, location=None, calendar=None, all_day=False, notes=None, mode="background") → event
`calendar` defaults to the first local calendar ("Calendar").
```python
calendar.event_create(title="Team offsite", start="2026-11-30", end="2026-12-01", all_day=True, calendar="Work")
```

### event_list(from_date, to_date, limit=50, fields=None, calendar=None, mode="background") → [event]
Events that start between the two days (both included), earliest first.
```python
calendar.event_list(from_date="2026-11-18", to_date="2026-11-18", fields="title,start,end")
```

### event_search(query, from_date, to_date, fields=None, mode="background") → [event]
Events between the days whose title, location or notes contain `query`, ignoring case.

### event_get(match, date, fields=None, calendar=None, mode="background") → event

### event_update(match, date, title=None, start=None, end=None, location=None, notes=None, all_day=None, calendar=None, mode="background") → event
Only the values given change. A new `start` without an `end` keeps the old end, so give both to move an event.
```python
calendar.event_update(match="Dentist", date="2026-11-18", start="2026-11-20 15:15", end="2026-11-20 16:00")
```

### event_delete(match, date, calendar=None, mode="ui") → event as it was, with `"deleted": true`
UI steps: show the event, check that the inspector shows its title, then **Edit** › **Delete**.

### calendar_create(name, mode="ui") → {name}
UI steps: show the calendar list (**View** › **Show Calendar List**), then **File** › **New Calendar** ›
**On My Mac**, paste `name` into the new row's name field, press Return.

### calendar_list(mode="background") → [{name}]
The local calendars that can hold events. Subscribed, birthday and reminder calendars are left out.

### calendar_delete(name, mode="ui") → {name, "deleted": true}
Deletes the calendar and its events.
UI steps: select the calendar's row in the calendar list, then **Edit** › **Delete**, and click **Delete** in the
confirmation.

## Repeats and alerts (added later, macOS 15.6.1 only)

These were verified on macOS 15.6.1 with Calendar 15.0, unlike the commands above (macOS 26.6.2). They use their own script, added
after the code above, which is unchanged. Background mode only.

### event_details(match, date, calendar=None, mode="background") → event, with `repeat` and `alerts`
`repeat` is the RRULE text as Calendar stores it, or `None`. `alerts` is a sorted list of minutes before the start; Calendar's own
default alert isn't listed.

### event_set_repeat(match, date, rule, calendar=None, mode="background") → event, with `repeat`
Makes the event repeat by an iCalendar RRULE, such as `"FREQ=WEEKLY;COUNT=5"` or `"FREQ=WEEKLY;INTERVAL=2;BYDAY=MO,WE"`. Allowed
parts: FREQ (DAILY, WEEKLY, MONTHLY, YEARLY), INTERVAL, COUNT or UNTIL, BYDAY, BYMONTHDAY and BYMONTH. Any repeat it had is replaced.
**Stopping a repeat isn't supported** (`rule=None` raises `NotSupported`): Calendar's scripting kept the repeat when it was cleared.

### event_add_alert(match, date, minutes_before, calendar=None, mode="background") → event, with `alerts`
Adds an on-screen alert `minutes_before` minutes before the start (0 to 40320). `AlreadyExists` if one is already set for that
time. **Removing alerts isn't supported**: every delete of an alert through Calendar's scripting failed.

Left out: exporting a calendar as `.ics`. On a fresh macOS 15.6.1 VM Calendar first shows a What's New screen that leads into
location use, which the tests don't click through, and the Export menu offered only Export Event… and Calendar Archive….

These were read back from Calendar.sqlitedb (its repeat and alarm tables), not through Calendar, and every other event in the
database was compared before and after.

Commands added later, verified separately:

| Function | Mode | Verified | Cases | macOS | App |
|---|---|---|---|---|---|
| `event_add_alert` | background | yes | 23 | 15.6.1 (24G90) | 15.0 (2995.7.1) |
| `event_details` | background | yes | 10 | 15.6.1 (24G90) | 15.0 (2995.7.1) |
| `event_set_repeat` | background | yes | 36 | 15.6.1 (24G90) | 15.0 (2995.7.1) |

## Verification

| Function | Mode | Verified | Cases | Start states |
|---|---|---|---|---|
| `calendar_create` | background | yes | 3 | app closed, app open |
| `calendar_create` | ui | yes | 12 | a confirmation dialog open, app closed, app hidden, app still launching, minimized, another app in front, another folder/list/view showing, a popover open, search field with text, another item selected |
| `calendar_delete` | background | yes | 3 | app closed, app open |
| `calendar_delete` | ui | yes | 11 | a confirmation dialog open, app closed, app hidden, app still launching, minimized, another app in front, another folder/list/view showing, a popover open, search field with text, another item selected |
| `calendar_list` | background | yes | 2 | app closed, app open |
| `event_create` | background | yes | 8 | app closed, app open |
| `event_delete` | background | yes | 4 | app closed, app open |
| `event_delete` | ui | yes | 13 | a confirmation dialog open, app closed, app hidden, app still launching, minimized, another app in front, another folder/list/view showing, a popover open, search field with text, another item selected |
| `event_get` | background | yes | 3 | app closed, app open |
| `event_list` | background | yes | 2 | app closed, app open |
| `event_search` | background | yes | 2 | app closed, app open |
| `event_update` | background | yes | 3 | app closed, app open |

End-to-end programs (run in UI mode from a messy start state, outcome read from the app's database):

- Move a dentist appointment to the same time on Friday: passed.
- Delete overlapping holds: passed.

Verified on macOS 26.6.2 (25G83), calendar 16.0 (3036.4.14), 2026-11-01, in fresh VM clones.

## Permissions

UI mode needs **Accessibility** and **Automation** (System Events and Calendar). Background mode needs
**Automation** for Calendar. The UI calls type nothing but names, so the date-format caveat above doesn't affect
them.
