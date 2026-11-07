# Reusable Commands

Plain Python functions for macOS apps, for an agent that writes a short program to do a task.

One folder per app, one Python file per app. Python 3.9 or later, standard library only: no package, no
install, no model, no keys.

| App | Folder | Import |
|---|---|---|
| Notes | [`notes/`](notes/) | `import notes` |
| Calendar | [`calendar/`](calendar/) | `import calendar_app as calendar` |
| Gmail | [`gmail/`](gmail/) | `import gmail` |
| Finder | [`finder/`](finder/) | `import finder` |
| Safari | [`safari/`](safari/) | `import safari` |
| Google Chrome | [`chrome/`](chrome/) | `import chrome` |
| Reminders | [`reminders/`](reminders/) | `import reminders` |
| Contacts | [`contacts/`](contacts/) | `import contacts` |
| TextEdit | [`textedit/`](textedit/) | `import textedit` |
| Preview | [`preview/`](preview/) | `import preview` |
| Keka | [`keka/`](keka/) | `import keka` |
| Obsidian | [`obsidian/`](obsidian/) | `import obsidian` |
| Automator | [`automator/`](automator/) | `import automator` |
| VS Code | [`vscode/`](vscode/) | `import vscode` |
| Xcode | [`xcode/`](xcode/) | `import xcode` |
| OBS Studio | [`obs/`](obs/) | `import obs` |
| Anaconda Navigator | [`anaconda/`](anaconda/) | `import anaconda` |
| LibreOffice Calc | [`libreoffice/`](libreoffice/) | `import calc` |
| System Settings | [`settings/`](settings/) | `import system_settings` |
| Shortcuts | [`shortcuts/`](shortcuts/) | `import shortcuts` |

An agent writes a short program with keyword arguments, like this:

```python
import notes
import calendar_app as calendar

found = notes.note_search(query="Goa trip", limit=20, fields="title,folder,modified_date")
if found:
    notes.note_append(match=found[0]["title"], folder=found[0]["folder"], text="Book the cab")
calendar.event_create(title="Dentist", start="2026-11-18 15:15", end="2026-11-18 16:00", location="Room 4")
```

Put the app folders on `sys.path` (or copy the files next to the program). `calendar_app.py` is named so that it
doesn't clash with Python's own `calendar` module, so import it `as calendar`.

## Catalog

`notes/catalog.json`, `calendar/catalog.json`, `gmail/catalog.json`, `finder/catalog.json`, `safari/catalog.json`, `chrome/catalog.json`, `reminders/catalog.json`, `contacts/catalog.json`, `textedit/catalog.json`, `preview/catalog.json`, `keka/catalog.json`, `obsidian/catalog.json`, `automator/catalog.json`, `vscode/catalog.json`, `xcode/catalog.json`, `obs/catalog.json`, `anaconda/catalog.json`, `libreoffice/catalog.json`, `settings/catalog.json` and `shortcuts/catalog.json` describe every verified command, so an agent can find and call
one without reading the code. Each file gives the app, its import line, the versions it was verified on, and one
entry per command: description, arguments, verified and default modes, example requests, effects, whether it is
destructive, precondition, postcondition, returned fields and errors.

To use them, match the request against `description` and `example_requests`, check `precondition`, then write a
program with the `import` line and the `args`, using only a mode listed under `modes`. Results can also carry the
version keys described under [Versions](#versions).

- `idempotent` (in `effects`): a repeat with the same arguments changes nothing more, though it may raise an error
  such as `NotFound`.
- `destructive`: true if the effect can't be easily undone. These commands also have `confirm`, the question to ask
  the user first, with roles like `<title>` to fill in.
- `known_gaps` (optional): behaviours that are untested or not directly confirmed. Read them before calling the
  command.

On `NotFound`, report it or ask; don't create a replacement unless told to.

## Two modes, one interface

Every function takes `mode=` and returns the same value in both modes:

- **`mode="ui"`**: the change is made on screen, like a person would make it. System Events clicks buttons,
  menu items, rows and fields that it finds **by name and role**, never by screen position, and text is pasted
  through the clipboard. The clipboard is saved first and restored afterwards, so emoji, accents, quotes and line
  breaks arrive exactly. The item to act on is found by exact title through the app's own scripting, then shown,
  so the edit lands on that item only.
- **`mode="background"`**: the app's own scripting (AppleScript/JXA) is used and nothing appears on screen. A
  closed app is started hidden.

Functions that change something default to `ui`; functions that only read default to `background`. A mode that
wasn't verified raises `NotSupported`, and the message gives the reason.

## State independence (UI mode)

Before acting, a UI call brings the app to the front and clears away only the app's own transient UI: an open
menu, a popover, a search, or a confirmation with a Cancel button and no typed text. It works from the app
closed, launching, hidden or minimized, from another app in front, from another folder, list or view, and with
another item selected or half-typed text elsewhere. That typed text is kept.

If something on screen would be lost by clearing it, such as a dialog with typed text, the call raises
`StateBlocked` and changes nothing. It types only into fields it opened or found by name.

## Matching and errors

`match` is an exact title or name, plus a date (Calendar) where needed. If nothing
matches, the call raises `NotFound`. If more than one item matches, it raises `Ambiguous` and changes nothing. A
call never acts on the wrong item.

Results are dicts, or lists of dicts. `fields=` picks the keys, and dates are `YYYY-MM-DD HH:MM` in local time.

## Versions

Each file starts with `VERIFIED = {...}`: for each function and mode, the macOS and app versions and builds it
was verified on. Every call reads the running versions. If they differ, the call still runs, but its result
gains `"unverified_version": true` with both versions, so callers know.

## Permissions

- **UI mode**: **Accessibility** and **Automation** (System Events, and the app) for the program that runs
  Python.
- **Background mode**: **Automation** for the app.

macOS asks the first time. Answer the prompt once, then the calls run without prompts.

## How they were verified

Each function and mode was run in fresh macOS VM clones. In each case:

1. The start state and distractors were set up with plain scripting, never the function under test. The
   distractors included similar names, the same name elsewhere, and other items.
2. The function was called with new made-up values: emoji, accents, quotes and line breaks among them, and,
   for Calendar, times across midnight and month ends.
3. The result was read back from the app's **own database** (NoteStore.sqlite, Calendar.sqlitedb),
   not through the same path, and every field was checked.
4. The distractors were checked unchanged, and the return value checked against the stored data. In UI mode the
   screen had to change and no dialog could be left open; in background mode nothing came to the front.

NotFound, Ambiguous and StateBlocked were checked to change nothing. Only function+modes that passed every case
are enabled. Each folder's README lists the cases and start states, and what was left out and why.

## Verified

Each app's catalog gives the versions it was verified on. **Finder, Safari, Chrome, Reminders, Contacts, TextEdit, Preview, Keka and Obsidian were verified on macOS 15.6.1 only**, not macOS 26. Notes and Calendar were verified on macOS 26.6.2, except Notes' `note_attach_image` and Calendar's `event_details`, `event_set_repeat` and `event_add_alert`, which were verified on macOS 15.6.1 only. **Preview, Keka and Obsidian are UI mode only.** **Safari and Chrome are UI mode only**, including for reads, and were verified against a local test server only, not real websites.

**Notes** ([README](notes/README.md)):

| Function | Background | UI |
|---|---|---|
| `checklist_create` | — | verified |
| `folder_create` | verified | verified |
| `folder_delete` | — | verified |
| `folder_list` | verified | — |
| `folder_rename` | — | verified |
| `note_append` | verified | verified |
| `note_attach_image` | verified | — |
| `note_create` | verified | verified |
| `note_delete` | — | verified |
| `note_get` | verified | — |
| `note_list` | verified | — |
| `note_move` | verified | verified |
| `note_pin` | — | verified |
| `note_rename` | — | verified |
| `note_replace_body` | verified | verified |
| `note_search` | verified | — |

**Calendar** ([README](calendar/README.md)):

| Function | Background | UI |
|---|---|---|
| `calendar_create` | verified | verified |
| `calendar_delete` | verified | verified |
| `calendar_export_ics` | — | verified |
| `calendar_import_ics` | — | verified |
| `calendar_list` | verified | — |
| `calendar_rename` | verified | — |
| `event_add_alert` | verified | — |
| `event_create` | verified | — |
| `event_delete` | verified | verified |
| `event_details` | verified | — |
| `event_get` | verified | — |
| `event_list` | verified | — |
| `event_search` | verified | — |
| `event_set_repeat` | verified | — |
| `event_update` | verified | — |

**Gmail** ([README](gmail/README.md)):

| Function | Background | UI |
|---|---|---|
| `draft_create` | — | verified |
| `message_archive` | — | verified |
| `message_list` | — | verified |
| `message_mark_read` | — | verified |
| `message_reply` | — | verified |
| `message_search` | — | verified |
| `message_send` | — | verified |
| `message_star` | — | verified |
| `message_trash` | — | verified |

**Finder** ([README](finder/README.md)):

| Function | Background | UI |
|---|---|---|
| `file_add_tag` | — | verified |
| `file_compress` | — | verified |
| `file_copy` | verified | verified |
| `file_duplicate` | — | verified |
| `file_extract` | — | verified |
| `file_find` | verified | — |
| `file_info` | verified | — |
| `file_list` | verified | — |
| `file_make_alias` | — | verified |
| `file_move` | verified | verified |
| `file_open_with` | — | verified |
| `file_put_back` | — | verified |
| `file_rename` | verified | verified |
| `file_reveal` | — | verified |
| `file_set_locked` | verified | verified |
| `file_trash` | verified | verified |
| `folder_create` | verified | verified |
| `folder_new_with_selection` | — | verified |
| `folder_open` | — | verified |

**Safari** ([README](safari/README.md)):

| Function | Background | UI |
|---|---|---|
| `link_click` | — | verified |
| `page_add_bookmark` | — | verified |
| `page_add_to_reading_list` | — | verified |
| `page_back` | — | verified |
| `page_forward` | — | verified |
| `page_go` | — | verified |
| `page_info` | — | verified |
| `page_links` | — | verified |
| `page_reload` | — | verified |
| `page_save` | — | verified |
| `page_save_pdf` | — | verified |
| `page_text` | — | verified |
| `tab_activate` | — | verified |
| `tab_close` | — | verified |
| `tab_list` | — | verified |
| `tab_open` | — | verified |

**Google Chrome** ([README](chrome/README.md)):

| Function | Background | UI |
|---|---|---|
| `link_click` | — | verified |
| `page_add_bookmark` | — | verified |
| `page_back` | — | verified |
| `page_forward` | — | verified |
| `page_go` | — | verified |
| `page_info` | — | verified |
| `page_links` | — | verified |
| `page_reload` | — | verified |
| `page_save` | — | verified |
| `page_text` | — | verified |
| `tab_activate` | — | verified |
| `tab_close` | — | verified |
| `tab_list` | — | verified |
| `tab_open` | — | verified |

**Reminders** ([README](reminders/README.md)):

| Function | Background | UI |
|---|---|---|
| `list_create` | verified | verified |
| `list_delete` | verified | verified |
| `list_list` | verified | — |
| `list_rename` | verified | verified |
| `reminder_complete` | verified | verified |
| `reminder_create` | verified | verified |
| `reminder_delete` | verified | verified |
| `reminder_get` | verified | — |
| `reminder_list` | verified | — |
| `reminder_move` | verified | — |
| `reminder_reopen` | verified | — |
| `reminder_search` | verified | — |
| `reminder_update` | verified | verified |

**Contacts** ([README](contacts/README.md)):

| Function | Background | UI |
|---|---|---|
| `contact_add_address` | verified | — |
| `contact_add_email` | verified | — |
| `contact_add_phone` | verified | — |
| `contact_add_url` | verified | — |
| `contact_create` | verified | verified |
| `contact_delete` | verified | verified |
| `contact_details` | verified | — |
| `contact_export_vcard` | verified | — |
| `contact_get` | verified | — |
| `contact_import_vcard` | — | verified |
| `contact_list` | verified | — |
| `contact_merge` | — | verified |
| `contact_remove_email` | verified | — |
| `contact_remove_phone` | verified | — |
| `contact_search` | verified | — |
| `contact_set_birthday` | verified | — |
| `contact_set_job_title` | verified | — |
| `contact_set_phone` | verified | — |
| `contact_update` | verified | verified |
| `group_add` | verified | — |
| `group_create` | verified | verified |
| `group_delete` | verified | verified |
| `group_export_vcard` | verified | — |
| `group_list` | verified | — |
| `group_remove` | verified | — |
| `group_rename` | verified | verified |

**TextEdit** ([README](textedit/README.md)):

| Function | Background | UI |
|---|---|---|
| `document_append` | verified | verified |
| `document_close` | verified | verified |
| `document_convert` | — | verified |
| `document_copy_to_new` | verified | verified |
| `document_create` | verified | verified |
| `document_export_pdf` | — | verified |
| `document_list` | verified | verified |
| `document_open` | verified | verified |
| `document_read` | verified | verified |
| `document_replace_text` | verified | verified |
| `document_save` | verified | verified |
| `document_save_as` | verified | verified |

**Preview** ([README](preview/README.md)):

| Function | Background | UI |
|---|---|---|
| `document_close` | — | verified |
| `document_export` | — | verified |
| `document_list` | — | verified |
| `document_open` | — | verified |
| `image_adjust` | — | verified |
| `image_crop` | — | verified |
| `image_flip` | — | verified |
| `image_resize` | — | verified |
| `image_rotate` | — | verified |
| `pdf_append_file` | — | verified |
| `pdf_delete_page` | — | verified |
| `pdf_insert_blank_page` | — | verified |
| `pdf_move_page` | — | verified |
| `pdf_rotate_page` | — | verified |

**Keka** ([README](keka/README.md)):

| Function | Background | UI |
|---|---|---|
| `archive_create` | — | verified |
| `archive_extract` | — | verified |
| `archive_format` | — | verified |
| `archive_set_format` | — | verified |

**Obsidian** ([README](obsidian/README.md)):

| Function | Background | UI |
|---|---|---|
| `note_create` | — | verified |
| `note_open` | — | verified |
| `plugin_install` | — | verified |
| `vault_create` | — | verified |
| `vault_list` | — | verified |

**Automator** ([README](automator/README.md)):

| Function | Background | UI |
|---|---|---|
| `action_add_items` | — | verified |
| `action_set_filter` | — | verified |
| `action_set_folder` | — | verified |
| `action_set_option` | — | verified |
| `workflow_actions` | — | verified |
| `workflow_add_action` | — | verified |
| `workflow_new` | — | verified |
| `workflow_open` | — | verified |
| `workflow_run` | — | verified |
| `workflow_save` | — | verified |

**VS Code** ([README](vscode/README.md)):

| Function | Background | UI |
|---|---|---|
| `extension_install` | — | verified |
| `file_new` | — | verified |
| `file_open` | — | verified |
| `folder_open` | — | verified |

**Xcode** ([README](xcode/README.md)):

| Function | Background | UI |
|---|---|---|
| `project_build` | — | verified |
| `project_clean` | — | verified |
| `project_new` | — | verified |
| `project_open` | — | verified |

**OBS Studio** ([README](obs/README.md)):

| Function | Background | UI |
|---|---|---|
| `recording_start` | — | verified |
| `recording_stop` | — | verified |
| `scene_add` | — | verified |
| `source_add` | — | verified |

**Anaconda Navigator** ([README](anaconda/README.md)):

| Function | Background | UI |
|---|---|---|
| `environment_remove` | — | verified |

**LibreOffice Calc** ([README](libreoffice/README.md)):

| Function | Background | UI |
|---|---|---|
| `csv_convert` | — | verified |
| `csv_sort` | — | verified |
| `spreadsheet_to_csv` | — | verified |

**System Settings** ([README](settings/README.md)):

| Function | Background | UI |
|---|---|---|
| `appearance_set` | — | verified |
| `dock_set` | — | verified |
| `login_item_add` | — | verified |
| `login_item_list` | — | verified |
| `login_item_remove` | — | verified |
| `wallpaper_list` | — | verified |
| `wallpaper_set` | — | verified |

**Shortcuts** ([README](shortcuts/README.md)):

| Function | Background | UI |
|---|---|---|
| `folder_create` | verified | — |
| `shortcut_delete` | — | verified |
| `shortcut_list` | verified | — |
| `shortcut_move` | verified | — |
| `shortcut_run` | verified | — |
