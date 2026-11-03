"""Gmail commands for agents: plain functions with keyword arguments, in Gmail on the web in Safari.

UI mode only: there is no Gmail API, OAuth, app password, IMAP or browser cookie here. Calls find Gmail's elements by
role and name through the macOS Accessibility API (with ctypes, because System Events takes over a minute to scan
Gmail's page), press them, and paste text through the clipboard, which is restored afterwards. No screen coordinates
and no Gmail keyboard shortcuts.

A "message" is a Gmail conversation, found by its exact subject, optionally with its sender's name as shown in the row.
Star, archive, trash and mark read work from the selected row, so they don't open the message. message_get and
message_reply open it, which marks it read.

Sending needs GMAIL_ALLOWED_RECIPIENTS in the environment, a comma-separated list of addresses. If it is unset, or any
recipient is not on it, message_send and message_reply raise RecipientNotAllowed and send nothing.

Gmail's display language must be English, because Gmail's element names are translated. Gmail has no version number
and can change at any time.

Errors: NotFound, Ambiguous (nothing changed), StateBlocked (the screen holds something the call won't destroy),
SignedOut, RecipientNotAllowed, UnsupportedLanguage, UIError (an element never appeared), NotConfirmed (a send or save
couldn't be read back), NotSupported."""
from __future__ import annotations

import ctypes
import datetime as _dt
import os
import plistlib
import re
import subprocess
import time
import warnings

APP = "Safari"
GMAIL_URL = "https://mail.google.com/"
TIMEOUT = 15
SAVE_TIMEOUT = 40
SIGN_IN_HOLD = 8
ROW_FIELDS = ("sender", "subject", "date", "snippet", "unread", "starred", "labels")
MESSAGE_FIELDS = ("subject", "sender", "sender_address", "date", "body", "starred", "labels")
ROW_DEFAULT = "sender,subject,date,snippet,unread,starred"
MESSAGE_DEFAULT = "subject,sender,sender_address,date,body"
ALLOWED_ENV = "GMAIL_ALLOWED_RECIPIENTS"

VERIFIED: dict = {
    "draft_create": {
        "ui": {
            "macos": "26.6.2 (25G83)",
            "app": "26.6.2 (21624.5.1.11.3)"
        }
    },
    "message_archive": {
        "ui": {
            "macos": "26.6.2 (25G83)",
            "app": "26.6.2 (21624.5.1.11.3)"
        }
    },
    "message_list": {
        "ui": {
            "macos": "26.6.2 (25G83)",
            "app": "26.6.2 (21624.5.1.11.3)"
        }
    },
    "message_mark_read": {
        "ui": {
            "macos": "26.6.2 (25G83)",
            "app": "26.6.2 (21624.5.1.11.3)"
        }
    },
    "message_reply": {
        "ui": {
            "macos": "26.6.2 (25G83)",
            "app": "26.6.2 (21624.5.1.11.3)"
        }
    },
    "message_search": {
        "ui": {
            "macos": "26.6.2 (25G83)",
            "app": "26.6.2 (21624.5.1.11.3)"
        }
    },
    "message_send": {
        "ui": {
            "macos": "26.6.2 (25G83)",
            "app": "26.6.2 (21624.5.1.11.3)"
        }
    },
    "message_star": {
        "ui": {
            "macos": "26.6.2 (25G83)",
            "app": "26.6.2 (21624.5.1.11.3)"
        }
    },
    "message_trash": {
        "ui": {
            "macos": "26.6.2 (25G83)",
            "app": "26.6.2 (21624.5.1.11.3)"
        }
    }
}


class GmailError(Exception):
    pass


class NotFound(GmailError):
    pass


class Ambiguous(GmailError):
    pass


class StateBlocked(GmailError):
    pass


class SignedOut(GmailError):
    pass


class RecipientNotAllowed(GmailError):
    pass


class UnsupportedLanguage(GmailError):
    pass


class UIError(GmailError):
    pass


class NotConfirmed(GmailError):
    """Send or Save was pressed, but the result couldn't be read back. It may or may not have gone through."""


class NotSupported(GmailError):
    pass


# Accessibility ----------------------------------------------------------------------------------------------------

_AS = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices")
_CF = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
_P = ctypes.c_void_p
for _f, _res, _args in [
        (_AS.AXUIElementCreateApplication, _P, [ctypes.c_int]),
        (_AS.AXUIElementCopyAttributeValue, ctypes.c_int, [_P, _P, ctypes.POINTER(_P)]),
        (_AS.AXUIElementSetAttributeValue, ctypes.c_int, [_P, _P, _P]),
        (_AS.AXUIElementPerformAction, ctypes.c_int, [_P, _P]),
        (_AS.AXValueGetValue, ctypes.c_bool, [_P, ctypes.c_int, _P]),
        (_CF.CFStringCreateWithCString, _P, [_P, ctypes.c_char_p, ctypes.c_uint32]),
        (_CF.CFStringGetLength, ctypes.c_long, [_P]),
        (_CF.CFStringGetMaximumSizeForEncoding, ctypes.c_long, [ctypes.c_long, ctypes.c_uint32]),
        (_CF.CFStringGetCString, ctypes.c_bool, [_P, ctypes.c_char_p, ctypes.c_long, ctypes.c_uint32]),
        (_CF.CFGetTypeID, ctypes.c_ulong, [_P]), (_CF.CFStringGetTypeID, ctypes.c_ulong, []),
        (_CF.CFArrayGetTypeID, ctypes.c_ulong, []), (_CF.CFArrayGetCount, ctypes.c_long, [_P]),
        (_CF.CFArrayGetValueAtIndex, _P, [_P, ctypes.c_long])]:
    _f.restype, _f.argtypes = _res, _args
_UTF8 = 0x08000100
_TRUE = _P.in_dll(_CF, "kCFBooleanTrue")
_FALSE = _P.in_dll(_CF, "kCFBooleanFalse")
_NAMES: dict = {}


def _cf(text: str):
    if text not in _NAMES:
        _NAMES[text] = _CF.CFStringCreateWithCString(None, text.encode(), _UTF8)
    return _NAMES[text]


def _attr(element, name: str):
    out = _P()
    return out.value if _AS.AXUIElementCopyAttributeValue(element, _cf(name), ctypes.byref(out)) == 0 else None


def _string(element, name: str) -> str:
    value = _attr(element, name)
    if not value or _CF.CFGetTypeID(value) != _CF.CFStringGetTypeID():
        return ""
    size = _CF.CFStringGetMaximumSizeForEncoding(_CF.CFStringGetLength(value), _UTF8) + 1
    buffer = ctypes.create_string_buffer(size)
    return buffer.value.decode() if _CF.CFStringGetCString(value, buffer, size, _UTF8) else ""


def _children(element) -> list:
    value = _attr(element, "AXChildren")
    if not value or _CF.CFGetTypeID(value) != _CF.CFArrayGetTypeID():
        return []
    return [_CF.CFArrayGetValueAtIndex(value, i) for i in range(_CF.CFArrayGetCount(value))]


def _walk(root):
    stack = [root]
    while stack:
        element = stack.pop()
        yield element
        stack.extend(reversed(_children(element)))


def _role(element) -> str:
    return _string(element, "AXRole")


def _name(element) -> str:
    return _string(element, "AXDescription") or _string(element, "AXTitle")


def _top(element) -> float:
    """The element's height on the page, used only to tell which text sits on the same line, never to click."""
    value = _attr(element, "AXPosition")
    point = (ctypes.c_double * 2)()
    return point[1] if value and _AS.AXValueGetValue(value, 1, point) else 0.0


def _find(root, role: str, name: str, exact: bool = False):
    for element in _walk(root):
        if _role(element) == role and (_name(element) == name if exact else _name(element).startswith(name)):
            return element
    return None


def _press(element) -> None:
    if _AS.AXUIElementPerformAction(element, _cf("AXPress")) != 0:
        raise UIError(f"could not press {_name(element)!r}")


def _focus(element) -> None:
    _AS.AXUIElementSetAttributeValue(element, _cf("AXFocused"), _TRUE)


def _run(args: list) -> str:
    done = subprocess.run(args, capture_output=True, text=True)
    if done.returncode:
        raise UIError(done.stderr.strip())
    return done.stdout.strip()


def _wait_for(what: str, test, timeout: float = TIMEOUT):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = test()
        if value:
            return value
        time.sleep(0.25)
    raise UIError(f"{what} did not happen within {timeout}s")


# Versions ---------------------------------------------------------------------------------------------------------

def _versions() -> dict:
    macos = f"{_run(['sw_vers', '-productVersion'])} ({_run(['sw_vers', '-buildVersion'])})"
    with open("/Applications/Safari.app/Contents/Info.plist", "rb") as handle:
        info = plistlib.load(handle)
    return {"macos": macos, "app": f"{info['CFBundleShortVersionString']} ({info['CFBundleVersion']})"}


def _checked(function: str, result):
    verified = VERIFIED.get(function, {}).get("ui")
    if verified is None:
        return result
    now = _versions()
    if now == verified:
        return result
    flag = {"unverified_version": True, "verified_on": verified, "running_on": now}
    warnings.warn(f"{function} was verified on {verified}, running on {now}")
    if isinstance(result, dict):
        return {**result, **flag}
    return [{**item, **flag} for item in result]


def _mode(function: str, mode: str) -> None:
    if mode not in ("ui", "background"):
        raise ValueError(f"mode must be 'ui' or 'background', not {mode!r}")
    if mode == "background":
        raise NotSupported(f"{function} has no background mode: these commands only work on screen")
    if VERIFIED and "ui" not in VERIFIED.get(function, {}):
        raise NotSupported(f"{function} did not pass verification")


def _fields(fields, default: str, allowed: tuple) -> list:
    chosen = [part.strip() for part in (fields or default).split(",")] if isinstance(fields, (str, type(None))) \
        else list(fields)
    unknown = [name for name in chosen if name not in allowed]
    if unknown:
        raise ValueError(f"unknown fields {unknown}; choose from {', '.join(allowed)}")
    return chosen


# Safari and Gmail -------------------------------------------------------------------------------------------------

def _pid() -> int | None:
    found = subprocess.run(["pgrep", "-x", APP], capture_output=True, text=True).stdout.split()
    return int(found[0]) if found else None


def _app():
    return _AS.AXUIElementCreateApplication(_pid())


def _window():
    app = _app()
    return _attr(app, "AXFocusedWindow") or _attr(app, "AXMainWindow") or next(iter(_children(app)), None)


def _system_events(body: str, *args: str) -> str:
    return _run(["osascript", "-e", f'on run argv\ntell application "System Events" to tell process "{APP}"\n{body}\n'
                                    "end tell\nend run", *args])


def _keys(*codes: int) -> None:
    if _system_events("return frontmost") != "true":
        raise StateBlocked("another app came to the front; nothing more was typed")
    for code in codes:
        _system_events(f"key code {code}")


RETURN, TAB, ESCAPE = 36, 48, 53
CLIPBOARD = r"""
ObjC.import("AppKit");
function run(argv) {
  const pb = $.NSPasteboard.generalPasteboard;
  if (argv[0] === "save") {
    const items = ObjC.unwrap(pb.pasteboardItems) || [];
    return JSON.stringify(items.map(item => ObjC.unwrap(item.types).map(t => {
      const type = ObjC.unwrap(t);
      return [type, ObjC.unwrap(item.dataForType(type).base64EncodedStringWithOptions(0))];
    })));
  }
  pb.clearContents;
  if (argv[0] === "text") {
    pb.setStringForType($(argv[1]), "public.utf8-plain-text");
    return "ok";
  }
  const items = JSON.parse(argv[1]).map(pairs => {
    const item = $.NSPasteboardItem.alloc.init;
    pairs.forEach(([type, data]) => item.setDataForType($.NSData.alloc.initWithBase64EncodedStringOptions(data, 0), type));
    return item;
  });
  if (items.length) pb.writeObjects($(items));
  return "restored";
}"""


def _clipboard(*args: str) -> str:
    return _run(["osascript", "-l", "JavaScript", "-e", CLIPBOARD, *args])


def _paste(text: str, replace: bool = False) -> None:
    """Paste text at the focused element, then put the user's clipboard back."""
    if _system_events("return frontmost") != "true":
        raise StateBlocked("another app came to the front; nothing was pasted")
    saved = _clipboard("save")
    try:
        _clipboard("text", text)
        if replace:
            _system_events('keystroke "a" using command down')
        _system_events('keystroke "v" using command down')
        time.sleep(0.4)
    finally:
        _clipboard("restore", saved)


def _title() -> str:
    window = _window()
    return _string(window, "AXTitle") if window else ""


def _address_bar() -> str:
    window = _window()
    field = _find(window, "AXTextField", "smart search field") if window else None
    return _string(field, "AXValue") if field else ""


def _bring_forward() -> None:
    if _pid() is None:
        subprocess.run(["open", "-a", APP], check=True)
        _wait_for("Safari to start", lambda: _pid() and _children(_app()))
    _system_events("set visible to true\nset frontmost to true")
    for window in [e for e in _children(_app()) if _role(e) == "AXWindow"]:
        if _attr(window, "AXMinimized") == _TRUE.value:
            _AS.AXUIElementSetAttributeValue(window, _cf("AXMinimized"), _FALSE)
    _wait_for("Safari in front", lambda: _system_events("return frontmost") == "true" and _window())


def _gmail_tab():
    """The window tab showing Gmail, if another tab is in front."""
    for group in [e for e in _walk(_window()) if _role(e) == "AXTabGroup"]:
        for tab in _children(group):
            if " - Gmail" in (_string(tab, "AXTitle") or _string(tab, "AXDescription")):
                return tab
    return None


def _show_gmail() -> None:
    if " - Gmail" not in _title():
        tab = _gmail_tab()
        if tab:
            _press(tab)
        else:
            subprocess.run(["open", "-a", APP, GMAIL_URL], check=True)

    away_since = [None]

    def settled():
        # Gmail can pass through accounts.google.com while loading, so only a page that stays there counts.
        host = _address_bar()
        if ("accounts.google.com" in host or "/signin" in host or "workspace.google.com" in host
                or _title().startswith(("Sign in", "Gmail: "))):
            away_since[0] = away_since[0] or time.monotonic()
            if time.monotonic() - away_since[0] >= SIGN_IN_HOLD:
                raise SignedOut("Gmail is not signed in; this call will not try to sign in")
        else:
            away_since[0] = None
        return " - Gmail" in _title() and _find(_window(), "AXButton", "Google Account:")
    _wait_for("Gmail to load", settled, SAVE_TIMEOUT)
    try:
        _wait_for("the Search mail field", lambda: _find(_window(), "AXTextField", "Search mail", exact=True))
    except UIError:
        raise UnsupportedLanguage("Gmail's Search mail field wasn't found by its English name; these commands only "
                                  "work with Gmail's display language set to English") from None


def _compose_forms() -> list:
    """Every open compose or reply form."""
    window = _window()
    return [e for e in _walk(window) if _role(e) == "AXTextArea" and _name(e) == "Message Body"]


def _dialog_of(body):
    node = body
    for _ in range(14):
        node = _attr(node, "AXParent")
        if not node:
            return None
        name = _name(node)
        if name.startswith("Compose:") or _string(node, "AXSubrole") == "AXLandmarkRegion":
            return node
    return None


def _clear_transients() -> None:
    """Close only Gmail's own passing UI. A compose or reply holding text is left alone: StateBlocked."""
    for _ in range(4):
        window = _window()
        if not any(_role(e) == "AXMenu" for e in _walk(window)):
            break
        _keys(ESCAPE)
        time.sleep(0.4)
    for body in _compose_forms():
        form = _dialog_of(body)
        typed = _string(body, "AXValue").strip()
        title = _name(form) if form else ""
        subject = _find(form, "AXTextField", "Subject") if form else None
        recipients = _find(form, "AXComboBox", "To recipients") if form else None
        filled = (typed or (subject and _string(subject, "AXValue").strip())
                  or (recipients and _string(recipients, "AXValue").strip())
                  or (title and title not in ("Compose: New Message", "New Message") and not title.startswith("Re:")))
        if filled or (form and any("@" in _string(e, "AXTitle") for e in _walk(form) if _role(e) == "AXStaticText")):
            raise StateBlocked("Gmail has a compose or reply window with typed text in it; it was left as it is")
        discard = _find(form, "AXButton", "Discard draft") if form else None
        if discard:
            _press(discard)
            time.sleep(0.8)
    for element in _walk(_window()):
        if _role(element) == "AXTextField" and "label name" in _name(element):
            if _string(element, "AXValue").strip():
                raise StateBlocked("Gmail has a dialog with typed text in it; it was left as it is")
            cancel = _find(_window(), "AXButton", "Cancel", exact=True)
            if cancel:
                _press(cancel)
            break


def _ready() -> None:
    _bring_forward()
    _show_gmail()
    _clear_transients()


def _main():
    return next((e for e in _walk(_window()) if _string(e, "AXSubrole") == "AXLandmarkMain"), _window())


# Rows -------------------------------------------------------------------------------------------------------------

def _row_date(row) -> str:
    for element in _walk(row):
        if _role(element) == "AXGroup" and re.search(r"\d{4}", _name(element)):
            return _date(_name(element))
    return ""


def _date(text: str) -> str:
    """Gmail's long date as YYYY-MM-DD HH:MM; as shown if it isn't one of the forms below."""
    for shape in ("%a, %d %b %Y, %H:%M", "%d %b %Y, %H:%M", "%a, %b %d, %Y, %I:%M %p", "%b %d, %Y, %I:%M %p"):
        try:
            return _dt.datetime.strptime(text.replace(" ", " "), shape).strftime("%Y-%m-%d %H:%M")
        except ValueError:
            continue
    return text


def _text_of(parts: list) -> str:
    return "".join(_string(e, "AXValue") if _role(e) == "AXStaticText" else _name(e) for e in parts)


def _read_row(row) -> dict:
    prefix = _name(row)
    link = next((e for e in _walk(row) if _role(e) == "AXLink"), None)
    subject, snippet, labels, in_snippet = [], [], [], False
    for child in (_children(link) if link else []):
        role = _role(child)
        if role == "AXGroup":
            labels += [_string(e, "AXValue") for e in _walk(child) if _role(e) == "AXStaticText"]
        elif role == "AXStaticText" and _string(child, "AXValue").strip() == "-" and subject:
            in_snippet = True
        elif role in ("AXStaticText", "AXImage"):
            (snippet if in_snippet else subject).append(child)
    senders = []
    for cell in _children(row):
        if any(_role(e) == "AXLink" for e in _walk(cell)):
            break
        senders += [_string(e, "AXValue") for e in _walk(cell) if _role(e) == "AXStaticText"]
    return {"sender": " ".join(s for s in senders if s.strip()), "subject": _text_of(subject),
            "date": _row_date(row), "snippet": _text_of(snippet), "unread": bool(re.match(r"(starred, )?unread, ", prefix)),
            "starred": prefix.startswith("starred, "), "labels": [x for x in labels if x.strip()], "_row": row}


def _rows() -> list:
    return [e for e in _walk(_main()) if _role(e) == "AXRow" and any(_role(x) == "AXLink" for x in _walk(e))]


def _search(query: str) -> None:
    field = _wait_for("the Search mail field", lambda: _find(_window(), "AXTextField", "Search mail", exact=True))
    _focus(field)
    time.sleep(0.2)
    _paste(query, replace=True)
    _keys(RETURN)

    def signature():
        return tuple(sorted(_name(r) for r in _rows()))
    end, last, steady = time.monotonic() + TIMEOUT, None, 0
    time.sleep(0.8)
    while time.monotonic() < end:
        current = signature()
        none_matched = any(_role(e) == "AXStaticText" and _string(e, "AXValue").startswith("No messages matched")
                           for e in _walk(_main()))
        if ("#search" in _address_bar() or "search/" in _address_bar()) and (current or none_matched) and current == last:
            steady += 1
            if steady >= 2:
                return
        else:
            steady = 0
        last = current
        time.sleep(0.5)


def _quoted(text: str) -> str:
    words = re.sub(r"[^\w\s]", " ", text)
    return '"' + " ".join(words.split()) + '"'


def _matches(match: str, sender: str | None, scope: str = "") -> list:
    _search(f"{scope} subject:{_quoted(match)}".strip())
    found = [r for r in (_read_row(row) for row in _rows()) if r["subject"] == match]
    return [r for r in found if sender is None or r["sender"] == sender]


def _one(match: str, sender: str | None) -> dict:
    found = _matches(match, sender)
    who = f" from {sender!r}" if sender else ""
    if not found:
        raise NotFound(f"no message has the exact subject {match!r}{who}")
    if len(found) > 1:
        raise Ambiguous(f"{len(found)} messages have the subject {match!r}{who}; nothing was changed")
    return found[0]


def _select(row: dict) -> None:
    box = next(e for e in _walk(row["_row"]) if _role(e) == "AXCheckBox")
    _press(box)
    _wait_for("the selected-message toolbar", lambda: _find(_window(), "AXButton", "Delete", exact=True))


def _public(row: dict, fields) -> dict:
    return {name: row[name] for name in _fields(fields, ROW_DEFAULT, ROW_FIELDS)}


def _recipients(to) -> list:
    return [to] if isinstance(to, str) else list(to)


def _allowed(addresses: list) -> None:
    raw = os.environ.get(ALLOWED_ENV, "")
    allowed = {a.strip().lower() for a in raw.split(",") if a.strip()}
    if not allowed:
        raise RecipientNotAllowed(f"{ALLOWED_ENV} is not set; nothing was sent")
    refused = [a for a in addresses if a.strip().lower() not in allowed]
    if refused:
        raise RecipientNotAllowed(f"{refused} not in {ALLOWED_ENV}; nothing was sent")


def _compose(to: list, subject: str, body: str):
    _press(_wait_for("the Compose button", lambda: _find(_window(), "AXButton", "Compose")))
    form = _wait_for("the compose window", lambda: next((e for e in _walk(_window())
                                                          if _role(e) == "AXGroup" and _name(e).startswith("Compose:")), None))
    recipients = _wait_for("the To field", lambda: _find(form, "AXComboBox", "To recipients"))
    _focus(recipients)
    time.sleep(0.2)
    _paste(", ".join(to))
    _keys(TAB)
    subject_field = _find(form, "AXTextField", "Subject")
    _focus(subject_field)
    time.sleep(0.2)
    _paste(subject)
    if _string(subject_field, "AXValue") != subject:
        raise UIError("the subject did not arrive as typed")
    message = _find(form, "AXTextArea", "Message Body")
    _focus(message)
    time.sleep(0.2)
    if body:
        _paste(body)
    return form


def _closed(form) -> bool:
    """Only a readable Gmail page counts: an empty accessibility tree must not look like a closed window."""
    items = list(_walk(_window()))
    return (any(_role(e) == "AXTextField" and _name(e) == "Search mail" for e in items)
            and not any(_role(e) == "AXGroup" and _name(e).startswith("Compose:") for e in items))


def _plain(text: str) -> str:
    return "".join(re.findall(r"\w+", text)).lower()


def _wait_closed(form, what: str) -> None:
    try:
        _wait_for("the compose window to close", lambda: _closed(form))
    except UIError:
        raise NotConfirmed(f"{what}: its compose window is still open") from None


def _confirm_sent(form, subject: str) -> None:
    """Success means the message was read back from Sent. Send is never pressed twice."""
    _wait_closed(form, f"the message {subject!r} wasn't confirmed as sent")
    try:
        _wait_for("the message in Sent", lambda: _matches(subject, None, "in:sent"), SAVE_TIMEOUT)
    except UIError:
        raise NotConfirmed(f"the message {subject!r} wasn't found in Sent; check there before sending it again") from None


def _confirm_reply(form, match: str, body: str) -> None:
    """Success means the reply's own text was read back from the reopened conversation."""
    _wait_closed(form, f"the reply to {match!r} wasn't confirmed as sent")
    wanted = _plain(body)

    def found():
        rows = _matches(match, None, "in:sent")
        if not rows:
            return False
        try:
            _open(rows[0])
        except UIError:
            return False
        return wanted in _plain("\n".join(_newest_lines(_main())))
    try:
        _wait_for("the reply in its conversation", found, SAVE_TIMEOUT)
    except UIError:
        raise NotConfirmed(f"the reply's text wasn't found in {match!r}; check there before replying again") from None


def _confirm_draft(form, subject: str) -> None:
    """Success means the draft was read back from the Drafts folder. Gmail's search doesn't find drafts reliably."""
    _wait_closed(form, f"the draft {subject!r} wasn't confirmed as saved")

    def found():
        _press(_wait_for("the Sent link", lambda: _find(_window(), "AXLink", "Sent", exact=True)))
        _wait_for("the Sent folder", lambda: "#sent" in _address_bar())
        _press(_wait_for("the Drafts link", lambda: _find(_window(), "AXLink", "Drafts")))
        _wait_for("the Drafts folder", lambda: "#drafts" in _address_bar())
        time.sleep(1.5)
        return any(_read_row(row)["subject"] == subject for row in _rows())
    try:
        _wait_for("the draft in Drafts", found, SAVE_TIMEOUT)
    except UIError:
        raise NotConfirmed(f"the draft {subject!r} wasn't found in Drafts") from None


def _shown_addresses(main) -> dict:
    """{display name: address} from the headers of the open conversation."""
    shown = {}
    for heading in [e for e in _walk(main) if _role(e) == "AXHeading"]:
        parts = [_string(e, "AXValue") for e in _walk(heading) if _role(e) == "AXStaticText"]
        address = next((p.strip(" <>") for p in parts if "@" in p), None)
        name = next((p for p in parts if p and "@" not in p), None)
        if address and name:
            shown[name] = address
    return shown


def _open(row: dict) -> None:
    link = next(e for e in _walk(row["_row"]) if _role(e) == "AXLink")
    _press(link)
    _wait_for("the message to open", lambda: _find(_main(), "AXHeading", row["subject"], exact=True))


def _newest_lines(main) -> list:
    """The newest message's text in the open conversation, as lines."""
    items = list(_walk(main))
    start = max((i for i, e in enumerate(items) if _role(e) == "AXPopUpButton" and _name(e) == "Show details"), default=0)
    end = next((i for i, e in enumerate(items) if i > start and _role(e) == "AXLink" and _name(e) == "Reply"), len(items))
    lines, last = [], None
    for element in items[start + 1:end]:
        if _role(element) not in ("AXStaticText", "AXImage"):
            continue
        top = _top(element)
        piece = _string(element, "AXValue") if _role(element) == "AXStaticText" else _name(element)
        if last is not None and abs(top - last) < 6:
            lines[-1] += piece
        else:
            lines.append(piece)
        last = top
    return lines


# Commands ---------------------------------------------------------------------------------------------------------

def message_search(query: str, limit: int = 20, fields=None, mode: str = "ui") -> list:
    """Messages matching a Gmail search, as their rows; nothing is opened. At most one page (50 rows)."""
    _mode("message_search", mode)
    _ready()
    _search(query)
    return _checked("message_search", [_public(_read_row(row), fields) for row in _rows()[:limit]])


def message_list(label: str = "Inbox", limit: int = 20, fields=None, mode: str = "ui") -> list:
    """Messages under a label, as their rows; nothing is opened. At most one page (50 rows)."""
    _mode("message_list", mode)
    _ready()
    _search("in:inbox" if label.lower() == "inbox" else f"label:{_quoted(label)}")
    return _checked("message_list", [_public(_read_row(row), fields) for row in _rows()[:limit]])


def message_get(match: str, sender: str | None = None, fields=None, mode: str = "ui") -> dict:
    """Open the message with this exact subject and read its newest message. Opening it marks it read."""
    _mode("message_get", mode)
    chosen = _fields(fields, MESSAGE_DEFAULT, MESSAGE_FIELDS)
    _ready()
    row = _one(match, sender)
    starred, labels = row["starred"], row["labels"]
    _open(row)
    main = _main()
    items = list(_walk(main))
    lines = _newest_lines(main)
    headings = _shown_addresses(main)
    sender_name = next(reversed(list(headings)), "") if headings else ""
    dates = [_name(e) for e in items if _role(e) == "AXCell" and re.search(r"\d{4}", _name(e))]
    message = {"subject": match, "sender": sender_name, "sender_address": headings.get(sender_name, ""),
               "date": _date(dates[-1]) if dates else "", "body": "\n".join(lines), "starred": starred, "labels": labels}
    return _checked("message_get", {name: message[name] for name in chosen})


def message_send(to, subject: str, body: str = "", mode: str = "ui") -> dict:
    """Send a new message. Every address in to must be on GMAIL_ALLOWED_RECIPIENTS."""
    if not body.strip():
        raise ValueError("body must not be empty")
    _mode("message_send", mode)
    addresses = _recipients(to)
    if not addresses or not subject.strip() or "\n" in subject:
        raise ValueError("to must name a recipient and subject must be one non-empty line")
    _allowed(addresses)
    _ready()
    form = _compose(addresses, subject, body)
    _press(next(e for e in _walk(form) if _role(e) == "AXButton" and _name(e).startswith("Send") and "options" not in _name(e)))
    _confirm_sent(form, subject)
    return _checked("message_send", {"to": addresses, "subject": subject, "sent": True})


def draft_create(to, subject: str, body: str = "", mode: str = "ui") -> dict:
    """Save a new draft. It is never sent."""
    if not body.strip():
        raise ValueError("body must not be empty")
    _mode("draft_create", mode)
    addresses = _recipients(to)
    if not addresses or not subject.strip() or "\n" in subject:
        raise ValueError("to must name a recipient and subject must be one non-empty line")
    _ready()
    form = _compose(addresses, subject, body)
    _press(next(e for e in _walk(form) if _role(e) == "AXButton" and _name(e).startswith("Save & close")))
    _confirm_draft(form, subject)
    return _checked("draft_create", {"to": addresses, "subject": subject, "draft": True})


def message_reply(match: str, body: str, sender: str | None = None, mode: str = "ui") -> dict:
    """Reply to the message with this exact subject. Every recipient must be on GMAIL_ALLOWED_RECIPIENTS.

    The reply form shows names, not addresses, so each name is matched to an address shown in the conversation's
    headers; a name that can't be matched is refused."""
    _mode("message_reply", mode)
    if not body.strip():
        raise ValueError("body must not be empty")
    if not [a for a in os.environ.get(ALLOWED_ENV, "").split(",") if a.strip()]:
        raise RecipientNotAllowed(f"{ALLOWED_ENV} is not set; nothing was sent")
    _ready()
    row = _one(match, sender)
    _open(row)
    main = _main()
    known = _shown_addresses(main)
    _press(_wait_for("the Reply link", lambda: _find(main, "AXLink", "Reply", exact=True)))
    _wait_for("the reply form", lambda: _find(_main(), "AXTextArea", "Message Body"))
    _press(_wait_for("Pop-out reply", lambda: _find(_window(), "AXButton", "Pop-out reply")))
    form = _wait_for("the reply window", lambda: next((e for e in _walk(_window())
                                                        if _role(e) == "AXGroup" and _name(e).startswith("Compose:")), None))

    def discard():
        button = _find(form, "AXButton", "Discard draft")
        if button:
            _press(button)
    message = _wait_for("the reply body", lambda: _find(form, "AXTextArea", "Message Body"))
    _focus(message)
    time.sleep(0.3)
    _system_events("key code 48 using shift down")
    time.sleep(0.4)
    _system_events("key code 48 using shift down")
    recipients = _wait_for("the recipient row", lambda: _find(form, "AXComboBox", "To recipients"))
    time.sleep(0.4)
    row_group = recipients
    for _ in range(4):
        row_group = _attr(row_group, "AXParent")
    chips = [_string(e, "AXTitle") or _string(e, "AXValue") for e in _walk(row_group)
             if _role(e) == "AXStaticText" and (_string(e, "AXTitle") or _string(e, "AXValue")) not in ("", "To", "Cc", "Bcc")]
    resolved = [c if "@" in c else known.get(c) for c in chips]
    if not chips or None in resolved:
        discard()
        raise RecipientNotAllowed(f"couldn't confirm the address of every reply recipient {chips}; nothing was sent")
    try:
        _allowed(resolved)
    except RecipientNotAllowed:
        discard()
        raise
    message = _find(form, "AXTextArea", "Message Body")
    _focus(message)
    time.sleep(0.2)
    _system_events("key code 126 using command down")
    _paste(body)
    _press(next(e for e in _walk(form) if _role(e) == "AXButton" and _name(e).startswith("Send") and "options" not in _name(e)))
    _confirm_reply(form, match, body)
    back = _find(_window(), "AXButton", "Back to Search Results")
    if back:
        _press(back)
    return _checked("message_reply", {"subject": match, "to": resolved, "sent": True})


def _on_selected(function: str, match: str, sender: str | None, button: str, done, mode: str) -> dict:
    _mode(function, mode)
    _ready()
    row = _one(match, sender)
    public = _public(row, None)
    _select(row)
    _press(_wait_for(f"the {button} button", lambda: _find(_window(), "AXButton", button, exact=True)))
    _wait_for(f"{button} to take effect", done, SAVE_TIMEOUT)
    return public


def message_archive(match: str, sender: str | None = None, mode: str = "ui") -> dict:
    """Remove the message from the Inbox without opening it."""
    _mode("message_archive", mode)
    _ready()
    row = _one(match, sender)
    public = _public(row, None)
    if "Inbox" not in row["labels"]:
        return _checked("message_archive", {**public, "archived": True})
    _select(row)
    _press(_wait_for("the Archive button", lambda: _find(_window(), "AXButton", "Archive", exact=True)))
    _wait_for("the message to leave the Inbox", lambda: not _matches(match, sender, "in:inbox"), SAVE_TIMEOUT)
    return _checked("message_archive", {**public, "archived": True})


def message_trash(match: str, sender: str | None = None, mode: str = "ui") -> dict:
    """Move the message to the Bin without opening it."""
    result = _on_selected("message_trash", match, sender, "Delete", lambda: not _matches(match, sender), mode)
    return _checked("message_trash", {**result, "trashed": True})


def message_star(match: str, sender: str | None = None, mode: str = "ui") -> dict:
    """Star the message without opening it."""
    _mode("message_star", mode)
    _ready()
    row = _one(match, sender)
    if not row["starred"]:
        _press(next(e for e in _walk(row["_row"]) if _role(e) == "AXButton" and _name(e) == "Not starred"))
        _wait_for("the star", lambda: _one(match, sender)["starred"], SAVE_TIMEOUT)
    return _checked("message_star", {**_public(_one(match, sender), None), "starred": True})


def message_mark_read(match: str, sender: str | None = None, mode: str = "ui") -> dict:
    """Mark the message read without opening it."""
    _mode("message_mark_read", mode)
    _ready()
    row = _one(match, sender)
    if row["unread"]:
        _select(row)
        _press(_wait_for("the Mark as read button", lambda: _find(_window(), "AXButton", "Mark as read", exact=True)))
        _wait_for("the mark", lambda: not _one(match, sender)["unread"], SAVE_TIMEOUT)
    return _checked("message_mark_read", _public(_one(match, sender), None))

