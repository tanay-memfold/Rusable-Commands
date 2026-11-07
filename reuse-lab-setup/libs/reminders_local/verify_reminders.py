"""Verify reminders.py inside the VM: python3 verify_reminders.py <group> <seed> <state|errors|blocked> ...

Every case: set up with plain scripting (never reminders.py), put Reminders into a start state, call the function with
fresh made-up values, read Reminders' own database, check every field, that nothing else changed, and the screen."""
import ctypes, hashlib, json, os, sys, time, traceback
HOME = os.path.expanduser("~"); sys.path[:0] = [f"{HOME}/reminders-test"]
import ax, bigclip, rem_db as D, reminders as R
from vcommon import Recorder, Values, osa, se, sh, wait
GROUP, SEED, ONLY = sys.argv[1], int(sys.argv[2]), sys.argv[3:]
V = Values(SEED)
REC = Recorder(GROUP, {"versions": R._versions(), "code_sha": hashlib.sha256(open(R.__file__, "rb").read()).hexdigest()[:12], "seed": SEED, "started": time.strftime("%Y-%m-%d %H:%M:%S")})
APP = "Reminders"
FAILS = {}
# Set by the laptop's runner: skip cases already run before a time limit was hit, and limit which commands run.
RESUME = int(os.environ.get("RESUME", "0"))
ONLY_FNS = set(filter(None, os.environ.get("FNS", "").split(",")))
COUNT = {"n": 0}
open(f"{HOME}/reminders-test/verifier.pid", "w").write(str(os.getpid()))
PREP = r"""
function run(argv) {
  const Rem = Application("Reminders"), a = JSON.parse(argv[1]);
  const acc = Rem.accounts()[0];
  const at = p => new Date(p[0], p[1] - 1, p[2], p[3], p[4]);
  const list = n => acc.lists().find(l => l.name() === n);
  switch (argv[0]) {
    case "list": acc.lists.push(Rem.List({name: a.name})); return "ok";
    case "reminder": {
      const p = {name: a.title}; if (a.notes) p.body = a.notes; if (a.priority) p.priority = a.priority;
      const r = Rem.Reminder(p); list(a.list).reminders.push(r);
      if (a.due) r.dueDate = at(a.due);
      if (a.done) r.completed = true;
      return "ok";
    }
    case "show": Rem.show(list(a.name)); return "ok";
    case "default": return Rem.defaultList().name();
    case "sweep": {
      for (const l of acc.lists()) {
        if (!a.lists.includes(l.name())) { try { Rem.delete(l); } catch (e) {} continue; }
        for (const r of l.reminders()) if (!a.titles.includes(r.name())) Rem.delete(r);
      }
      return "ok";
    }
  }
}"""
def prep(op, **a): return osa(PREP, op, json.dumps(a), lang="JavaScript")
A = lambda: ax.app(APP)
def win(): return next((c for c in ax.children(A()) if ax.sattr(c, "AXRole") == "AXWindow"), None)
def sheets(): return [e for e in ax.children(win())if ax.sattr(e, "AXRole") == "AXSheet"] if win() else []
def running(): return bool(sh(f"pgrep -x {APP}"))
def menu(m, i): return se(f'click menu item "{i}" of menu "{m}" of menu bar item "{m}" of menu bar 1', APP)
def pane(): return next((e for e in ax.walk(win()) if ax.sattr(e, "AXRole") == "AXLayoutArea" and ax.sattr(e, "AXDescription") != "Reminder lists"), None)
def quit_app():
    if running():
        sh("osascript -e 'tell application \"Reminders\" to quit'")
        wait(lambda: not running(), 15)
def row_of(title):
    for e in ax.walk(pane()):
        if ax.sattr(e, "AXRole") == "AXRow" and any(ax.sattr(f, "AXRole") == "AXTextField" and ax.sattr(f, "AXValue") == title for f in ax.walk(e)):
            return e
def front():
    sh("open -b com.apple.reminders"); wait(running, 15); sh("osascript -e 'tell application \"Reminders\" to activate'")
    se("set visible to true", APP)
    wait(win, 10)
    w = win()
    if w and ax.attr(w, "AXMinimized") == ax.TRUE.value:
        ax.AS.AXUIElementSetAttributeValue(w, ax.cf("AXMinimized"), ctypes.c_void_p.in_dll(ax.CF, "kCFBooleanFalse")); time.sleep(0.6)
    if not win(): sh("open -b com.apple.reminders"); wait(win, 10)
    for _ in range(6):
        ss = sheets()
        if ss:
            b = next((x for x in (ax.find(ss[0], "AXButton", n, exact=True) for n in ("Cancel", "Not Now", "Continue")) if x), None)
            if b: ax.press(b); time.sleep(1.2); continue
        c = ax.find(win(), "AXButton", "Continue", exact=True)
        if c: ax.press(c); time.sleep(1.2); continue
        if any(ax.sattr(e, "AXRole") == "AXPopover" for e in ax.walk(win())):
            se("key code 53", APP); time.sleep(0.5); continue
        break
    s = next((e for e in ax.walk(win()) if ax.sattr(e, "AXSubrole") == "AXSearchField"), None)
    if s and ax.sattr(s, "AXValue"):
        c = ax.find(s, "AXButton", "cancel")
        if c: ax.press(c)
        se("key code 53", APP); time.sleep(0.4)
    if se('exists menu item "Show Sidebar" of menu "View" of menu bar item "View" of menu bar 1', APP) == "true":
        menu("View", "Show Sidebar"); time.sleep(0.5)
BASE = ["Base Alpha", "Base Beta"]
TITLES = ["Standup", "Standup review", "Dentist", "Done thing"]
def base():
    if all(n in D.snapshot()["lists"].values() for n in BASE): return
    for n in BASE: prep("list", name=n)
    time.sleep(1)
    prep("reminder", title="Standup", list="Base Alpha"); prep("reminder", title="Standup", list="Base Beta")
    prep("reminder", title="Standup review", list="Base Alpha", notes="keep me")
    prep("reminder", title="Dentist", list="Base Beta", due=[2026, 11, 19, 15, 0], priority=5)
    prep("reminder", title="Done thing", list="Base Alpha", done=True)
    wait(lambda: len(D.snapshot()["reminders"]) >= 5, 15)
def sweep():
    prep("sweep", lists=BASE + [prep("default")], titles=TITLES)
def start(state):
    if state in ("closed", "launching"):
        quit_app()
        if state == "launching": sh("open -b com.apple.reminders")
        return
    front()
    if state == "open": prep("show", name=prep("default"))
    elif state == "other_view": prep("show", name="Base Beta")
    elif state == "hidden": se("set visible to false", APP)
    elif state == "minimized": ax.AS.AXUIElementSetAttributeValue(win(), ax.cf("AXMinimized"), ax.TRUE)
    elif state == "other_app":
        sh("open -a Calculator"); wait(lambda: se("return frontmost", APP) == "false", 8)
    elif state == "search_text":
        s = next(e for e in ax.walk(win()) if ax.sattr(e, "AXSubrole") == "AXSearchField"); ax.focus(s); time.sleep(0.3); se('keystroke "half typed"', APP)
    elif state == "popover_open":
        prep("show", name="Base Beta"); r = wait(lambda: row_of("Dentist"), 6); ax.AS.AXUIElementSetAttributeValue(r, ax.cf("AXSelected"), ax.TRUE); time.sleep(0.6)
        ax.press(ax.find(r, "AXButton", "Edit Details")); wait(lambda: any(ax.sattr(e, "AXRole") == "AXPopover" for e in ax.walk(win())), 5)
    elif state == "alert_open":
        menu("File", "New List"); wait(sheets, 5)
    elif state == "selected_row":
        prep("show", name="Base Beta"); r = wait(lambda: row_of("Dentist"), 6); ax.AS.AXUIElementSetAttributeValue(r, ax.cf("AXSelected"), ax.TRUE)
    elif state == "no_sidebar":
        if se('exists menu item "Hide Sidebar" of menu "View" of menu bar item "View" of menu bar 1', APP) == "true": menu("View", "Hide Sidebar")
    elif state == "no_window":
        menu("File", "Close"); wait(lambda: not win(), 5)
    time.sleep(0.6)
def clean():
    if not running() or not win(): return True
    if sheets() or any(ax.sattr(e, "AXRole") in ("AXPopover", "AXMenu") for e in ax.walk(win())): return False
    return True
def titles_of(snap, names): return {k for k, r in snap["reminders"].items() if r["title"] in names}
def case(fn, mode, state, kind, setup, call, read, allowed=()):
    """read(snap, res, err) -> checks; retried until they hold or 12 s pass."""
    if ONLY_FNS and fn not in ONLY_FNS:
        return
    COUNT["n"] += 1
    if COUNT["n"] <= RESUME:
        return
    if FAILS.get((fn, mode), 0) >= 3:
        return
    print(f"CASE {COUNT['n']} {fn} {mode} {state} {kind}", flush=True)
    began = None
    try:
        names = setup() or ()
        time.sleep(0.4)
        start(state)
        before = D.snapshot()
        was_front = se("return frontmost", APP) if running() else "false"
        began = time.monotonic()
        try: res, err = call(), None
        except R.RemindersError as e: res, err = None, e
        except ValueError as e: res, err = None, e
        secs = round(time.monotonic() - began, 1)
        last = {}
        end = time.monotonic() + 12
        while True:
            snap = D.snapshot(); last = read(snap, res, err)
            if all(last.values()) or time.monotonic() > end: break
            time.sleep(0.5)
        watched = titles_of(before, set(names) | set(allowed)) | titles_of(snap, set(names) | set(allowed))
        last["others_unchanged"] = not D.others(before, snap, watched)
        last["base_lists_kept"] = all(n in snap["lists"].values() for n in BASE)
        if mode == "ui": last["nothing_left_open"] = clean()
        elif state != "alert_open": last["stayed_in_background"] = (not running() or se("return frontmost", APP) == was_front)
        REC.case(fn, mode, state, kind, last, repr(err)[:160] if err else None, secs)
        if not all(last.values()): FAILS[(fn, mode)] = FAILS.get((fn, mode), 0) + 1
    except Exception:
        REC.case(fn, mode, state, kind, {"harness": False}, traceback.format_exc()[-300:])
        FAILS[(fn, mode)] = FAILS.get((fn, mode), 0) + 1
def text(i): return V.special() if i % 2 else V.word()
def run_state(state, i):
    d1 = lambda t, **k: prep("reminder", title=t, list="Base Alpha", **k)
    for mode in os.environ.get("MODES", "background,ui").split(","):
        # create
        t, n = text(i), f"note {V.word(1)}\nsecond line {i}"
        case("reminder_create", mode, state, "normal", lambda: [t], lambda: R.reminder_create(title=t, list="Base Alpha", notes=n, mode=mode),
             lambda s, r, e: (lambda f: {"no_error": e is None, "one": len(f) == 1, "list": bool(f) and f[0]["list"] == "Base Alpha", "notes": bool(f) and f[0]["notes"].strip() == n.strip(), "return": bool(r) and r["title"] == t})(D.titled(s, t)))
        t2 = text(i + 1)
        default = prep("default")
        case("reminder_create", mode, state, "default_list", lambda: [t2], lambda: R.reminder_create(title=t2, mode=mode),
             lambda s, r, e: (lambda f: {"no_error": e is None, "one": len(f) == 1, "default_list": bool(f) and f[0]["list"] == default})(D.titled(s, t2)))
        if mode == "background":
            t3, t4 = text(i), text(i + 1)
            case("reminder_create", mode, state, "due_time", lambda: [t3], lambda: R.reminder_create(title=t3, list="Base Beta", due="2026-12-31 23:45", priority="high", mode=mode),
                 lambda s, r, e: (lambda f: {"no_error": e is None, "due": bool(f) and f[0]["due"] == "2026-12-31 23:45", "priority": bool(f) and f[0]["priority"] == "high", "return": bool(r) and r["due"] == "2026-12-31 23:45"})(D.titled(s, t3)))
            case("reminder_create", mode, state, "due_day", lambda: [t4], lambda: R.reminder_create(title=t4, list="Base Beta", due="2027-02-28", mode=mode),
                 lambda s, r, e: (lambda f: {"no_error": e is None, "due": bool(f) and f[0]["due"] == "2027-02-28", "return": bool(r) and r["due"] == "2027-02-28"})(D.titled(s, t4)))
            q = V.word(1).split()[0] + f"Z{i}"
            t5 = f"{q} list target"
            case("reminder_list", mode, state, "normal", lambda: d1(t5) and [], lambda: R.reminder_list(list="Base Alpha", fields="title,list,completed", mode=mode),
                 lambda s, r, e: {"no_error": e is None, "matches_db": bool(r) and sorted(x["title"] for x in r) == sorted(v["title"] for v in s["reminders"].values() if v["list"] == "Base Alpha" and not v["completed"]), "only_fields": bool(r) and set(r[0]) == {"title", "list", "completed"}})
            case("reminder_list", mode, state, "completed", lambda: [], lambda: R.reminder_list(list="Base Alpha", completed=True, mode=mode),
                 lambda s, r, e: {"no_error": e is None, "matches_db": r is not None and sorted(x["title"] for x in r) == sorted(v["title"] for v in s["reminders"].values() if v["list"] == "Base Alpha" and v["completed"])})
            case("reminder_search", mode, state, "normal", lambda: [], lambda: R.reminder_search(query=q.lower(), mode=mode),
                 lambda s, r, e: {"no_error": e is None, "found": bool(r) and [x["title"] for x in r] == [t5]})
            t6 = text(i)
            case("reminder_get", mode, state, "normal", lambda: prep("reminder", title=t6, list="Base Beta", notes="got it", due=[2026, 12, 1, 9, 30], priority=9) and [], lambda: R.reminder_get(match=t6, fields="title,notes,list,due,priority,completed", mode=mode),
                 lambda s, r, e: (lambda f: {"no_error": e is None, "fields_match_db": bool(r) and bool(f) and all(r[k] == f[0][k] for k in ("title", "notes", "list", "due", "priority", "completed"))})(D.titled(s, t6)))
            u1, u2 = text(i), text(i + 1)
            case("reminder_update", mode, state, "all_fields", lambda: d1(u1) and [u1, u2], lambda: R.reminder_update(match=u1, title=u2, due="2027-03-04 08:05", notes="changed", priority="low", mode=mode),
                 lambda s, r, e: (lambda f: {"no_error": e is None, "old_gone": not D.titled(s, u1), "due": bool(f) and f[0]["due"] == "2027-03-04 08:05", "notes": bool(f) and f[0]["notes"] == "changed", "priority": bool(f) and f[0]["priority"] == "low"})(D.titled(s, u2)))
            u3 = text(i)
            case("reminder_update", mode, state, "only_due_day", lambda: d1(u3, notes="stay") and [u3], lambda: R.reminder_update(match=u3, due="2027-04-05", mode=mode),
                 lambda s, r, e: (lambda f: {"no_error": e is None, "due": bool(f) and f[0]["due"] == "2027-04-05", "notes_kept": bool(f) and f[0]["notes"] == "stay"})(D.titled(s, u3)))
            case("list_list", mode, state, "normal", lambda: [], lambda: R.list_list(mode=mode),
                 lambda s, r, e: {"no_error": e is None, "names_match_db": r is not None and {x["name"] for x in r} == set(s["lists"].values()) - {"SiriFoundInApps"}})
        else:
            u4, u5 = text(i), text(i + 1)
            case("reminder_update", mode, state, "title_notes", lambda: d1(u4, notes="old") and [u4, u5], lambda: R.reminder_update(match=u4, list="Base Alpha", title=u5, notes="new notes", mode=mode),
                 lambda s, r, e: (lambda f: {"no_error": e is None, "old_gone": not D.titled(s, u4), "notes": bool(f) and f[0]["notes"] == "new notes"})(D.titled(s, u5)))
        c = text(i)
        case("reminder_complete", mode, state, "normal", lambda: d1(c, due=[2026, 12, 2, 10, 0]) and [c], lambda: R.reminder_complete(match=c, mode=mode),
             lambda s, r, e: (lambda f: {"no_error": e is None, "done": bool(f) and f[0]["completed"], "due_kept": bool(f) and f[0]["due"] == "2026-12-02 10:00", "return": bool(r) and r["completed"]})(D.titled(s, c)))
        x = text(i + 1)
        case("reminder_delete", mode, state, "normal", lambda: d1(x) and [x], lambda: R.reminder_delete(match=x, mode=mode),
             lambda s, r, e: {"no_error": e is None, "gone": not D.titled(s, x), "return": bool(r) and r["deleted"]})
        xc = text(i)
        case("reminder_delete", mode, state, "completed", lambda: d1(xc, done=True) and [xc], lambda: R.reminder_delete(match=xc, mode=mode),
             lambda s, r, e: {"no_error": e is None, "gone": not D.titled(s, xc)})
        l1, l2, l3, l4 = text(i), text(i + 1), text(i), text(i + 1)
        case("list_create", mode, state, "normal", lambda: [], lambda: R.list_create(name=l1, mode=mode),
             lambda s, r, e: {"no_error": e is None, "one": list(s["lists"].values()).count(l1) == 1, "return": bool(r) and r["name"] == l1})
        case("list_rename", mode, state, "normal", lambda: prep("list", name=l2) and prep("reminder", title=l2 + " item", list=l2) and [l2 + " item"], lambda: R.list_rename(name=l2, to=l3, mode=mode),
             lambda s, r, e: (lambda f: {"no_error": e is None, "renamed": l3 in s["lists"].values() and l2 not in s["lists"].values(), "item_moved_with": bool(f) and f[0]["list"] == l3})(D.titled(s, l2 + " item")))
        case("list_delete", mode, state, "with_items", lambda: prep("list", name=l4) and prep("reminder", title=l4 + " item", list=l4) and [l4 + " item"], lambda: R.list_delete(name=l4, mode=mode),
             lambda s, r, e: {"no_error": e is None, "gone": l4 not in s["lists"].values(), "item_gone": not D.titled(s, l4 + " item")})
        l5 = text(i)
        case("list_delete", mode, state, "empty", lambda: prep("list", name=l5) and [], lambda: R.list_delete(name=l5, mode=mode),
             lambda s, r, e: {"no_error": e is None, "gone": l5 not in s["lists"].values()})
    sweep()
def errors():
    st = "other_view"
    for mode in ("background", "ui"):
        nope = "No Such Thing 58291"
        for fn, call in [("reminder_complete", lambda: R.reminder_complete(match=nope, mode=mode)), ("reminder_delete", lambda: R.reminder_delete(match=nope, mode=mode)), ("reminder_update", lambda: R.reminder_update(match=nope, title="x", mode=mode)), ("list_rename", lambda: R.list_rename(name=nope, to="x y", mode=mode)), ("list_delete", lambda: R.list_delete(name=nope, mode=mode))]:
            case(fn, mode, st, "not_found", lambda: [], call, lambda s, r, e: {"raised_NotFound": isinstance(e, R.NotFound)})
        for fn, call in [("reminder_complete", lambda: R.reminder_complete(match="Standup", mode=mode)), ("reminder_delete", lambda: R.reminder_delete(match="Standup", mode=mode)), ("reminder_update", lambda: R.reminder_update(match="Standup", title="x", mode=mode))]:
            case(fn, mode, st, "ambiguous", lambda: [], call, lambda s, r, e: {"raised_Ambiguous": isinstance(e, R.Ambiguous), "both_kept": len(D.titled(s, "Standup")) == 2})
        case("reminder_complete", mode, st, "list_narrows", lambda: ["Standup"], lambda: R.reminder_complete(match="Standup", list="Base Beta", mode=mode),
             lambda s, r, e: {"no_error": e is None, "right_one": [x["completed"] for x in D.titled(s, "Standup") if x["list"] == "Base Beta"] == [True], "other_kept": [x["completed"] for x in D.titled(s, "Standup") if x["list"] == "Base Alpha"] == [False]})
        case("list_create", mode, st, "already_exists", lambda: [], lambda: R.list_create(name="Base Beta", mode=mode), lambda s, r, e: {"raised": isinstance(e, R.AlreadyExists), "one": list(s["lists"].values()).count("Base Beta") == 1})
        case("list_rename", mode, st, "already_exists", lambda: [], lambda: R.list_rename(name="Base Alpha", to="Base Beta", mode=mode), lambda s, r, e: {"raised": isinstance(e, R.AlreadyExists), "kept": "Base Alpha" in s["lists"].values()})
        case("reminder_create", mode, st, "bad_list", lambda: [], lambda: R.reminder_create(title="Never", list="No Such List", mode=mode), lambda s, r, e: {"raised_NotFound": isinstance(e, R.NotFound), "none": not D.titled(s, "Never")})
        case("reminder_create", mode, st, "bad_due", lambda: [], lambda: R.reminder_create(title="Never", due="soon", mode=mode), lambda s, r, e: {"raised": isinstance(e, ValueError), "none": not D.titled(s, "Never")})
        case("reminder_create", mode, st, "midnight_refused", lambda: [], lambda: R.reminder_create(title="Never", due="2027-01-01 00:00", mode=mode), lambda s, r, e: {"raised": isinstance(e, (ValueError, R.NotSupported)), "none": not D.titled(s, "Never")})
    case("reminder_create", "ui", st, "due_refused", lambda: [], lambda: R.reminder_create(title="Never", due="2027-01-01", mode="ui"), lambda s, r, e: {"raised": isinstance(e, R.NotSupported), "none": not D.titled(s, "Never")})
    case("reminder_update", "ui", st, "due_refused", lambda: ["Dentist"], lambda: R.reminder_update(match="Dentist", due="2027-01-01", mode="ui"), lambda s, r, e: {"raised": isinstance(e, R.NotSupported), "kept": D.titled(s, "Dentist")[0]["due"] == "2026-11-19 15:00"})
    sweep()
def big(fn, setup, call, read):
    """A very large clipboard before the call: the call must work and the clipboard must come back exactly."""
    box = {}
    def prepare():
        names = setup() or []; box["want"] = bigclip.fill(V.rng.randint(1, 10**9)); return names
    def checks(s, r, e):
        c = read(s, r, e); c.update(bigclip.check(box["want"])); return c
    case(fn, "ui", "other_view", "large_clipboard", prepare, call, checks)
def moving():
    for state in ("closed", "open", "other_view", "hidden", "minimized", "other_app", "search_text", "selected_row"):
        t, n = V.special(), f"note {V.word(1)}"
        case("reminder_move", "background", state, "normal", lambda: prep("reminder", title=t, list="Base Alpha", notes=n, due=[2027, 1, 5, 9, 30], priority=5) and [t], lambda: R.reminder_move(match=t, to_list="Base Beta"),
             lambda s, r, e: (lambda f: {"no_error": e is None, "one": len(f) == 1, "in_new_list": bool(f) and f[0]["list"] == "Base Beta", "notes_kept": bool(f) and f[0]["notes"] == n, "due_kept": bool(f) and f[0]["due"] == "2027-01-05 09:30", "priority_kept": bool(f) and f[0]["priority"] == "medium", "return": bool(r) and r["list"] == "Base Beta"})(D.titled(s, t)))
        sweep()
    case("reminder_move", "background", "other_view", "not_found", lambda: [], lambda: R.reminder_move(match="No Such Thing 58291", to_list="Base Beta"), lambda s, r, e: {"raised": isinstance(e, R.NotFound)})
    case("reminder_move", "background", "other_view", "no_list", lambda: [], lambda: R.reminder_move(match="Dentist", to_list="No Such List"), lambda s, r, e: {"raised": isinstance(e, R.NotFound), "kept": D.titled(s, "Dentist")[0]["list"] == "Base Beta"})
    case("reminder_move", "background", "other_view", "ambiguous", lambda: [], lambda: R.reminder_move(match="Standup", to_list="Base Beta"), lambda s, r, e: {"raised": isinstance(e, R.Ambiguous)})
    case("reminder_move", "background", "other_view", "list_narrows", lambda: ["Standup"], lambda: R.reminder_move(match="Standup", list="Base Alpha", to_list=prep("default")), lambda s, r, e: {"no_error": e is None, "other_stays": [x["list"] for x in D.titled(s, "Standup") if x["list"] == "Base Beta"] == ["Base Beta"], "moved": sum(x["list"] != "Base Beta" and x["list"] != "Base Alpha" for x in D.titled(s, "Standup")) == 1})
    sweep()
def large_clipboard():
    d1 = lambda t, **k: prep("reminder", title=t, list="Base Alpha", **k)
    t, n, u1, u2, c, x, l1, l2, l3, l4 = V.special(), f"note {V.word(1)}\nsecond line", V.word(), V.special(), V.word(), V.word(), V.special(), V.word(), V.special(), V.word()
    big("reminder_create", lambda: [t], lambda: R.reminder_create(title=t, list="Base Alpha", notes=n, mode="ui"),
        lambda s, r, e: (lambda f: {"no_error": e is None, "one": len(f) == 1, "notes": bool(f) and f[0]["notes"].strip() == n.strip()})(D.titled(s, t)))
    big("reminder_update", lambda: d1(u1, notes="old") and [u1, u2], lambda: R.reminder_update(match=u1, list="Base Alpha", title=u2, notes="new notes", mode="ui"),
        lambda s, r, e: (lambda f: {"no_error": e is None, "old_gone": not D.titled(s, u1), "notes": bool(f) and f[0]["notes"] == "new notes"})(D.titled(s, u2)))
    big("reminder_complete", lambda: d1(c) and [c], lambda: R.reminder_complete(match=c, mode="ui"),
        lambda s, r, e: (lambda f: {"no_error": e is None, "done": bool(f) and f[0]["completed"]})(D.titled(s, c)))
    big("reminder_delete", lambda: d1(x) and [x], lambda: R.reminder_delete(match=x, mode="ui"), lambda s, r, e: {"no_error": e is None, "gone": not D.titled(s, x)})
    big("list_create", lambda: [], lambda: R.list_create(name=l1, mode="ui"), lambda s, r, e: {"no_error": e is None, "one": list(s["lists"].values()).count(l1) == 1})
    big("list_rename", lambda: prep("list", name=l2) and [], lambda: R.list_rename(name=l2, to=l3, mode="ui"), lambda s, r, e: {"no_error": e is None, "renamed": l3 in s["lists"].values() and l2 not in s["lists"].values()})
    big("list_delete", lambda: prep("list", name=l4) and [], lambda: R.list_delete(name=l4, mode="ui"), lambda s, r, e: {"no_error": e is None, "gone": l4 not in s["lists"].values()})
    sweep()
def blocked():
    # typed dialog
    front(); menu("File", "New List"); wait(sheets, 5); time.sleep(0.4); se('keystroke "half typed list"', APP); time.sleep(0.6)
    before = D.snapshot()
    for fn, call in [("reminder_create", lambda: R.reminder_create(title="Never", mode="ui")), ("reminder_complete", lambda: R.reminder_complete(match="Dentist", mode="ui")), ("reminder_delete", lambda: R.reminder_delete(match="Dentist", mode="ui")), ("reminder_update", lambda: R.reminder_update(match="Dentist", title="Never", mode="ui")), ("list_create", lambda: R.list_create(name="Never L", mode="ui")), ("list_rename", lambda: R.list_rename(name="Base Beta", to="Never L", mode="ui")), ("list_delete", lambda: R.list_delete(name="Base Beta", mode="ui"))]:
        try: call(); err = None
        except Exception as e: err = e
        ss = sheets(); f = next((e for e in ax.walk(ss[0]) if ax.sattr(e, "AXRole") == "AXTextField"), None) if ss else None
        REC.case(fn, "ui", "typed_text", "blocked", {"raised_StateBlocked": isinstance(err, R.StateBlocked), "typed_kept": bool(f) and ax.sattr(f, "AXValue") == "half typed list", "nothing_changed": not D.others(before, D.snapshot(), ())}, repr(err)[:120])
    # scripting isn't touched by what's on screen
    t = V.word()
    try: r = R.reminder_create(title=t, list="Base Alpha", mode="background"); err = None
    except Exception as e: r, err = None, e
    ss = sheets(); f = next((e for e in ax.walk(ss[0]) if ax.sattr(e, "AXRole") == "AXTextField"), None) if ss else None
    REC.case("reminder_create", "background", "typed_text", "works_and_leaves_it", {"no_error": err is None, "typed_kept": bool(f) and ax.sattr(f, "AXValue") == "half typed list", "created": wait(lambda: D.titled(D.snapshot(), t), 12) is not None}, repr(err)[:120])
    c = ax.find(ss[0], "AXButton", "Cancel", exact=True) if ss else None
    if c: ax.press(c); time.sleep(1)
    sweep()
STATES = ["closed", "launching", "open", "other_view", "hidden", "minimized", "other_app", "search_text", "popover_open", "alert_open", "selected_row", "no_sidebar", "no_window"]
try:
    base()
    for i, state in enumerate(STATES):
        if state in ONLY:
            print(f"== state starts: {state} at {time.strftime('%H:%M:%S')}, reminders {len(D.snapshot()['reminders'])}", flush=True); run_state(state, i)
    if "errors" in ONLY:
        print(f"== state starts: errors at {time.strftime('%H:%M:%S')}", flush=True); errors()
    if "blocked" in ONLY:
        print(f"== state starts: blocked at {time.strftime('%H:%M:%S')}", flush=True); blocked()
    if "moving" in ONLY:
        print(f"== state starts: moving at {time.strftime('%H:%M:%S')}", flush=True); moving()
    if "large_clipboard" in ONLY:
        print(f"== state starts: large_clipboard at {time.strftime('%H:%M:%S')}", flush=True); large_clipboard()
finally:
    REC.data["meta"]["finished"] = time.strftime("%Y-%m-%d %H:%M:%S"); REC.save(); print("DONE", flush=True)
