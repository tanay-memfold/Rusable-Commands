"""verify_xcode.py <group> <seed> <states...>: Xcode's project commands, read back from the files Xcode writes (project.pbxproj and the
template's sources); opening is read from Xcode's window title and document through Accessibility (not independent of Xcode)."""
import glob, os, re, sys, time, urllib.parse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["XCODE_ALLOWED_ROOT"] = os.path.expanduser("~/xcode-test")
import xcode as X, vkit, ax
from vcommon import osa, sh, se
group, seed, states = sys.argv[1], int(sys.argv[2]), sys.argv[3:]
APP = "Xcode"
def running(): return bool(sh("pgrep -x Xcode"))
def front_app():
    try: return osa('tell application "System Events" to return name of first process whose frontmost is true')
    except RuntimeError: return ""
def windows(): return [w for w in ax.children(ax.app(APP)) if ax.sattr(w, "AXRole") == "AXWindow"] if running() else []
def sheets(): return [s for w in windows() for s in ax.children(w) if ax.sattr(s, "AXRole") == "AXSheet"]
def project_docs():
    out = []
    for w in windows():
        if ax.sattr(w, "AXIdentifier") == "Xcode.WorkspaceWindow":
            out.append((ax.sattr(w, "AXTitle") or "", urllib.parse.unquote(urllib.parse.urlparse(ax.sattr(w, "AXDocument") or "").path)))
    return out
K = vkit.Kit("xcode", X, APP, group, seed, X.XcodeError, None, None)
D = f"{K.DATA}/projects"; os.makedirs(D, exist_ok=True)
BASE = {}
def base_project():
    """A project to open, made once per batch by project_new itself (tested in its own cases)."""
    if "p" not in BASE:
        nm = f"Base {K.word()}"; X.project_new(name=nm, folder=D); BASE["p"] = f"{D}/{nm}/{nm}.xcodeproj"; BASE["n"] = nm
    return BASE
def close_others(keep=None):
    """Setup only: close project windows left open by earlier cases, with their close buttons."""
    for w in windows():
        t = (ax.sattr(w, "AXTitle") or "").split(" — ")[0]
        if ax.sattr(w, "AXIdentifier") == "Xcode.WorkspaceWindow" and t and t != keep:
            b = next((e for e in ax.children(w) if ax.sattr(e, "AXSubrole") == "AXCloseButton"), None); b and ax.press(b); time.sleep(0.8)
def ui_state_files(c):
    """Xcode rewrites this per-user window-state file of every project open in Xcode when its windows change. Only for the projects
    whose windows were open before the call is that one file left out of the others-unchanged check (recorded in the README)."""
    user = os.environ.get("USER", "admin"); out = set()
    for title, _ in c.get("open_before", []):
        name = title.split(" — ")[0]
        for proj in glob.glob(f"{glob.escape(D)}/*/{glob.escape(name)}.xcodeproj"):
            out.add(vkit.nfc(f"{proj}/project.xcworkspace/xcuserdata/{user}.xcuserdatad/UserInterfaceState.xcuserstate"))
    return out
def start(state, ctx=None):
    if state == "blocked": return
    if running(): close_others(BASE.get("n") if state == "project_open" else None)
    if state == "closed":
        if running():
            for s in sheets():
                b = ax.find(s, "AXButton", "Cancel", exact=True); b and ax.press(b)
            sh("pkill -x Xcode"); [time.sleep(0.5) for _ in range(30) if running()]
        return
    if not running(): sh("open -b com.apple.dt.Xcode"); [time.sleep(0.5) for _ in range(120) if not (running() and windows())]; time.sleep(3)
    se("set visible to true\nset frontmost to true", APP); time.sleep(0.5)
    if state == "project_open" and not any(BASE.get("n", "\0") in t for t, _ in project_docs()):
        osa(f'tell application "Xcode" to open (POSIX file "{base_project()["p"]}")'); [time.sleep(0.5) for _ in range(60) if not any(BASE["n"] in t for t, _ in project_docs())]
    if state == "other_app": sh("open -a Calculator"); [time.sleep(0.3) for _ in range(20) if front_app() == APP]
    if state == "hidden": se("set visible to false", APP); time.sleep(1)
    time.sleep(0.5)
    if ctx is not None: ctx["open_before"] = project_docs()
def clean(state): return True if state == "blocked" else not sheets()  # the blocked case checks the sheet is kept (sheet_kept)
K.start, K.clean = start, clean
def pbx(c):
    try: return open(f"{c['dir']}/{c['name']}.xcodeproj/project.pbxproj", encoding="utf-8").read()
    except OSError: return ""
def made(c, b, a, r, e):
    s = pbx(c); safe = re.sub(r"[^A-Za-z0-9]", "_", c["name"])
    src = f"{c['dir']}/{c['name']}"
    files = sorted(os.listdir(src)) if os.path.isdir(src) else []
    return {"no_error": e is None, "pbxproj": bool(s), "sdk": f"SDKROOT = {c['sdk']};" in s,
            "bundle_id": f"PRODUCT_BUNDLE_IDENTIFIER = \"{c['org']}." in s or f"PRODUCT_BUNDLE_IDENTIFIER = {c['org']}." in s,
            "app_sources": "ContentView.swift" in files and any(f.endswith("App.swift") for f in files),
            "no_git": not os.path.exists(f"{c['dir']}/.git"),
            "return": bool(r) and r.get("path") == vkit.nfc(f"{c['dir']}/{c['name']}.xcodeproj") and r.get("platform") == c["platform"]}
n = {"i": 0}
def pname(style):
    n["i"] += 1; w = K.word().capitalize()
    return {"plain": f"{w}{n['i']}", "spaced": f"{w} Café {n['i']}", "mac": f"{w}Mac{n['i']}"}[style]
def state_cases(state):
    m = "ui"
    for kind, platform, sdk in (("ios_app", "iOS", "iphoneos"), ("ios_spaced", "iOS", "iphoneos"), ("macos_app", "macOS", "macosx")):
        def setup(kind=kind, platform=platform, sdk=sdk):
            nm = pname("spaced" if kind == "ios_spaced" else "mac" if platform == "macOS" else "plain"); org = f"com.example.{K.word().lower()}"
            return {"name": nm, "dir": f"{D}/{nm}", "org": org, "platform": platform, "sdk": sdk}
        K.case("project_new", m, state, kind, setup, lambda c: X.project_new(name=c["name"], folder=D, platform=c["platform"], organization=c["org"]),
               made, lambda c: {c["dir"]} | ui_state_files(c))
    def open_setup():
        bp = base_project(); return {"p": bp["p"], "n": bp["n"]}
    def shown(c, b, a, r, e):
        docs = project_docs()
        return {"no_error": e is None, "window": any(t.split(" — ")[0] == c["n"] for t, _ in docs),
                "document_inside": any(p.startswith(os.path.dirname(c["p"]) + "/") for _, p in docs), "return": bool(r) and r.get("name") == c["n"]}
    if state != "project_open":
        K.case("project_open", m, state, "xcodeproj", open_setup, lambda c: X.project_open(path=c["p"]), shown, lambda c: {os.path.dirname(c["p"])} | ui_state_files(c))
def close_base():
    """Setup only: close the base project's window with its close button (Xcode's scripting timed out on close)."""
    if not BASE.get("n"): return
    for w in windows():
        if ax.sattr(w, "AXIdentifier") == "Xcode.WorkspaceWindow" and (ax.sattr(w, "AXTitle") or "").split(" — ")[0] == BASE["n"]:
            b = next((e for e in ax.children(w) if ax.sattr(e, "AXSubrole") == "AXCloseButton"), None); b and ax.press(b)
    [time.sleep(0.5) for _ in range(20) if any(t.split(" — ")[0] == BASE["n"] for t, _ in project_docs())]
def state_cases_wrapped(state):
    if state not in ("project_open",): close_base()
    state_cases(state)
def errors():
    m, st = "ui", "open"
    def taken():
        nm = pname("plain"); os.makedirs(f"{D}/{nm}"); open(f"{D}/{nm}/keep", "w").write("keep"); return {"name": nm}
    K.case("project_new", m, st, "exists", taken, lambda c: X.project_new(name=c["name"], folder=D), lambda c, b, a, r, e: {"raised": isinstance(e, X.AlreadyExists), "kept": open(f"{D}/{c['name']}/keep").read() == "keep"})
    K.case("project_new", m, st, "no_folder", lambda: {}, lambda c: X.project_new(name="Nowhere1", folder=f"{K.DATA}/none"), lambda c, b, a, r, e: {"raised": isinstance(e, X.NotFound)})
    K.case("project_new", m, st, "no_template", lambda: {"name": pname("plain")}, lambda c: X.project_new(name=c["name"], folder=D, template="No Such Template"),
           lambda c, b, a, r, e: {"raised": isinstance(e, X.NotFound), "nothing_made": not os.path.exists(f"{D}/{c['name']}")})
    for kind, kw in (("slash_name", {"name": "a/b"}), ("empty_name", {"name": " "}), ("bad_platform", {"name": "Plat1", "platform": "Windows"}), ("bad_org", {"name": "Org1", "organization": "com example"})):
        K.case("project_new", m, st, kind, lambda: {}, lambda c, kw=kw: X.project_new(folder=D, **kw), lambda c, b, a, r, e: {"raised": isinstance(e, ValueError)})
    K.case("project_new", m, st, "guard", lambda: {}, lambda c: X.project_new(name="Out1", folder="/tmp"), lambda c, b, a, r, e: {"raised_Outside": isinstance(e, X.OutsideAllowedRoot), "nothing_outside": not os.path.exists("/tmp/Out1")})
    def typed():
        start("open"); osa('tell application "System Events" to tell process "Xcode" to click menu item "Project…" of menu 1 of menu item "New" of menu "File" of menu bar item "File" of menu bar 1'); time.sleep(3)
        s = next(x for x in sheets()); nx = ax.find(s, "AXButton", "Next", exact=True); ax.press(nx); time.sleep(2)
        f = next(e for e in ax.walk(s) if ax.sattr(e, "AXIdentifier") == "productName"); ax.AS.AXUIElementSetAttributeValue(f, ax.cf("AXValue"), ax.cf("Half Typed")); time.sleep(0.5)
        return {"name": pname("plain")}
    def untype():
        for s in sheets():
            b = ax.find(s, "AXButton", "Cancel", exact=True); b and ax.press(b)
        time.sleep(1)
    K.case("project_new", m, "blocked", "typed_name", typed, lambda c: X.project_new(name=c["name"], folder=D),
           lambda c, b, a, r, e: {"raised": isinstance(e, X.StateBlocked), "nothing_made": not os.path.exists(f"{D}/{c['name']}"), "sheet_kept": bool(sheets())})
    untype()
    K.case("project_open", m, st, "not_found", lambda: {}, lambda c: X.project_open(path=f"{D}/None.xcodeproj"), lambda c, b, a, r, e: {"raised": isinstance(e, X.NotFound)})
    K.case("project_open", m, st, "bad_suffix", lambda: {}, lambda c: X.project_open(path=D), lambda c, b, a, r, e: {"raised": isinstance(e, ValueError)})
    K.case("project_open", "background", st, "not_supported", lambda: {}, lambda c: X.project_open(path=f"{D}/None.xcodeproj", mode="background"), lambda c, b, a, r, e: {"raised": isinstance(e, X.NotSupported)})
    K.case("project_new", "background", st, "not_supported", lambda: {}, lambda c: X.project_new(name="Bg1", folder=D, mode="background"), lambda c, b, a, r, e: {"raised": isinstance(e, X.NotSupported)})
def large_clipboard():
    def setup():
        nm = pname("plain"); return {"name": nm, "dir": f"{D}/{nm}", "org": "com.example.big", "platform": "iOS", "sdk": "iphoneos"}
    K.case("project_new", "ui", "open", "large_clipboard", setup, lambda c: X.project_new(name=c["name"], folder=D, organization=c["org"]), made, lambda c: {c["dir"]}, big=True)
    def open_setup():
        bp = base_project(); close_base(); time.sleep(2); return {"p": bp["p"], "n": bp["n"]}
    K.case("project_open", "ui", "open", "large_clipboard", open_setup, lambda c: X.project_open(path=c["p"]),
           lambda c, b, a, r, e: {"no_error": e is None, "window": any(t.split(" — ")[0] == c["n"] for t, _ in project_docs())}, lambda c: {os.path.dirname(c["p"])} | ui_state_files(c), big=True)
groups = [(s, (lambda s=s: state_cases_wrapped(s))) for s in ("closed", "open", "project_open", "other_app", "hidden")] + [("errors", errors), ("large_clipboard", large_clipboard)]
K.run(states, groups)
