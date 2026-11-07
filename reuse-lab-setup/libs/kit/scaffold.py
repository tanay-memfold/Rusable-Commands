"""Start a new app's library from TextEdit's helpers: python3 scaffold.py <folder> <module> <App name> <bundle id> <ROOT_ENV> <plist path> <doc line>."""
import os, sys
folder, module, app, bundle, env, plist, doc = sys.argv[1:8]
src = open(os.path.join(os.path.dirname(__file__), "..", "textedit", "textedit.py")).read()
def between(a, b): return src[src.index(a):src.index(b)]
camel = "".join(w.title() for w in module.split("_")) + "Error"
classes = "".join(f"class {n}({camel}):\n    pass\n\n\n" for n in ("NotFound", "Ambiguous", "AlreadyExists", "OutsideAllowedRoot", "StateBlocked", "UIError", "NotSupported"))
head = f'''"""{doc}

mode="ui" works on screen: elements are found by role and name through the macOS Accessibility API, menu items are clicked by name, and
text is pasted through the clipboard, which is restored afterwards. No screen coordinates.

Set {env} to a folder and every path is checked to be inside it, after following links, before anything happens.

Errors: NotFound, Ambiguous, AlreadyExists, OutsideAllowedRoot, StateBlocked (the screen holds something the call won't destroy),
UIError (an element never appeared), NotSupported (the mode can't do it or wasn't verified)."""
from __future__ import annotations

import ctypes
import json
import os
import plistlib
import subprocess
import time
import unicodedata
import urllib.parse
import warnings

APP = "{app}"
BUNDLE_ID = "{bundle}"
TIMEOUT = 10
SAVE_TIMEOUT = 15
ROOT_ENV = "{env}"
APP_PLIST = "{plist}"

VERIFIED: dict = {{}}
UNSUPPORTED: dict = {{}}


class {camel}(Exception):
    pass


{classes}'''
core = between("def _run(args: list)", "def _mode(function")
wait = between("def _wait_for(what", "# Paths ---")
mode = f'''def _mode(function: str, mode: str, supported: tuple = ("ui",)) -> None:
    if mode not in ("ui", "background"):
        raise ValueError(f"mode must be 'ui' or 'background', not {{mode!r}}")
    if mode not in supported or (VERIFIED and mode not in VERIFIED.get(function, {{}})):
        raise NotSupported(f"{{function}} has no verified {{mode}} mode: {{UNSUPPORTED.get((function, mode), 'it did not pass verification')}}")


'''
path = f'''def _path(path: str) -> str:
    full = os.path.abspath(os.path.expanduser(path))
    root = os.environ.get(ROOT_ENV)
    if root:
        allowed, real = os.path.realpath(os.path.expanduser(root)), os.path.realpath(full)
        if real != allowed and not real.startswith(allowed + os.sep):
            raise OutsideAllowedRoot(f"{{full}} is outside {{ROOT_ENV}}; nothing was done")
    return full


def _existing(path: str) -> str:
    full = _path(path)
    if not os.path.exists(full):
        raise NotFound(f"nothing at {{full}}")
    return full


def _new_path(path: str) -> str:
    full = _path(path)
    if os.path.lexists(full):
        raise AlreadyExists(f"{{full}} already exists; nothing is overwritten")
    if not os.path.isdir(os.path.dirname(full)):
        raise NotFound(f"the folder {{os.path.dirname(full)}} doesn't exist")
    return full


'''
screen = between("# The screen ---", "MENU_OPEN = ")
forward = between("def _forward()", "def _raise(window)")
panel = between("def _fill_save_panel(window", "def _saved_at(full")
body = head + core + mode + wait + path + screen + forward + panel + "# Commands ---------------------------------------------------------------------------------------------------------\n\n"
os.makedirs(folder, exist_ok=True)
target = os.path.join(folder, module + ".py")
if os.path.exists(target): sys.exit(target + " exists")
open(target, "w").write(body); print("wrote", target)
