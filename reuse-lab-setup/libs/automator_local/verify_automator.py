"""verify_automator.py <group> <seed> <states...>: Automator's workflow commands, read back from the saved .workflow files."""
import glob, os, plistlib, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["AUTOMATOR_ALLOWED_ROOT"] = os.path.expanduser("~/automator-test")
import automator as A, vkit, ax
from vcommon import osa, sh, se
group, seed, states = sys.argv[1], int(sys.argv[2]), sys.argv[3:]
APP = "Automator"
BUNDLES = {}
for info in glob.glob("/System/Library/Automator/*.action/Contents/Info.plist"):
    try:
        d = plistlib.load(open(info, "rb")); BUNDLES.setdefault(d.get("AMName") or d.get("CFBundleName"), set()).add(d.get("CFBundleIdentifier"))  # some names have two bundles
    except Exception: pass
def saved_ids(path):
    try: return [a["action"]["BundleIdentifier"] for a in plistlib.load(open(f"{path}/Contents/document.wflow", "rb"))["actions"]]
    except Exception: return None
def matches(ids, names): return ids is not None and len(ids) == len(names) and all(i in BUNDLES.get(n, set()) for i, n in zip(ids, names))
def running(): return bool(sh("pgrep -x Automator"))
def front_app():
    try: return osa('tell application "System Events" to return name of first process whose frontmost is true')
    except RuntimeError: return ""
def windows(): return [w for w in ax.children(ax.app(APP)) if ax.sattr(w, "AXRole") == "AXWindow"] if running() else []
def start(state):
    if state == "closed":
        if running():
            for w in windows():
                for s in [c for c in ax.children(w) if ax.sattr(c, "AXRole") == "AXSheet"]:
                    b = ax.find(s, "AXButton", "Cancel", exact=True) or ax.find(s, "AXButton", "Delete", exact=True); b and ax.press(b)
            sh("pkill -x Automator"); [time.sleep(0.5) for _ in range(30) if running()]
        return
    if not running(): sh("open -b com.apple.Automator"); [time.sleep(0.5) for _ in range(30) if not running()]; time.sleep(2)
    se("set visible to true\nset frontmost to true", APP); time.sleep(0.5)
    if state == "other_app": sh("open -a Calculator"); [time.sleep(0.3) for _ in range(20) if front_app() == APP]
    time.sleep(0.5)
def clean(state):
    return not any(ax.sattr(c, "AXRole") == "AXSheet" for w in windows() for c in ax.children(w))
K = vkit.Kit("automator", A, APP, group, seed, A.AutomatorError, start, clean)
OUT = f"{K.DATA}/wf"; os.makedirs(OUT, exist_ok=True)
n = {"i": 0}
def build(names, copy=()):
    """A new workflow with these actions, through the library commands (themselves tested in their own cases)."""
    A.workflow_new()
    for nm in names: A.workflow_add_action(name=nm, copy_first=nm in copy)
def wname():
    n["i"] += 1; return f"{OUT}/{(K.V.special() if n['i'] % 2 else K.V.word()).replace('/', '-')} {n['i']}.workflow"
FLOWS = [("png_to_jpeg", ["Get Specified Finder Items", "Copy Finder Items", "Change Type of Images"], ()),
         ("resize", ["Get Specified Finder Items", "Scale Images"], ()),
         ("pdf_from_text", ["Get Specified Finder Items", "New PDF from Images"], ()),
         ("text_list", ["Get Specified Finder Items", "Get Folder Contents", "New Text File"], ()),
         ("move_old", ["Get Specified Finder Items", "Filter Finder Items", "Move Finder Items"], ())]
def state_cases(state):
    m = "ui"
    K.case("workflow_new", m, state, "empty", lambda: {}, lambda c: A.workflow_new(), lambda c, b, a, r, e: {"no_error": e is None, "empty": bool(r) and r["actions"] == []})
    K.case("workflow_add_action", m, state, "copy_offered_yes", lambda: (A.workflow_new(), {})[1] if state != "closed" else {}, lambda c: (A.workflow_new() if state == "closed" else None, A.workflow_add_action(name="Change Type of Images", copy_first=True))[1],
           lambda c, b, a, r, e: {"no_error": e is None, "both_added": bool(r) and r["actions"] == ["Copy Finder Items", "Change Type of Images"]})
    K.case("workflow_add_action", m, state, "copy_offered_no", lambda: (A.workflow_new(), {})[1] if state != "closed" else {}, lambda c: (A.workflow_new() if state == "closed" else None, A.workflow_add_action(name="Scale Images", copy_first=False))[1],
           lambda c, b, a, r, e: {"no_error": e is None, "only_it": bool(r) and r["actions"] == ["Scale Images"]})
    names3 = ["Get Specified Finder Items", "Copy Finder Items", "Change Type of Images", "Scale Images"]
    def built():
        if state != "closed": build(["Get Specified Finder Items", "Change Type of Images", "Scale Images"], ("Change Type of Images",))
        return {}
    def listed(c):
        if state == "closed": build(["Get Specified Finder Items", "Change Type of Images", "Scale Images"], ("Change Type of Images",))
        return A.workflow_actions()
    K.case("workflow_actions", m, state, "four", built, listed, lambda c, b, a, r, e: {"no_error": e is None, "in_order": bool(r) and r["actions"] == names3})
    for kind, names, copy in FLOWS:
        def setup(names=names, copy=copy):
            if state != "closed": build(names, copy)
            return {"p": wname(), "names": names}
        def call(c, names=names, copy=copy):
            if state == "closed": build(names, copy)  # the state closes Automator after setup, so the workflow is built in the call
            return A.workflow_save(path=c["p"])
        K.case("workflow_save", m, state, kind, setup, call,
               lambda c, b, a, r, e: {"no_error": e is None, "file_actions": matches(saved_ids(c["p"]), c["names"]),
                                      "return": bool(r) and r["actions"] == c["names"]}, lambda c: {x for x in K.tree() if x.startswith(vkit.nfc(c["p"]))})
def errors():
    m, st = "ui", "open"
    K.case("workflow_add_action", m, st, "not_found", lambda: (A.workflow_new(), {})[1], lambda c: A.workflow_add_action(name="No Such Action 58291"), lambda c, b, a, r, e: {"raised": isinstance(e, A.NotFound)})
    def taken():
        build(["Get Specified Finder Items"]); p = wname(); os.makedirs(p); open(f"{p}/keep", "w").write("keep"); return {"p": p}
    K.case("workflow_save", m, st, "exists", taken, lambda c: A.workflow_save(path=c["p"]), lambda c, b, a, r, e: {"raised": isinstance(e, A.AlreadyExists), "kept": open(f"{c['p']}/keep").read() == "keep"})
    K.case("workflow_save", m, st, "bad_suffix", lambda: (build(["Get Specified Finder Items"]), {})[1], lambda c: A.workflow_save(path=f"{OUT}/x.txt"), lambda c, b, a, r, e: {"raised": isinstance(e, ValueError)})
    K.case("workflow_save", m, st, "guard", lambda: {}, lambda c: A.workflow_save(path="/tmp/x.workflow"), lambda c, b, a, r, e: {"raised_Outside": isinstance(e, A.OutsideAllowedRoot)})
    K.case("workflow_add_action", m, st, "empty_name", lambda: {}, lambda c: A.workflow_add_action(name=" "), lambda c, b, a, r, e: {"raised": isinstance(e, ValueError)})
    for fn, call in (("workflow_new", lambda c: A.workflow_new(mode="background")), ("workflow_save", lambda c: A.workflow_save(path=f"{OUT}/bg.workflow", mode="background"))):
        K.case(fn, "background", st, "not_supported", lambda: {}, call, lambda c, b, a, r, e: {"raised": isinstance(e, A.NotSupported)})
def large_clipboard():
    def setup():
        build(["Get Specified Finder Items", "Scale Images"]); return {"p": wname(), "names": ["Get Specified Finder Items", "Scale Images"]}
    K.case("workflow_save", "ui", "open", "large_clipboard", setup, lambda c: A.workflow_save(path=c["p"]), lambda c, b, a, r, e: {"no_error": e is None, "file_actions": matches(saved_ids(c["p"]), c["names"])}, lambda c: {x for x in K.tree() if x.startswith(vkit.nfc(c["p"]))}, big=True)
# Opening a saved workflow (overnight): each case saves a workflow with the library (verified on its own), then opens it; the
# window in front must hold that file, and its actions must match the file's own.
import urllib.parse
def front_doc():
    main = ax.attr(ax.app(APP), "AXMainWindow") if running() else None
    url = ax.sattr(main, "AXDocument") if main else ""
    return vkit.nfc(urllib.parse.unquote(urllib.parse.urlparse(url).path).rstrip("/")) if url else ""
OPEN_FLOWS = [["Get Specified Finder Items", "Get Folder Contents"], ["Get Specified Finder Items", "Scale Images"], ["Get Specified Finder Items", "Copy Finder Items", "Change Type of Images"]]
def open_setup(names):
    start("open"); build(names, ("Change Type of Images",) if "Change Type of Images" in names else ()); p = wname(); A.workflow_save(path=p)
    A.workflow_new()  # another workflow in front
    return {"p": p, "names": names}
def opened(c, b, a, r, e):
    return {"no_error": e is None, "front_is_it": front_doc() == vkit.nfc(os.path.realpath(c["p"])), "file_actions_match": matches(saved_ids(c["p"]), r["actions"] if r else []),
            "return": bool(r) and r["path"] == c["p"] and r["actions"] == c["names"]}
def open_cases(state):
    for k, names in enumerate(OPEN_FLOWS):
        K.case("workflow_open", "ui", state, f"flow_{k + 1}", lambda names=names: open_setup(names), lambda c: A.workflow_open(path=c["p"]), opened, lambda c: set())
def open_group():
    for st in ("closed", "open", "other_app"): open_cases(st)
    m, st = "ui", "open"
    K.case("workflow_open", m, st, "already_open", lambda: (lambda c: (A.workflow_open(path=c["p"]), A.workflow_new(), c)[2])(open_setup(OPEN_FLOWS[0])), lambda c: A.workflow_open(path=c["p"]), opened, lambda c: set())
    K.case("workflow_open", m, st, "missing", lambda: {}, lambda c: A.workflow_open(path=f"{OUT}/none.workflow"), lambda c, b, a, r, e: {"raised": isinstance(e, A.NotFound)})
    def plain_folder():
        d = f"{OUT}/folder {K.word()}.workflow"; os.makedirs(d); return {"p": d}
    K.case("workflow_open", m, st, "not_a_workflow", plain_folder, lambda c: A.workflow_open(path=c["p"]), lambda c, b, a, r, e: {"raised": isinstance(e, ValueError)})
    K.case("workflow_open", m, st, "guard", lambda: {}, lambda c: A.workflow_open(path="/tmp/x.workflow"), lambda c, b, a, r, e: {"raised_Outside": isinstance(e, A.OutsideAllowedRoot)})
    K.case("workflow_open", "background", st, "not_supported", lambda: {}, lambda c: A.workflow_open(path=f"{OUT}/none.workflow", mode="background"), lambda c, b, a, r, e: {"raised": isinstance(e, A.NotSupported)})
    K.case("workflow_open", m, st, "large_clipboard", lambda: open_setup(OPEN_FLOWS[1]), lambda c: A.workflow_open(path=c["p"]), opened, lambda c: set(), big=True)
groups = [(s, (lambda s=s: state_cases(s))) for s in ("closed", "open", "other_app")] + [("errors", errors), ("large_clipboard", large_clipboard), ("open", open_group)]
K.run(states, groups)
