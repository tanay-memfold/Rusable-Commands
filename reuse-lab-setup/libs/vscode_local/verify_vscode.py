"""verify_vscode.py <group> <seed> <states...>: VS Code's folder, file and extension commands, read back from disk."""
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
def state_cases(state):
    m = "ui"
    K.case("folder_open", m, state, "project", project, lambda c: V.folder_open(path=c["d"]), lambda c, b, a, r, e: {"no_error": e is None, "shown": bool(r) and vkit.nfc(os.path.basename(c["d"])) in vkit.nfc(r["window"]), "nothing_changed": a == b})
    K.case("folder_open", m, state, "subfolder", project, lambda c: V.folder_open(path=c["d"] + "/src"), lambda c, b, a, r, e: {"no_error": e is None, "shown": bool(r) and "src" in r["window"], "nothing_changed": a == b})
    K.case("file_open", m, state, "js", project, lambda c: V.file_open(path=c["d"] + "/src/main.js"), lambda c, b, a, r, e: {"no_error": e is None, "shown": bool(r) and "main.js" in r["window"], "file_same": a == b})
    for kind, name, text in (("js", "util.js", "export const add = (a, b) => a + b;\n"), ("special_md", "Café notes ✨.md", "# Café ✨\n\n- one \"two\"\n")):
        def setup(name=name):
            c = project(); c["p"] = f"{c['d']}/{name}"; return c
        K.case("file_new", m, state, kind, setup, lambda c, text=text: V.file_new(path=c["p"], text=text),
               lambda c, b, a, r, e, text=text: {"no_error": e is None, "file_exact": os.path.isfile(c["p"]) and open(c["p"], encoding="utf-8").read() == text, "return": bool(r) and r["path"] == c["p"]}, lambda c: {vkit.nfc(c["p"])})
def extensions():
    m, st = "ui", "open"
    for ext_id in ("streetsidesoftware.code-spell-checker", "editorconfig.editorconfig"):
        K.case("extension_install", m, st, ext_id.split(".")[1], lambda: {}, lambda c, ext_id=ext_id: V.extension_install(ext_id=ext_id),
               lambda c, b, a, r, e, ext_id=ext_id: {"no_error": e is None, "listed": ext_id.lower() in installed(), "on_disk": ext_folder(ext_id), "return": bool(r) and r["installed"]}, front=False)
    K.case("extension_install", m, st, "already", lambda: {}, lambda c: V.extension_install(ext_id="streetsidesoftware.code-spell-checker"), lambda c, b, a, r, e: {"raised": isinstance(e, V.AlreadyExists)})
    K.case("extension_install", m, st, "bad_id", lambda: {}, lambda c: V.extension_install(ext_id="not an id"), lambda c, b, a, r, e: {"raised": isinstance(e, ValueError)})
def errors():
    m, st = "ui", "open"
    K.case("folder_open", m, st, "not_found", lambda: {}, lambda c: V.folder_open(path=f"{K.DATA}/none"), lambda c, b, a, r, e: {"raised": isinstance(e, V.NotFound)})
    K.case("folder_open", m, st, "is_file", project, lambda c: V.folder_open(path=c["d"] + "/src/main.js"), lambda c, b, a, r, e: {"raised": isinstance(e, ValueError)})
    K.case("file_open", m, st, "is_folder", project, lambda c: V.file_open(path=c["d"]), lambda c, b, a, r, e: {"raised": isinstance(e, ValueError)})
    K.case("file_new", m, st, "exists", project, lambda c: V.file_new(path=c["d"] + "/src/main.js", text="x"), lambda c, b, a, r, e: {"raised": isinstance(e, V.AlreadyExists), "kept": a == b})
    K.case("file_new", m, st, "guard", lambda: {}, lambda c: V.file_new(path="/tmp/outside.js"), lambda c, b, a, r, e: {"raised_Outside": isinstance(e, V.OutsideAllowedRoot), "nothing_outside": not os.path.exists("/tmp/outside.js")})
    for fn, call in (("folder_open", lambda c: V.folder_open(path=K.DATA, mode="background")), ("file_new", lambda c: V.file_new(path=f"{K.DATA}/bg.js", mode="background"))):
        K.case(fn, "background", st, "not_supported", lambda: {}, call, lambda c, b, a, r, e: {"raised": isinstance(e, V.NotSupported)})
def large_clipboard():
    def setup():
        c = project(); c["p"] = f"{c['d']}/big.js"; return c
    K.case("file_new", "ui", "open", "large_clipboard", setup, lambda c: V.file_new(path=c["p"], text="const big = 1;\n"), lambda c, b, a, r, e: {"no_error": e is None, "file_exact": os.path.isfile(c["p"]) and open(c["p"]).read() == "const big = 1;\n"}, lambda c: {vkit.nfc(c["p"])}, big=True)
groups = [(s, (lambda s=s: state_cases(s))) for s in ("closed", "open", "other_app")] + [("errors", errors), ("large_clipboard", large_clipboard)]
K.run(states, groups)
