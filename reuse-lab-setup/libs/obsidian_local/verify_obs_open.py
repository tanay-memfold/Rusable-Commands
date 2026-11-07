"""verify_obs_open.py <group> <seed> <states...>: Obsidian's note_open (overnight); which note a vault window shows is read from the
window titles with separate Accessibility code, and the note files must be unchanged."""
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
def shown(vault, note):
    want = vkit.nfc(f"{os.path.basename(note)} - {os.path.basename(vault)} - Obsidian")
    return running() and any(vkit.nfc(ax.sattr(w, "AXTitle") or "").startswith(want) for w in ax.children(ax.app(APP)) if ax.sattr(w, "AXRole") == "AXWindow")
def note_setup(sub=False):
    v = base_vault(); n["i"] += 1
    rel = (f"Sub {K.V.word(1)}/" if sub else "") + (K.V.special() if n["i"] % 2 else K.V.word()).replace("/", "-").lstrip(".")
    p = f"{v}/{rel}.md"; os.makedirs(os.path.dirname(p), exist_ok=True); open(p, "w", encoding="utf-8").write(f"# {K.V.word()}\nbody ✨\n")
    time.sleep(2)  # Obsidian notices new files on its own
    return {"v": v, "note": rel, "p": p, "text": open(p, encoding="utf-8").read()}
def opened(c, b, a, r, e):
    return {"no_error": e is None, "window_shows_it": shown(c["v"], c["note"]), "note_same": open(c["p"], encoding="utf-8").read() == c["text"],
            "return": bool(r) and r["path"] == c["p"] and r["note"] == c["note"]}
def state_cases(state):
    for kind, sub in (("top", False), ("in_folder", True)):
        K.case("note_open", "ui", state, kind, lambda sub=sub: note_setup(sub), lambda c: O.note_open(vault=c["v"], note=c["note"]), opened, lambda c: own_state())
def errors():
    m, st = "ui", "open"; v = base_vault()
    K.case("note_open", m, st, "no_note", lambda: {}, lambda c: O.note_open(vault=v, note="No Such Note 4141"), lambda c, b, a, r, e: {"raised": isinstance(e, O.NotFound)}, lambda c: own_state())
    K.case("note_open", m, st, "unknown_vault", lambda: {}, lambda c: O.note_open(vault=K.DATA, note="X"), lambda c, b, a, r, e: {"raised": isinstance(e, O.NotFound)}, lambda c: own_state())
    K.case("note_open", m, st, "outside_vault", lambda: {}, lambda c: O.note_open(vault=v, note="../escape"), lambda c, b, a, r, e: {"raised": isinstance(e, ValueError)}, lambda c: own_state())
    K.case("note_open", "background", st, "not_supported", lambda: {}, lambda c: O.note_open(vault=v, note="X", mode="background"), lambda c, b, a, r, e: {"raised": isinstance(e, O.NotSupported)}, lambda c: own_state())
def large_clipboard():
    K.case("note_open", "ui", "open", "large_clipboard", note_setup, lambda c: O.note_open(vault=c["v"], note=c["note"]), opened, lambda c: own_state(), big=True)
groups = [(s, (lambda s=s: state_cases(s))) for s in ("closed", "open", "other_app", "hidden")] + [("errors", errors), ("large_clipboard", large_clipboard)]
K.run(states, groups)
