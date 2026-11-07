"""End-to-end: run each Notes example program in UI mode from a messy start state (a confirmation dialog open and
text half-typed in another note), then check the exact outcome in NoteStore.sqlite.
   python3 e2e_notes.py <group> [record]"""
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.expanduser("~/libs/notes"))
import notes as N  # noqa: E402
import notes_db as D  # noqa: E402
from vcommon import Recorder, osa, se, sh, wait  # noqa: E402

GROUP = sys.argv[1]
RECORD = len(sys.argv) > 2
R = Recorder(GROUP, {"versions": N._versions(), "started": time.strftime("%Y-%m-%d %H:%M:%S")})
EXAMPLES = os.path.expanduser("~/libs/notes/examples")
PREP = r"""
function run(argv) {
  const Notes = Application("Notes"), a = JSON.parse(argv[1]);
  const account = Notes.accounts.byName("On My Mac");
  if (argv[0] === "folder") { Notes.make({new: "folder", at: account, withProperties: {name: a.name}}); return "ok"; }
  const where = a.folder === null ? account.defaultFolder() : account.folders.byName(a.folder);
  return Notes.make({new: "note", at: where, withProperties: {body: a.html}}).id();
}"""


def prep(op, **args):
    return osa(PREP, op, __import__("json").dumps(args), lang="JavaScript")


def note(title, body, folder):
    return prep("note", folder=folder, html=N._html(title + ("\n" + body if body else "")))


def messy(typed_in):
    """A Delete Folder confirmation open over Notes, and text half-typed at the end of another note."""
    sh("open -b com.apple.Notes")
    wait(lambda: se("return (count of windows) > 0", "Notes") == "true", 20)
    time.sleep(1)
    osa(r'function run(argv){const N=Application("Notes");N.show(N.notes.byId(argv[0]));}', typed_in,
        lang="JavaScript")
    time.sleep(0.7)
    se('''repeat with a in scroll areas of splitter group 1 of window 1
  repeat with t in text areas of a
    set focused of t to true
  end repeat
end repeat''', "Notes")
    se('key code 125 using command down', "Notes")
    se('keystroke " still typing"', "Notes")
    osa(r'function run(argv){const N=Application("Notes");N.show(N.accounts.byName("On My Mac").folders.byName("Keep"));}',
        lang="JavaScript")
    time.sleep(0.7)
    se('''set sidebar to first outline of scroll area 1 of splitter group 1 of window 1 whose description is "Folders"
set focused of sidebar to true
click menu item "Delete Folder" of menu "Edit" of menu bar item "Edit" of menu bar 1''', "Notes")
    wait(lambda: se("return (count of sheets of window 1) > 0", "Notes") == "true", 5)
    return " still typing"


def run_program(name):
    recorder = None
    if RECORD:
        recorder = subprocess.Popen(["screencapture", "-x", "-V", "90", os.path.expanduser(f"~/verify-out/{name}.mov")])
        time.sleep(1.5)
    began = time.monotonic()
    done = subprocess.run([sys.executable, os.path.join(EXAMPLES, name + ".py")], capture_output=True, text=True,
                          cwd=EXAMPLES, env={**os.environ, "PYTHONPATH": os.path.expanduser("~/libs/notes")})
    seconds = round(time.monotonic() - began, 1)
    if recorder:
        time.sleep(2)
        recorder.terminate()
        recorder.wait()
    return done, seconds


def body(n):
    return n["body"][:-1] if n["body"].endswith("\n") else n["body"]


def main():
    sh("open -g -j -b com.apple.Notes")
    time.sleep(4)
    for folder in ["Travel", "Work", "Keep"]:
        prep("folder", name=folder)
    note("Goa trip ideas", "beaches\nforts", "Travel")
    time.sleep(1.5)
    note("Goa trip plan", "flights booked", "Travel")
    note("Invoice March", "amount 120", "Work")
    note("Acme invoice 42", "due Friday", None)
    note("Invitation list", "Ravi, Meera", "Work")
    scratch = note("Scratch pad", "writing here", "Keep")
    time.sleep(2)
    typed = messy(scratch)
    before = D.snapshot()
    done, seconds = run_program("goa_trip_and_invoices")
    time.sleep(3)
    after = D.snapshot()
    live = D.live(after)
    plan = [n for n in live.values() if n["title"] == "Goa trip plan"]
    ideas = [n for n in live.values() if n["title"] == "Goa trip ideas"]
    checks = {
        "program_ok": done.returncode == 0,
        "newest_goa_note_appended": bool(plan) and body(plan[0]) == "flights booked\nBook the cab",
        "older_goa_note_unchanged": bool(ideas) and body(ideas[0]) == "beaches\nforts",
        "invoices_folder_made": "Invoices" in D.folder_names(after),
        "invoice_notes_moved": all(n["folder"] == "Invoices" for n in live.values()
                                   if "invoice" in n["title"].lower()),
        "two_invoice_notes": sum(1 for n in live.values() if n["folder"] == "Invoices") == 2,
        "invitation_untouched": any(n["title"] == "Invitation list" and n["folder"] == "Work" for n in live.values()),
        "typed_text_kept": typed in live[int(scratch.rsplit("/p", 1)[1])]["text"],
        "no_dialog_left": se('return (count of sheets of window 1)', "Notes") == "0",
    }
    R.case("e2e goa_trip_and_invoices", "ui", "dialog_open+typed_text", "e2e", checks,
           {"stdout": done.stdout[-500:], "stderr": done.stderr[-1500:]}, seconds)

    for title, folder in [("Empty one", None), ("Empty two", "Work"), ("Empty keep", "Keep")]:
        note(title, "", folder)
    note("Not empty", "has words", "Work")
    time.sleep(2)
    scratch2 = note("Second scratch", "notes", "Travel")
    time.sleep(1.5)
    typed = messy(scratch2)
    done, seconds = run_program("delete_empty_notes")
    time.sleep(3)
    after = D.snapshot()
    live = D.live(after)
    checks = {
        "program_ok": done.returncode == 0,
        "empty_outside_keep_deleted": not any(n["title"] in ("Empty one", "Empty two") for n in live.values()),
        "empty_in_keep_kept": any(n["title"] == "Empty keep" and n["folder"] == "Keep" for n in live.values()),
        "non_empty_kept": any(n["title"] == "Not empty" for n in live.values())
        and any(n["title"] == "Goa trip plan" for n in live.values()),
        "typed_text_kept": typed in live[int(scratch2.rsplit("/p", 1)[1])]["text"],
        "no_dialog_left": se('return (count of sheets of window 1)', "Notes") == "0",
    }
    R.case("e2e delete_empty_notes", "ui", "dialog_open+typed_text", "e2e", checks,
           {"stdout": done.stdout[-500:], "stderr": done.stderr[-1500:]}, seconds)
    R.save()


main()
