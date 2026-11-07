"""verify_rem15.py <group> <seed> <states...>: Reminders' flag and reopen commands, read back from Reminders' database."""
import glob, json, os, sqlite3, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import reminders as R, vkit
from vcommon import osa, sh, se
group, seed, states = sys.argv[1], int(sys.argv[2]), sys.argv[3:]
APP = "Reminders"
STORES = os.path.expanduser("~/Library/Group Containers/group.com.apple.reminders/Container_v1/Stores")
def rows(title):
    """(flagged, completed) of every live reminder with this title, straight from the database."""
    out = []
    for path in glob.glob(STORES + "/*.sqlite"):
        db = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5)
        try: out += [(bool(f), bool(c)) for f, c in db.execute("select ZFLAGGED, ZCOMPLETED from ZREMCDREMINDER where ZTITLE = ? and (ZMARKEDFORDELETION is null or ZMARKEDFORDELETION = 0)", (title,))]
        except sqlite3.Error: pass
        finally: db.close()
    return out
def running(): return bool(sh("pgrep -x Reminders"))
def front_app():
    try: return osa('tell application "System Events" to return name of first process whose frontmost is true')
    except RuntimeError: return ""
def start(state):
    if state == "closed":
        if running(): osa('tell application "Reminders" to quit'); [time.sleep(0.5) for _ in range(30) if running()]
        return
    if not running(): sh("open -b com.apple.reminders"); [time.sleep(0.5) for _ in range(30) if not running()]; time.sleep(2)
    se("set visible to true\nset frontmost to true", APP); time.sleep(0.5)
    if state == "hidden": se("set visible to false", APP)
    elif state == "other_app": sh("open -a Calculator"); [time.sleep(0.3) for _ in range(20) if front_app() == APP]
    time.sleep(0.5)
K = vkit.Kit("rem15", R, APP, group, seed, R.RemindersError, start)
LIST = f"Rusable R {K.V.rng.randint(1000, 9999)}"
MAKE = r"""function run(argv) { const Rem = Application("Reminders"), a = JSON.parse(argv[0]);
  let l = Rem.lists.whose({name: a.list})(); if (!l.length) { Rem.lists.push(Rem.List({name: a.list})); l = Rem.lists.whose({name: a.list})(); }
  const r = Rem.Reminder({name: a.title}); l[0].reminders.push(r); if (a.flagged) r.flagged = true; if (a.done) r.completed = true; return "ok"; }"""
n = {"i": 0}
def rem(flagged=False, done=False, twin=False):
    n["i"] += 1; t = (K.V.special() if n["i"] % 2 else K.V.word()) + f" {n['i']}"
    if not running(): sh("open -g -j -b com.apple.reminders"); [time.sleep(0.5) for _ in range(30) if not running()]; time.sleep(2)
    for _ in range(2 if twin else 1): osa(MAKE, json.dumps({"list": LIST, "title": t, "flagged": flagged, "done": done}), lang="JavaScript")
    for _ in range(40):
        if len(rows(t)) == (2 if twin else 1): break
        time.sleep(0.5)
    return {"t": t}
def state_cases(state):
    m = "background"
    K.case("reminder_reopen", m, state, "done", lambda: rem(done=True), lambda c: R.reminder_reopen(match=c["t"]), lambda c, b, a, r, e: {"no_error": e is None, "db_open": rows(c["t"]) == [(False, False)], "return": bool(r) and r.get("completed") is False if "completed" in (r or {}) else bool(r)})
    K.case("reminder_reopen", m, state, "done_twice", lambda: rem(done=True), lambda c: R.reminder_reopen(match=c["t"]), lambda c, b, a, r, e: {"no_error": e is None, "db_open": rows(c["t"]) == [(False, False)]})
def errors():
    m, st = "background", "open"
    K.case("reminder_reopen", m, st, "not_found", lambda: {}, lambda c: R.reminder_reopen(match="No Such Reminder 58291"), lambda c, b, a, r, e: {"raised": isinstance(e, R.NotFound)})
    K.case("reminder_reopen", m, st, "ambiguous", lambda: rem(done=True, twin=True), lambda c: R.reminder_reopen(match=c["t"]), lambda c, b, a, r, e: {"raised": isinstance(e, R.Ambiguous), "neither": rows(c["t"]) == [(False, True), (False, True)]})
    K.case("reminder_reopen", m, st, "not_done", lambda: rem(), lambda c: R.reminder_reopen(match=c["t"]), lambda c, b, a, r, e: {"raised": isinstance(e, ValueError), "same": rows(c["t"]) == [(False, False)]})
    for fn, call in (("reminder_reopen", lambda c: R.reminder_reopen(match=c["t"], mode="ui")),):
        K.case(fn, "ui", st, "ui_not_supported", lambda: rem(done=True), call, lambda c, b, a, r, e: {"raised": isinstance(e, R.NotSupported)}, clip=False)
def tidy():
    try: osa('on run argv\ntell application "Reminders" to delete (every list whose name is (item 1 of argv))\nend run', LIST)
    except RuntimeError: pass
groups = [(s, (lambda s=s: state_cases(s))) for s in ("closed", "open", "other_app", "hidden")] + [("errors", errors)]
try: K.run(states, groups)
finally: tidy()
