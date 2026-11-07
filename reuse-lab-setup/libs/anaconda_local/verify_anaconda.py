"""verify_anaconda.py <group> <seed> <states...>: environment_create, read back from conda's own files (conda-meta, bin/python,
~/.conda/environments.txt), not through Navigator or the library."""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import anaconda as A, vkit, ax
from vcommon import osa, sh, se
group, seed, states = sys.argv[1], int(sys.argv[2]), sys.argv[3:]
ENVS = "/opt/homebrew/anaconda3/envs"; LIST = os.path.expanduser("~/.conda/environments.txt")
CMD = "/opt/homebrew/anaconda3/bin/python /opt/homebrew/anaconda3/bin/anaconda-navigator"
def pid():
    out = sh(f"pgrep -f -x '{CMD}'").split(); return int(out[0]) if out else None
def app(): return ax.AS.AXUIElementCreateApplication(pid())
def windows(): return [w for w in ax.children(app()) if ax.sattr(w, "AXRole") == "AXWindow"] if pid() else []
def dialogs(): return [w for w in windows() if ax.sattr(w, "AXTitle") != "Anaconda Navigator"]
def by(root, role, title=None, desc=None):
    return next((e for e in ax.walk(root) if ax.sattr(e, "AXRole") == role and (title is None or ax.sattr(e, "AXTitle") == title) and (desc is None or ax.sattr(e, "AXDescription") == desc)), None)
def pse(body): return osa(f'tell application "System Events" to tell (first process whose unix id is {pid()})\n{body}\nend tell')
def front_is_nav():
    try: return pse("return frontmost") == "true"
    except Exception: return False
def key(code): pse(f"key code {code}"); time.sleep(0.8)
def main(): return next((w for w in windows() if ax.sattr(w, "AXTitle") == "Anaconda Navigator" and by(w, "AXCheckBox", "Environments")), None)
def settle():
    """Test setup only: decline Navigator's offers the way a person would (No, remind me later; Escape on the sign-in offer)."""
    for _ in range(3):
        for w in dialogs():
            b = by(w, "AXButton", "No, remind me later") or by(w, "AXButton", "Cancel")
            if b: ax.press(b)
            elif by(w, "AXButton", "Sign In"): pse("set frontmost to true"); key(53)
        time.sleep(1)
def page(name):
    m = main(); cb = by(m, "AXCheckBox", name); ax.focus(cb); time.sleep(0.4); key(49); time.sleep(2)
def start(state):
    if state == "blocked":
        return  # the case's setup left a dialog with a typed name on purpose
    if state == "closed":
        if pid():
            sh(f"pkill -f -x '{CMD}'"); sh("pkill -f 'Anaconda-Navigator.app/Contents/MacOS/run.py'")
            [time.sleep(0.5) for _ in range(40) if pid()]
        return
    if not pid():
        sh("open -b com.anaconda.io"); [time.sleep(1) for _ in range(150) if not (pid() and main())]; time.sleep(15)
    settle(); pse("set visible to true\nset frontmost to true"); time.sleep(0.5)
    page("Environments" if state == "env_page" else "Home")
    if state == "other_app": sh("open -a Calculator"); [time.sleep(0.3) for _ in range(20) if front_is_nav()]
    if state == "hidden": pse("set visible to false"); time.sleep(1)
    time.sleep(0.5)
def clean(state): return not dialogs()
K = vkit.Kit("anaconda", A, "python", group, seed, A.AnacondaError, start, clean)
def envs():
    return set(os.listdir(ENVS)) if os.path.isdir(ENVS) else set()
def listed():
    try: return {l.strip().rstrip("/") for l in open(LIST) if l.strip()}
    except OSError: return set()
n = {"i": 0}
def newname(style):
    n["i"] += 1; w = K.word().lower()[:10] or "env"
    return {"plain": f"{w}{n['i']}", "dashed": f"{w}-{n['i']}_v2-x", "upper": f"Proj_{w.capitalize()}{n['i']}"}[style]
def created(c, b, a, r, e):
    p = f"{ENVS}/{c['name']}"
    return {"no_error": e is None, "conda_meta": os.path.isfile(f"{p}/conda-meta/history"), "python": os.path.exists(f"{p}/bin/python"),
            "in_environments_txt": p in listed(), "only_this_env_added": envs() == c["envs0"] | {c["name"]},
            "return": bool(r) and r.get("name") == c["name"] and r.get("path") == p}
def unchanged(c): return envs() == c["envs0"] and listed() == c["list0"]
def state_cases(state):
    for style in ("plain", "dashed") + (("upper",) if state == "open" else ()):
        def setup(style=style): return {"name": newname(style), "envs0": envs(), "list0": listed()}
        K.case("environment_create", "ui", state, style, setup, lambda c: A.environment_create(name=c["name"]), created, clip=True)
def errors():
    st = "open"
    def existing():
        nm = sorted(envs())[0] if envs() else "base"; return {"name": nm, "envs0": envs(), "list0": listed()}
    K.case("environment_create", "ui", st, "exists", existing, lambda c: A.environment_create(name=c["name"]), lambda c, b, a, r, e: {"raised": isinstance(e, A.AlreadyExists), "unchanged": unchanged(c)})
    K.case("environment_create", "ui", st, "base", lambda: {"envs0": envs(), "list0": listed()}, lambda c: A.environment_create(name="base"), lambda c, b, a, r, e: {"raised": isinstance(e, A.AlreadyExists), "unchanged": unchanged(c)})
    for kind, bad in (("space", "my env"), ("slash", "a/b"), ("dot_first", ".hidden"), ("empty", ""), ("dot_inside", "env.v2"),
                      ("digit_first", "2env"), ("underscore_first", "_env"), ("too_long", "a" * 32)):
        K.case("environment_create", "ui", st, f"bad_{kind}", lambda: {"envs0": envs(), "list0": listed()}, lambda c, bad=bad: A.environment_create(name=bad), lambda c, b, a, r, e: {"raised": isinstance(e, ValueError), "unchanged": unchanged(c)})
    def typed():
        page("Environments")
        for _ in range(3):  # test setup: Navigator's button sometimes ignores the first press
            ax.press(by(main(), "AXButton", "Create")); time.sleep(3)
            if any(by(w, "AXTextField", desc="New environment name") for w in dialogs()): break
        f = next(by(w, "AXTextField", desc="New environment name") for w in dialogs())
        ax.AS.AXUIElementSetAttributeValue(f, ax.cf("AXValue"), ax.cf("half typed")); time.sleep(0.5)
        return {"name": newname("plain"), "envs0": envs(), "list0": listed()}
    def untyped():
        for w in dialogs():
            c = by(w, "AXButton", "Cancel"); c and ax.press(c)
        time.sleep(1)
    K.case("environment_create", "ui", "blocked", "typed_name", typed, lambda c: A.environment_create(name=c["name"]),
           lambda c, b, a, r, e: {"raised": isinstance(e, A.StateBlocked), "unchanged": unchanged(c), "dialog_kept": any("half typed" == (ax.sattr(by(w, "AXTextField", desc="New environment name"), "AXValue") if by(w, "AXTextField", desc="New environment name") else "") for w in dialogs())},
           after=None)
    untyped()
    K.case("environment_create", "background", st, "not_supported", lambda: {}, lambda c: A.environment_create(name="bgenv", mode="background"), lambda c, b, a, r, e: {"raised": isinstance(e, A.NotSupported)})
def large_clipboard():
    def setup(): return {"name": newname("plain"), "envs0": envs(), "list0": listed()}
    K.case("environment_create", "ui", "open", "large_clipboard", setup, lambda c: A.environment_create(name=c["name"]), created, big=True)
groups = [(s, (lambda s=s: state_cases(s))) for s in ("closed", "open", "env_page", "other_app", "hidden")] + [("errors", errors), ("large_clipboard", large_clipboard)]
K.run(states, groups)
