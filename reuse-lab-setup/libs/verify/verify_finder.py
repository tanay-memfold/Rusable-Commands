"""Verify finder.py inside a clone: python3 verify_finder.py <group> <seed> [function ...]

Every case: make files and folders with plain shell commands (never finder.py), put Finder into a start state,
call the function with fresh names, read the file system (os.stat, contents), check the target, the distractors,
that no dialog is left open, and the screen."""
import hashlib
import os
import shutil
import sys
import time
import traceback

sys.path.insert(0, os.path.expanduser("~/libs/finder"))
import finder as F  # noqa: E402
from vcommon import Recorder, Values, osa, se, screenshot, rows_changed, sh, wait  # noqa: E402

GROUP, SEED = sys.argv[1], int(sys.argv[2])
ONLY = set(sys.argv[3:])
STATES = set(filter(None, os.environ.get("STATES", "").split(",")))
V = Values(SEED)
R = Recorder(GROUP, {"versions": F._versions(), "seed": SEED, "started": time.strftime("%Y-%m-%d %H:%M:%S")})
APP = "Finder"
ROOT = os.path.expanduser("~/Documents/Lab")
TRASH = os.path.expanduser("~/.Trash")
WIDE = "380,26,644,660"


def tree():
    """Every file and folder under ROOT with its size and content hash (folders: None)."""
    out = {}
    for base, dirs, files in os.walk(ROOT):
        for name in dirs:
            out[os.path.join(base, name)] = None
        for name in files:
            path = os.path.join(base, name)
            with open(path, "rb") as handle:
                out[path] = hashlib.sha256(handle.read()).hexdigest()
    return out


def trashed():
    return set(os.listdir(TRASH)) if os.path.isdir(TRASH) else set()


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as handle:
        handle.write(text)


def base():
    for folder in ["Inbox", "Archive", "Invoices", "Photos"]:
        os.makedirs(os.path.join(ROOT, folder), exist_ok=True)
    write(os.path.join(ROOT, "Inbox", "notes.txt"), "keep me\n")
    write(os.path.join(ROOT, "Inbox", "notes copy.txt"), "similar name\n")
    write(os.path.join(ROOT, "Archive", "notes.txt"), "same name elsewhere\n")
    write(os.path.join(ROOT, "Photos", "readme.md"), "# photos\n")


def finder_windows_close():
    se('''repeat with x in windows
  try
    click (first button of x whose subrole is "AXCloseButton")
  end try
end repeat''', APP)


def start(state):
    if state == "closed":
        finder_windows_close()
        return
    sh(f"open '{os.path.join(ROOT, 'Photos')}'")
    time.sleep(0.8)
    if state == "hidden":
        se("set visible to false", APP)
    elif state == "minimized":
        se('set value of attribute "AXMinimized" of window 1 to true', APP)
    elif state == "other_app":
        sh("open -a Calculator")
        wait(lambda: front() == "Calculator", 10)
    elif state == "search_text":
        se('keystroke "f" using command down', APP)
        time.sleep(0.7)
        se('keystroke "zq"', APP)
    elif state == "selected":
        sh(f"open -R '{os.path.join(ROOT, 'Photos', 'readme.md')}'")
    elif state == "two_windows":
        sh(f"open '{os.path.join(ROOT, 'Inbox')}'")
    elif state == "alert_open":
        se('click menu item "Connect to Server…" of menu "Go" of menu bar item "Go" of menu bar 1', APP)
        wait(lambda: se('return (count of windows whose subrole is "AXDialog")', APP) != "0", 5)
    elif state == "blocked":
        sh(f"open -R '{os.path.join(ROOT, 'Photos', 'readme.md')}'")
        time.sleep(0.5)
        se("key code 36", APP)
        time.sleep(0.7)
        se('keystroke "half typed"', APP)
    time.sleep(0.8)


UI_STATES = ["closed", "other_view", "hidden", "minimized", "other_app", "search_text", "selected", "two_windows",
             "alert_open"]


def front():
    return osa('tell application "System Events" to return name of first process whose frontmost is true')


def clean_screen():
    try:
        return se('''repeat with x in windows
  if (count of sheets of x) > 0 then return "sheet"
  if subrole of x is "AXDialog" then return "dialog"
end repeat
if exists menu 1 then return "menu"
return "clean"''', APP) == "clean"
    except RuntimeError:
        return True


def escape_all():
    for _ in range(3):
        try:
            se("key code 53", APP)
        except RuntimeError:
            pass


CHANGED = []


def run_case(function, mode, state, setup, call, expect, kind="normal"):
    if ONLY and function not in ONLY:
        return
    if STATES and state not in STATES:
        return
    try:
        ctx = setup()
        start(state)
        before, trash0 = tree(), trashed()
        name = f"{function}-{mode}-{state}-{kind}"
        shot0 = screenshot(name + "-0")
        wide0 = screenshot(name + "-0w", WIDE) if mode == "background" else None
        front0 = front()
        began = time.monotonic()
        try:
            result, error = call(ctx), None
        except Exception as exc:  # noqa: BLE001
            result, error = None, exc
        seconds = round(time.monotonic() - began, 1)
        time.sleep(1)
        after, trash1 = tree(), trashed()
        checks, targets = expect(ctx, result, error, before, after, trash1 - trash0)
        CHANGED.clear()
        for path, digest in before.items():
            if path not in targets and after.get(path) != digest:
                CHANGED.append(path)
        for path in after:
            if path not in before and path not in targets:
                CHANGED.append(path)
        checks["distractors_unchanged"] = not CHANGED
        if kind != "blocked":
            checks["no_dialog_or_menu_left"] = clean_screen()
        changed = rows_changed(shot0, screenshot(name + "-1"))
        if mode == "background":
            checks["front_app_unchanged"] = front0 == front()
            checks["screen_unchanged"] = rows_changed(wide0, screenshot(name + "-1w", WIDE)) <= 40
        elif kind == "normal":
            checks["screen_changed_by_ui"] = changed > 40
        R.case(function, mode, state, kind, checks, {"result": result, "error": repr(error) if error else None,
                                                      "rows_changed": changed, "changed": list(CHANGED)}, seconds)
    except Exception:  # noqa: BLE001
        R.case(function, mode, state, kind, {"harness": False}, traceback.format_exc()[-1500:])
    finally:
        if state in ("blocked", "alert_open", "search_text"):
            escape_all()


def name_for(special, suffix=".txt"):
    return (V.special() if special else V.word()).replace("/", "-") + suffix


def cases(mode, state, special):
    def setup_file():
        path = os.path.join(ROOT, "Inbox", name_for(special))
        write(path, "content " + V.word())
        return {"path": path, "digest": None}

    def made(ctx, before, after):
        return {p for p in after if p not in before}

    def expect_folder(ctx, result, error, before, after, gone):
        return {"no_error": error is None, "folder_made": os.path.isdir(ctx["path"]),
                "only_it_added": made(ctx, before, after) == {ctx["path"]},
                "return_matches": bool(result) and result["path"] == ctx["path"] and result["kind"] == "folder"}, \
            {ctx["path"]}
    run_case("folder_create", mode, state, lambda: {"path": os.path.join(ROOT, "Archive", name_for(special, ""))},
             lambda c: F.folder_create(path=c["path"], mode=mode), expect_folder)

    def expect_copy(ctx, result, error, before, after, gone):
        copy = os.path.join(ROOT, "Archive", os.path.basename(ctx["path"]))
        return {"no_error": error is None, "copy_made": after.get(copy) == before.get(ctx["path"]),
                "original_kept": after.get(ctx["path"]) == before.get(ctx["path"]),
                "return_matches": bool(result) and result["path"] == copy}, {copy}
    run_case("file_copy", mode, state, setup_file,
             lambda c: F.file_copy(path=c["path"], to_folder=os.path.join(ROOT, "Archive"), mode=mode), expect_copy)

    def expect_move(ctx, result, error, before, after, gone):
        moved = os.path.join(ROOT, "Invoices", os.path.basename(ctx["path"]))
        return {"no_error": error is None, "moved_with_content": after.get(moved) == before.get(ctx["path"]),
                "original_gone": ctx["path"] not in after,
                "return_matches": bool(result) and result["path"] == moved}, {moved, ctx["path"]}
    run_case("file_move", mode, state, setup_file,
             lambda c: F.file_move(path=c["path"], to_folder=os.path.join(ROOT, "Invoices"), mode=mode), expect_move)

    def setup_rename():
        ctx = setup_file()
        ctx["to"] = name_for(special)
        return ctx

    def expect_rename(ctx, result, error, before, after, gone):
        renamed = os.path.join(os.path.dirname(ctx["path"]), ctx["to"])
        return {"no_error": error is None, "renamed_with_content": after.get(renamed) == before.get(ctx["path"]),
                "old_name_gone": ctx["path"] not in after,
                "return_matches": bool(result) and result["name"] == ctx["to"]}, {renamed, ctx["path"]}
    run_case("file_rename", mode, state, setup_rename,
             lambda c: F.file_rename(path=c["path"], to=c["to"], mode=mode), expect_rename)

    def expect_trash(ctx, result, error, before, after, gone):
        return {"no_error": error is None, "gone_from_folder": ctx["path"] not in after,
                "in_trash": any(n.startswith(os.path.splitext(os.path.basename(ctx["path"]))[0]) for n in gone),
                "return_matches": bool(result) and result["trashed"]}, {ctx["path"]}
    run_case("file_trash", mode, state, setup_file, lambda c: F.file_trash(path=c["path"], mode=mode), expect_trash)


def reads():
    def check_list(ctx, result, error, before, after, gone):
        expected = sorted(n for n in os.listdir(os.path.join(ROOT, "Inbox")) if not n.startswith("."))
        return {"no_error": error is None, "same_names": [r["name"] for r in result] == expected,
                "sizes": all(r["size"] == os.path.getsize(os.path.join(ROOT, "Inbox", r["name"])) for r in result
                             if r["kind"] == "file")}, set()
    run_case("file_list", "background", "open", lambda: {},
             lambda c: F.file_list(folder=os.path.join(ROOT, "Inbox"), fields="name,kind,size"), check_list)

    def check_find(ctx, result, error, before, after, gone):
        expected = sorted(p for p in after if os.path.basename(p).endswith(".md"))
        return {"no_error": error is None, "found_all": sorted(r["path"] for r in result) == expected}, set()
    run_case("file_find", "background", "open", lambda: {},
             lambda c: F.file_find(query="*.md", folder=ROOT, fields="path"), check_find)

    def check_info(ctx, result, error, before, after, gone):
        path = os.path.join(ROOT, "Inbox", "notes.txt")
        return {"no_error": error is None, "size": result["size"] == os.path.getsize(path),
                "kind": result["kind"] == "file"}, set()
    run_case("file_info", "background", "open", lambda: {},
             lambda c: F.file_info(path=os.path.join(ROOT, "Inbox", "notes.txt")), check_info)

    def setup_text():
        path = os.path.join(ROOT, "Inbox", "letter.rtf")
        write(os.path.join(ROOT, "Inbox", "plain ✨.txt"), "Zoë said \"hi\"\nline two\n")
        sh(f"printf 'Dear Ravi,\\nThe invoice is attached.\\n' | textutil -stdin -format txt -convert rtf -output "
           f"'{path}'")
        return {}

    def check_text(ctx, result, error, before, after, gone):
        plain = F.file_read_text(path=os.path.join(ROOT, "Inbox", "plain ✨.txt"))
        return {"no_error": error is None, "rtf_text": "The invoice is attached." in result["text"],
                "plain_exact": plain["text"] == "Zoë said \"hi\"\nline two\n"}, set()
    run_case("file_read_text", "background", "open", setup_text,
             lambda c: F.file_read_text(path=os.path.join(ROOT, "Inbox", "letter.rtf")), check_text)


def error_case(function, mode, call, expected, state, kind):
    def expect(ctx, result, error, before, after, gone):
        return {"raised_" + expected.__name__: isinstance(error, expected), "nothing_changed": before == after}, set()
    run_case(function, mode, state, lambda: {}, call, expect, kind)


def main():
    if os.path.isdir(ROOT):
        shutil.rmtree(ROOT)
    base()
    for state in ("closed", "open"):
        for special in (False, True):
            cases("background", state, special)
    reads()
    for i, state in enumerate(UI_STATES):
        cases("ui", state, i % 2 == 1)
    for mode in ("ui", "background"):
        st = "other_view" if mode == "ui" else "open"
        error_case("file_move", mode, lambda c: F.file_move(path=os.path.join(ROOT, "Inbox", "nope.txt"),
                                                            to_folder=os.path.join(ROOT, "Archive"), mode=mode),
                   F.NotFound, st, "not_found")
        error_case("file_copy", mode, lambda c: F.file_copy(path=os.path.join(ROOT, "Inbox", "notes.txt"),
                                                            to_folder=os.path.join(ROOT, "Archive"), mode=mode),
                   F.AlreadyExists, st, "exists")
        error_case("file_rename", mode, lambda c: F.file_rename(path=os.path.join(ROOT, "Inbox", "notes.txt"),
                                                                to="notes copy.txt", mode=mode),
                   F.AlreadyExists, st, "exists")
    for function, call in [("file_trash", lambda c: F.file_trash(path=os.path.join(ROOT, "Inbox", "notes.txt"))),
                           ("folder_create", lambda c: F.folder_create(path=os.path.join(ROOT, "Archive", "x1")))]:
        def expect(ctx, result, error, before, after, gone):
            return {"raised_StateBlocked": isinstance(error, F.StateBlocked), "nothing_changed": before == after}, set()
        run_case(function, "ui", "blocked", lambda: {}, call, expect, "blocked")
    escape_all()
    R.data["meta"]["finished"] = time.strftime("%Y-%m-%d %H:%M:%S")
    R.save()


main()
