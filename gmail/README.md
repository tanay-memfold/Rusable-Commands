# Gmail commands

`gmail.py`: plain Python functions for Gmail on the web, in Safari. Python 3.9+, standard library only. Put this
folder on `sys.path` (or copy the file next to your program) and `import gmail`.

```python
import gmail

found = gmail.message_search(query="from:billing@example.com", limit=10, fields="sender,subject,date,snippet,unread")
if found:
    gmail.message_star(match=found[0]["subject"])
```

## How it works, and what it won't do

UI mode only. Calls find Gmail's elements by role and name through the macOS Accessibility API, press them, and paste
text through the clipboard, which is saved first and restored afterwards. They use `ctypes` because going through
System Events took over a minute to scan Gmail's page. There are no screen coordinates and no Gmail keyboard shortcuts,
which are off by default.

There is no Gmail API, OAuth, app password, IMAP or browser cookie access. If Gmail is signed out, a call raises
`SignedOut` and doesn't try to sign in. There is no background mode: asking for one raises `NotSupported`.

Left out on purpose: permanent delete, emptying the Bin, filters, forwarding rules, account settings, and anything that
changes who can access the account.

Left out because they couldn't be made reliable:

- `label_apply`: it was never written or run as a command. At Safari's usual window size Gmail hides Labels in a More menu,
  and its "Label as" submenu wouldn't open by pressing, by keyboard or with the page zoomed out. The only other route found
  is Gmail's "advanced toolbar" setting, which would change the account.
- `message_get`: it returned the right subject, address and body in some start states, but in others its check couldn't
  read the page back, and in one run it timed out waiting for Gmail to load. The cause is unknown, so the function refuses
  with `NotSupported`. **Use `message_search` or `message_list` to read rows**: they return sender, subject, date, snippet,
  unread and starred, and open nothing.

## Which messages it acts on

A "message" is a Gmail conversation. `match` is its exact subject; add `sender=` (the name shown in its row) when the
same subject exists more than once. If nothing matches the call raises `NotFound`. If more than one does it raises
`Ambiguous`. Either way nothing changes. An existing message with an empty body can't be found by exact subject, so it
raises `NotFound` and nothing changes.

- `message_search` and `message_list` read rows and open nothing.
- `message_star`, `message_archive`, `message_trash` and `message_mark_read` work from the selected row and don't open
  the message.
- **`message_reply` opens the message, which marks it read.** `message_get`, which is left out, would too.

## Sending

Set `GMAIL_ALLOWED_RECIPIENTS` to a comma-separated list of addresses. If it's unset, or any recipient isn't on it,
`message_send` and `message_reply` raise `RecipientNotAllowed` and send nothing. `draft_create` never sends, so it doesn't
need the list.

`message_send` and `draft_create` refuse an empty or whitespace-only body with `ValueError` before anything else runs.

Success means the result was read back: a sent message from Sent, a draft from Drafts, a reply by its own text in the
reopened conversation. Otherwise `message_send`, `message_reply` and `draft_create` raise `NotConfirmed`. **On `NotConfirmed`
from `message_send` or `message_reply`, the message may have gone out: check Sent before retrying, and don't resend
automatically.** Send is never pressed twice.

A reply form shows recipients' names, not their addresses. So each name is matched to an address shown in the
conversation's headers, and a name that can't be matched is refused and the reply discarded. A reply-to address that
differs while the display name stays the same can't be seen this way.

## Start states

The start states were Safari closed, launching, hidden and minimized; another app in front; Gmail not open; Gmail on another
tab; another label showing; a message open; search text present; a popup open; and an empty compose window. `message_reply`
was tested only with Safari closed, another app in front, a message open and a popup open.

Each call brings Safari to the front, opens or switches to Gmail, and closes Gmail's passing UI: an open menu, or an empty
compose window. If a compose or reply window holds typed text, the call raises `StateBlocked` and changes nothing. A half-typed
search is replaced by the call's own search.

## Language

Gmail's element names are translated, so its display language must be English. If the Search mail field can't be found
by its English name, a call raises `UnsupportedLanguage`. Only English was tested, and the account's language was not
changed to test others. The code depends on the English names Compose, Search mail, Delete, Archive, Mark as read, Send,
Save & close, Discard draft, Reply, Pop-out reply, Show details, Not starred, To recipients, Subject, Message Body, Sent,
Drafts, Back to Search Results and Google Account. It doesn't depend on Bin or Trash, because it uses Gmail's search terms such as
`in:inbox`, which aren't translated.

## Errors

| Error | When |
|---|---|
| `NotFound` | no message has that exact subject, from that sender if given |
| `Ambiguous` | more than one message matches; nothing is changed |
| `StateBlocked` | a compose or reply window holds typed text, or another app came to the front during a step |
| `SignedOut` | Gmail isn't signed in; the call doesn't try to sign in |
| `RecipientNotAllowed` | the recipient list isn't set, or a recipient isn't on it or can't be confirmed; nothing is sent |
| `UnsupportedLanguage` | Gmail's elements weren't found by their English names |
| `UIError` | a named element never appeared within the timeout |
| `NotConfirmed` | Send or Save & close was pressed, but the result wasn't read back; a message may have gone out |
| `NotSupported` | background mode, or a command that wasn't verified, such as `message_get` |

## Fields

Rows: `sender`, `subject`, `date`, `snippet`, `unread`, `starred`, `labels`. The default is all but `labels`.
Dates are `YYYY-MM-DD HH:MM` in local time when Gmail's long date can be read, and as shown otherwise.

## Limits

- Results come from one page: at most 50 rows.
- Emoji are images in Gmail's editor. They are read from the image's name, so they come back in rows, but a field's raw
  text doesn't contain them.
- Archiving the same message twice wasn't verified, because that repeat case never completed.
- Attachments, CC and BCC aren't supported.
- Only Gmail on the web in Safari was tested, not Chrome, whose message links have no names.

## Functions

### message_search(query, limit=20, fields=None, mode="ui") → [row]
Any Gmail search. Nothing is opened.

### message_list(label="Inbox", limit=20, fields=None, mode="ui") → [row]
The messages under a label. Nothing is opened.

### message_send(to, subject, body="", mode="ui") → {to, subject, sent}
`to` is an address or a list. Destructive: it can't be taken back once sent. An empty body is refused. On `NotConfirmed`,
check Sent before retrying; don't resend automatically.

### draft_create(to, subject, body="", mode="ui") → {to, subject, draft}
Saves, closes and reads the draft back from Drafts. Never sends. An empty body is refused.

### message_reply(match, body, sender=None, mode="ui") → {subject, to, sent}
Replies to the conversation's newest message, to its sender only, and marks it read. Destructive. On `NotConfirmed`, check
Sent before retrying; don't resend automatically.

### message_archive(match, sender=None, mode="ui") → row + `archived`
Removes it from the Inbox without opening it.

### message_trash(match, sender=None, mode="ui") → row + `trashed`
Moves it to the Bin without opening it. Destructive.

### message_star(match, sender=None, mode="ui") → row
Stars it without opening it. A starred message stays starred.

### message_mark_read(match, sender=None, mode="ui") → row
Marks it read without opening it.

## How it was verified, and the limit of that

Each command ran from its start states in the table below, in one VM clone, on messages the tests created themselves and
found by a unique made-up value. Results were read back after reloading Gmail, with separate code from the library. Other
rows were only compared as hashes and flags, and no text or screenshots of them were kept. The start-state runs came before
the empty-body check was added; that check was tested on its own, and it changes nothing for a message with a body.

**This read-back uses the same browser and the same Gmail page, so it is not independent of Gmail itself.** The one
independent check is the spot check below.

Gmail has no version number and can change at any time, which can break these commands without warning. `VERIFIED` records
macOS and Safari only.

| Function | Mode | Verified | Cases | Start states |
|---|---|---|---|---|
| `draft_create` | ui | yes | 17 | app closed, an empty compose window, a compose window with typed text (StateBlocked), app hidden, app still launching, a message open, minimized, Gmail not open, another app in front, another label showing, Gmail on another tab, a popup open, search field with text |
| `message_archive` | ui | yes | 15 | app closed, an empty compose window, a compose window with typed text (StateBlocked), app hidden, app still launching, a message open, minimized, Gmail not open, another app in front, another label showing, Gmail on another tab, a popup open, search field with text |
| `message_list` | ui | yes | 13 | app closed, an empty compose window, a compose window with typed text (StateBlocked), app hidden, app still launching, a message open, minimized, Gmail not open, another app in front, another label showing, Gmail on another tab, a popup open, search field with text |
| `message_mark_read` | ui | yes | 16 | app closed, an empty compose window, a compose window with typed text (StateBlocked), app hidden, app still launching, a message open, minimized, Gmail not open, another app in front, another label showing, Gmail on another tab, a popup open, search field with text |
| `message_reply` | ui | yes | 11 | app closed, a compose window with typed text (StateBlocked), a message open, another app in front, another label showing, a popup open |
| `message_search` | ui | yes | 13 | app closed, an empty compose window, a compose window with typed text (StateBlocked), app hidden, app still launching, a message open, minimized, Gmail not open, another app in front, another label showing, Gmail on another tab, a popup open, search field with text |
| `message_send` | ui | yes | 20 | app closed, an empty compose window, a compose window with typed text (StateBlocked), app hidden, app still launching, a message open, minimized, Gmail not open, another app in front, another label showing, Gmail on another tab, a popup open, search field with text |
| `message_star` | ui | yes | 17 | app closed, an empty compose window, a compose window with typed text (StateBlocked), app hidden, app still launching, a message open, minimized, Gmail not open, another app in front, another label showing, Gmail on another tab, a popup open, search field with text |
| `message_trash` | ui | yes | 15 | app closed, an empty compose window, a compose window with typed text (StateBlocked), app hidden, app still launching, a message open, minimized, Gmail not open, another app in front, another label showing, Gmail on another tab, a popup open, search field with text |

Verified on macOS 26.6.2 (25G83), gmail 26.6.2 (21624.5.1.11.3), 2026-11-03, in fresh VM clones.

The one independent check, done once at the end: Apple Mail, signed in to the same account in the same clone, compared by
flags and counts only, with nothing opened. Against Mail's own copy from before any test, all 975 existing messages were
still there, with the same read, star and Inbox state, and none in the Bin. Test messages showed the Bin and read states
Gmail had shown. Mail's flags may lag behind Gmail, and opening an already-read message leaves no trace, so this can't prove
that nothing was ever opened. Gmail can change at any time.

## Permissions

The program running Python needs **Accessibility** and **Automation** for System Events. It also needs a Safari already
signed in to Gmail, in a session you set up yourself.
