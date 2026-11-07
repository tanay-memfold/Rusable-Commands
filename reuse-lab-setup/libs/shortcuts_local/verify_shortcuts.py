"""verify_shortcuts.py <group> <seed> <states...>: Shortcuts' commands, read back independently: Shortcuts' own database (read
only: names, deleted flags, saved actions and their paths, run counts) and the `shortcuts` command-line tool (folders)."""
import os, plistlib, sqlite3, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shortcuts as S, vkit, ax
from vcommon import osa, sh, se
group, seed, states = sys.argv[1], int(sys.argv[2]), sys.argv[3:]
APP = "Shortcuts"
DB = os.path.expanduser("~/Library/Shortcuts/Shortcuts.sqlite")
IDS = {"Comment": "is.workflow.actions.comment", "Random Number": "is.workflow.actions.number.random", "Stop and Output": "is.workflow.actions.output",
       "File": "is.workflow.actions.file", "Make Archive": "is.workflow.actions.makezip", "Save File": "is.workflow.actions.documentpicker.save",
       "Show Result": "is.workflow.actions.showresult", "Wait": "is.workflow.actions.delay", "Count": "is.workflow.actions.count"}
def db():
    return sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
def rows():
    """Live shortcuts: name -> (pk, run count, actions list)."""
    out = {}
    with db() as c:
        for pk, name, runs, acts in c.execute("select Z_PK, ZNAME, ZRUNEVENTSCOUNT, ZACTIONS from ZSHORTCUT where ZTOMBSTONED = 0"):
            data = c.execute("select ZDATA from ZSHORTCUTACTIONS where Z_PK = ?", (acts,)).fetchone()
            try: actions = plistlib.loads(data[0]) if data and data[0] else []
            except Exception: actions = None
            out.setdefault(name, []).append((pk, runs or 0, actions))
    return out
def live(name): return len(rows().get(name, []))
def acts(name):
    r = rows().get(name, [])
    return r[0][2] if len(r) == 1 else None
def runs(name):
    r = rows().get(name, [])
    return r[0][1] if len(r) == 1 else None
def ids(name): return [a.get("WFWorkflowActionIdentifier") for a in (acts(name) or [])]
def home_rel(p): return os.path.relpath(os.path.realpath(p), os.path.realpath(os.path.expanduser("~")))
def file_param(a, key):
    loc = (a.get("WFWorkflowActionParameters", {}).get(key) or {}).get("fileLocation") or {}
    return loc.get("relativeSubpath") if loc.get("WFFileLocationType") == "Home" else None
def cli_folders(): return [l for l in sh("shortcuts list --folders").split("\n") if l]
def cli_in(folder): return [l for l in sh(f"shortcuts list -f {sh_quote(folder)}").split("\n") if l]
def sh_quote(t): return "'" + t.replace("'", "'\\''") + "'"
def running(): return bool(sh("pgrep -x Shortcuts"))
def front_app():
    try: return osa('tell application "System Events" to return name of first process whose frontmost is true')
    except RuntimeError: return ""
def windows(): return [w for w in ax.children(ax.app(APP)) if ax.sattr(w, "AXRole") == "AXWindow"] if running() else []
def editors(): return [w for w in windows() if any(ax.sattr(e, "AXIdentifier") == "actions.list" for e in ax.walk(w))]
def start(state):
    if state == "closed":
        if running():
            sh("pkill -x Shortcuts"); [time.sleep(0.5) for _ in range(30) if running()]
        return
    if not running(): sh("open -b com.apple.shortcuts"); [time.sleep(0.5) for _ in range(30) if not windows()]; time.sleep(1.5)
    for w in editors():  # setup only: an editor left by a failed setup create is closed before the case starts
        b = ax.attr(w, "AXCloseButton"); b and ax.press(b); time.sleep(0.8)
    se("set visible to true\nset frontmost to true", APP); time.sleep(0.5)
    if state == "other_app": sh("open -a Calculator"); [time.sleep(0.3) for _ in range(20) if front_app() == APP]
    time.sleep(0.4)
def clean(state):
    """Nothing modal and no editor left open (a successful create closes its editor)."""
    if not running(): return True
    return not editors() and not any(ax.sattr(c, "AXRole") == "AXSheet" for w in windows() for c in ax.children(w)) \
        and not any(ax.sattr(w, "AXIdentifier") in ("open-panel", "save-panel") for w in windows())
K = vkit.Kit("shortcuts", S, APP, group, seed, S.ShortcutsError, start, clean)
D = f"{K.DATA}/files"; os.makedirs(D, exist_ok=True)
def nm(special=False): return (K.V.special() if special else K.V.word()).replace("/", "-").replace("“", "").replace("”", "")
def folder_with_files():
    p = f"{D}/{K.word()} src"; os.makedirs(f"{p}/inner"); open(f"{p}/a.txt", "w").write(K.V.word()); open(f"{p}/inner/b.md", "w").write(K.V.word())
    return p
def out_folder():
    p = f"{D}/{K.word()} out"; os.makedirs(p); return p
def make(name, actions):
    """Setup only: a shortcut made through the lab's shortcut_create (left out of the published library after two fixes),
    tried up to three times; the commands under test are checked as before."""
    for attempt in range(3):
        try:
            S.shortcut_create(name=name, actions=actions)
            break
        except S.ShortcutsError:
            if attempt == 2 or any(s["name"] == name for s in S.shortcut_list()):
                raise
            start("open")
    start("open")
FLOWS = [("comment", ["Comment"]), ("two", ["Random Number", "Stop and Output"]), ("three", ["Comment", "Wait", "Show Result"])]
def created(c, b, a, r, e):
    want = [IDS[x if isinstance(x, str) else x["action"]] for x in c["actions"]]
    return {"no_error": e is None, "one_live": live(c["n"]) == 1, "actions_saved": ids(c["n"]) == want,
            "return": bool(r) and r["name"] == c["n"] and r["action_count"] == len(want)}
def create_cases(state):
    m = "ui"
    for kind, actions in FLOWS:
        K.case("shortcut_create", m, state, kind, lambda actions=actions: {"n": nm(), "actions": actions}, lambda c: S.shortcut_create(name=c["n"], actions=c["actions"]), created)
    K.case("shortcut_create", m, state, "special_name", lambda: {"n": nm(True), "actions": ["Comment"]}, lambda c: S.shortcut_create(name=c["n"], actions=c["actions"]), created)
    def archive():
        src, out = folder_with_files(), out_folder()
        return {"n": nm(), "src": src, "out": out, "actions": [{"action": "File", "path": src}, "Make Archive", {"action": "Save File", "save_to": out}]}
    def archived(c, b, a, r, e):
        got = acts(c["n"]) or [{}, {}, {}]
        save = got[-1].get("WFWorkflowActionParameters", {}) if got else {}
        return {**created(c, b, a, r, e), "file_path": file_param(got[0], "WFFile") == home_rel(c["src"]),
                "save_folder": file_param(got[-1], "WFFolder") == home_rel(c["out"]), "ask_off": save.get("WFAskWhereToSave") is False}
    K.case("shortcut_create", m, state, "archive_flow", archive, lambda c: S.shortcut_create(name=c["n"], actions=c["actions"]), archived)
def delete_cases(state):
    m = "ui"
    def one(special=False, folder=False):
        def setup():
            n = nm(special); make(n, ["Comment"])
            if folder:
                f = nm(); S.folder_create(name=f); S.shortcut_move(name=n, folder=f)
            start(state); return {"n": n}
        return setup
    gone = lambda c, b, a, r, e: {"no_error": e is None, "gone": live(c["n"]) == 0, "not_listed": c["n"] not in sh("shortcuts list").split("\n"),
                                  "return": bool(r) and r["deleted"] is True}
    K.case("shortcut_delete", m, state, "plain", one(), lambda c: S.shortcut_delete(name=c["n"]), gone)
    K.case("shortcut_delete", m, state, "special_name", one(True), lambda c: S.shortcut_delete(name=c["n"]), gone)
    K.case("shortcut_delete", m, state, "in_folder", one(folder=True), lambda c: S.shortcut_delete(name=c["n"]), gone)
def background_cases(state):
    m = "background"
    def listed_setup():
        n1, n2, f = nm(), nm(True), nm(); make(n1, ["Comment"]); make(n2, ["Random Number", "Stop and Output"]); S.folder_create(name=f); S.shortcut_move(name=n2, folder=f)
        start(state); return {"n1": n1, "n2": n2, "f": f}
    def listed(c, b, a, r, e):
        r = r or []; by = {x["name"]: x for x in r}
        names = [l for l in sh("shortcuts list").split("\n") if l]
        return {"no_error": e is None, "same_names": sorted(by) == sorted(names) and len(by) == len(r),
                "folder": by.get(c["n2"], {}).get("folder") == c["f"] and c["n2"] in cli_in(c["f"]) and by.get(c["n1"], {}).get("folder") is None,
                "counts": all(by.get(n, {}).get("action_count") == len(acts(n) or []) for n in (c["n1"], c["n2"])), "sorted": [x["name"] for x in r] == sorted(x["name"] for x in r)}
    K.case("shortcut_list", m, state, "mixed", listed_setup, lambda c: S.shortcut_list(), listed)
    def run_setup(actions, folder=False):
        def setup():
            n = nm(); make(n, actions)
            f = None
            if folder: f = nm(); S.folder_create(name=f); S.shortcut_move(name=n, folder=f)
            start(state); return {"n": n, "runs": runs(n)}
        return setup
    ran = lambda check: (lambda c, b, a, r, e: {"no_error": e is None, "ran_once": runs(c["n"]) == (c["runs"] or 0) + 1, "output": bool(r) and check(r["output"])})
    def number(t):
        try: float(t); return True
        except (TypeError, ValueError): return False
    K.case("shortcut_run", m, state, "no_output", run_setup(["Comment"]), lambda c: S.shortcut_run(name=c["n"]), ran(lambda o: o is None))
    K.case("shortcut_run", m, state, "number_output", run_setup(["Random Number", "Stop and Output"]), lambda c: S.shortcut_run(name=c["n"]), ran(number))
    K.case("shortcut_run", m, state, "in_folder", run_setup(["Random Number", "Stop and Output"], True), lambda c: S.shortcut_run(name=c["n"]), ran(number))
    K.case("folder_create", m, state, "plain", lambda: (start(state), {"f": nm()})[1], lambda c: S.folder_create(name=c["f"]),
           lambda c, b, a, r, e: {"no_error": e is None, "listed": cli_folders().count(c["f"]) == 1, "empty": cli_in(c["f"]) == [], "return": bool(r) and r["name"] == c["f"]})
    K.case("folder_create", m, state, "special_name", lambda: (start(state), {"f": nm(True)})[1], lambda c: S.folder_create(name=c["f"]),
           lambda c, b, a, r, e: {"no_error": e is None, "listed": cli_folders().count(c["f"]) == 1})
    def move_setup(already=False, between=False):
        def setup():
            n, f = nm(), nm(); make(n, ["Comment"]); S.folder_create(name=f)
            if already: S.shortcut_move(name=n, folder=f)
            if between:
                g = nm(); S.folder_create(name=g); S.shortcut_move(name=n, folder=g)
            start(state); return {"n": n, "f": f}
        return setup
    moved = lambda flag: (lambda c, b, a, r, e: {"no_error": e is None, "in_folder": c["n"] in cli_in(c["f"]), "still_one": live(c["n"]) == 1, "return": bool(r) and r["moved"] is flag})
    K.case("shortcut_move", m, state, "top_to_folder", move_setup(), lambda c: S.shortcut_move(name=c["n"], folder=c["f"]), moved(True))
    K.case("shortcut_move", m, state, "folder_to_folder", move_setup(between=True), lambda c: S.shortcut_move(name=c["n"], folder=c["f"]), moved(True))
    K.case("shortcut_move", m, state, "already_there", move_setup(already=True), lambda c: S.shortcut_move(name=c["n"], folder=c["f"]), moved(False))
def errors():
    m, st = "ui", "open"
    def existing():
        n = nm(); make(n, ["Comment"]); return {"n": n, "ids": ids(n)}
    K.case("shortcut_create", m, st, "exists", existing, lambda c: S.shortcut_create(name=c["n"], actions=["Wait"]),
           lambda c, b, a, r, e: {"raised": isinstance(e, S.AlreadyExists), "kept": live(c["n"]) == 1 and ids(c["n"]) == c["ids"]})
    def counted(): return {"n": nm(), "before": sorted(rows())}
    K.case("shortcut_create", m, st, "unknown_action", counted, lambda c: S.shortcut_create(name=c["n"], actions=["No Such Action 4417"]),
           lambda c, b, a, r, e: {"raised": isinstance(e, S.NotFound), "not_made": live(c["n"]) == 0})
    K.case("shortcut_create", m, st, "ambiguous_action", counted, lambda c: S.shortcut_create(name=c["n"], actions=["Create Folder"]),
           lambda c, b, a, r, e: {"raised": isinstance(e, S.Ambiguous), "not_made": live(c["n"]) == 0})
    K.case("shortcut_create", m, st, "missing_path", counted, lambda c: S.shortcut_create(name=c["n"], actions=[{"action": "File", "path": f"{D}/none {K.word()}"}]),
           lambda c, b, a, r, e: {"raised": isinstance(e, S.NotFound), "nothing_new": sorted(rows()) == c["before"]})
    K.case("shortcut_create", m, st, "path_on_other_action", counted, lambda c: S.shortcut_create(name=c["n"], actions=[{"action": "Comment", "path": D}]),
           lambda c, b, a, r, e: {"raised": isinstance(e, ValueError), "nothing_new": sorted(rows()) == c["before"]})
    K.case("shortcut_create", m, st, "empty_actions", counted, lambda c: S.shortcut_create(name=c["n"], actions=[]), lambda c, b, a, r, e: {"raised": isinstance(e, ValueError)})
    K.case("shortcut_create", m, st, "blank_name", lambda: {}, lambda c: S.shortcut_create(name="  ", actions=["Comment"]), lambda c, b, a, r, e: {"raised": isinstance(e, ValueError)})
    K.case("shortcut_delete", m, st, "missing", lambda: {}, lambda c: S.shortcut_delete(name=f"none {K.word()}"), lambda c, b, a, r, e: {"raised": isinstance(e, S.NotFound)})
    def prefix():
        n = nm(); make(n, ["Comment"]); make(n + " 2", ["Comment"]); start(st); return {"n": n}
    K.case("shortcut_delete", m, st, "other_name_contains_it", prefix, lambda c: S.shortcut_delete(name=c["n"]),
           lambda c, b, a, r, e: {"raised": isinstance(e, S.Ambiguous), "both_kept": live(c["n"]) == 1 and live(c["n"] + " 2") == 1})
    b = "background"
    K.case("shortcut_run", b, st, "missing", lambda: {}, lambda c: S.shortcut_run(name=f"none {K.word()}"), lambda c, b_, a, r, e: {"raised": isinstance(e, S.NotFound)})
    K.case("shortcut_move", b, st, "missing_folder", existing, lambda c: S.shortcut_move(name=c["n"], folder=f"none {K.word()}"),
           lambda c, b_, a, r, e: {"raised": isinstance(e, S.NotFound), "kept": live(c["n"]) == 1})
    K.case("shortcut_move", b, st, "missing_shortcut", lambda: (lambda f: (S.folder_create(name=f), {"f": f})[1])(nm()), lambda c: S.shortcut_move(name=f"none {K.word()}", folder=c["f"]),
           lambda c, b_, a, r, e: {"raised": isinstance(e, S.NotFound)})
    K.case("folder_create", b, st, "exists", lambda: (lambda f: (S.folder_create(name=f), {"f": f})[1])(nm()), lambda c: S.folder_create(name=c["f"]),
           lambda c, b_, a, r, e: {"raised": isinstance(e, S.AlreadyExists), "still_one": cli_folders().count(c["f"]) == 1})
    for fn, md, call in (("shortcut_create", "background", lambda c: S.shortcut_create(name="x", actions=["Comment"], mode="background")),
                         ("shortcut_delete", "background", lambda c: S.shortcut_delete(name="x", mode="background")),
                         ("shortcut_list", "ui", lambda c: S.shortcut_list(mode="ui")), ("shortcut_run", "ui", lambda c: S.shortcut_run(name="x", mode="ui")),
                         ("folder_create", "ui", lambda c: S.folder_create(name="x", mode="ui")), ("shortcut_move", "ui", lambda c: S.shortcut_move(name="x", folder="y", mode="ui"))):
        K.case(fn, md, st, "not_supported", lambda: {}, call, lambda c, b_, a, r, e: {"raised": isinstance(e, S.NotSupported)})
def permission():
    """Last in its batch: the privacy question it raises is left on screen, unanswered."""
    st = "open"
    def setup():
        src, out = folder_with_files(), out_folder(); n = nm()
        make(n, [{"action": "File", "path": src}, "Make Archive", {"action": "Save File", "save_to": out}]); return {"n": n, "out": out}
    K.case("shortcut_run", "background", st, "privacy_question", setup, lambda c: S.shortcut_run(name=c["n"], timeout=30),
           lambda c, b, a, r, e: {"raised": isinstance(e, S.PermissionNeeded), "nothing_saved": os.listdir(c["out"]) == [], "named": bool(e) and c["n"] in str(e)},
           lambda c: set())
    K.case("shortcut_run", "background", st, "blocked_while_asking", lambda: {"n": S.shortcut_list()[0]["name"]},
           lambda c: S.shortcut_run(name=c["n"]), lambda c, b, a, r, e: {"raised": isinstance(e, S.PermissionNeeded), "says_waiting": bool(e) and "already on screen" in str(e)})
def large_clipboard():
    K.case("shortcut_create", "ui", "open", "large_clipboard", lambda: {"n": nm(), "actions": ["Comment", "Wait"]}, lambda c: S.shortcut_create(name=c["n"], actions=c["actions"]), created, big=True)
groups = [(s, (lambda s=s: create_cases(s))) for s in ("closed", "open", "other_app")] + \
         [(f"delete_{s}", (lambda s=s: delete_cases(s))) for s in ("closed", "open", "other_app")] + \
         [(f"bg_{s}", (lambda s=s: background_cases(s))) for s in ("closed", "open")] + \
         [("errors", errors), ("large_clipboard", large_clipboard), ("permission", permission)]
K.run(states, groups)
