"""verify_vscode_day4.py <group> <seed> <states...>: VS Code's extension_install and folder_new (day 4), read back from disk
(~/.vscode/extensions and its extensions.json; the new folders), not through VS Code."""
import json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["VSCODE_ALLOWED_ROOT"] = os.path.expanduser("~/vscode-test")
import vscode as V, vkit
from vcommon import osa, sh, se
group, seed, states = sys.argv[1], int(sys.argv[2]), sys.argv[3:]
APP = "Code"
def running(): return V._running()
def front_app():
    try: return osa('tell application "System Events" to return name of first process whose frontmost is true')
    except RuntimeError: return ""
def start(state):
    if state == "closed":
        if running():
            try: osa('tell application "Visual Studio Code" to quit')
            except RuntimeError: pass
            [time.sleep(0.5) for _ in range(40) if running()]
        return
    if not running(): sh("open -b com.microsoft.VSCode"); [time.sleep(0.5) for _ in range(40) if not running()]; time.sleep(4)
    se("set visible to true\nset frontmost to true", APP); time.sleep(0.5)
    if state == "other_app": sh("open -a Calculator"); [time.sleep(0.3) for _ in range(20) if front_app() == APP]
    if state == "hidden": se("set visible to false", APP); time.sleep(1)
    time.sleep(0.5)
def installed():
    try: return {e["identifier"]["id"].lower() for e in json.load(open(os.path.expanduser("~/.vscode/extensions/extensions.json")))}
    except (OSError, ValueError, KeyError): return set()
def ext_folder(ext_id): return any(n.lower().startswith(ext_id.lower() + "-") for n in os.listdir(os.path.expanduser("~/.vscode/extensions"))) if os.path.isdir(os.path.expanduser("~/.vscode/extensions")) else False
K = vkit.Kit("vscode", V, APP, group, seed, V.VscodeError, start)
n = {"i": 0}
def project():
    n["i"] += 1; d = f"{K.DATA}/{(K.V.special() if n['i'] % 2 else K.V.word()).replace('/', '-')} {n['i']}"
    os.makedirs(f"{d}/src"); open(f"{d}/src/main.js", "w").write(f"// {K.V.word()}\nlet n = {n['i']};\n"); return {"d": d}
def title_has(name): return lambda: vkit.nfc(name) in vkit.nfc(V._main_title()) if running() else False
POOL = ["EditorConfig.EditorConfig", "streetsidesoftware.code-spell-checker", "dbaeumer.vscode-eslint", "christian-kohler.path-intellisense",
        "mikestead.dotenv", "yzhang.markdown-all-in-one", "redhat.vscode-yaml", "naumovs.color-highlight", "wayou.vscode-todo-highlight", "oderwat.indent-rainbow"]
pool = {"i": 0}
def next_ext():
    while pool["i"] < len(POOL):
        e = POOL[pool["i"]]; pool["i"] += 1
        if e.lower() not in installed(): return e
    raise RuntimeError("the test's extension pool ran out")
def ext_setup():
    return {"id": next_ext(), "before": installed()}
def ext_done(c, b, a, r, e):
    now = installed()
    return {"no_error": e is None, "listed": c["id"].lower() in now, "on_disk": ext_folder(c["id"]), "only_it": now - c["before"] == {c["id"].lower()},
            "return": bool(r) and r.get("id") == c["id"] and "also_installed" not in r}
def opened_project():
    c = project(); V.folder_open(path=c["d"]); time.sleep(1); return c
def folder_done(c, b, a, r, e):
    return {"no_error": e is None, "made": os.path.isdir(c["p"]), "empty": os.path.isdir(c["p"]) and os.listdir(c["p"]) == [], "return": bool(r) and r.get("path") == vkit.nfc(c["p"])}
def state_cases(state):
    m = "ui"
    K.case("extension_install", m, state, "from_marketplace", ext_setup, lambda c: V.extension_install(ext_id=c["id"]), ext_done)
    if state != "closed":
        for kind, rel in (("src", "src"), ("nested", f"lib/{K.word()}"), ("special", K.V.special().replace("/", "-"))):
            def setup(rel=rel):
                c = opened_project(); c["p"] = f"{c['d']}/{rel}"
                if os.path.exists(c["p"]): c["p"] += " 2"
                return c
            K.case("folder_new", m, state, kind, setup, lambda c: V.folder_new(path=c["p"]), folder_done, lambda c: {vkit.nfc(c["p"]), vkit.nfc(os.path.dirname(c["p"]))})
def errors():
    m, st = "ui", "open"
    def already():
        c = ext_setup(); V.extension_install(ext_id=c["id"]); c["before"] = installed(); return c
    K.case("extension_install", m, st, "already", already, lambda c: V.extension_install(ext_id=c["id"]), lambda c, b, a, r, e: {"raised": isinstance(e, V.AlreadyExists), "unchanged": installed() == c["before"]})
    K.case("extension_install", m, st, "bad_id", lambda: {"before": installed()}, lambda c: V.extension_install(ext_id="not an id"), lambda c, b, a, r, e: {"raised": isinstance(e, ValueError), "unchanged": installed() == c["before"]})
    K.case("extension_install", m, st, "no_such_extension", lambda: {"before": installed()}, lambda c: V.extension_install(ext_id="rusabletest.no-such-extension-4242"),
           lambda c, b, a, r, e: {"raised": isinstance(e, V.UIError), "unchanged": installed() == c["before"]})
    def taken():
        c = opened_project(); c["p"] = f"{c['d']}/src"; return c
    K.case("folder_new", m, st, "exists", taken, lambda c: V.folder_new(path=c["p"]), lambda c, b, a, r, e: {"raised": isinstance(e, V.AlreadyExists)})
    def outside():
        c = opened_project(); other = project(); c["p"] = f"{other['d']}/elsewhere"; return c
    K.case("folder_new", m, st, "outside_open_folder", outside, lambda c: V.folder_new(path=c["p"]), lambda c, b, a, r, e: {"raised": isinstance(e, ValueError), "not_made": not os.path.exists(c["p"])})
    K.case("folder_new", m, st, "guard", lambda: {}, lambda c: V.folder_new(path="/tmp/rusable-x"), lambda c, b, a, r, e: {"raised_Outside": isinstance(e, V.OutsideAllowedRoot), "not_made": not os.path.exists("/tmp/rusable-x")})
    for fn, call in (("extension_install", lambda c: V.extension_install(ext_id="a.b", mode="background")), ("folder_new", lambda c: V.folder_new(path=f"{K.DATA}/bg", mode="background"))):
        K.case(fn, "background", st, "not_supported", lambda: {}, call, lambda c, b, a, r, e: {"raised": isinstance(e, V.NotSupported)})
def large_clipboard():
    K.case("extension_install", "ui", "open", "large_clipboard", ext_setup, lambda c: V.extension_install(ext_id=c["id"]), ext_done, big=True)
    def setup():
        c = opened_project(); c["p"] = f"{c['d']}/big {K.word()}"; return c
    K.case("folder_new", "ui", "open", "large_clipboard", setup, lambda c: V.folder_new(path=c["p"]), folder_done, lambda c: {vkit.nfc(c["p"])}, big=True)
# Uninstall (overnight): each case installs a pool extension with extension_install (tested on its own), then uninstalls it.
# Read back from VS Code's extensions.json and its .obsolete list (VS Code deletes the folder when extensions next restart).
def obsolete():
    try: return {k.lower().rsplit("-", 1)[0] for k, v in json.load(open(os.path.expanduser("~/.vscode/extensions/.obsolete"))).items() if v}
    except (OSError, ValueError): return set()
def un_setup():
    e = next_ext(); V.extension_install(ext_id=e); time.sleep(2); return {"id": e, "before": installed()}
def un_done(c, b, a, r, e):
    now = installed()
    return {"no_error": e is None, "not_listed": c["id"].lower() not in now, "marked_obsolete_or_gone": c["id"].lower() in obsolete() or not ext_folder(c["id"]),
            "only_it": c["before"] - now == {c["id"].lower()} and now <= c["before"], "return": bool(r) and r.get("id") == c["id"] and r.get("uninstalled") is True}
def uninstall_group():
    for st in ("closed", "open", "other_app", "hidden"):
        K.case("extension_uninstall", "ui", st, "installed", un_setup, lambda c: V.extension_uninstall(ext_id=c["id"]), un_done)
    K.case("extension_uninstall", "ui", "open", "not_installed", lambda: {"before": installed()}, lambda c: V.extension_uninstall(ext_id="rusabletest.never-installed-4242"),
           lambda c, b, a, r, e: {"raised": isinstance(e, V.NotFound), "unchanged": installed() == c["before"]})
    K.case("extension_uninstall", "ui", "open", "bad_id", lambda: {"before": installed()}, lambda c: V.extension_uninstall(ext_id="not an id"), lambda c, b, a, r, e: {"raised": isinstance(e, ValueError)})
    K.case("extension_uninstall", "background", "open", "not_supported", lambda: {}, lambda c: V.extension_uninstall(ext_id="a.b", mode="background"), lambda c, b, a, r, e: {"raised": isinstance(e, V.NotSupported)})
    K.case("extension_uninstall", "ui", "open", "large_clipboard", un_setup, lambda c: V.extension_uninstall(ext_id=c["id"]), un_done, big=True)
groups = [(s, (lambda s=s: state_cases(s))) for s in ("closed", "open", "other_app", "hidden")] + [("errors", errors), ("large_clipboard", large_clipboard), ("uninstall", uninstall_group)]
K.run(states, groups)
