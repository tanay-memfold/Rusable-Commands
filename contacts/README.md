# Contacts commands

`contacts.py`: plain Python functions for Apple Contacts, for the cards on this Mac. Python 3.9+, standard library only. Put
this folder on `sys.path` (or copy the file next to your program) and `import contacts`.

```python
import contacts

contacts.contact_create(first="Sam", last="Rao", company="Quartz & Co", email="sam@example.com", phone="+1 555 0100")
contacts.group_create(name="Team")
contacts.group_add(match="Sam Rao", group="Team")
```

**Verified on macOS 15.6.1 only, with no account signed in to Contacts. This doesn't cover macOS 26 or any other version.** On
another version, results gain `"unverified_version": true` and both versions.

## Modes

- `mode="background"`: Contacts' own scripting. Nothing appears on screen. If Contacts isn't running, it starts hidden.
- `mode="ui"`: the change is made on screen. Elements are found by role and name through the macOS Accessibility API and pressed,
  menu items are clicked by name, and text is pasted through the clipboard, which is restored afterwards. The card is found by
  exact name through scripting and its row is selected. It depends on English names such as New Card, Edit and Done.

The read commands (`contact_list`, `contact_search`, `contact_get`, `group_list`) are background only.

**Left out of UI mode: `group_add` and `group_remove`.** Adding to a list on screen means dragging a card, and these commands use no
screen coordinates.

Also left out: photos, addresses, birthdays, more than one email or phone at a time, smart lists, import and export.

## Start states (UI mode)

Each UI call brings Contacts to the front and closes only its passing UI: a menu, a search, or a dialog with a Cancel button and no
text. If a card or a list name is being edited, or a dialog holds typed text, the call raises `StateBlocked` and changes nothing. It
works with Contacts closed, launching, hidden or minimized, with another app in front, another list showing, another card selected,
and no window open.

## Matching and errors

`match` is the exact name as Contacts shows it: first and last name, or the company for a card with neither. Two cards with the same
name are `Ambiguous`, and there's no way to pick between them yet.

| Error | When |
|---|---|
| `NotFound` | no card or list has that name |
| `Ambiguous` | more than one matches; nothing is changed |
| `AlreadyExists` | `group_create` or `group_rename` with a name that is taken |
| `StateBlocked` | a card or list name is being edited, a dialog holds typed text, or another app came to the front during a step |
| `UIError` | a named element never appeared within the timeout, or a change wasn't seen in time |
| `NotSupported` | the mode can't do this, or it wasn't verified |
| `ValueError` | no name or company, a value with a line break where one isn't allowed, or an unknown field |

## Fields

`id`, `name`, `first`, `last`, `company`, `emails`, `phones`, `note`, `groups`. The default is all but `id`; changes also return `id`.
Contacts may show a phone number formatted differently from how it was typed.

## Functions

### contact_create(first=None, last=None, company=None, email=None, phone=None, note=None, mode="ui") → contact
It needs a first name, last name or company.

### contact_list(group=None, limit=100, fields=None, mode="background") → [contact]

### contact_search(query, limit=100, fields=None, mode="background") → [contact]
Name, company, email, phone or note contain `query`, ignoring case.

### contact_get(match, fields=None, mode="background") → contact

### contact_update(match, first=None, last=None, company=None, email=None, phone=None, note=None, mode="ui") → contact
Only the values given change. `email` and `phone` replace the first one, or add one if there are none.

### contact_delete(match, mode="ui") → contact as it was, with `"deleted": true`
In UI mode, Delete is pressed only if Contacts' alert names this card.

### group_create(name, mode="ui") → {name, count}
What Contacts now calls a list; its scripting calls it a group.

### group_list(mode="background") → [{name, count}]

### group_rename(name, to, mode="ui") → {name, count}

### group_delete(name, mode="ui") → {name, count, "deleted": true}
The cards stay in Contacts.

### group_add(match, group, mode="background") → contact

### group_remove(match, group, mode="background") → contact
The card stays in Contacts.

### contact_details(match, mode="background") → {id, name, job_title, phones, emails}
The job title, and each phone number and email as `{label, value}`, in the order Contacts keeps them.

### contact_set_job_title(match, job_title, mode="background") → details
Sets the job title; empty clears it.

### contact_add_phone(match, number, label="mobile", mode="background") → details
Adds a number under a label such as `mobile`, `home` or `work`. Numbers already there stay, so a card can have separate home and
mobile numbers, or several of either.

### contact_set_phone(match, label, number, mode="background") → details
Changes the number under that label (every one, if several share it). `NotFound` if the card has none with the label.

### contact_remove_phone(match, label, mode="background") → details
Removes the numbers under that label; the others stay. `NotFound` if there are none.

### contact_add_email(match, address, label="work", mode="background") → details
### contact_remove_email(match, label, mode="background") → details
The same for email addresses.

### contact_set_birthday(match, date, mode="background") → {id, name, birthday}
Sets the birthday, `YYYY-MM-DD`.

### contact_add_address(match, street, city, zip=None, country=None, label="home", mode="background") → {id, name, addresses}
Adds a postal address under a label; addresses already there stay. Street line breaks are kept.

### contact_export_vcard(path, match=None, mode="background") → {path, count}
Writes one card, or every card with no `match`, to a new `.vcf` file, as Contacts makes the vCards. Nothing is overwritten.

### contact_merge(match, mode="ui") → contact
Selects every card with exactly that name and uses **Card > Merge Selected Cards**. Their numbers and emails end up on one card;
which name, company and note win is Contacts' own choice. UI only: Contacts' scripting has no merge. `ValueError` if only one card
has the name.

### contact_add_url(match, url, label="homepage", mode="background") → {id, name, urls}
Adds a web address (`http` or `https`) under a label to the card named `match`, through Contacts' scripting; addresses already
there stay. `AlreadyExists` if the card already has that address. Added overnight at the end of the file and tested on its own
(read back from Contacts' database).

### group_export_vcard(name, path, mode="background") → {name, path, count}
Writes every card in the list (group) named `name` to a new `.vcf` file, as Contacts makes the vCards, through Contacts' scripting.
Nothing is overwritten; the number of cards must match the list's. Added overnight at the end of the file and tested on its own (the
file's cards compared with the list's members in Contacts' database).

### contact_import_vcard(path, mode="ui") → {path, count}
Adds the cards in a `.vcf` file as new cards. The file is opened in Contacts, as a double-click would. **Add** is pressed only when
Contacts' question is exactly "Are you sure you want to add N cards?" with N the number of cards in the file. When some cards match
cards you have, Contacts says they "will be updated" instead. That is cancelled and `AlreadyExists` raised, so **no existing card is
changed**. UI only. In testing, each import also updated the modification time of the cards from the previous import, without changing
their content. Added overnight at the end of the file and tested on its own (cards read back from Contacts'
database, and every other card's name, company, emails and phones compared before and after).

## How it was verified

In fresh copies of one VM with no contacts in it to begin with, using made-up data including emoji, accents, quotes and line breaks.
Results were read back from Contacts' own database, not through scripting or the library, and every other card and list was compared
before and after.

Every case ran on the final code of its commands. The commands added on day 3 sit in their own section at the end of the file and were tested on their own; the code above them is unchanged.

Each UI command that changes something was also run with a very large clipboard (about 3.5 MB, text and other data): the change had to land and the clipboard had to come back exactly, read back with `pbpaste` and separate code.

| Function | Mode | Verified | Cases | Start states |
|---|---|---|---|---|
| `contact_add_address` | background | yes | 10 | app closed, app hidden, app open, another app in front |
| `contact_add_email` | background | yes | 5 | app closed, app hidden, another app in front, another folder/list/view showing |
| `contact_add_phone` | background | yes | 5 | app closed, app hidden, another app in front, another folder/list/view showing |
| `contact_add_url` | background | yes | 14 | app closed, app hidden, app open, another app in front |
| `contact_create` | background | yes | 21 | app closed, app hidden, app still launching, minimized, no window open, app open, another app in front, another folder/list/view showing, search field with text, another item selected |
| `contact_create` | ui | yes | 23 | app closed, app hidden, app still launching, minimized, no window open, app open, another app in front, another folder/list/view showing, search field with text, another item selected, half-typed text in another item |
| `contact_delete` | background | yes | 12 | app closed, app hidden, app still launching, minimized, no window open, app open, another app in front, another folder/list/view showing, search field with text, another item selected |
| `contact_delete` | ui | yes | 14 | app closed, app hidden, app still launching, minimized, no window open, app open, another app in front, another folder/list/view showing, search field with text, another item selected, half-typed text in another item |
| `contact_details` | background | yes | 5 | app closed, app hidden, another app in front, another folder/list/view showing |
| `contact_export_vcard` | background | yes | 11 | app closed, app hidden, another app in front, another folder/list/view showing |
| `contact_get` | background | yes | 12 | app closed, app hidden, app still launching, minimized, no window open, app open, another app in front, another folder/list/view showing, search field with text, another item selected |
| `contact_import_vcard` | ui | yes | 11 | app closed, app hidden, app open, another app in front |
| `contact_list` | background | yes | 20 | app closed, app hidden, app still launching, minimized, no window open, app open, another app in front, another folder/list/view showing, search field with text, another item selected |
| `contact_merge` | ui | yes | 12 | app closed, app hidden, minimized, no window open, another app in front, another folder/list/view showing, search field with text, another item selected |
| `contact_remove_email` | background | yes | 5 | app closed, app hidden, another app in front, another folder/list/view showing |
| `contact_remove_phone` | background | yes | 5 | app closed, app hidden, another app in front, another folder/list/view showing |
| `contact_search` | background | yes | 10 | app closed, app hidden, app still launching, minimized, no window open, app open, another app in front, another folder/list/view showing, search field with text, another item selected |
| `contact_set_birthday` | background | yes | 15 | app closed, app hidden, app open, another app in front |
| `contact_set_job_title` | background | yes | 6 | app closed, app hidden, another app in front, another folder/list/view showing |
| `contact_set_phone` | background | yes | 5 | app closed, app hidden, another app in front, another folder/list/view showing |
| `contact_update` | background | yes | 12 | app closed, app hidden, app still launching, minimized, no window open, app open, another app in front, another folder/list/view showing, search field with text, another item selected |
| `contact_update` | ui | yes | 14 | app closed, app hidden, app still launching, minimized, no window open, app open, another app in front, another folder/list/view showing, search field with text, another item selected, half-typed text in another item |
| `group_add` | background | yes | 12 | app closed, app hidden, app still launching, minimized, no window open, app open, another app in front, another folder/list/view showing, search field with text, another item selected |
| `group_create` | background | yes | 11 | app closed, app hidden, app still launching, minimized, no window open, app open, another app in front, another folder/list/view showing, search field with text, another item selected |
| `group_create` | ui | yes | 13 | app closed, app hidden, app still launching, minimized, no window open, app open, another app in front, another folder/list/view showing, search field with text, another item selected, half-typed text in another item |
| `group_delete` | background | yes | 11 | app closed, app hidden, app still launching, minimized, no window open, app open, another app in front, another folder/list/view showing, search field with text, another item selected |
| `group_delete` | ui | yes | 13 | app closed, app hidden, app still launching, minimized, no window open, app open, another app in front, another folder/list/view showing, search field with text, another item selected, half-typed text in another item |
| `group_export_vcard` | background | yes | 9 | app closed, app hidden, app open, another app in front |
| `group_list` | background | yes | 10 | app closed, app hidden, app still launching, minimized, no window open, app open, another app in front, another folder/list/view showing, search field with text, another item selected |
| `group_remove` | background | yes | 10 | app closed, app hidden, app still launching, minimized, no window open, app open, another app in front, another folder/list/view showing, search field with text, another item selected |
| `group_rename` | background | yes | 12 | app closed, app hidden, app still launching, minimized, no window open, app open, another app in front, another folder/list/view showing, search field with text, another item selected |
| `group_rename` | ui | yes | 14 | app closed, app hidden, app still launching, minimized, no window open, app open, another app in front, another folder/list/view showing, search field with text, another item selected, half-typed text in another item |

Verified on macOS 15.6.1 (24G90), contacts 14.0 (2695.500.71), 2026-11-06, in fresh VM clones.

## Permissions

Both modes need access to Contacts and **Automation** for Contacts. UI mode also needs **Accessibility**, and **Automation** for System
Events.
