"""Notes commands for agents: plain functions with keyword arguments, on the local "On My Mac" account.

mode="ui" (the default) makes the change on screen: System Events clicks buttons, menu items and rows found by
name and role, and text is pasted through the clipboard (which is restored afterwards). The note to act on is
found by exact title through Notes' own scripting, then shown, so the edit lands on that note only.
mode="background" uses Notes' own scripting and shows nothing.

Errors: NotFound, Ambiguous (nothing changed), StateBlocked (the screen holds something the call won't destroy),
UIError (an element never appeared), NotSupported (the mode can't do it)."""
from __future__ import annotations

import html
import json
import plistlib
import subprocess
import time
import warnings

APP = "Notes"
BUNDLE_ID = "com.apple.Notes"
ACCOUNT = "On My Mac"
TRASH = "Recently Deleted"
TIMEOUT = 10
FIELDS = ("id", "title", "body", "folder", "created_date", "modified_date")
DEFAULT_FIELDS = "title,body,folder,modified_date"

VERIFIED: dict = {
    "checklist_create": {
        "ui": {
            "macos": "26.6.2 (25G83)",
            "app": "4.13 (3146.141.6)"
        }
    },
    "folder_create": {
        "background": {
            "macos": "26.6.2 (25G83)",
            "app": "4.13 (3146.141.6)"
        },
        "ui": {
            "macos": "26.6.2 (25G83)",
            "app": "4.13 (3146.141.6)"
        }
    },
    "folder_delete": {
        "ui": {
            "macos": "26.6.2 (25G83)",
            "app": "4.13 (3146.141.6)"
        }
    },
    "folder_list": {
        "background": {
            "macos": "26.6.2 (25G83)",
            "app": "4.13 (3146.141.6)"
        }
    },
    "folder_rename": {
        "ui": {
            "macos": "26.6.2 (25G83)",
            "app": "4.13 (3146.141.6)"
        }
    },
    "note_append": {
        "background": {
            "macos": "26.6.2 (25G83)",
            "app": "4.13 (3146.141.6)"
        },
        "ui": {
            "macos": "26.6.2 (25G83)",
            "app": "4.13 (3146.141.6)"
        }
    },
    "note_create": {
        "background": {
            "macos": "26.6.2 (25G83)",
            "app": "4.13 (3146.141.6)"
        },
        "ui": {
            "macos": "26.6.2 (25G83)",
            "app": "4.13 (3146.141.6)"
        }
    },
    "note_delete": {
        "ui": {
            "macos": "26.6.2 (25G83)",
            "app": "4.13 (3146.141.6)"
        }
    },
    "note_get": {
        "background": {
            "macos": "26.6.2 (25G83)",
            "app": "4.13 (3146.141.6)"
        }
    },
    "note_list": {
        "background": {
            "macos": "26.6.2 (25G83)",
            "app": "4.13 (3146.141.6)"
        }
    },
    "note_move": {
        "background": {
            "macos": "26.6.2 (25G83)",
            "app": "4.13 (3146.141.6)"
        },
        "ui": {
            "macos": "26.6.2 (25G83)",
            "app": "4.13 (3146.141.6)"
        }
    },
    "note_pin": {
        "ui": {
            "macos": "26.6.2 (25G83)",
            "app": "4.13 (3146.141.6)"
        }
    },
    "note_rename": {
        "ui": {
            "macos": "26.6.2 (25G83)",
            "app": "4.13 (3146.141.6)"
        }
    },
    "note_replace_body": {
        "background": {
            "macos": "26.6.2 (25G83)",
            "app": "4.13 (3146.141.6)"
        },
        "ui": {
            "macos": "26.6.2 (25G83)",
            "app": "4.13 (3146.141.6)"
        }
    },
    "note_search": {
        "background": {
            "macos": "26.6.2 (25G83)",
            "app": "4.13 (3146.141.6)"
        }
    }
}


class NotesError(Exception):
    pass


class NotFound(NotesError):
    pass


class Ambiguous(NotesError):
    pass


class AlreadyExists(NotesError):
    pass


class StateBlocked(NotesError):
    pass


class UIError(NotesError):
    pass


class NotSupported(NotesError):
    pass


def _run(args: list, data: str | None = None) -> str:
    done = subprocess.run(args, input=data, capture_output=True, text=True)
    if done.returncode:
        raise UIError(done.stderr.strip())
    return done.stdout.strip()


def _osascript(script: str, *args: str) -> str:
    return _run(["osascript", "-e", script, *args])


def _jxa(script: str, *args: str) -> str:
    return _run(["osascript", "-l", "JavaScript", "-e", script, *args])


# Versions ----------------------------------------------------------------------------------------------------------

def _versions() -> dict:
    macos = f"{_run(['sw_vers', '-productVersion'])} ({_run(['sw_vers', '-buildVersion'])})"
    path = _run(["mdfind", f"kMDItemCFBundleIdentifier == '{BUNDLE_ID}'"]).splitlines()
    plist = f"{path[0] if path else '/System/Applications/Notes.app'}/Contents/Info.plist"
    with open(plist, "rb") as handle:
        info = plistlib.load(handle)
    return {"macos": macos, "app": f"{info['CFBundleShortVersionString']} ({info['CFBundleVersion']})"}


def _checked(function: str, mode: str, result):
    _leave_as_found()
    verified = VERIFIED.get(function, {}).get(mode)
    if verified is None:
        return result
    now = _versions()
    if now == verified:
        return result
    flag = {"unverified_version": True, "verified_on": verified, "running_on": now}
    warnings.warn(f"{function} ({mode}) was verified on {verified}, running on {now}")
    if isinstance(result, dict):
        return {**result, **flag}
    if isinstance(result, list):
        return [{**item, **flag} if isinstance(item, dict) else item for item in result]
    return result


def _mode(function: str, mode: str, supported: tuple = ("ui", "background")) -> None:
    if mode not in ("ui", "background"):
        raise ValueError(f"mode must be 'ui' or 'background', not {mode!r}")
    if VERIFIED and mode not in VERIFIED.get(function, {}):
        raise NotSupported(f"{function} has no verified {mode} mode: "
                           f"{UNSUPPORTED.get((function, mode), 'it did not pass verification')}")
    if mode not in supported:
        raise NotSupported(f"{function} has no {mode} mode: {UNSUPPORTED.get((function, mode), 'not verified')}")


UNSUPPORTED = {
    ("checklist_create", "background"): "Notes' scripting can't make a checklist; an HTML list would be a fake one",
    ("note_pin", "background"): "Notes' scripting has no pinned property",
    ("note_rename", "background"): "with Notes open, a rename through Notes' scripting did not reach Notes' "
                                   "database within 150 s (twice); use mode='ui'",
    ("note_delete", "background"): "with Notes open, a delete through Notes' scripting did not reach Notes' "
                                   "database within 150 s (twice); use mode='ui'",
    ("folder_rename", "background"): "with Notes open, a folder rename through Notes' scripting did not reach "
                                     "Notes' database within 150 s (twice); use mode='ui'",
    ("folder_delete", "background"): "with Notes open, a folder delete through Notes' scripting did not reach "
                                     "Notes' database within 150 s (twice); use mode='ui'",
}


def _fields(fields, default: str = DEFAULT_FIELDS) -> list:
    chosen = [part.strip() for part in (fields or default).split(",")] if isinstance(fields, (str, type(None))) \
        else list(fields)
    unknown = [name for name in chosen if name not in FIELDS]
    if unknown:
        raise ValueError(f"unknown fields {unknown}; choose from {', '.join(FIELDS)}")
    return chosen


# Notes' own scripting ---------------------------------------------------------------------------------------------

DATA = r"""
function run(argv) {
  const Notes = Application("Notes");
  const op = argv[0], a = JSON.parse(argv[1]);
  const accounts = Notes.accounts.whose({name: "%ACCOUNT%"});
  if (accounts.length === 0) throw new Error('no local account "%ACCOUNT%"');
  const account = accounts[0];
  const pad = n => String(n).padStart(2, "0");
  const when = d => d ? `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}` : null;
  const allFolders = parent => parent.folders().flatMap(f => [f, ...allFolders(f)]);
  const folders = () => allFolders(account).filter(f => f.name() !== "%TRASH%");
  const foldersNamed = name => folders().filter(f => f.name() === name);
  const trashed = new Set(account.folders.whose({name: "%TRASH%"}).length ? account.folders.byName("%TRASH%").notes.id() : []);
  const live = () => {
    const ids = account.notes.id(), names = account.notes.name();
    return ids.map((id, i) => ({id, name: names[i]})).filter(n => !trashed.has(n.id));
  };
  const note = id => Notes.notes.byId(id);
  const info = id => {
    const n = note(id), text = n.plaintext().replace(/\n$/, ""), cut = text.indexOf("\n");
    return {id, title: n.name(), body: cut < 0 ? "" : text.slice(cut + 1), folder: n.container().name(),
            created_date: when(n.creationDate()), modified_date: when(n.modificationDate()),
            modified: n.modificationDate().getTime()};
  };
  const newest = ids => ids.map(info).sort((x, y) => y.modified - x.modified);
  switch (op) {
    case "find": return JSON.stringify(live().filter(n => n.name === a.title).map(n => n.id)
      .filter(id => !a.folder || note(id).container().name() === a.folder));
    case "info": return JSON.stringify(a.ids.map(info));
    case "search": {
      const q = a.query.toLowerCase();
      const hits = live().filter(n => n.name.toLowerCase().includes(q) || note(n.id).plaintext().toLowerCase().includes(q));
      return JSON.stringify(newest(hits.map(n => n.id)).slice(0, a.limit));
    }
    case "list": {
      const ids = a.folder === null ? live().map(n => n.id) : foldersNamed(a.folder)[0].notes.id();
      return JSON.stringify(newest(ids).slice(0, a.limit));
    }
    case "create": {
      const where = a.folder === null ? account.defaultFolder() : foldersNamed(a.folder)[0];
      return JSON.stringify(Notes.make({new: "note", at: where, withProperties: {body: a.html}}).id());
    }
    case "body": return JSON.stringify(note(a.id).body());
    case "plain": return JSON.stringify(note(a.id).plaintext());
    case "set_body": note(a.id).body = a.html; return "true";
    case "set_name": note(a.id).name = a.title; return "true";
    case "move": Notes.move(note(a.id), {to: foldersNamed(a.folder)[0]}); return "true";
    case "delete": Notes.delete(note(a.id)); return "true";
    case "show": Notes.show(note(a.id)); return "true";
    case "default_folder": return JSON.stringify(account.defaultFolder().name());
    case "folders": return JSON.stringify(folders().map(f => ({name: f.name(), notes: f.notes.length,
                                                              id: f.id()})));
    case "folder_create": return JSON.stringify(Notes.make({new: "folder", at: account,
                                                            withProperties: {name: a.name}}).id());
    case "folder_rename": foldersNamed(a.name)[0].name = a.to; return "true";
    case "folder_delete": Notes.delete(foldersNamed(a.name)[0]); return "true";
    case "folder_show": Notes.show(foldersNamed(a.name)[0]); return "true";
  }
  throw new Error("unknown op " + op);
}""".replace("%ACCOUNT%", ACCOUNT).replace("%TRASH%", TRASH)


_STARTED = []


def _launch_hidden() -> None:
    """Start Notes hidden and in the background when it isn't running, so nothing shows on screen. A call that
    started Notes quits it again when it ends, which also makes Notes write the change to its database."""
    if _running():
        return
    subprocess.run(["open", "-g", "-j", "-b", BUNDLE_ID], check=True)
    _wait_for("Notes to start", _scriptable, TIMEOUT * 3)
    _STARTED.append(True)


def _leave_as_found() -> None:
    if _STARTED:
        _STARTED.clear()
        _osascript('tell application "Notes" to quit')
        _wait_for("Notes to quit", lambda: not _running(), TIMEOUT * 3)


def _running() -> bool:
    return subprocess.run(["pgrep", "-x", APP], capture_output=True).returncode == 0


def _scriptable() -> bool:
    try:
        _data("folders")
        return True
    except UIError:
        return False


def _data(op: str, **args):
    return json.loads(_jxa(DATA, op, json.dumps(args)))


def _one(title: str, folder: str | None = None) -> str:
    ids = _data("find", title=title, folder=folder)
    where = f" in folder {folder!r}" if folder else ""
    if not ids:
        raise NotFound(f"no note titled {title!r}{where}")
    if len(ids) > 1:
        raise Ambiguous(f"{len(ids)} notes are titled {title!r}{where}; nothing was changed")
    return ids[0]


def _folder(name: str) -> None:
    found = [f for f in _data("folders") if f["name"] == name]
    if not found:
        raise NotFound(f"no folder named {name!r}")
    if len(found) > 1:
        raise Ambiguous(f"{len(found)} folders are named {name!r}; nothing was changed")


def _shape(note: dict, fields) -> dict:
    return {name: note[name] for name in _fields(fields)}


def _html(lines: str) -> str:
    return "".join(f"<div>{html.escape(line, quote=False) if line else '<br>'}</div>" for line in lines.split("\n"))


def _wait_for(what: str, test, timeout: float = TIMEOUT):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            value = test()
        except UIError:
            value = None
        if value:
            return value
        time.sleep(0.2)
    raise UIError(f"{what} did not happen within {timeout}s")


def _saved(note_id: str, test) -> dict:
    return _wait_for("the change being saved", lambda: next((n for n in _data("info", ids=[note_id]) if test(n)),
                                                            None))


# The screen -------------------------------------------------------------------------------------------------------

UI = """on run argv
  tell application "System Events" to tell process "Notes"
    try
      set w to missing value
      repeat with x in windows
        try
          if exists (first button of toolbar 1 of x whose description is "New Note") then
            set w to x
            exit repeat
          end if
        end try
      end repeat
%s
    end try
  end tell
  return "no"
end run"""


def _ui(body: str, *args: str) -> str:
    return _osascript(UI % body, *args)


def _until(what: str, body: str, *args: str) -> str:
    """Run a step until it returns something other than "no" (its element was there and it acted)."""
    deadline = time.monotonic() + TIMEOUT
    while time.monotonic() < deadline:
        answer = _ui(body, *args)
        if answer.startswith("blocked:"):
            raise StateBlocked(f"Notes shows {answer[8:]}; it was left as it is")
        if answer != "no":
            return answer
        time.sleep(0.1)
    raise UIError(f"{what} not found within {TIMEOUT}s")


FRONT = """      tell application "Notes" to activate
      set visible to true
      repeat with x in windows
        try
          if value of attribute "AXMinimized" of x is true then set value of attribute "AXMinimized" of x to false
        end try
      end repeat
      if w is missing value then
        tell application "Notes" to reopen
        return "no"
      end if
      perform action "AXRaise" of w
      if frontmost and (value of attribute "AXMinimized" of w) is false then return "ok\""""

TRANSIENT = """      repeat with b in menu bar items of menu bar 1
        if selected of b then
          key code 53
          return "no"
        end if
      end repeat
      if exists menu 1 then
        key code 53
        return "no"
      end if
      repeat with x in windows
        set extra to {}
        if x is not w and subrole of x is in {"AXDialog", "AXSystemDialog"} then set extra to {x}
        repeat with s in (sheets of x) & extra
          repeat with f in text fields of s
            if value of f is not "" then return "blocked:a dialog with typed text in it"
          end repeat
          if exists button "Cancel" of s then
            click button "Cancel" of s
            return "no"
          end if
          return "blocked:a dialog without a Cancel button (" & (description of s) & ")"
        end repeat
      end repeat
      if exists pop over 1 of w then
        key code 53
        return "no"
      end if
      repeat with g in {toolbar 1 of w} & (groups of toolbar 1 of w)
        repeat with f in text fields of g
          if subrole of f is "AXSearchField" and value of f is not missing value and value of f is not "" then
            if exists (first button of f whose description is "cancel") then
              click (first button of f whose description is "cancel")
            else
              set value of f to ""
            end if
            key code 53
            return "no"
          end if
        end repeat
      end repeat
      if not (exists (first outline of scroll area 1 of splitter group 1 of w whose description is "Folders")) then
        click (first button of toolbar 1 of w whose description is "Folders")
        return "no"
      end if
      return "ok\""""


def _ready() -> None:
    """Notes in front, its main window showing, with no menu, dialog, popover or search left open."""
    if not _running():
        subprocess.run(["open", "-b", BUNDLE_ID], check=True)
    _until("the Notes window in front", FRONT)
    _until("Notes with no menu, dialog or search open", TRANSIENT)


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
    return String(pb.changeCount);
  }
  const items = JSON.parse(argv[1]).map(pairs => {
    const item = $.NSPasteboardItem.alloc.init;
    pairs.forEach(([type, data]) => item.setDataForType($.NSData.alloc.initWithBase64EncodedStringOptions(data, 0), type));
    return item;
  });
  if (items.length) pb.writeObjects($(items));
  return "restored";
}"""

PASTE = """      if not frontmost then return "blocked:another app in front"
      keystroke "v" using command down
      return "ok\""""


def _paste(text: str, landed) -> None:
    """Paste text where the cursor is, wait until landed() sees it, then put the user's clipboard back."""
    saved = _jxa(CLIPBOARD, "save")
    try:
        _jxa(CLIPBOARD, "text", text)
        _until("the paste", PASTE)
        _wait_for("the pasted text to appear", landed)
    finally:
        _jxa(CLIPBOARD, "restore", saved)


EDITOR = """      repeat with a in scroll areas of splitter group 1 of w
        repeat with t in (text areas of a)
          if item 1 of argv is "" or (value of t starts with item 1 of argv) then
            set focused of t to true
            if focused of t then return "ok"
          end if
        end repeat
      end repeat"""

EDITOR_TEXT = """      repeat with a in scroll areas of splitter group 1 of w
        repeat with t in (text areas of a)
          if focused of t then
            if value of t is missing value then return ""
            return value of t
          end if
        end repeat
      end repeat"""

KEYS = """      if not frontmost then return "blocked:another app in front"
      repeat with k in argv
        set k to k as text
        if k starts with "shift+cmd+" then
          key code ((text 11 thru -1 of k) as integer) using {shift down, command down}
        else if k starts with "cmd+" then
          key code ((text 5 thru -1 of k) as integer) using command down
        else
          key code (k as integer)
        end if
      end repeat
      return "ok\""""

DOWN, UP, RIGHT, RETURN, DELETE = "125", "126", "124", "36", "51"


def _keys(*keys: str) -> None:
    _until("the keys", KEYS, *keys)


def _editor_text() -> str:
    return _ui(EDITOR_TEXT)


def _open_note(note_id: str, title: str) -> None:
    """Show the note and put the cursor in its text, after checking the editor holds that note."""
    _data("show", id=note_id)
    _until(f"the note {title!r} in the editor", EDITOR, title + "\n")


FOLDER_ROW = """      set sidebar to first outline of scroll area 1 of splitter group 1 of w whose description is "Folders"
      repeat with r in rows of sidebar
        try
          if value of UI element 1 of UI element 1 of UI element 1 of r is item 1 of argv then
            if item 2 of argv is "select" then
              set selected of r to true
              return "ok"
            end if
            perform action "AXShowMenu" of UI element 1 of r
            return "ok"
          end if
        end try
      end repeat"""

SHOWING = """      if name of w starts with (item 1 of argv & " – ") then return "ok"
      set sidebar to first outline of scroll area 1 of splitter group 1 of w whose description is "Folders"
      repeat with r in (rows of sidebar whose selected is true)
        if value of UI element 1 of UI element 1 of UI element 1 of r is item 1 of argv then return "ok"
      end repeat"""

BUTTON = """      click (first button of toolbar 1 of w whose description is item 1 of argv)
      return "ok\""""

NEW_NOTE = """      if name of w is not item 1 of argv then
        repeat with a in scroll areas of splitter group 1 of w
          repeat with t in (text areas of a)
            if focused of t and (value of t is "" or value of t is missing value) then return "ok"
          end repeat
        end repeat
      end if"""

MENU_ITEM = """      click menu item (item 2 of argv) of menu (item 1 of argv) of menu bar item (item 1 of argv) of menu bar 1
      return "ok\""""

MORE_ITEM = """      repeat with g in groups of toolbar 1 of w
        repeat with m in menu buttons of g
          if description of m is "More" then
            click m
            try
              if (count of argv) is 1 then
                click menu item (item 1 of argv) of menu 1 of m
              else
                click menu item (item 2 of argv) of menu 1 of menu item (item 1 of argv) of menu 1 of m
              end if
              return "ok"
            on error
              key code 53
            end try
          end if
        end repeat
      end repeat"""

SIDEBAR_FOCUS = """      set sidebar to first outline of scroll area 1 of splitter group 1 of w whose description is "Folders"
      set focused of sidebar to true
      if focused of sidebar then return "ok\""""

ALERT = """      repeat with x in windows
        repeat with s in sheets of x
          if exists button (item 1 of argv) of s then
            click button (item 1 of argv) of s
            set clicked to true
            return "no"
          end if
        end repeat
      end repeat
      if (count of argv) > 1 then return "ok\""""

DELETE_NOTICE = """      repeat with x in sheets of w
        if exists (first static text of x whose value starts with "Deleted notes are moved") then
          click button "OK" of x
          return "ok"
        end if
      end repeat"""

ALERT_SHOWN = """      repeat with x in windows
        repeat with s in sheets of x
          if exists button (item 1 of argv) of s then return "ok"
        end repeat
      end repeat"""

CLEAN = """      repeat with x in windows
        if (count of sheets of x) > 0 then return "no"
      end repeat
      if exists menu 1 then return "no"
      return "ok\""""


def _select_folder(name: str) -> None:
    _until(f"the folder row {name!r}", FOLDER_ROW, name, "select")
    _until(f"the folder {name!r} on screen", SHOWING, name)


def _new_note() -> None:
    before = _ui('      return name of w')
    _until("the New Note button", BUTTON, "New Note")
    _until("the new note's empty text area", NEW_NOTE, before)


def _done() -> None:
    _until("Notes with no dialog or menu left open", CLEAN)


# Notes ------------------------------------------------------------------------------------------------------------

def note_create(title: str, body: str = "", folder: str | None = None, mode: str = "ui") -> dict:
    """Make a note titled title with body as its text, in folder (default: the Notes folder)."""
    _mode("note_create", mode)
    if "\n" in title or not title.strip():
        raise ValueError("title must be one non-empty line")
    _ready_for(mode)
    if folder is not None:
        _folder(folder)
    before = set(_data("find", title=title, folder=None))
    if mode == "background":
        note_id = _data("create", html=_html(title + ("\n" + body if body else "")), folder=folder)
    else:
        _select_folder(folder if folder is not None else _data("default_folder"))
        _new_note()
        text = title + ("\n" + body if body else "")
        _paste(text, lambda: _editor_text() == text)
        note_id = _wait_for("the new note to be saved",
                            lambda: next(iter(set(_data("find", title=title, folder=None)) - before), None))
        _done()
    note = _saved(note_id, lambda n: n["title"] == title and n["body"] == body)
    return _checked("note_create", mode, _shape(note, "id," + DEFAULT_FIELDS))


def checklist_create(title: str, items: list, folder: str | None = None, mode: str = "ui") -> dict:
    """Make a note titled title holding a real Notes checklist with one unchecked item per entry of items."""
    _mode("checklist_create", mode, ("ui",))
    if not items or any("\n" in item or not item.strip() for item in items):
        raise ValueError("items must be non-empty single lines")
    _ready_for(mode)
    if folder is not None:
        _folder(folder)
    before = set(_data("find", title=title, folder=None))
    _select_folder(folder if folder is not None else _data("default_folder"))
    _new_note()
    _paste(title, lambda: _editor_text() == title)
    _keys(RETURN)
    _until("the Checklist button", BUTTON, "Checklist")
    _paste("\n".join(items), lambda: _editor_text() == title + "\n" + "\n".join(items))
    note_id = _wait_for("the new note to be saved",
                        lambda: next(iter(set(_data("find", title=title, folder=None)) - before), None))
    _done()
    note = _saved(note_id, lambda n: n["body"] == "\n".join(items))
    return _checked("checklist_create", mode, {**_shape(note, "id," + DEFAULT_FIELDS), "items": list(items)})


def note_get(match: str, fields=None, folder: str | None = None, mode: str = "background") -> dict:
    """The note titled exactly match (optionally only in folder)."""
    _mode("note_get", mode, ("background",))
    _ready_for(mode)
    return _checked("note_get", mode, _shape(_data("info", ids=[_one(match, folder)])[0], fields))


def note_search(query: str, limit: int = 20, fields=None, mode: str = "background") -> list:
    """Notes whose title or text contains query (any case), newest first."""
    _mode("note_search", mode, ("background",))
    _ready_for(mode)
    return _checked("note_search", mode, [_shape(n, fields) for n in _data("search", query=query, limit=limit)])


def note_list(folder: str | None = None, limit: int = 50, fields=None, mode: str = "background") -> list:
    """Notes in folder (default: every folder), newest first."""
    _mode("note_list", mode, ("background",))
    _ready_for(mode)
    if folder is not None:
        _folder(folder)
    return _checked("note_list", mode, [_shape(n, fields) for n in _data("list", folder=folder, limit=limit)])


def note_append(match: str, text: str, folder: str | None = None, mode: str = "ui") -> dict:
    """Add text as new lines at the end of the note titled match."""
    _mode("note_append", mode)
    _ready_for(mode)
    note_id = _one(match, folder)
    old = _data("info", ids=[note_id])[0]
    body = old["body"] + ("\n" if old["body"] else "") + text
    if mode == "background":
        _data("set_body", id=note_id, html=_data("body", id=note_id) + _html(text))
    else:
        _open_note(note_id, match)
        _keys(f"cmd+{DOWN}")
        added = text if _data("plain", id=note_id).endswith("\n") else "\n" + text
        _paste(added, lambda: _editor_text() == match + "\n" + body)
        _done()
    return _checked("note_append", mode, _shape(_saved(note_id, lambda n: n["body"] == body), "id," + DEFAULT_FIELDS))


def note_rename(match: str, title: str, folder: str | None = None, mode: str = "ui") -> dict:
    """Change the title (first line) of the note titled match."""
    _mode("note_rename", mode)
    if "\n" in title or not title.strip():
        raise ValueError("title must be one non-empty line")
    _ready_for(mode)
    note_id = _one(match, folder)
    body = _data("info", ids=[note_id])[0]["body"]
    if mode == "background":
        _data("set_name", id=note_id, title=title)
    else:
        _open_note(note_id, match)
        _keys(f"cmd+{UP}", f"shift+cmd+{RIGHT}")
        _paste(title, lambda: _editor_text() == title + ("\n" + body if body else ""))
        _done()
    note = _saved(note_id, lambda n: n["title"] == title and n["body"] == body)
    return _checked("note_rename", mode, _shape(note, "id," + DEFAULT_FIELDS))


def note_replace_body(match: str, body: str, folder: str | None = None, mode: str = "ui") -> dict:
    """Replace everything after the title of the note titled match with body."""
    _mode("note_replace_body", mode)
    _ready_for(mode)
    note_id = _one(match, folder)
    if mode == "background":
        _data("set_body", id=note_id, html=_html(match + ("\n" + body if body else "")))
    else:
        _open_note(note_id, match)
        _keys(f"cmd+{UP}", f"cmd+{RIGHT}", f"shift+cmd+{DOWN}")
        if body:
            _paste("\n" + body, lambda: _editor_text() == match + "\n" + body)
        else:
            _keys(DELETE)
        _done()
    note = _saved(note_id, lambda n: n["title"] == match and n["body"] == body)
    return _checked("note_replace_body", mode, _shape(note, "id," + DEFAULT_FIELDS))


def note_move(match: str, folder: str, from_folder: str | None = None, mode: str = "ui") -> dict:
    """Move the note titled match into folder."""
    _mode("note_move", mode)
    _ready_for(mode)
    note_id = _one(match, from_folder)
    _folder(folder)
    if mode == "background":
        _data("move", id=note_id, folder=folder)
    else:
        _open_note(note_id, match)
        _until("Move to in the note's More menu", MORE_ITEM, "Move to", folder)
        _done()
    note = _saved(note_id, lambda n: n["folder"] == folder)
    return _checked("note_move", mode, _shape(note, "id," + DEFAULT_FIELDS))


def note_delete(match: str, folder: str | None = None, mode: str = "ui") -> dict:
    """Move the note titled match to Recently Deleted. Returns the note as it was."""
    _mode("note_delete", mode)
    _ready_for(mode)
    note_id = _one(match, folder)
    note = _data("info", ids=[note_id])[0]
    if mode == "background":
        _data("delete", id=note_id)
    else:
        _open_note(note_id, match)
        _until("Delete Note in the note's More menu", MORE_ITEM, "Delete Note")
        _wait_for("the note leaving its folder", lambda: note_id not in _data("find", title=match, folder=None)
                  or _ui(DELETE_NOTICE) == "ok")
        _done()
    _wait_for("the note leaving its folder", lambda: note_id not in _data("find", title=match, folder=None))
    return _checked("note_delete", mode, {**_shape(note, "id," + DEFAULT_FIELDS), "deleted": True})


def note_pin(match: str, folder: str | None = None, mode: str = "ui") -> dict:
    """Pin the note titled match (it stays pinned if it already is)."""
    _mode("note_pin", mode, ("ui",))
    _ready_for(mode)
    note_id = _one(match, folder)
    _open_note(note_id, match)
    _until("Pin Note in the File menu", MENU_ITEM, "File", "Pin Note")
    _done()
    return _checked("note_pin", mode, {**_shape(_data("info", ids=[note_id])[0], "id," + DEFAULT_FIELDS),
                                       "pinned": True})


# Folders ----------------------------------------------------------------------------------------------------------

def folder_create(name: str, mode: str = "ui") -> dict:
    """Make a top-level folder named name in On My Mac."""
    _mode("folder_create", mode)
    if not name.strip() or "\n" in name:
        raise ValueError("name must be one non-empty line")
    _ready_for(mode)
    if any(f["name"] == name for f in _data("folders")):
        raise AlreadyExists(f"a folder named {name!r} already exists")
    if mode == "background":
        _data("folder_create", name=name)
    else:
        _until("the Add Folder button", BUTTON, "Add Folder")
        _until("the new folder's name field", NEW_FOLDER)
        _paste(name, lambda: _ui(NEW_FOLDER_VALUE) == name)
        _keys(RETURN)
        _done()
    found = _wait_for("the folder to be saved", lambda: [f for f in _data("folders") if f["name"] == name])
    return _checked("folder_create", mode, {"name": name, "notes": found[0]["notes"]})


NEW_FOLDER = """      set f to value of attribute "AXFocusedUIElement"
      if role of f is "AXTextField" and subrole of f is not "AXSearchField" then return "ok\""""

NEW_FOLDER_VALUE = """      set f to value of attribute "AXFocusedUIElement"
      if role of f is "AXTextField" then return value of f"""


def folder_list(mode: str = "background") -> list:
    """Every folder in On My Mac (except Recently Deleted), with its number of notes."""
    _mode("folder_list", mode, ("background",))
    _ready_for(mode)
    return _checked("folder_list", mode, [{"name": f["name"], "notes": f["notes"]} for f in _data("folders")])


def folder_rename(name: str, to: str, mode: str = "ui") -> dict:
    """Rename the folder named name to to."""
    _mode("folder_rename", mode)
    if not to.strip() or "\n" in to:
        raise ValueError("to must be one non-empty line")
    _ready_for(mode)
    _folder(name)
    if any(f["name"] == to for f in _data("folders")):
        raise AlreadyExists(f"a folder named {to!r} already exists")
    if mode == "background":
        _data("folder_rename", name=name, to=to)
    else:
        _select_folder(name)
        _until("the folder list focused", SIDEBAR_FOCUS)
        _until("Rename Folder in the Edit menu", MENU_ITEM, "Edit", "Rename Folder")
        _until("the folder's name field", NEW_FOLDER)
        _keys("cmd+0")
        _paste(to, lambda: _ui(NEW_FOLDER_VALUE) == to)
        _keys(RETURN)
        _done()
    found = _wait_for("the rename to be saved", lambda: [f for f in _data("folders") if f["name"] == to])
    return _checked("folder_rename", mode, {"name": to, "notes": found[0]["notes"]})


def folder_delete(name: str, mode: str = "ui") -> dict:
    """Delete the folder named name; its notes go to Recently Deleted."""
    _mode("folder_delete", mode)
    _ready_for(mode)
    _folder(name)
    folder = next(f for f in _data("folders") if f["name"] == name)
    if mode == "background":
        _data("folder_delete", name=name)
    else:
        _select_folder(name)
        _until("the folder list focused", SIDEBAR_FOCUS)
        _until("Delete Folder in the Edit menu", MENU_ITEM, "Edit", "Delete Folder")
        _until("the Delete button of the confirmation", ALERT_SHOWN, "Delete")
        _until("the confirmation to close", ALERT, "Delete", "until gone")
        _done()
    _wait_for("the folder to go", lambda: not [f for f in _data("folders") if f["name"] == name])
    return _checked("folder_delete", mode, {"name": name, "notes": folder["notes"], "deleted": True})


def _ready_for(mode: str) -> None:
    if mode == "ui":
        _ready()
    else:
        _launch_hidden()
