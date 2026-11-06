# Reminders commands

`reminders.py`: plain Python functions for Apple Reminders, on the local account only: no iCloud, no account, no sign-in.
Python 3.9+, standard library only. Put this folder on `sys.path` (or copy the file next to your program) and
`import reminders`.

```python
import reminders

reminders.list_create(name="Trip")
reminders.reminder_create(title="Book the cab", list="Trip", due="2026-12-01 09:30", priority="high", mode="background")
reminders.reminder_complete(match="Book the cab", list="Trip")
```

**Verified on macOS 15.6.1 only. This doesn't cover macOS 26 or any other version.** On another version, results gain
`"unverified_version": true` and both versions.

## Modes

- `mode="background"`: Reminders' own scripting. Nothing appears on screen. If Reminders isn't running, it starts hidden.
- `mode="ui"`: the change is made on screen. Elements are found by role and name through the macOS Accessibility API and
  pressed, menu items are clicked by name, and text is pasted through the clipboard, which is restored afterwards. The
  reminder is found by exact title through scripting and its list is shown, so the edit lands on that row. It depends on
  English names such as Add Reminder, Edit Details and Show List Info.

**Left out of UI mode: due dates and priority.** Reminders' date field exposes no parts to Accessibility, and pressing
On a Day set nothing in testing, so a due date can't be set on screen safely. `reminder_create` and `reminder_update` raise
`NotSupported` if you pass `due` or `priority` with `mode="ui"`; use `mode="background"`. The read commands
(`reminder_list`, `reminder_search`, `reminder_get`, `list_list`) are background only, like Calendar's.

Also left out: clearing a due date, repeating reminders, subtasks, tags, sections, smart lists, and marking a completed
reminder as not done.

## Start states (UI mode)

Each UI call brings Reminders to the front and closes only its passing UI: a menu, a details popover, a search, or a dialog
with a Cancel button. A New List dialog holding typed text, or a new row holding typed text, is left alone: the call raises
`StateBlocked` and changes nothing. It then works with Reminders closed, launching, hidden or minimized, with another app
in front, another list showing, the sidebar hidden, no window open, and another reminder selected.

**First launch:** on a machine that has never opened Reminders, a UI call presses Continue on the Welcome screen and
"Never Miss a Reminder", and Not Now on "Enable iCloud Syncing?". Continue on "Never Miss a Reminder" makes macOS show its
own notifications prompt. These commands don't answer it and it didn't get in their way; it only decides whether due
reminders notify you.

## Dates

`"YYYY-MM-DD HH:MM"` in local time, or `"YYYY-MM-DD"` for a day without a time. A due time of `00:00` is refused, because it
can't be told apart from a day without a time when read back through scripting.

## Matching and errors

`match` is the exact title; add `list=` when the same title is in more than one list. A completed reminder counts, so a
completed one and an open one with the same title are `Ambiguous`.

| Error | When |
|---|---|
| `NotFound` | no reminder with that title, or no list with that name |
| `Ambiguous` | more than one matches; nothing is changed |
| `AlreadyExists` | `list_create` or `list_rename` with a name that is taken |
| `StateBlocked` | the screen holds typed text, or another app came to the front during a step |
| `UIError` | a named element never appeared within the timeout, or a change wasn't seen in time |
| `NotSupported` | the mode can't do this, or it wasn't verified |
| `ValueError` | an empty title, a bad date or priority, or an unknown field |

## Fields

`fields=` picks from `id`, `title`, `notes`, `list`, `due`, `priority`, `completed`, `completed_date`. The default is all
but `id` and `completed_date`; changes also return `id`.

## Functions

### reminder_create(title, list=None, due=None, notes=None, priority=None, mode="ui") → reminder
Adds it to `list`, or the default list. `due` and `priority` need `mode="background"`.

### reminder_list(list=None, completed=False, limit=100, fields=None, mode="background") → [reminder]
`completed=False` open ones, `True` done ones, `None` both. Newest first.

### reminder_search(query, fields=None, completed=None, mode="background") → [reminder]
Title or notes contain `query`, ignoring case.

### reminder_get(match, list=None, fields=None, mode="background") → reminder

### reminder_update(match, list=None, title=None, due=None, notes=None, priority=None, mode="background") → reminder
Only the values given change. UI mode changes `title` and `notes` only.

### reminder_complete(match, list=None, mode="ui") → reminder

### reminder_delete(match, list=None, mode="ui") → reminder as it was, with `"deleted": true`
UI mode moves focus to the rows first, because with focus in the sidebar Edit › Delete means the whole list. If Reminders
shows any alert, the call cancels it and raises `UIError`.

### reminder_move(match, to_list, list=None, mode="background") → reminder
Moves the reminder to the list `to_list`. Its title, notes, due date and priority stay. Background only: on screen this means
dragging, and these commands use no screen positions.

### reminder_reopen(match, list=None, mode="background") → reminder
Marks a completed reminder as not completed again. `ValueError` if it isn't completed. Flagging isn't offered: Reminders' scripting
ignores writes to a reminder's flag, and there's no Flag menu item.

### list_create(name, mode="ui") → {name, open}

### list_list(mode="background") → [{name, open}]
`open` is the number of open reminders.

### list_rename(name, to, mode="ui") → {name, open}

### list_delete(name, mode="ui") → {name, open, "deleted": true}
Deletes the list and its reminders. In UI mode, Delete is pressed only if Reminders' alert names this list.

## How it was verified

In fresh copies of one VM, with made-up data including emoji, accents, quotes and line breaks. Results were read back from
Reminders' own database, not through scripting or the library, and every other reminder and list was compared before and
after. That nothing changes on NotFound, Ambiguous, AlreadyExists and StateBlocked was read back the same way.

Every case ran on the final code of its commands. The commands added on day 3 sit in their own section at the end of the file and were tested on their own; the code above them is unchanged.

Each UI command that changes something was also run with a very large clipboard (about 3.5 MB, text and other data): the change had to land and the clipboard had to come back exactly, read back with `pbpaste` and separate code.

Two cases failed once and passed when their batches were rerun in fresh VMs on the same code: `reminder_update` in UI mode with a
confirmation alert open (the renamed row didn't appear within 10 s, and the half-done edit made the next 7 UI cases refuse, as they
should), and `reminder_move` started from closed (Reminders came to the front). They may fail now and then.

| Function | Mode | Verified | Cases | Start states |
|---|---|---|---|---|
| `list_create` | background | yes | 14 | a confirmation dialog open, app closed, app hidden, app still launching, minimized, the sidebar hidden, no window open, app open, another app in front, another folder/list/view showing, a popover open, search field with text, another item selected |
| `list_create` | ui | yes | 16 | a confirmation dialog open, app closed, app hidden, app still launching, minimized, the sidebar hidden, no window open, app open, another app in front, another folder/list/view showing, a popover open, search field with text, another item selected, half-typed text in another item |
| `list_delete` | background | yes | 27 | a confirmation dialog open, app closed, app hidden, app still launching, minimized, the sidebar hidden, no window open, app open, another app in front, another folder/list/view showing, a popover open, search field with text, another item selected |
| `list_delete` | ui | yes | 29 | a confirmation dialog open, app closed, app hidden, app still launching, minimized, the sidebar hidden, no window open, app open, another app in front, another folder/list/view showing, a popover open, search field with text, another item selected, half-typed text in another item |
| `list_list` | background | yes | 13 | a confirmation dialog open, app closed, app hidden, app still launching, minimized, the sidebar hidden, no window open, app open, another app in front, another folder/list/view showing, a popover open, search field with text, another item selected |
| `list_rename` | background | yes | 15 | a confirmation dialog open, app closed, app hidden, app still launching, minimized, the sidebar hidden, no window open, app open, another app in front, another folder/list/view showing, a popover open, search field with text, another item selected |
| `list_rename` | ui | yes | 17 | a confirmation dialog open, app closed, app hidden, app still launching, minimized, the sidebar hidden, no window open, app open, another app in front, another folder/list/view showing, a popover open, search field with text, another item selected, half-typed text in another item |
| `reminder_complete` | background | yes | 16 | a confirmation dialog open, app closed, app hidden, app still launching, minimized, the sidebar hidden, no window open, app open, another app in front, another folder/list/view showing, a popover open, search field with text, another item selected |
| `reminder_complete` | ui | yes | 18 | a confirmation dialog open, app closed, app hidden, app still launching, minimized, the sidebar hidden, no window open, app open, another app in front, another folder/list/view showing, a popover open, search field with text, another item selected, half-typed text in another item |
| `reminder_create` | background | yes | 56 | a confirmation dialog open, app closed, app hidden, app still launching, minimized, the sidebar hidden, no window open, app open, another app in front, another folder/list/view showing, a popover open, search field with text, another item selected, half-typed text in another item |
| `reminder_create` | ui | yes | 32 | a confirmation dialog open, app closed, app hidden, app still launching, minimized, the sidebar hidden, no window open, app open, another app in front, another folder/list/view showing, a popover open, search field with text, another item selected, half-typed text in another item |
| `reminder_delete` | background | yes | 28 | a confirmation dialog open, app closed, app hidden, app still launching, minimized, the sidebar hidden, no window open, app open, another app in front, another folder/list/view showing, a popover open, search field with text, another item selected |
| `reminder_delete` | ui | yes | 30 | a confirmation dialog open, app closed, app hidden, app still launching, minimized, the sidebar hidden, no window open, app open, another app in front, another folder/list/view showing, a popover open, search field with text, another item selected, half-typed text in another item |
| `reminder_get` | background | yes | 13 | a confirmation dialog open, app closed, app hidden, app still launching, minimized, the sidebar hidden, no window open, app open, another app in front, another folder/list/view showing, a popover open, search field with text, another item selected |
| `reminder_list` | background | yes | 26 | a confirmation dialog open, app closed, app hidden, app still launching, minimized, the sidebar hidden, no window open, app open, another app in front, another folder/list/view showing, a popover open, search field with text, another item selected |
| `reminder_move` | background | yes | 12 | app closed, app hidden, minimized, app open, another app in front, another folder/list/view showing, search field with text, another item selected |
| `reminder_reopen` | background | yes | 11 | app closed, app hidden, app open, another app in front |
| `reminder_search` | background | yes | 13 | a confirmation dialog open, app closed, app hidden, app still launching, minimized, the sidebar hidden, no window open, app open, another app in front, another folder/list/view showing, a popover open, search field with text, another item selected |
| `reminder_update` | background | yes | 28 | a confirmation dialog open, app closed, app hidden, app still launching, minimized, the sidebar hidden, no window open, app open, another app in front, another folder/list/view showing, a popover open, search field with text, another item selected |
| `reminder_update` | ui | yes | 18 | a confirmation dialog open, app closed, app hidden, app still launching, minimized, the sidebar hidden, no window open, app open, another app in front, another folder/list/view showing, a popover open, search field with text, another item selected, half-typed text in another item |

Verified on macOS 15.6.1 (24G90), reminders 7.0 (3740), 2026-11-06, in fresh VM clones.

## Permissions

UI mode needs **Accessibility**, and **Automation** for System Events and Reminders. Background mode needs **Automation**
for Reminders.
