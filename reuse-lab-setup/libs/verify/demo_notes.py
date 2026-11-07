"""Record one UI-mode end-to-end run (goa_trip_and_invoices) from a messy start state: python3 demo_notes.py"""
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.expanduser("~/libs/notes"))
import notes as N  # noqa: E402
from vcommon import osa, se, sh, wait  # noqa: E402

PREP = r"""
function run(argv) {
  const Notes = Application("Notes"), a = JSON.parse(argv[0]);
  const account = Notes.accounts.byName("On My Mac");
  if (a.folder && !account.folders.whose({name: a.folder}).length)
    Notes.make({new: "folder", at: account, withProperties: {name: a.folder}});
  const where = a.folder ? account.folders.byName(a.folder) : account.defaultFolder();
  return Notes.make({new: "note", at: where, withProperties: {body: a.html}}).id();
}"""


def note(title, body, folder):
    return osa(PREP, json.dumps({"folder": folder, "html": N._html(title + "\n" + body)}), lang="JavaScript")


sh("open -b com.apple.Notes")
wait(lambda: se("return (count of windows) > 0", "Notes") == "true", 20)
note("Goa trip beaches", "Baga, Anjuna", "Holidays")
time.sleep(1.5)
note("Goa trip hotel", "check-in Friday", "Holidays")
note("Invoice April", "amount 80", "Work")
scratch = note("Shopping", "bread", None)
time.sleep(2)
osa(r'function run(argv){const N=Application("Notes");N.show(N.notes.byId(argv[0]));}', scratch, lang="JavaScript")
time.sleep(0.7)
se('''repeat with a in scroll areas of splitter group 1 of window 1
  repeat with t in text areas of a
    set focused of t to true
  end repeat
end repeat''', "Notes")
se("key code 125 using command down", "Notes")
se('keystroke " and milk"', "Notes")
se('keystroke "f" using command down', "Notes")
se('keystroke "zq"', "Notes")
time.sleep(1)
recorder = subprocess.Popen(["screencapture", "-x", "-V", "40", os.path.expanduser("~/verify-out/notes-demo.mov")])
time.sleep(2)
examples = os.path.expanduser("~/libs/notes/examples")
done = subprocess.run([sys.executable, os.path.join(examples, "goa_trip_and_invoices.py")], cwd=examples,
                      env={**os.environ, "PYTHONPATH": os.path.expanduser("~/libs/notes")}, capture_output=True,
                      text=True)
print(done.returncode, done.stderr[-500:])
recorder.wait()
print("recorded")
