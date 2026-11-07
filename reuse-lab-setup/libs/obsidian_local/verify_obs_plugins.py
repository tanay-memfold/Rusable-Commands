"""verify_obs_plugins.py <group> <seed> <states...>: Obsidian's plugin_install (day 4), read back from the vault's own files
(.obsidian/community-plugins.json and the plugin's manifest), not through Obsidian."""
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
import subprocess
POOL = ["calendar", "templater-obsidian", "obsidian-tasks-plugin", "quickadd", "obsidian-outliner", "table-editor-obsidian",
        "obsidian-style-settings", "editing-toolbar", "obsidian-day-planner", "obsidian-kanban", "dataview", "homepage"]
pool = {"i": 0}
def next_plugin():
    p = POOL[pool["i"] % len(POOL)]; pool["i"] += 1; return p
def enabled(v):
    try: return json.load(open(f"{v}/.obsidian/community-plugins.json"))
    except (OSError, ValueError): return []
def manifest_id(v, pid):
    try: return json.load(open(f"{v}/.obsidian/plugins/{pid}/manifest.json")).get("id")
    except (OSError, ValueError): return None
def fresh_vault():
    name = vname(); O.vault_create(name=name, folder=VAULTS); return f"{VAULTS}/{name}"
def setup():
    v = fresh_vault(); return {"v": v, "pid": next_plugin(), "before": enabled(v)}
def installed(c, b, a, r, e):
    now = enabled(c["v"])
    return {"no_error": e is None, "enabled_listed": c["pid"] in now and [x for x in now if x != c["pid"]] == c["before"],
            "manifest": manifest_id(c["v"], c["pid"]) == c["pid"], "return": bool(r) and r.get("plugin") == c["pid"] and r.get("vault") == vkit.nfc(c["v"])}
def dotobsidian(c): return {vkit.nfc(f"{c['v']}/.obsidian")}
def state_cases(state):
    K.case("plugin_install", "ui", state, "restricted_vault", setup, lambda c: O.plugin_install(vault=c["v"], plugin_id=c["pid"]), installed, dotobsidian)
def second():
    def s():
        c = setup(); O.plugin_install(vault=c["v"], plugin_id=c["pid"]); c["pid"] = next_plugin(); c["before"] = enabled(c["v"]); return c
    K.case("plugin_install", "ui", "open", "second_plugin", s, lambda c: O.plugin_install(vault=c["v"], plugin_id=c["pid"]), installed, dotobsidian)
def errors():
    m, st = "ui", "open"
    def already():
        c = setup(); O.plugin_install(vault=c["v"], plugin_id=c["pid"]); c["before"] = enabled(c["v"]); return c
    K.case("plugin_install", m, st, "already", already, lambda c: O.plugin_install(vault=c["v"], plugin_id=c["pid"]), lambda c, b, a, r, e: {"raised": isinstance(e, O.AlreadyExists), "unchanged": enabled(c["v"]) == c["before"]})
    K.case("plugin_install", m, st, "unknown_vault", lambda: {}, lambda c: O.plugin_install(vault=f"{VAULTS}/no such vault", plugin_id="calendar"), lambda c, b, a, r, e: {"raised": isinstance(e, O.NotFound)})
    K.case("plugin_install", m, st, "bad_id", lambda: {"v": fresh_vault()}, lambda c: O.plugin_install(vault=c["v"], plugin_id="bad id/x"), lambda c, b, a, r, e: {"raised": isinstance(e, ValueError), "nothing": enabled(c["v"]) == []})
    K.case("plugin_install", m, st, "no_such_plugin", lambda: {"v": fresh_vault()}, lambda c: O.plugin_install(vault=c["v"], plugin_id="rusable-no-such-plugin-4242"),
           lambda c, b, a, r, e: {"raised": isinstance(e, O.UIError), "nothing_enabled": enabled(c["v"]) == [], "no_plugin_folder": not os.path.isdir(f"{c['v']}/.obsidian/plugins/rusable-no-such-plugin-4242")}, dotobsidian)
    K.case("plugin_install", "background", st, "not_supported", lambda: {}, lambda c: O.plugin_install(vault=f"{VAULTS}/x", plugin_id="calendar", mode="background"), lambda c, b, a, r, e: {"raised": isinstance(e, O.NotSupported)})
def large_clipboard():
    K.case("plugin_install", "ui", "open", "large_clipboard", setup, lambda c: O.plugin_install(vault=c["v"], plugin_id=c["pid"]), installed, dotobsidian, big=True)
groups = [(s, (lambda s=s: state_cases(s))) for s in ("closed", "open", "other_app", "hidden")] + [("second", second), ("errors", errors), ("large_clipboard", large_clipboard)]
K.run(states, groups)
