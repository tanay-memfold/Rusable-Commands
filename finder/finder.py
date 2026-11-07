"""Finder commands for agents: plain functions with keyword arguments, for files and folders.

mode="ui" does the change on screen in a Finder window: Go to Folder, the item's row in list view found by its exact
name, and menu items found by name (Move to Trash, New Folder, Copy, Paste Item, Move Item Here). Names are pasted through
the clipboard, which is restored afterwards.
mode="background" makes the change through the macOS file APIs and shows nothing; Finder shows the result. Reads use the
file system directly.

Set FINDER_ALLOWED_ROOT to a folder and every path is checked to be inside it, after following links, before anything
happens: a path outside raises OutsideAllowedRoot. Emptying the Trash and permanent delete aren't here on purpose.

Paths are absolute or start with ~. Errors: NotFound, AlreadyExists, OutsideAllowedRoot, StateBlocked (the screen holds
something the call won't destroy), UIError (an element never appeared), NotSupported (the mode can't do it)."""
from __future__ import annotations

import datetime as _dt
import fnmatch
import json
import os
import plistlib
import shutil
import subprocess
import time
import unicodedata
import warnings

APP = "Finder"
TIMEOUT = 10
SAVE_TIMEOUT = 15
FIELDS = ("name", "path", "kind", "size", "created_date", "modified_date")
DEFAULT_FIELDS = "name,path,kind,size,modified_date"
ROOT_ENV = "FINDER_ALLOWED_ROOT"

VERIFIED: dict = {
    "file_add_tag": {
        "ui": {
            "macos": "15.6.1 (24G90)",
            "app": "15.5 (1732.6.4)"
        }
    },
    "file_compress": {
        "ui": {
            "macos": "15.6.1 (24G90)",
            "app": "15.5 (1732.6.4)"
        }
    },
    "file_copy": {
        "background": {
            "macos": "15.6.1 (24G90)",
            "app": "15.5 (1732.6.4)"
        },
        "ui": {
            "macos": "15.6.1 (24G90)",
            "app": "15.5 (1732.6.4)"
        }
    },
    "file_duplicate": {
        "ui": {
            "macos": "15.6.1 (24G90)",
            "app": "15.5 (1732.6.4)"
        }
    },
    "file_extract": {
        "ui": {
            "macos": "15.6.1 (24G90)",
            "app": "15.5 (1732.6.4)"
        }
    },
    "file_find": {
        "background": {
            "macos": "15.6.1 (24G90)",
            "app": "15.5 (1732.6.4)"
        }
    },
    "file_info": {
        "background": {
            "macos": "15.6.1 (24G90)",
            "app": "15.5 (1732.6.4)"
        }
    },
    "file_list": {
        "background": {
            "macos": "15.6.1 (24G90)",
            "app": "15.5 (1732.6.4)"
        }
    },
    "file_make_alias": {
        "ui": {
            "macos": "15.6.1 (24G90)",
            "app": "15.5 (1732.6.4)"
        }
    },
    "file_move": {
        "background": {
            "macos": "15.6.1 (24G90)",
            "app": "15.5 (1732.6.4)"
        },
        "ui": {
            "macos": "15.6.1 (24G90)",
            "app": "15.5 (1732.6.4)"
        }
    },
    "file_open_with": {
        "ui": {
            "macos": "15.6.1 (24G90)",
            "app": "15.5 (1732.6.4)"
        }
    },
    "file_put_back": {
        "ui": {
            "macos": "15.6.1 (24G90)",
            "app": "15.5 (1732.6.4)"
        }
    },
    "file_rename": {
        "background": {
            "macos": "15.6.1 (24G90)",
            "app": "15.5 (1732.6.4)"
        },
        "ui": {
            "macos": "15.6.1 (24G90)",
            "app": "15.5 (1732.6.4)"
        }
    },
    "file_reveal": {
        "ui": {
            "macos": "15.6.1 (24G90)",
            "app": "15.5 (1732.6.4)"
        }
    },
    "file_set_locked": {
        "background": {
            "macos": "15.6.1 (24G90)",
            "app": "15.5 (1732.6.4)"
        },
        "ui": {
            "macos": "15.6.1 (24G90)",
            "app": "15.5 (1732.6.4)"
        }
    },
    "file_trash": {
        "background": {
            "macos": "15.6.1 (24G90)",
            "app": "15.5 (1732.6.4)"
        },
        "ui": {
            "macos": "15.6.1 (24G90)",
            "app": "15.5 (1732.6.4)"
        }
    },
    "folder_create": {
        "background": {
            "macos": "15.6.1 (24G90)",
            "app": "15.5 (1732.6.4)"
        },
        "ui": {
            "macos": "15.6.1 (24G90)",
            "app": "15.5 (1732.6.4)"
        }
    },
    "folder_new_with_selection": {
        "ui": {
            "macos": "15.6.1 (24G90)",
            "app": "15.5 (1732.6.4)"
        }
    },
    "folder_open": {
        "ui": {
            "macos": "15.6.1 (24G90)",
            "app": "15.5 (1732.6.4)"
        }
    }
}


class FinderError(Exception):
    pass


class NotFound(FinderError):
    pass


class Ambiguous(FinderError):
    pass


class AlreadyExists(FinderError):
    pass


class StateBlocked(FinderError):
    pass


class UIError(FinderError):
    pass


class NotSupported(FinderError):
    pass


class OutsideAllowedRoot(FinderError):
    pass


def _run(args: list) -> str:
    done = subprocess.run(args, capture_output=True, text=True)
    if done.returncode:
        raise UIError(done.stderr.strip())
    return done.stdout.strip()


def _osascript(script: str, *args: str) -> str:
    return _run(["osascript", "-e", script, *args])


def _jxa(script: str, *args: str) -> str:
    return _run(["osascript", "-l", "JavaScript", "-e", script, *args])


def _versions() -> dict:
    macos = f"{_run(['sw_vers', '-productVersion'])} ({_run(['sw_vers', '-buildVersion'])})"
    with open("/System/Library/CoreServices/Finder.app/Contents/Info.plist", "rb") as handle:
        info = plistlib.load(handle)
    return {"macos": macos, "app": f"{info['CFBundleShortVersionString']} ({info['CFBundleVersion']})"}


def _checked(function: str, mode: str, result):
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


ON_SCREEN = "showing something on screen is all this command does"
UNSUPPORTED = {("file_reveal", "background"): ON_SCREEN, ("folder_open", "background"): ON_SCREEN}


def _mode(function: str, mode: str, supported: tuple = ("ui", "background")) -> None:
    if mode not in ("ui", "background"):
        raise ValueError(f"mode must be 'ui' or 'background', not {mode!r}")
    if VERIFIED and mode not in VERIFIED.get(function, {}):
        raise NotSupported(f"{function} has no verified {mode} mode: "
                           f"{UNSUPPORTED.get((function, mode), 'it did not pass verification')}")
    if mode not in supported:
        raise NotSupported(f"{function} has no {mode} mode: "
                           f"{UNSUPPORTED.get((function, mode), 'it reads data, which the background mode does')}")


def _fields(fields) -> list:
    chosen = [part.strip() for part in (fields or DEFAULT_FIELDS).split(",")] if isinstance(fields, (str, type(None))) \
        else list(fields)
    unknown = [name for name in chosen if name not in FIELDS]
    if unknown:
        raise ValueError(f"unknown fields {unknown}; choose from {', '.join(FIELDS)}")
    return chosen


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


# Files ------------------------------------------------------------------------------------------------------------

def _path(path: str) -> str:
    full = os.path.abspath(os.path.expanduser(path))
    root = os.environ.get(ROOT_ENV)
    if root:
        allowed, real = os.path.realpath(os.path.expanduser(root)), os.path.realpath(full)
        if real != allowed and not real.startswith(allowed + os.sep):
            raise OutsideAllowedRoot(f"{full} is outside {ROOT_ENV}; nothing was done")
    return full


def _existing(path: str, kind: str = "item") -> str:
    full = _path(path)
    if not os.path.lexists(full):
        raise NotFound(f"no {kind} at {full}")
    return full


def _folder(path: str) -> str:
    full = _existing(path, "folder")
    if not os.path.isdir(full):
        raise NotFound(f"{full} is not a folder")
    return full


def _free(path: str) -> None:
    if os.path.lexists(path):
        raise AlreadyExists(f"{path} already exists")


def _when(seconds: float) -> str:
    return _dt.datetime.fromtimestamp(seconds).strftime("%Y-%m-%d %H:%M")


def _info(full: str) -> dict:
    stat = os.lstat(full)
    kind = "link" if os.path.islink(full) else "folder" if os.path.isdir(full) else "file"
    return {"name": os.path.basename(full), "path": full, "kind": kind,
            "size": None if kind == "folder" else stat.st_size, "created_date": _when(stat.st_birthtime),
            "modified_date": _when(stat.st_mtime)}


def _shape(item: dict, fields) -> dict:
    return {name: item[name] for name in _fields(fields)}


def _wait_exists(path: str, present: bool = True) -> None:
    _wait_for(f"{path} to {'appear' if present else 'go'}", lambda: os.path.lexists(path) == present, SAVE_TIMEOUT)


TRASH = r"""
ObjC.import("Foundation");
function run(argv) {
  const url = $.NSURL.fileURLWithPath(argv[0]);
  const error = Ref();
  if (!$.NSFileManager.defaultManager.trashItemAtURLResultingItemURLError(url, null, error)) {
    throw new Error("could not move to the Trash: " + ObjC.unwrap(error[0].localizedDescription));
  }
  return "true";
}"""


def _background(op: str, **args) -> None:
    """The change through the macOS file APIs: nothing on screen, and Finder shows the result."""
    if op == "make_folder":
        os.mkdir(os.path.join(args["parent"], args["name"]))
    elif op == "duplicate":
        target = os.path.join(args["to"], os.path.basename(args["path"]))
        if os.path.isdir(args["path"]):
            shutil.copytree(args["path"], target, symlinks=True)
        else:
            shutil.copy2(args["path"], target, follow_symlinks=False)
    elif op == "move":
        shutil.move(args["path"], os.path.join(args["to"], os.path.basename(args["path"])))
    elif op == "rename":
        os.rename(args["path"], os.path.join(os.path.dirname(args["path"]), args["to"]))
    elif op == "trash":
        _jxa(TRASH, args["path"])


# The screen -------------------------------------------------------------------------------------------------------

UI = """on run argv
  tell application "System Events" to tell process "Finder"
    try
      set w to missing value
      repeat with x in windows
        try
          if subrole of x is "AXStandardWindow" and (exists toolbar 1 of x) then
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
    deadline = time.monotonic() + TIMEOUT
    while time.monotonic() < deadline:
        answer = _ui(body, *args)
        if answer.startswith("blocked:"):
            raise StateBlocked(f"Finder shows {answer[8:]}; it was left as it is")
        if answer != "no":
            return answer
        time.sleep(0.1)
    raise UIError(f"{what} not found within {TIMEOUT}s")


FRONT = """      set visible to true
      set frontmost to true
      repeat with x in windows
        try
          if value of attribute "AXMinimized" of x is true then set value of attribute "AXMinimized" of x to false
        end try
      end repeat
      if w is missing value then
        keystroke "n" using command down
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
          key code 53
          return "no"
        end repeat
      end repeat
      if exists pop over 1 of w then
        repeat with f in text fields of pop over 1 of w
          if description of f is "New Quick Event" and value of f is not "" then return "blocked:a quick event with typed text"
        end repeat
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
      set f to value of attribute "AXFocusedUIElement"
      if role of f is "AXTextField" and subrole of f is not "AXSearchField" then return "blocked:a name being edited"
      return "ok\""""


EDITING_NOW = """      if frontmost and subrole of window 1 is "AXStandardWindow" and (count of sheets of window 1) is 0 then
        set f to value of attribute "AXFocusedUIElement"
        if role of f is "AXTextField" and subrole of f is not "AXSearchField" then return "blocked:a name being edited"
      end if"""


def _ready() -> None:
    """Finder in front with a window showing, and no menu, dialog, popover or search left open."""
    # Checked first, because raising the window ends the edit and keeps the half-typed name.
    if _ui(EDITING_NOW).startswith("blocked:"):
        raise StateBlocked("Finder has a name being edited; it was left as it is")
    _until("a Finder window in front", FRONT)
    _until("Finder with no menu, dialog, popover or search open", TRANSIENT)


def _ready_for(mode: str) -> None:
    if mode == "ui":
        _ready()


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
  const input = $.NSFileHandle.fileHandleWithStandardInput.readDataToEndOfFile;
  const items = JSON.parse(ObjC.unwrap($.NSString.alloc.initWithDataEncoding(input, $.NSUTF8StringEncoding))).map(pairs => {
    const item = $.NSPasteboardItem.alloc.init;
    pairs.forEach(([type, data]) => item.setDataForType($.NSData.alloc.initWithBase64EncodedStringOptions(data, 0), type));
    return item;
  });
  if (items.length) pb.writeObjects($(items));
  return "restored";
}"""

KEYS = """      if not frontmost then return "blocked:another app in front"
      repeat with k in argv
        set k to k as text
        if k starts with "type:" then
          keystroke (text 6 thru -1 of k)
        else if k starts with "cmd+opt+" then
          key code ((text 9 thru -1 of k) as integer) using {command down, option down}
        else if k starts with "cmd+" then
          key code ((text 5 thru -1 of k) as integer) using command down
        else
          key code (k as integer)
        end if
      end repeat
      return "ok\""""

RETURN, TAB, ESCAPE, SELECT_ALL, PASTE, DELETE = "36", "48", "53", "cmd+0", "cmd+9", "51"


def _keys(*keys: str) -> None:
    _until("the keys", KEYS, *keys)


FOCUSED = """      set f to value of attribute "AXFocusedUIElement"
      if role of f is in {"AXTextField", "AXTextArea"} then
        if value of f is missing value then return ""
        return value of f
      end if"""


def _focused_text() -> str:
    return _ui(FOCUSED)


def _paste(text: str, replace: bool = True) -> None:
    """Paste text into the focused field (replacing its text), wait until it shows, restore the clipboard."""
    saved = _jxa(CLIPBOARD, "save")
    try:
        _jxa(CLIPBOARD, "text", text)
        _keys(*((SELECT_ALL,) if replace else ()), PASTE)
        _wait_for("the pasted text to appear", lambda: _focused_text() == text or None)
    finally:
        # What was on the clipboard can be too large for an argument, so it goes through standard input.
        done = subprocess.run(["osascript", "-l", "JavaScript", "-e", CLIPBOARD, "restore"], input=saved,
                              capture_output=True, text=True)
        if done.returncode:
            raise UIError(done.stderr.strip())


MENU_ITEM = """      if (count of argv) is 2 then
        click menu item (item 2 of argv) of menu (item 1 of argv) of menu bar item (item 1 of argv) of menu bar 1
      else
        click menu item (item 3 of argv) of menu 1 of menu item (item 2 of argv) of menu (item 1 of argv) of menu bar item (item 1 of argv) of menu bar 1
      end if
      return "ok\""""

NAME_FIELD = """      set f to value of attribute "AXFocusedUIElement"
      if role of f is "AXTextField" and subrole of f is not "AXSearchField" then return "ok\""""

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

ALERT_SHOWN = """      repeat with x in windows
        repeat with s in sheets of x
          if exists button (item 1 of argv) of s then return "ok"
        end repeat
      end repeat"""

CLEAN = """      repeat with x in windows
        if (count of sheets of x) > 0 then return "no"
      end repeat
      if exists pop over 1 of w then return "no"
      if exists menu 1 then return "no"
      return "ok\""""


GO_SHEET = """      repeat with s in sheets of w
        repeat with f in text fields of s
          set focused of f to true
          if focused of f then return "ok"
        end repeat
      end repeat
      repeat with x in windows
        if subrole of x is "AXDialog" or subrole of x is "AXSystemDialog" then
          repeat with f in text fields of x
            set focused of f to true
            if focused of f then return "ok"
          end repeat
        end if
      end repeat"""

SHOWING = """      if name of w is item 1 of argv then return "ok\""""

AS_LIST = """      click menu item "as List" of menu "View" of menu bar item "View" of menu bar 1
      return "ok\""""

ROW = """      repeat with o in outlines of scroll area 1 of splitter group 1 of splitter group 1 of w
        repeat with r in rows of o
          try
            repeat with e in (UI elements of UI element 1 of r)
              if role of e is "AXTextField" and value of e is item 1 of argv then
                set selected of r to true
                set focused of o to true
                if selected of r then return "ok"
              end if
            end repeat
          end try
        end repeat
      end repeat"""

EDITING = """      set f to value of attribute "AXFocusedUIElement"
      if role of f is "AXTextField" and subrole of f is not "AXSearchField" then return "ok\""""

MENU_ITEM_ALT = """      repeat with i in menu items of menu (item 1 of argv) of menu bar item (item 1 of argv) of menu bar 1
        if name of i is item 2 of argv then
          click i
          return "ok"
        end if
      end repeat"""


class _ClipboardKept:
    """Copy and Paste of files go through the clipboard; what was on it is put back afterwards, through standard input."""

    def __enter__(self):
        self.saved = _jxa(CLIPBOARD, "save")

    def __exit__(self, *exc):
        done = subprocess.run(["osascript", "-l", "JavaScript", "-e", CLIPBOARD, "restore"], input=self.saved,
                              capture_output=True, text=True)
        if done.returncode and exc[0] is None:
            raise UIError(done.stderr.strip())


def _go(folder: str) -> None:
    """Show folder in the front Finder window, in list view."""
    _until("Go to Folder… in the Go menu", MENU_ITEM, "Go", "Go to Folder…")
    _until("the Go to Folder field", GO_SHEET)
    _paste(folder)
    _keys(RETURN)
    _until(f"the folder {os.path.basename(folder) or folder!r} in the window", SHOWING, os.path.basename(folder))
    _until("as List in the View menu", AS_LIST)


def _select(full: str) -> None:
    _go(os.path.dirname(full))
    _until(f"the row {os.path.basename(full)!r}", ROW, os.path.basename(full))


def _rename_selected(name: str) -> None:
    _keys(RETURN)
    _until("the name field", EDITING)
    _paste(name)
    _keys(RETURN)


def _done() -> None:
    _until("Finder with no popover, dialog or menu left open", CLEAN)


# Functions --------------------------------------------------------------------------------------------------------

def file_list(folder: str, limit: int = 100, fields=None, mode: str = "background") -> list:
    """The files and folders directly in folder (hidden ones left out), by name."""
    _mode("file_list", mode, ("background",))
    full = _folder(folder)
    names = sorted(n for n in os.listdir(full) if not n.startswith("."))[:limit]
    return _checked("file_list", mode, [_shape(_info(os.path.join(full, n)), fields) for n in names])


def file_find(query: str, folder: str = "~", limit: int = 100, fields=None, mode: str = "background") -> list:
    """Files and folders under folder whose name contains query (any case) or matches it as a pattern (*.pdf),
    newest first. Hidden folders and Library are skipped."""
    _mode("file_find", mode, ("background",))
    root = _folder(folder)
    q = query.lower()
    found = []
    for base, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if not d.startswith(".") and not (base == os.path.expanduser("~") and d == "Library")]
        for name in dirs + files:
            if name.startswith("."):
                continue
            if q in name.lower() or fnmatch.fnmatch(name.lower(), q):
                found.append(_info(os.path.join(base, name)))
    found.sort(key=lambda item: item["modified_date"], reverse=True)
    return _checked("file_find", mode, [_shape(item, fields) for item in found[:limit]])


def file_info(path: str, fields=None, mode: str = "background") -> dict:
    _mode("file_info", mode, ("background",))
    return _checked("file_info", mode, _shape(_info(_existing(path)), fields))


def folder_create(path: str, mode: str = "ui") -> dict:
    """Make the folder at path (its parent must exist)."""
    _mode("folder_create", mode)
    full = _path(path)
    parent = _folder(os.path.dirname(full))
    _free(full)
    if mode == "background":
        _background("make_folder", parent=parent, name=os.path.basename(full))
    else:
        _ready()
        _go(parent)
        time.sleep(0.8)
        before = set(os.listdir(parent))
        _until("New Folder in the File menu", MENU_ITEM, "File", "New Folder")
        try:
            _until("the new folder's name field", EDITING)
        except UIError:
            # The folder was made but its name isn't being edited: select only that new folder and edit its name.
            new = [n for n in set(os.listdir(parent)) - before if n.startswith("untitled folder")]
            if len(new) != 1:
                raise
            _until(f"the row {new[0]!r}", ROW, new[0])
            _keys(RETURN)
            _until("the new folder's name field", EDITING)
        _paste(os.path.basename(full))
        _keys(RETURN)
        _done()
    _wait_exists(full)
    return _checked("folder_create", mode, _shape(_info(full), None))


def file_copy(path: str, to_folder: str, mode: str = "ui") -> dict:
    """Copy the file or folder at path into to_folder. Returns the copy."""
    _mode("file_copy", mode)
    full = _existing(path)
    target = _folder(to_folder)
    copy = os.path.join(target, os.path.basename(full))
    _free(copy)
    if mode == "background":
        _background("duplicate", path=full, to=target)
    else:
        _ready()
        with _ClipboardKept():
            _select(full)
            _until("Copy in the Edit menu", MENU_ITEM_ALT, "Edit", f"Copy “{os.path.basename(full)}”")
            _go(target)
            _until("Paste Item in the Edit menu", MENU_ITEM_ALT, "Edit", "Paste Item")
            _wait_exists(copy)
        _done()
    _wait_exists(copy)
    return _checked("file_copy", mode, _shape(_info(copy), None))


def file_move(path: str, to_folder: str, mode: str = "ui") -> dict:
    """Move the file or folder at path into to_folder. Returns it at its new place."""
    _mode("file_move", mode)
    full = _existing(path)
    target = _folder(to_folder)
    moved = os.path.join(target, os.path.basename(full))
    _free(moved)
    if mode == "background":
        _background("move", path=full, to=target)
    else:
        _ready()
        with _ClipboardKept():
            _select(full)
            _until("Copy in the Edit menu", MENU_ITEM_ALT, "Edit", f"Copy “{os.path.basename(full)}”")
            _go(target)
            _keys("cmd+opt+9")
            _wait_exists(moved)
        _done()
    _wait_exists(moved)
    _wait_exists(full, False)
    return _checked("file_move", mode, _shape(_info(moved), None))


def file_rename(path: str, to: str, mode: str = "ui") -> dict:
    """Rename the file or folder at path to the name to (same folder)."""
    _mode("file_rename", mode)
    if not to or to in (".", "..") or "/" in to or "\n" in to:
        raise ValueError("to must be a single name without / or line breaks")
    full = _existing(path)
    renamed = os.path.join(os.path.dirname(full), to)
    _free(renamed)
    if mode == "background":
        _background("rename", path=full, to=to)
    else:
        _ready()
        _select(full)
        _rename_selected(to)
        _done()
    _wait_exists(renamed)
    return _checked("file_rename", mode, _shape(_info(renamed), None))


def file_trash(path: str, mode: str = "ui") -> dict:
    """Move the file or folder at path to the Trash. Returns it as it was, with "trashed": True."""
    _mode("file_trash", mode)
    full = _existing(path)
    before = _info(full)
    if mode == "background":
        _background("trash", path=full)
    else:
        _ready()
        _select(full)
        _until("Move to Trash in the File menu", MENU_ITEM, "File", "Move to Trash")
        _done()
    _wait_exists(full, False)
    return _checked("file_trash", mode, {**_shape(before, None), "trashed": True})


def file_reveal(path: str, mode: str = "ui") -> dict:
    """Show the file or folder at path selected in a Finder window. Nothing changes on disk."""
    _mode("file_reveal", mode, ("ui",))
    full = _existing(path)
    _ready()
    _select(full)
    _done()
    return _checked("file_reveal", mode, {**_shape(_info(full), None), "revealed": True})


def folder_open(path: str, mode: str = "ui") -> dict:
    """Show the folder at path in a Finder window. Nothing changes on disk."""
    _mode("folder_open", mode, ("ui",))
    full = _folder(path)
    _ready()
    _go(full)
    _done()
    return _checked("folder_open", mode, {**_shape(_info(full), None), "opened": True})


# More commands (UI only) ------------------------------------------------------------------------------------------
# These use Finder's own menus. Finder has no scripting or file API that is the same action, so there is no background mode.

SELECT_ITEMS = """on run argv
  tell application "Finder"
    set f to (POSIX file (item 1 of argv)) as alias
    set picked to {}
    repeat with i from 2 to count of argv
      set end of picked to item (item i of argv) of folder f
    end repeat
    select picked
  end tell
  return "ok"
end run"""

SELECTED_NAMES = """tell application "Finder"
  set names to {}
  repeat with x in (selection as list)
    set end of names to (name of x)
  end repeat
end tell
set AppleScript's text item delimiters to linefeed
return names as text"""

TAG_FIELD = """      repeat with x in windows
        if name of x is (item 1 of argv) then
          repeat with a in ({x} & scroll areas of x & scroll areas of scroll area 1 of x)
            repeat with f in text fields of a
              try
                if value of attribute "AXDescription" of f is "tag editor" then
                  set focused of f to true
                  if focused of f then return "ok"
                end if
              end try
            end repeat
          end repeat
        end if
      end repeat"""

CLOSE_INFO = """      repeat with x in windows
        if name of x is (item 1 of argv) then
          click (first button of x whose subrole is "AXCloseButton")
          return "no"
        end if
      end repeat
      return "ok\""""

TRASH_DIR = os.path.expanduser("~/.Trash")


def _same_folder(paths: list) -> tuple:
    if not paths:
        raise ValueError("give at least one path")
    full = [_existing(p) for p in paths]
    if len(set(full)) != len(full):
        raise ValueError("a path is given twice")
    folders = {os.path.dirname(p) for p in full}
    if len(folders) != 1:
        raise ValueError("all the items must be in the same folder")
    return full, folders.pop()


def _select_many(full: list) -> None:
    _go(os.path.dirname(full[0]))
    names = [os.path.basename(p) for p in full]
    if len(names) == 1:
        _until(f"the row {names[0]!r}", ROW, names[0])
        return
    # Finder's own select, by name, because setting rows selected through Accessibility selects only one.
    _osascript(SELECT_ITEMS, os.path.dirname(full[0]), *names)
    want = sorted(unicodedata.normalize("NFC", n) for n in names)
    _wait_for(f"the items {names!r} to be selected", lambda: sorted(
        unicodedata.normalize("NFC", n) for n in _osascript(SELECTED_NAMES).split("\n") if n) == want)


def _new_items(folder: str, before: set, count: int = 1, timeout: float = SAVE_TIMEOUT) -> list:
    def made():
        now = set(os.listdir(folder)) - before
        return sorted(now) if len(now) >= count and not any(n.startswith(".") or n.endswith(".download") for n in now) else None
    return _wait_for("the new item to appear", made, timeout)


def _steady(full: str) -> None:
    seen = []

    def test():
        size = sum(os.path.getsize(os.path.join(b, f)) for b, _, fs in os.walk(full) for f in fs) if os.path.isdir(full) \
            else os.path.getsize(full)
        seen.append(size)
        return len(seen) >= 3 and seen[-1] == seen[-2] == seen[-3]
    _wait_for("the item to finish writing", test, SAVE_TIMEOUT)


def file_compress(paths: list, mode: str = "ui") -> dict:
    """Make a .zip of one or more items in the same folder with File > Compress. One item gives "name.zip"; several give
    "Archive.zip". The items themselves stay."""
    _mode("file_compress", mode, ("ui",))
    full, folder = _same_folder(paths)
    target = os.path.join(folder, (os.path.basename(full[0]) if len(full) == 1 else "Archive") + ".zip")
    _free(target)
    before = set(os.listdir(folder))
    _ready()
    _select_many(full)
    item = f"Compress “{os.path.basename(full[0])}”" if len(full) == 1 else f"Compress {len(full)} Items"
    _until(f"{item} in the File menu", MENU_ITEM_ALT, "File", item)
    _wait_exists(target)
    _steady(target)
    _new_items(folder, before)
    _done()
    return _checked("file_compress", mode, _shape(_info(target), None))


def file_extract(path: str, mode: str = "ui") -> dict:
    """Open a .zip with File > Open, so Archive Utility expands it next to itself. Returns the new item(s); the .zip stays."""
    _mode("file_extract", mode, ("ui",))
    full = _existing(path)
    if not full.lower().endswith(".zip"):
        raise ValueError("path must be a .zip")
    folder = os.path.dirname(full)
    before = set(os.listdir(folder))
    _ready()
    _select(full)
    _until("Open in the File menu", MENU_ITEM, "File", "Open")
    made = _new_items(folder, before, timeout=SAVE_TIMEOUT * 2)
    for name in made:
        _steady(os.path.join(folder, name))
    _ready()
    _done()
    return _checked("file_extract", mode, {"zip": full, "items": [_shape(_info(os.path.join(folder, n)), None) for n in made]})


def file_duplicate(path: str, mode: str = "ui") -> dict:
    """Duplicate the item at path in its own folder with File > Duplicate ("name copy"). Returns the copy."""
    _mode("file_duplicate", mode, ("ui",))
    full = _existing(path)
    folder = os.path.dirname(full)
    before = set(os.listdir(folder))
    _ready()
    _select(full)
    _until("Duplicate in the File menu", MENU_ITEM, "File", "Duplicate")
    made = _new_items(folder, before)
    if len(made) != 1:
        raise UIError(f"expected one copy, found {made}")
    copy = os.path.join(folder, made[0])
    _steady(copy)
    _done()
    return _checked("file_duplicate", mode, _shape(_info(copy), None))


def file_put_back(name: str, mode: str = "ui") -> dict:
    """Put the item named name in the Trash back where it came from (File > Put Back). Returns it at its old place."""
    _mode("file_put_back", mode, ("ui",))
    if not name or "/" in name:
        raise ValueError("name must be the item's name in the Trash, without /")
    trashed = os.path.join(TRASH_DIR, name)
    if not os.path.lexists(trashed):
        raise NotFound(f"nothing named {name!r} in the Trash")
    _ready()
    # Go to Folder won't show ~/.Trash, so Finder's own scripting opens the Trash window.
    _osascript('tell application "Finder" to open trash')
    _until("the Trash in the window", SHOWING, "Trash")
    _until("as List in the View menu", AS_LIST)
    _until(f"the row {name!r}", ROW, name)
    _until("Put Back in the File menu", MENU_ITEM, "File", "Put Back")
    _wait_exists(trashed, False)
    _done()
    return _checked("file_put_back", mode, {"name": name, "put_back": True})


def file_add_tag(path: str, tag: str, mode: str = "ui") -> dict:
    """Add the tag (a name such as "Red" or "Project X") to the item at path, in its Get Info window. Returns its tags."""
    _mode("file_add_tag", mode, ("ui",))
    if not tag.strip() or "\n" in tag or "," in tag:
        raise ValueError("tag must be one non-empty line without commas")
    full = _existing(path)
    if tag in _tags(full):
        raise AlreadyExists(f"{full} already has the tag {tag!r}")
    _ready()
    _select(full)
    info = f"{os.path.basename(full)} Info"
    _until("Get Info in the File menu", MENU_ITEM, "File", "Get Info")
    try:
        _until("the Info window's tag field", TAG_FIELD, info)
        saved = _jxa(CLIPBOARD, "save")
        try:
            _jxa(CLIPBOARD, "text", tag)
            _keys(PASTE, RETURN)
            _wait_for("the tag to be saved", lambda: tag in _tags(full), SAVE_TIMEOUT)
        finally:
            done = subprocess.run(["osascript", "-l", "JavaScript", "-e", CLIPBOARD, "restore"], input=saved,
                                  capture_output=True, text=True)
            if done.returncode:
                raise UIError(done.stderr.strip())
    finally:
        _until("the Info window to close", CLOSE_INFO, info)
    _done()
    return _checked("file_add_tag", mode, {**_shape(_info(full), None), "tags": _tags(full)})


def _tags(full: str) -> list:
    """The item's tag names, from its extended attribute (colour numbers after a line break are dropped)."""
    try:
        raw = subprocess.run(["xattr", "-px", "com.apple.metadata:_kMDItemUserTags", full], capture_output=True, text=True)
        if raw.returncode:
            return []
        return [t.split("\n")[0] for t in plistlib.loads(bytes.fromhex("".join(raw.stdout.split())))]
    except (ValueError, plistlib.InvalidFileException):
        return []


def folder_new_with_selection(paths: list, name: str, mode: str = "ui") -> dict:
    """Move items in the same folder into a new folder there named name, with File > New Folder with Selection."""
    _mode("folder_new_with_selection", mode, ("ui",))
    if not name or name in (".", "..") or "/" in name or "\n" in name:
        raise ValueError("name must be a single name without / or line breaks")
    full, folder = _same_folder(paths)
    if len(full) < 2:
        raise ValueError("give at least two items")
    target = os.path.join(folder, name)
    _free(target)
    before = set(os.listdir(folder))
    _ready()
    _select_many(full)
    item = f"New Folder with Selection ({len(full)} Items)"
    _until(f"{item} in the File menu", MENU_ITEM_ALT, "File", item)
    names = {os.path.basename(p) for p in full}

    def made():
        new = [n for n in set(os.listdir(folder)) - before if os.path.isdir(os.path.join(folder, n))
               and names <= set(os.listdir(os.path.join(folder, n)))]
        return new[0] if len(new) == 1 else None
    made_name = _wait_for("the new folder with the items", made, SAVE_TIMEOUT)
    try:
        editing = _wait_for("the new folder's name field", lambda: _ui(EDITING) == "ok", 3)
    except UIError:
        editing = False
    if editing:
        _paste(name)
        _keys(RETURN)
    else:
        # Finder didn't leave the new name ready to type, so the folder is renamed like any other item.
        _ready()
        _select(os.path.join(folder, made_name))
        _rename_selected(name)
    _wait_exists(target)
    _wait_for("the items to move", lambda: all(os.path.lexists(os.path.join(target, os.path.basename(p))) and
                                               not os.path.lexists(p) for p in full), SAVE_TIMEOUT)
    _done()
    return _checked("folder_new_with_selection", mode, {**_shape(_info(target), None),
                                                        "items": sorted(os.listdir(target))})


def file_make_alias(path: str, mode: str = "ui") -> dict:
    """Make a Finder alias of the item at path, next to it, with File > Make Alias. Finder names it ("name alias")."""
    _mode("file_make_alias", mode, ("ui",))
    full = _existing(path)
    folder = os.path.dirname(full)
    before = set(os.listdir(folder))
    _ready()
    _select(full)
    _until("Make Alias in the File menu", MENU_ITEM, "File", "Make Alias")
    made = _new_items(folder, before)
    if len(made) != 1:
        raise UIError(f"expected one alias, found {made}")
    alias = os.path.join(folder, made[0])
    # A new alias's name can be left ready to edit; Return keeps Finder's name.
    if _ui(EDITING) == "ok":
        _keys(RETURN)
    _done()
    return _checked("file_make_alias", mode, {"name": made[0], "path": alias, "original": full})


# Open With (overnight, in its own section, tested on its own) ------------------------------------------------------
# The item is selected in a Finder window, then File > Open With > the app, chosen by its name in that submenu (Finder adds
# " (default)" to the default app's name). Then the app must come to the front with a window showing the file.

OPEN_WITH_ITEMS = """      return name of every menu item of menu 1 of menu item "Open With" of menu "File" of menu bar item "File" of menu bar 1"""

FRONT_DOCS = r"""ObjC.import("AppKit");
function run(argv) {
  const app = $.NSWorkspace.sharedWorkspace.frontmostApplication;
  const se = Application("System Events");
  const out = {name: ObjC.unwrap(app.localizedName), docs: []};
  try {
    const p = se.processes.whose({unixId: app.processIdentifier})()[0];
    for (const w of p.windows()) { try { out.docs.push(w.attributes.byName("AXDocument").value() || ""); } catch (e) {} }
  } catch (e) {}
  return JSON.stringify(out);
}"""


def file_open_with(path: str, app: str, mode: str = "ui") -> dict:
    """Open the file at path with the app named app, as File > Open With in Finder offers it (for example "TextEdit" or "Preview").
    The app must then be in front with a window showing the file."""
    import json as _json
    import urllib.parse as _up
    _mode("file_open_with", mode, ("ui",))
    if not isinstance(app, str) or not app.strip() or app.endswith("…"):
        raise ValueError("app must be an app's name as Finder's Open With menu shows it")
    full = _existing(path, "file")
    if os.path.isdir(full):
        raise ValueError(f"{full} is a folder; give a file")
    _ready()
    _select(full)
    names = [n for n in _until("the Open With menu", OPEN_WITH_ITEMS).split(", ") if n and n != "missing value"]
    item = next((n for n in names if n in (app, f"{app} (default)")), None)
    if item is None:
        _done()
        raise NotFound(f"Finder's Open With menu doesn't offer {app!r} for this file (it offers {', '.join(n for n in names if not n.endswith('…'))})")
    _until(f"{item} in the Open With menu", MENU_ITEM, "File", "Open With", item)

    def showing():
        state = _json.loads(_jxa(FRONT_DOCS))
        if state["name"] != app:
            return None
        for url in state["docs"]:
            if url and _os_path_same(_up.unquote(_up.urlparse(url).path), full):
                return state
        return None
    _wait_for(f"{app} in front showing the file", showing, SAVE_TIMEOUT)
    return _checked("file_open_with", mode, {**_shape(_info(full), None), "app": app, "default": item.endswith(" (default)")})


def _os_path_same(a: str, b: str) -> bool:
    import os as _o
    import unicodedata as _u
    try:
        return _o.path.samefile(a, b)
    except OSError:
        return _u.normalize("NFC", a.rstrip("/")) == _u.normalize("NFC", b.rstrip("/"))


# Locking (overnight, in its own section, tested on its own) --------------------------------------------------------
# ui: the item's Get Info window, its Locked checkbox by name, then the window is closed. background: the file's own lock flag
# (the user-immutable flag Finder's Locked sets), through the macOS file APIs.

LOCKED_BOX = """      repeat with x in windows
        if name of x is (item 1 of argv) then
          repeat with c in (checkboxes of x & checkboxes of scroll area 1 of x)
            if title of c is "Locked" then
              if (value of c as integer) is not ((item 2 of argv) as integer) then click c
              return "ok"
            end if
          end repeat
        end if
      end repeat"""


def _is_locked(full: str) -> bool:
    import stat as _stat
    return bool(os.lstat(full).st_flags & _stat.UF_IMMUTABLE)


def file_set_locked(path: str, locked: bool = True, mode: str = "ui") -> dict:
    """Lock the file or folder at path (Get Info > Locked), or unlock it with locked=False. A locked item can't be changed or moved
    to the Trash without unlocking it first."""
    import stat as _stat
    _mode("file_set_locked", mode)
    if not isinstance(locked, bool):
        raise ValueError("locked must be True or False")
    full = _existing(path)
    if _is_locked(full) == locked:
        return _checked("file_set_locked", mode, {**_shape(_info(full), None), "locked": locked, "changed": False})
    if mode == "background":
        flags = os.lstat(full).st_flags
        os.chflags(full, (flags | _stat.UF_IMMUTABLE) if locked else (flags & ~_stat.UF_IMMUTABLE), follow_symlinks=False)
    else:
        _ready()
        _select(full)
        info = f"{os.path.basename(full)} Info"
        _until("Get Info in the File menu", MENU_ITEM, "File", "Get Info")
        try:
            _until("the Info window's Locked checkbox", LOCKED_BOX, info, "1" if locked else "0")
        finally:
            _until("the Info window to close", CLOSE_INFO, info)
        _done()
    _wait_for(f"{full} to be {'locked' if locked else 'unlocked'}", lambda: _is_locked(full) == locked, SAVE_TIMEOUT)
    return _checked("file_set_locked", mode, {**_shape(_info(full), None), "locked": locked, "changed": True})
