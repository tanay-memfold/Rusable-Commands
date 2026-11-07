"""verify_obsidian.py <group> <seed> <states...>: Obsidian's vault, note and theme commands, read back from the files on disk."""
import json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["OBSIDIAN_ALLOWED_ROOT"] = os.path.expanduser("~/obsidian-test")
import obsidian as O, vkit, ax
from vcommon import osa, sh, se
group, seed, states = sys.argv[1], int(sys.argv[2]), sys.argv[3:]
APP = "Obsidian"
def running(): return bool(sh("pgrep -x Obsidian"))
def front_app():
    try: return osa('tell application "System Events" to return name of first process whose frontmost is true')
    except RuntimeError: return ""
def registry():
    try: return {v["path"] for v in json.load(open(O.REGISTRY)).get("vaults", {}).values()}
    except (OSError, ValueError): return set()
def start(state):
    if state == "closed":
        if running():
            try: osa('tell application "Obsidian" to quit')
            except RuntimeError: pass
            [time.sleep(0.5) for _ in range(30) if running()]
        return
    if not running(): sh("open -b md.obsidian"); [time.sleep(0.5) for _ in range(40) if not running()]; time.sleep(3)
    se("set visible to true\nset frontmost to true", APP); time.sleep(0.5)
    if state == "hidden": se("set visible to false", APP)
    elif state == "other_app": sh("open -a Calculator"); [time.sleep(0.3) for _ in range(20) if front_app() == APP]
    time.sleep(0.5)
K = vkit.Kit("obsidian", O, APP, group, seed, O.ObsidianError, start)
VAULTS = f"{K.DATA}/vaults"; os.makedirs(VAULTS, exist_ok=True)
n = {"i": 0}
def vname():
    n["i"] += 1; return f"{(K.V.special() if n['i'] % 2 else K.V.word()).replace('/', '-').lstrip('.')} {n['i']}"
BASE = {}
def base_vault():
    if "p" not in BASE or BASE["p"] not in registry():
        name = vname(); O.vault_create(name=name, folder=VAULTS); BASE["p"] = f"{VAULTS}/{name}"
    return BASE["p"]
def appearance(v):
    try: return json.load(open(f"{v}/.obsidian/appearance.json")).get("theme")
    except (OSError, ValueError): return "unreadable"
WANT = {"light": ("moonstone",), "dark": ("obsidian",), "system": ("system", None)}
def own_state(): return {x for x in K.tree() if "/.obsidian/" in x}  # Obsidian's own settings folder in each vault, which it writes by itself
def plugins_of(v):
    """Read straight from the vault: each plugin folder's manifest name, and the list of plugins turned on."""
    names, on = {}, set()
    d = f"{v}/.obsidian/plugins"
    for i in (os.listdir(d) if os.path.isdir(d) else []):
        try: names[i] = json.load(open(f"{d}/{i}/manifest.json")).get("name")
        except (OSError, ValueError): pass
    try: on = set(json.load(open(f"{v}/.obsidian/community-plugins.json")))
    except (OSError, ValueError): pass
    return {"names": names, "on": on}
def under(p): return lambda c: {x for x in K.tree() if x == vkit.nfc(p) or x.startswith(vkit.nfc(p) + "/")} | own_state()
def state_cases(state):
    m = "ui"
    K.case("vault_create", m, state, "new", lambda: {"name": vname()}, lambda c: O.vault_create(name=c["name"], folder=VAULTS),
           lambda c, b, a, r, e: (lambda p: {"no_error": e is None, "folder_made": os.path.isdir(f"{p}/.obsidian"), "registered": p in registry(), "return": bool(r) and r["path"] == p})(f"{VAULTS}/{c['name']}"),
           lambda c: under(f"{VAULTS}/{c['name']}")(c))
    for kind, title, text in (("plain", "Plain " + K.V.word(), "Just text " + K.V.word()), ("links", K.V.special().replace("/", "-"), "See [[Other " + K.V.word() + "]] and [[Third]] ✨\nsecond line")):
        def setup(title=title):
            v = base_vault(); return {"v": v, "p": f"{v}/{title}.md"}
        K.case("note_create", m, state, kind, setup, lambda c, title=title, text=text: O.note_create(vault=c["v"], title=title, text=text),
               lambda c, b, a, r, e, text=text: {"no_error": e is None, "file_exact": os.path.isfile(c["p"]) and open(c["p"], encoding="utf-8").read() == text, "return": bool(r) and r["path"] == c["p"]},
               lambda c: under(c["v"])(c))
    for plugin in (("Advanced Tables",) if state in ("closed", "hidden") else ("Advanced Tables", "Kanban")):
        def fresh_vault():
            name = vname(); O.vault_create(name=name, folder=VAULTS); return {"v": f"{VAULTS}/{name}"}
        K.case("plugin_install", m, state, plugin.replace(" ", "_").lower(), fresh_vault, lambda c, plugin=plugin: O.plugin_install(vault=c["v"], name=plugin),
               lambda c, b, a, r, e, plugin=plugin: (lambda h: {"no_error": e is None, "installed": plugin in h["names"].values(), "turned_on": any(n == plugin and i in h["on"] for i, n in h["names"].items()),
                                                                 "return": bool(r) and r["name"] == plugin})(plugins_of(c["v"])),
               lambda c: under(c["v"])(c))
    K.case("vault_list", m, state, "normal", lambda: {}, lambda c: O.vault_list(), lambda c, b, a, r, e: {"no_error": e is None, "matches_registry": r is not None and {x["path"] for x in r} == registry()}, lambda c: own_state())
def errors():
    m, st = "ui", "open"
    v = base_vault()
    K.case("vault_create", m, st, "exists", lambda: {}, lambda c: O.vault_create(name=os.path.basename(v), folder=VAULTS), lambda c, b, a, r, e: {"raised": isinstance(e, O.AlreadyExists)})
    K.case("vault_create", m, st, "no_folder", lambda: {}, lambda c: O.vault_create(name="X", folder=f"{K.DATA}/none"), lambda c, b, a, r, e: {"raised": isinstance(e, O.NotFound)})
    K.case("vault_create", m, st, "bad_name", lambda: {}, lambda c: O.vault_create(name="a/b", folder=VAULTS), lambda c, b, a, r, e: {"raised": isinstance(e, ValueError)})
    K.case("vault_create", m, st, "guard", lambda: {}, lambda c: O.vault_create(name="X", folder="/tmp"), lambda c, b, a, r, e: {"raised_Outside": isinstance(e, O.OutsideAllowedRoot)})
    open(f"{v}/Taken.md", "w").write("keep")
    K.case("note_create", m, st, "exists", lambda: {}, lambda c: O.note_create(vault=v, title="Taken", text="no"), lambda c, b, a, r, e: {"raised": isinstance(e, O.AlreadyExists), "kept": open(f"{v}/Taken.md").read() == "keep"})
    K.case("note_create", m, st, "unknown_vault", lambda: {}, lambda c: O.note_create(vault=f"{K.DATA}", title="X"), lambda c, b, a, r, e: {"raised": isinstance(e, O.NotFound)})
    K.case("note_create", m, st, "bad_title", lambda: {}, lambda c: O.note_create(vault=v, title="a/b"), lambda c, b, a, r, e: {"raised": isinstance(e, ValueError)})
    K.case("plugin_install", m, st, "unknown_vault", lambda: {}, lambda c: O.plugin_install(vault=f"{K.DATA}", name="Kanban"), lambda c, b, a, r, e: {"raised": isinstance(e, O.NotFound)})
    K.case("plugin_install", m, st, "no_such_plugin", lambda: {"v": base_vault()}, lambda c: O.plugin_install(vault=c["v"], name="No Such Plugin 58291"),
           lambda c, b, a, r, e: {"raised": isinstance(e, O.UIError), "none_added": plugins_of(c["v"])["names"] == {}}, lambda c: under(c["v"])(c))
    for fn, call in (("vault_create", lambda c: O.vault_create(name="X", folder=VAULTS, mode="background")), ("note_create", lambda c: O.note_create(vault=v, title="X", mode="background"))):
        K.case(fn, "background", st, "not_supported", lambda: {}, call, lambda c, b, a, r, e: {"raised": isinstance(e, O.NotSupported)})
def large_clipboard():
    K.case("vault_create", "ui", "open", "large_clipboard", lambda: {"name": vname()}, lambda c: O.vault_create(name=c["name"], folder=VAULTS),
           lambda c, b, a, r, e: {"no_error": e is None, "folder_made": os.path.isdir(f"{VAULTS}/{c['name']}/.obsidian")}, lambda c: under(f"{VAULTS}/{c['name']}")(c), big=True)
    K.case("note_create", "ui", "open", "large_clipboard", lambda: {"v": base_vault(), "t": "Big " + K.V.word()}, lambda c: O.note_create(vault=c["v"], title=c["t"], text="big clip"),
           lambda c, b, a, r, e: {"no_error": e is None, "file_exact": open(f"{c['v']}/{c['t']}.md").read() == "big clip" if os.path.exists(f"{c['v']}/{c['t']}.md") else False}, lambda c: under(c["v"])(c), big=True)
groups = [(s, (lambda s=s: state_cases(s))) for s in ("closed", "open", "other_app", "hidden")] + [("errors", errors), ("large_clipboard", large_clipboard)]
K.run(states, groups)
