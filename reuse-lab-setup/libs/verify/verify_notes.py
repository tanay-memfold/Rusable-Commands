"""Verify notes.py inside a clone: python3 verify_notes.py <group> <seed> [function ...]

Every case: set up items and a start state with plain scripting (never notes.py), call the function with fresh
values, read NoteStore.sqlite, check every field, the distractors, the user's typed text, that no dialog is left
open, and the screen."""
import os
import sys
import time
import traceback

sys.path.insert(0, __import__("os").path.expanduser("~/libs/notes"))
import notes as N  # noqa: E402
import notes_db as D  # noqa: E402
from vcommon import Recorder, Values, osa, se, screenshot, rows_changed, sh, wait  # noqa: E402

GROUP, SEED = sys.argv[1], int(sys.argv[2])
ONLY = set(sys.argv[3:])
STATES = set(filter(None, os.environ.get("STATES", "").split(",")))
V = Values(SEED)
R = Recorder(GROUP, {"versions": N._versions(), "seed": SEED, "started": time.strftime("%Y-%m-%d %H:%M:%S")})

PREP = r"""
function run(argv) {
  const Notes = Application("Notes"), a = JSON.parse(argv[1]);
  const account = Notes.accounts.byName("On My Mac");
  const folder = name => name === null ? account.defaultFolder() : account.folders.byName(name);
  switch (argv[0]) {
    case "folder":
      if (!account.folders.whose({name: a.name}).length)
        Notes.make({new: "folder", at: account, withProperties: {name: a.name}});
      return "ok";
    case "note": return Notes.make({new: "note", at: folder(a.folder), withProperties: {body: a.html}}).id();
    case "show": Notes.show(Notes.notes.byId(a.id)); return "ok";
    case "show_folder": Notes.show(folder(a.name)); return "ok";
  }
}"""


def prep(op, **args):
    return osa(PREP, op, __import__("json").dumps(args), lang="JavaScript")


def html(title, body=""):
    return N._html(title + ("\n" + body if body else ""))


def quit_notes():
    sh('osascript -e \'tell application "Notes" to quit\'')
    wait(lambda: not sh("pgrep -x Notes"), 15)


def open_notes():
    sh("open -b com.apple.Notes")
    wait(lambda: se('return (count of windows) > 0', "Notes") == "true", 20)
    time.sleep(1)


def escape_all():
    for _ in range(3):
        try:
            se('key code 53', "Notes")
        except RuntimeError:
            pass
    try:
        se('''repeat with x in windows
  repeat with s in sheets of x
    if exists button "Cancel" of s then click button "Cancel" of s
    if exists button "OK" of s then click button "OK" of s
  end repeat
end repeat''', "Notes")
    except RuntimeError:
        pass


# Base distractors: same-name notes in two folders (for Ambiguous), similar names, other items.
BASE = {}


def base():
    for name in ["Archive Box", "Archive Box 2", "Travel"]:
        prep("folder", name=name)
    BASE["twin"] = "Twin Ledger"
    prep("note", folder="Archive Box", html=html("Twin Ledger", "first twin"))
    prep("note", folder="Travel", html=html("Twin Ledger", "second twin"))
    prep("note", folder="Travel", html=html("Goa trip plan", "flights and hotel"))
    prep("note", folder=None, html=html("Goa trip plan old", "draft ideas"))
    BASE["typed"] = prep("note", folder="Archive Box 2", html=html("Scratch pad", "user writes here"))
    BASE["other"] = prep("note", folder="Travel", html=html("Packing", "socks"))


def start(state):
    """Put Notes into a start state. Returns text the user typed in it, which must survive."""
    if state in ("closed", "launching"):
        quit_notes()
        if state == "launching":
            sh("open -b com.apple.Notes")
        return None
    if not sh("pgrep -x Notes"):
        open_notes()
    escape_all()
    se('set frontmost to true', "Notes")
    if state == "open":
        prep("show_folder", name="Travel")
    elif state == "other_view":
        prep("show_folder", name="Archive Box 2")
    elif state == "hidden":
        prep("show_folder", name="Travel")
        se('set visible to false', "Notes")
    elif state == "minimized":
        se('set value of attribute "AXMinimized" of window 1 to true', "Notes")
    elif state == "other_app":
        sh("open -a Calculator")
        wait(lambda: front() == "Calculator", 10)
    elif state == "alert_open":
        prep("show_folder", name="Archive Box 2")
        time.sleep(0.5)
        se('''set sidebar to first outline of scroll area 1 of splitter group 1 of window 1 whose description is "Folders"
set focused of sidebar to true
click menu item "Delete Folder" of menu "Edit" of menu bar item "Edit" of menu bar 1''', "Notes")
        wait(lambda: se('return (count of sheets of window 1) > 0', "Notes") == "true", 5)
    elif state == "search_text":
        se('keystroke "f" using command down', "Notes")
        time.sleep(0.7)
        se('keystroke "zq"', "Notes")
    elif state in ("typed_text", "blocked"):
        word = f" half typed {V.rng.randint(100, 999)}"
        for _ in range(3):
            prep("show", id=BASE["typed"])
            time.sleep(1.5)
            se('''repeat with a in scroll areas of splitter group 1 of window 1
  repeat with t in text areas of a
    set focused of t to true
  end repeat
end repeat''', "Notes")
            se('key code 125 using command down', "Notes")
            se(f'keystroke "{word}"', "Notes")
            if wait(lambda: word.lower() in D.snapshot()["notes"][pk_of(BASE["typed"])]["text"].lower(), 30, 1):
                break
        else:
            raise RuntimeError("the half-typed text never reached the scratch note, so this start state wasn't made")
        if state == "blocked":
            se('click menu item "Add Link…" of menu "Edit" of menu bar item "Edit" of menu bar 1', "Notes")
            wait(lambda: se('return (count of sheets of window 1) > 0', "Notes") == "true", 5)
            se('keystroke "example.com/draft"', "Notes")
        return word
    elif state == "selected_row":
        prep("show", id=BASE["other"])
    elif state == "two_windows":
        prep("show", id=BASE["other"])
        time.sleep(0.5)
        se('click menu item "Open Note in New Window" of menu "Window" of menu bar item "Window" of menu bar 1',
           "Notes")
        wait(lambda: se('return (count of windows) > 1', "Notes") == "true", 5)
    time.sleep(0.8)
    return None


WIDE = "380,26,644,660"
UI_STATES = ["closed", "other_view", "hidden", "minimized", "other_app", "alert_open", "search_text", "typed_text",
             "selected_row", "two_windows", "launching"]
BG_STATES = ["closed", "open"]


def front():
    return osa('tell application "System Events" to return name of first process whose frontmost is true')


def windows():
    try:
        return se('''set out to {}
repeat with x in windows
  set end of out to (count of sheets of x)
end repeat
return (count of windows) & out''', "Notes")
    except RuntimeError:
        return "not running"


def clean_screen():
    try:
        return se('''repeat with x in windows
  if (count of sheets of x) > 0 then return "sheet"
end repeat
if exists menu 1 then return "menu"
return "clean"''', "Notes") == "clean"
    except RuntimeError:
        return True


CHANGED = []


def unchanged(before, after, targets, typed):
    """Every note and folder other than the targets is as it was; typed text is still in the scratch note."""
    ok = True
    CHANGED.clear()
    for pk, note in before["notes"].items():
        if pk in targets:
            continue
        if after["notes"].get(pk) != note:
            ok = False
            CHANGED.append({"before": note, "after": after["notes"].get(pk)})
    for pk, folder in before["folders"].items():
        if pk not in targets and after["folders"].get(pk) != folder:
            ok = False
    if typed is not None:
        ok = ok and typed.lower() in after["notes"][int(BASE["typed"].rsplit("/p", 1)[1])]["text"].lower()
    return ok


def run_case(function, mode, state, setup, call, expect, kind="normal"):
    """setup() -> context; call(ctx) -> result; expect(ctx, result, before, after) -> (checks, targets)."""
    if ONLY and function not in ONLY:
        return
    if STATES and state not in STATES:
        return
    try:
        ctx = setup()
        typed = start(state)
        time.sleep(0.5)
        if typed is None and state in ("typed_text", "blocked"):
            typed = None
        before = D.snapshot()
        shot0 = screenshot(f"{function}-{mode}-{state}-{kind}-0")
        front0, windows0 = front(), windows()
        wide0 = screenshot(f"{function}-{mode}-{state}-{kind}-0w", WIDE) if mode == "background" else None
        began = time.monotonic()
        try:
            result, error = call(ctx), None
        except Exception as exc:  # noqa: BLE001
            result, error = None, exc
        seconds = round(time.monotonic() - began, 1)
        deadline = time.monotonic() + (150 if mode == "background" else 90)
        while True:
            time.sleep(1)
            after = D.snapshot()
            checks, targets = expect(ctx, result, error, before, after)
            checks["distractors_and_typed_text_unchanged"] = unchanged(before, after, targets, typed)
            if all(checks.values()) or time.monotonic() > deadline:
                break
        shot1 = screenshot(f"{function}-{mode}-{state}-{kind}-1")
        if kind != "blocked":
            checks["no_dialog_or_menu_left"] = clean_screen()
        changed = rows_changed(shot0, shot1)
        if mode == "background":
            checks["front_app_unchanged"] = front0 == front()
            if state == "closed":
                checks["notes_not_shown"] = not sh("pgrep -x Notes") or se("return visible", "Notes") == "false"
                checks["screen_unchanged"] = rows_changed(wide0, screenshot(f"{function}-{mode}-{state}-{kind}-1w",
                                                                         WIDE)) <= 40
            else:
                checks["no_new_window_or_dialog"] = windows0 == windows()
        elif kind == "normal":
            checks["screen_changed_by_ui"] = changed > 40
        detail = {"result": result, "error": repr(error) if error else None, "rows_changed": changed,
                  "changed_distractors": list(CHANGED)}
        R.case(function, mode, state, kind, checks, detail, seconds)
    except Exception:  # noqa: BLE001
        R.case(function, mode, state, kind, {"harness": False}, traceback.format_exc()[-1500:])
    finally:
        if state == "blocked":
            escape_all()


def pk_of(note_id):
    return int(note_id.rsplit("/p", 1)[1])


def new_notes(before, after):
    return {pk: n for pk, n in D.live(after).items() if pk not in before["notes"]}


def body_of(note):
    return note["body"][:-1] if note["body"].endswith("\n") else note["body"]


# Cases ------------------------------------------------------------------------------------------------------------

def cases_note_create(mode, state, special):
    values = {}

    def setup():
        values["title"] = V.special() if special else V.word()
        values["body"] = (V.special() + "\nsecond line " + V.word()) if special else V.word(3)
        values["folder"] = "Travel"
        return values

    def call(ctx):
        return N.note_create(title=ctx["title"], body=ctx["body"], folder=ctx["folder"], mode=mode)

    def expect(ctx, result, error, before, after):
        made = new_notes(before, after)
        note = next(iter(made.values()), None)
        checks = {"no_error": error is None, "one_note_made": len(made) == 1}
        if note:
            checks.update(title=note["title"] == ctx["title"], body=body_of(note) == ctx["body"],
                          folder=note["folder"] == ctx["folder"], not_pinned=not note["pinned"],
                          return_matches=bool(result) and result["title"] == note["title"]
                          and result["body"] == body_of(note) and result["folder"] == note["folder"])
        return checks, set(made)
    run_case("note_create", mode, state, setup, call, expect)


def cases_note_create_empty(mode):
    ctx = {}

    def setup():
        ctx["title"] = V.word()
        return ctx

    def expect(c, result, error, before, after):
        made = new_notes(before, after)
        note = next(iter(made.values()), None)
        return ({"no_error": error is None, "one_note_made": len(made) == 1,
                 "title": bool(note) and note["title"] == c["title"], "empty_body": bool(note) and body_of(note) == "",
                 "default_folder": bool(note) and note["folder"] == "Notes"}, set(made))
    run_case("note_create", mode, "other_view" if mode == "ui" else "open", setup,
             lambda c: N.note_create(title=c["title"], mode=mode), expect, "empty_body")


def cases_checklist(state, special):
    def setup():
        return {"title": V.special() if special else V.word(),
                "items": [V.special() if special else V.word(), V.word(), V.word(1)], "folder": "Archive Box 2"}

    def expect(ctx, result, error, before, after):
        made = new_notes(before, after)
        note = next(iter(made.values()), None)
        checks = {"no_error": error is None, "one_note_made": len(made) == 1}
        if note:
            checks.update(title=note["title"] == ctx["title"], folder=note["folder"] == ctx["folder"],
                          real_checklist=note["checklist"] == ctx["items"], unchecked=not any(note["checked"]),
                          return_matches=bool(result) and result["items"] == ctx["items"])
        return checks, set(made)
    run_case("checklist_create", "ui", state, setup,
             lambda c: N.checklist_create(title=c["title"], items=c["items"], folder=c["folder"]), expect)


def edit_case(function, mode, state, special, change, verify, kind="normal"):
    """A case on one existing note made by setup: change(ctx) calls the function, verify(ctx, note) checks it."""
    def setup():
        title = V.special() if special else V.word()
        folder = "Archive Box"
        body = V.word(3)
        note_id = prep("note", folder=folder, html=html(title, body))
        ctx = {"title": title, "body": body, "folder": folder, "id": note_id, "pk": pk_of(note_id),
               "new": V.special() if special else V.word()}
        if kind == "similar":
            prep("note", folder="Travel", html=html(title + " copy", "similar title"))
        time.sleep(1)
        return ctx

    def expect(ctx, result, error, before, after):
        note = after["notes"].get(ctx["pk"])
        checks = {"no_error": error is None, "note_present": note is not None}
        if note:
            checks.update(verify(ctx, note, result))
        return checks, {ctx["pk"]}
    run_case(function, mode, state, setup, change, expect, kind)


def cases_edits(mode, state, special, kind="normal"):
    edit_case("note_append", mode, state, special,
              lambda c: N.note_append(match=c["title"], text=c["new"] + "\nmore " + c["body"][:5], mode=mode),
              lambda c, n, r: {"body": body_of(n) == c["body"] + "\n" + c["new"] + "\nmore " + c["body"][:5],
                               "title": n["title"] == c["title"], "folder": n["folder"] == c["folder"],
                               "return_matches": bool(r) and r["body"] == body_of(n)}, kind)
    edit_case("note_rename", mode, state, special,
              lambda c: N.note_rename(match=c["title"], title=c["new"], mode=mode),
              lambda c, n, r: {"title": n["title"] == c["new"], "body": body_of(n) == c["body"],
                               "folder": n["folder"] == c["folder"],
                               "return_matches": bool(r) and r["title"] == n["title"]}, kind)
    edit_case("note_replace_body", mode, state, special,
              lambda c: N.note_replace_body(match=c["title"], body=c["new"] + "\nline two", mode=mode),
              lambda c, n, r: {"body": body_of(n) == c["new"] + "\nline two", "title": n["title"] == c["title"],
                               "folder": n["folder"] == c["folder"],
                               "return_matches": bool(r) and r["body"] == body_of(n)}, kind)
    edit_case("note_move", mode, state, special,
              lambda c: N.note_move(match=c["title"], folder="Archive Box 2", mode=mode),
              lambda c, n, r: {"folder": n["folder"] == "Archive Box 2", "title": n["title"] == c["title"],
                               "body": body_of(n) == c["body"], "not_trashed": not n["trashed"],
                               "return_matches": bool(r) and r["folder"] == "Archive Box 2"}, kind)
    edit_case("note_delete", mode, state, special,
              lambda c: N.note_delete(match=c["title"], mode=mode),
              lambda c, n, r: {"trashed": n["trashed"], "title": n["title"] == c["title"],
                               "body": body_of(n) == c["body"], "return_matches": bool(r) and r["deleted"]}, kind)
    if mode == "ui":
        edit_case("note_pin", mode, state, special,
                  lambda c: N.note_pin(match=c["title"]),
                  lambda c, n, r: {"pinned": n["pinned"], "title": n["title"] == c["title"],
                                   "body": body_of(n) == c["body"], "folder": n["folder"] == c["folder"]}, kind)


def folder_case(function, mode, state, special, kind="normal"):
    def setup():
        ctx = {"name": V.special() if special else V.word(), "to": V.special() if special else V.word()}
        if function != "folder_create":
            prep("folder", name=ctx["name"])
            prep("note", folder=ctx["name"], html=html(V.word(), "inside " + V.word()))
            time.sleep(1)
        return ctx

    def expect(ctx, result, error, before, after):
        names_before, names_after = D.folder_names(before), D.folder_names(after)
        checks = {"no_error": error is None}
        targets = set()
        if function == "folder_create":
            checks.update(made=names_after.count(ctx["name"]) == 1,
                          only_one_added=len(names_after) == len(names_before) + 1,
                          return_matches=bool(result) and result["name"] == ctx["name"])
        elif function == "folder_rename":
            targets |= {pk for pk, n in before["notes"].items() if n["folder"] == ctx["name"]}
            checks.update(renamed=ctx["to"] in names_after and ctx["name"] not in names_after,
                          count_same=len(names_after) == len(names_before),
                          return_matches=bool(result) and result["name"] == ctx["to"])
        else:
            gone = [pk for pk, f in before["folders"].items() if f["name"] == ctx["name"]]
            moved = [pk for pk, n in before["notes"].items() if n["folder"] == ctx["name"]]
            checks.update(deleted=ctx["name"] not in names_after,
                          its_notes_trashed=all(after["notes"][pk]["trashed"] for pk in moved),
                          return_matches=bool(result) and result["deleted"])
            targets |= set(gone) | set(moved)
        targets |= {pk for pk, f in after["folders"].items() if f["name"] in (ctx["name"], ctx["to"])}
        targets |= {pk for pk, f in before["folders"].items() if f["name"] in (ctx["name"], ctx["to"])}
        return checks, targets
    call = {"folder_create": lambda c: N.folder_create(name=c["name"], mode=mode),
            "folder_rename": lambda c: N.folder_rename(name=c["name"], to=c["to"], mode=mode),
            "folder_delete": lambda c: N.folder_delete(name=c["name"], mode=mode)}[function]
    run_case(function, mode, state, setup, call, expect, kind)


def error_case(function, mode, call, expected, state, kind):
    def expect(ctx, result, error, before, after):
        return {"raised_" + expected.__name__: isinstance(error, expected),
                "nothing_changed": D.live(before) == D.live(after)
                and D.folder_names(before) == D.folder_names(after)}, set()
    run_case(function, mode, state, lambda: {}, call, expect, kind)


def blocked_still_open():
    return se('return (count of sheets of window 1) > 0', "Notes") == "true"


def reads(state):
    """note_get / note_search / note_list / folder_list (background) against the database."""
    def check_get(ctx, result, error, before, after):
        note = next(n for n in D.live(after).values() if n["title"] == ctx["title"])
        return {"no_error": error is None, "title": result["title"] == note["title"],
                "body": result["body"] == body_of(note), "folder": result["folder"] == note["folder"],
                "only_fields_asked": set(result) == {"title", "body", "folder", "created_date"}}, set()

    def setup_get():
        ctx = {"title": V.special()}
        prep("note", folder="Archive Box 2", html=html(ctx["title"], "read me\n" + V.word()))
        prep("note", folder="Travel", html=html(ctx["title"] + " 2", "similar"))
        time.sleep(1)
        return ctx
    run_case("note_get", "background", state, setup_get,
             lambda c: N.note_get(match=c["title"], fields="title,body,folder,created_date"), check_get)

    def setup_search():
        word = "zephyr" + str(V.rng.randint(1000, 9999))
        prep("note", folder="Travel", html=html("Search one " + V.word(), "has " + word + " inside"))
        prep("note", folder="Archive Box", html=html("Title " + word.upper(), "plain"))
        time.sleep(1)
        return {"word": word}

    def check_search(ctx, result, error, before, after):
        expected = sorted(n["title"] for n in D.live(after).values()
                          if ctx["word"] in n["text"].lower())
        return {"no_error": error is None, "found_all": sorted(r["title"] for r in result) == expected,
                "two_found": len(result) == 2}, set()
    run_case("note_search", "background", state, setup_search,
             lambda c: N.note_search(query=c["word"], limit=10, fields="title,folder"), check_search)

    def check_list(ctx, result, error, before, after):
        expected = sorted(n["title"] for n in D.live(after).values() if n["folder"] == "Travel")
        return {"no_error": error is None, "all_in_folder": sorted(r["title"] for r in result) == expected,
                "bodies_match": all(r["body"] == body_of(next(n for n in D.live(after).values()
                                                             if n["title"] == r["title"] and n["folder"] == "Travel"))
                                    for r in result)}, set()
    run_case("note_list", "background", state, lambda: {}, lambda c: N.note_list(folder="Travel", limit=100), check_list)

    def check_folders(ctx, result, error, before, after):
        counts = {f: sum(1 for n in D.live(after).values() if n["folder"] == f) for f in D.folder_names(after)}
        return {"no_error": error is None,
                "names": sorted(r["name"] for r in result) == sorted(f for f in D.folder_names(after)),
                "counts": all(counts[r["name"]] == r["notes"] for r in result)}, set()
    run_case("folder_list", "background", state, lambda: {}, lambda c: N.folder_list(), check_folders)


def main():
    open_notes()
    base()
    time.sleep(2)
    if "background" not in ONLY or True:
        for state in BG_STATES:
            for special in (False, True):
                cases_note_create("background", state, special)
                cases_edits("background", state, special)
                for function in ("folder_create", "folder_rename", "folder_delete"):
                    folder_case(function, "background", state, special)
            reads(state)
        cases_note_create_empty("background")
    for index, state in enumerate(UI_STATES):
        special = index % 2 == 1
        cases_note_create("ui", state, special)
        cases_checklist(state, special)
        cases_edits("ui", state, special)
        for function in ("folder_create", "folder_rename", "folder_delete"):
            folder_case(function, "ui", state, special)
    cases_note_create_empty("ui")
    for mode in ("ui", "background"):
        st = "other_view" if mode == "ui" else "open"
        error_case("note_append", mode, lambda c: N.note_append(match="No Such Note 4242", text="x", mode=mode),
                   N.NotFound, st, "not_found")
        error_case("note_rename", mode, lambda c: N.note_rename(match=BASE["twin"], title="Nope", mode=mode),
                   N.Ambiguous, st, "ambiguous")
        error_case("note_delete", mode, lambda c: N.note_delete(match=BASE["twin"], mode=mode),
                   N.Ambiguous, st, "ambiguous")
        error_case("note_move", mode, lambda c: N.note_move(match="Packing", folder="No Such Folder", mode=mode),
                   N.NotFound, st, "not_found")
        error_case("folder_delete", mode, lambda c: N.folder_delete(name="No Such Folder 77", mode=mode),
                   N.NotFound, st, "not_found")
        error_case("folder_create", mode, lambda c: N.folder_create(name="Travel", mode=mode),
                   N.AlreadyExists, st, "exists")
        cases_edits(mode, st, False, "similar")
    error_case("note_get", "background", lambda c: N.note_get(match=BASE["twin"]), N.Ambiguous, "open", "ambiguous")
    error_case("note_get", "background", lambda c: N.note_get(match="Missing 9"), N.NotFound, "open", "not_found")
    for function, call in [("note_create", lambda c: N.note_create(title=V.word(), body="b")),
                           ("note_append", lambda c: N.note_append(match="Packing", text="never")),
                           ("folder_create", lambda c: N.folder_create(name=V.word()))]:
        def expect(ctx, result, error, before, after):
            return {"raised_StateBlocked": isinstance(error, N.StateBlocked),
                    "nothing_changed": D.live(before) == D.live(after)
                    and D.folder_names(before) == D.folder_names(after),
                    "dialog_left_with_its_text": blocked_still_open()}, set()
        run_case(function, "ui", "blocked", lambda: {}, call, expect, "blocked")
    escape_all()
    R.data["meta"]["finished"] = time.strftime("%Y-%m-%d %H:%M:%S")
    R.save()


main()
