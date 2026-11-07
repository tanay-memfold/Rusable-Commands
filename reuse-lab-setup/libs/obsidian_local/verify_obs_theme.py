"""verify_obs_theme.py <group> <seed> <states...>: Obsidian's vault, note and theme commands, read back from the files on disk."""
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
import ctypes, subprocess
MEAN = r"""ObjC.import("AppKit"); function run(argv) { const r = $.NSBitmapImageRep.imageRepWithData($.NSData.dataWithContentsOfFile(argv[0])); if (r.isNil()) return "-1";
  const w = r.pixelsWide, h = r.pixelsHigh; let s = 0, n = 0;
  for (let y = 5; y < h; y += Math.max(1, Math.floor(h / 15))) for (let x = 5; x < w; x += Math.max(1, Math.floor(w / 15))) { const c = r.colorAtXY(x, y); s += (c.redComponent + c.greenComponent + c.blueComponent) / 3 * 255; n++; }
  return String(s / n); }"""
def window_of(name):
    return next((w for w in ax.children(ax.app(APP)) if ax.sattr(w, "AXRole") == "AXWindow" and f" - {name} - Obsidian" in (ax.sattr(w, "AXTitle") or "")), None) if running() else None
def brightness(name):
    """Mean brightness of the vault's window, from a screenshot of its frame (independent of Obsidian's own state)."""
    w = window_of(name)
    if w is None: return None
    f = ax.AS.AXValueGetValue; f.restype = ctypes.c_bool; f.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
    p = (ctypes.c_double * 2)(); z = (ctypes.c_double * 2)(); f(ax.attr(w, "AXPosition"), 1, p); f(ax.attr(w, "AXSize"), 2, z)
    shot = f"{K.TOOLS}/out/theme.png"; os.makedirs(os.path.dirname(shot), exist_ok=True)
    subprocess.run(["screencapture", "-x", "-R", f"{int(p[0])},{int(p[1])},{int(z[0])},{int(z[1])}", shot])
    try: return float(osa(MEAN, shot, lang="JavaScript"))
    except Exception: return None
def show(name):
    sh(f"open 'obsidian://open?vault={__import__('urllib.parse').parse.quote(name)}'"); [time.sleep(0.5) for _ in range(20) if window_of(name) is None]; time.sleep(2)
    se("set visible to true\nset frontmost to true", APP); w = window_of(name); w and ax.AS.AXUIElementSetAttributeValue(w, ax.cf("AXMain"), ax.TRUE); time.sleep(1.5)
def setup():
    p = base_vault(); name = os.path.basename(p); show(name); return {"v": p, "name": name, "b0": brightness(name)}
def flipped(c, b, a, r, e):
    time.sleep(1.5); show(c["name"]); now = brightness(c["name"])
    return {"no_error": e is None, "measured": c["b0"] is not None and now is not None, "flipped": c["b0"] is not None and now is not None and abs(now - c["b0"]) > 100,
            "return": bool(r) and r.get("vault") == vkit.nfc(c["v"]) and r.get("toggled") is True}
def layout(c): return {vkit.nfc(f"{c['v']}/.obsidian/workspace.json")}
def state_cases(state):
    # Obsidian rewrites the vault's own window-layout file (.obsidian/workspace.json) when it starts or a window changes: that one file
    # may change (recorded in the README); every other file is compared.
    K.case("theme_toggle", "ui", state, "toggle", setup, lambda c: O.theme_toggle(vault=c["v"]), flipped, layout)
    K.case("theme_toggle", "ui", state, "toggle_back", setup, lambda c: O.theme_toggle(vault=c["v"]), flipped, layout)
def other_vault_cases():
    def s():
        c = setup(); other = vname(); O.vault_create(name=other, folder=VAULTS); show(other); return c
    K.case("theme_toggle", "ui", "other_vault", "toggle", s, lambda c: O.theme_toggle(vault=c["v"]), flipped, layout)
def errors():
    K.case("theme_toggle", "ui", "open", "unknown_vault", lambda: {}, lambda c: O.theme_toggle(vault=f"{VAULTS}/no such vault"), lambda c, b, a, r, e: {"raised": isinstance(e, O.NotFound)})
    K.case("theme_toggle", "background", "open", "not_supported", lambda: {}, lambda c: O.theme_toggle(vault=f"{VAULTS}/x", mode="background"), lambda c, b, a, r, e: {"raised": isinstance(e, O.NotSupported)})
def large_clipboard():
    K.case("theme_toggle", "ui", "open", "large_clipboard", setup, lambda c: O.theme_toggle(vault=c["v"]), flipped, layout, big=True)
groups = [(s, (lambda s=s: state_cases(s))) for s in ("closed", "open", "other_app", "hidden")] + [("other_vault", other_vault_cases), ("errors", errors), ("large_clipboard", large_clipboard)]
K.run(states, groups)
