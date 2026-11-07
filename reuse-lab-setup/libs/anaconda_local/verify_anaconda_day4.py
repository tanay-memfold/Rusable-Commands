"""verify_anaconda_day4.py <group> <seed> <states...>: environment_remove and notebook_launch (day 4), read back from conda's
files and Jupyter's runtime files (conda-meta, bin/python,
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
import json, subprocess
# Launching Notebook may make Anaconda's notebook folder ~/anaconda_projects: the kit's whole-home check leaves it out, and each case
# checks that nothing else outside the test folder appeared.
_ov = K.outside_view
def _outside_view():
    v = _ov(); v.pop("anaconda_projects", None); return v
K.outside_view = _outside_view; K.outside0 = _outside_view()
CONDA = "/opt/homebrew/anaconda3/bin/conda"; RUNTIME = os.path.expanduser("~/Library/Jupyter/runtime")
n = {"i": 0}
def made_env():
    """Setup: an environment made with conda itself (python only), then Navigator restarted so it lists it."""
    n["i"] += 1; name = f"{K.word().lower()[:8]}-{n['i']}_rm"
    done = subprocess.run([CONDA, "create", "-y", "-q", "-n", name, "python"], capture_output=True, text=True)
    if done.returncode: raise RuntimeError(done.stderr[-200:])
    sh(f"pkill -f -x '{CMD}'"); sh("pkill -f 'Anaconda-Navigator.app/Contents/MacOS/run.py'"); [time.sleep(0.5) for _ in range(30) if pid()]
    return {"name": name, "envs0": envs()}
def removed(c, b, a, r, e):
    return {"no_error": e is None, "gone": not os.path.exists(f"{ENVS}/{c['name']}/conda-meta"), "others_kept": envs() - {c["name"]} == c["envs0"] - {c["name"]},
            "return": bool(r) and r.get("name") == c["name"] and r.get("removed") is True}
def servers():
    try: return {f for f in os.listdir(RUNTIME) if f.startswith(("jpserver-", "nbserver-")) and f.endswith(".json")}
    except OSError: return set()
def no_servers():
    sh("pkill -f jupyter-notebook; pkill -f jupyter-lab; pkill -x Safari; pkill -x Terminal"); time.sleep(2)
    for f in servers():
        try: os.unlink(os.path.join(RUNTIME, f))
        except OSError: pass
    return {"s0": servers()}
def launched(c, b, a, r, e):
    new = servers() - c["s0"]; info = json.load(open(os.path.join(RUNTIME, sorted(new)[0]))) if new else {}
    alive = bool(info) and "jupyter-notebook" in sh(f"ps -o command= -p {info.get('pid', 0)}")
    return {"no_error": e is None, "server_file": len(new) == 1, "server_running": alive, "no_terminal": not sh("pgrep -x Terminal"), "return": bool(r) and r.get("url") == info.get("url") and r.get("url", "").startswith("http://localhost:")}
def state_cases(state):
    m = "ui"
    K.case("environment_remove", m, state, "made_by_conda", made_env, lambda c: A.environment_remove(name=c["name"]), removed)
    K.case("notebook_launch", m, state, "base", no_servers, lambda c: A.notebook_launch(), launched)
def errors():
    m, st = "ui", "open"
    K.case("environment_remove", m, st, "base", lambda: {"envs0": envs()}, lambda c: A.environment_remove(name="base"), lambda c, b, a, r, e: {"raised": isinstance(e, ValueError), "unchanged": envs() == c["envs0"]})
    K.case("environment_remove", m, st, "missing", lambda: {"envs0": envs()}, lambda c: A.environment_remove(name="nosuchenv42"), lambda c, b, a, r, e: {"raised": isinstance(e, A.NotFound), "unchanged": envs() == c["envs0"]})
    K.case("notebook_launch", m, st, "missing_env", no_servers, lambda c: A.notebook_launch(env="nosuchenv42"), lambda c, b, a, r, e: {"raised": isinstance(e, A.NotFound), "no_server": servers() == c["s0"]})
    def bare():
        c = made_env(); c.update(no_servers()); return c
    K.case("notebook_launch", m, st, "no_jupyter_in_env", bare, lambda c: A.notebook_launch(env=c["name"]),
           lambda c, b, a, r, e: {"raised": isinstance(e, A.NotSupported), "no_server": servers() == c["s0"], "no_terminal": not sh("pgrep -x Terminal")})
    for fn, call in (("environment_remove", lambda c: A.environment_remove(name="x", mode="background")), ("notebook_launch", lambda c: A.notebook_launch(mode="background"))):
        K.case(fn, "background", st, "not_supported", lambda: {}, call, lambda c, b, a, r, e: {"raised": isinstance(e, A.NotSupported)})
def large_clipboard():
    K.case("environment_remove", "ui", "open", "large_clipboard", made_env, lambda c: A.environment_remove(name=c["name"]), removed, big=True)
groups = [(s, (lambda s=s: state_cases(s))) for s in ("closed", "open", "env_page", "other_app", "hidden")] + [("errors", errors), ("large_clipboard", large_clipboard)]
K.run(states, groups)
