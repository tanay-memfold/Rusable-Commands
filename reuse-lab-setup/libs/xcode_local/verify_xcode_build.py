"""verify_xcode_build.py <group> <seed> <states...>: Xcode's project_build, read back from the files Xcode writes (project.pbxproj and the
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
DERIVED = os.path.expanduser("~/Library/Developer/Xcode/DerivedData")
def apps(name):
    out = []
    for f in glob.glob(f"{glob.escape(DERIVED)}/{glob.escape(name.replace(' ', '_'))}-*/Build/Products/*/*.app"):
        out.append((f, os.path.getmtime(f)))
    return out
def download_offer(): return any(ax.sattr(e, "AXRole") == "AXButton" and ax.sattr(e, "AXTitle") == "Download & Install" for w in windows() for e in ax.walk(w))
n = {"i": 0}
def proj(platform="macOS", broken=False):
    """Setup: a project made by project_new (verified on its own), optionally with a source file that won't compile."""
    n["i"] += 1; nm = f"{K.word().capitalize()}{'Mac' if platform == 'macOS' else 'Phone'}{n['i']}"
    start("open"); X.project_new(name=nm, folder=D, platform=platform)
    if broken:
        open(f"{D}/{nm}/{nm}/ContentView.swift", "a").write("\nlet broken: Int = \"not a number\"\n")
    close_others()
    return {"name": nm, "p": f"{D}/{nm}/{nm}.xcodeproj", "dir": f"{D}/{nm}"}
def userdata(c):
    return {f"{c['p']}/project.xcworkspace/xcuserdata", f"{c['p']}/xcuserdata"} | ui_state_files(c)
def snap(c): c["began"] = time.time(); c["apps0"] = apps(c["name"])
def built(c, b, a, r, e):
    fresh = [f for f, t in apps(c["name"]) if t >= c["began"] - 1]
    exe = [f for f in fresh if os.listdir(f"{f}/Contents/MacOS")] if fresh else []
    return {"no_error": e is None, "fresh_app": len(fresh) == 1, "has_executable": len(exe) == 1, "succeeded": bool(r) and r.get("succeeded") is True,
            "return_products": bool(r) and sorted(r.get("products", [])) == sorted(fresh),
            "log_without_failures": (lambda logs: bool(logs) and not any("nonzero exit code" in log or "Cannot convert" in log for log in logs))(build_logs(c["name"], c["began"]))}
def build_logs(name, since):
    """Xcode's own logs written since `since` for this project (DerivedData/<project>-*/Logs/Build/*.xcactivitylog, gzip), as text."""
    import gzip
    return [gzip.open(f).read().decode("utf-8", "replace") for f in glob.glob(f"{glob.escape(DERIVED)}/{glob.escape(name.replace(' ', '_'))}-*/Logs/Build/*.xcactivitylog")
            if os.path.getmtime(f) >= since - 1]
def failed(c, b, a, r, e):
    logs = build_logs(c["name"], c["began"])
    return {"no_error": e is None, "not_succeeded": bool(r) and r.get("succeeded") is False, "no_products_returned": bool(r) and r.get("products") == [],
            "log_has_the_error": any("Cannot convert value of type 'String' to specified type 'Int'" in log for log in logs)}
def state_cases(state):
    m = "ui"
    K.case("project_build", m, state, "macos_app", lambda: proj(), lambda c: X.project_build(path=c["p"]), built, userdata, before=snap)
    if state in ("open", "closed"):
        K.case("project_build", m, state, "compile_error", lambda: proj(broken=True), lambda c: X.project_build(path=c["p"]), failed, userdata, before=snap)
def errors():
    m, st = "ui", "open"
    K.case("project_build", m, st, "ios_needs_download", lambda: proj("iOS"), lambda c: X.project_build(path=c["p"]),
           lambda c, b, a, r, e: {"raised": isinstance(e, X.NotSupported), "offer_declined": not download_offer()}, userdata, before=snap)
    K.case("project_build", m, st, "not_found", lambda: {}, lambda c: X.project_build(path=f"{D}/None.xcodeproj"), lambda c, b, a, r, e: {"raised": isinstance(e, X.NotFound)})
    K.case("project_build", m, st, "bad_suffix", lambda: {}, lambda c: X.project_build(path=D), lambda c, b, a, r, e: {"raised": isinstance(e, ValueError)})
    K.case("project_build", m, st, "guard", lambda: {}, lambda c: X.project_build(path="/tmp/x.xcodeproj"), lambda c, b, a, r, e: {"raised": isinstance(e, X.OutsideAllowedRoot)})
    K.case("project_build", "background", st, "not_supported", lambda: {}, lambda c: X.project_build(path=f"{D}/None.xcodeproj", mode="background"), lambda c, b, a, r, e: {"raised": isinstance(e, X.NotSupported)})
def large_clipboard():
    K.case("project_build", "ui", "open", "large_clipboard", lambda: proj(), lambda c: X.project_build(path=c["p"]), built, userdata, before=snap, big=True)
# Clean (overnight): each case makes and builds a project with project_new and project_build (verified on their own), then cleans
# it. Read back from DerivedData: no built app and no file left in its Build folder; the project's own files unchanged.
def build_files(name):
    out = []
    for root in glob.glob(f"{glob.escape(DERIVED)}/{glob.escape(name.replace(' ', '_'))}-*/Build"):
        for base, dirs, files in os.walk(root):
            out += [os.path.join(base, f) for f in files]
    return out
def built_proj():
    c = proj(); X.project_build(path=c["p"]); c["had"] = len(build_files(c["name"])); return c
def cleaned(c, b, a, r, e):
    # Xcode's Clean keeps only its own build database (Build/Intermediates.noindex/XCBuildData); every other file must be gone.
    left = [f for f in build_files(c["name"]) if "/Build/Intermediates.noindex/XCBuildData/" not in f]
    return {"no_error": e is None, "had_products": c["had"] > 0, "no_app_left": apps(c["name"]) == [], "only_build_database_left": left == [],
            "return": bool(r) and r.get("name") == c["name"] and r.get("cleaned") is True}
def clean_cases(state):
    K.case("project_clean", "ui", state, "built", built_proj, lambda c: X.project_clean(path=c["p"]), cleaned, userdata)
def clean_errors():
    m, st = "ui", "open"
    K.case("project_clean", m, st, "never_built", lambda: (lambda c: (c.update(had=1), c)[1])(proj()), lambda c: X.project_clean(path=c["p"]),
           lambda c, b, a, r, e: {"no_error": e is None, "no_app_left": apps(c["name"]) == []}, userdata)
    K.case("project_clean", m, st, "not_found", lambda: {}, lambda c: X.project_clean(path=f"{D}/None.xcodeproj"), lambda c, b, a, r, e: {"raised": isinstance(e, X.NotFound)})
    K.case("project_clean", m, st, "bad_suffix", lambda: {}, lambda c: X.project_clean(path=D), lambda c, b, a, r, e: {"raised": isinstance(e, ValueError)})
    K.case("project_clean", m, st, "guard", lambda: {}, lambda c: X.project_clean(path="/tmp/x.xcodeproj"), lambda c, b, a, r, e: {"raised": isinstance(e, X.OutsideAllowedRoot)})
    K.case("project_clean", "background", st, "not_supported", lambda: {}, lambda c: X.project_clean(path=f"{D}/None.xcodeproj", mode="background"), lambda c, b, a, r, e: {"raised": isinstance(e, X.NotSupported)})
    K.case("project_clean", m, "open", "large_clipboard", built_proj, lambda c: X.project_clean(path=c["p"]), cleaned, userdata, big=True)
groups = [(s, (lambda s=s: state_cases(s))) for s in ("closed", "open", "project_open", "other_app", "hidden")] + [("errors", errors), ("large_clipboard", large_clipboard)]
groups += [("clean_" + s, (lambda s=s: clean_cases(s))) for s in ("closed", "open", "project_open", "other_app", "hidden")] + [("clean_errors", clean_errors)]
K.run(states, groups)
