"""verify_settings.py <group> <seed> <states...>: System Settings' wallpaper and login item commands, read back from the wallpaper
store and from System Events' login items (not from the pane the commands use)."""
import os, plistlib, sys, time, urllib.parse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import system_settings as S, vkit
from vcommon import osa, sh, se
group, seed, states = sys.argv[1], int(sys.argv[2]), sys.argv[3:]
APP = "System Settings"
GENERAL = "x-apple.systempreferences:com.apple.systempreferences.GeneralSettings"
def front_app():
    try: return osa('tell application "System Events" to return name of first process whose frontmost is true')
    except RuntimeError: return ""
def quit_settings():
    if S._running():
        try: osa('tell application "System Settings" to quit')
        except RuntimeError: pass
        [time.sleep(0.5) for _ in range(30) if S._running()]
def start(state, ctx):
    pane = ctx.get("pane")
    if state == "blocked": return  # the case's own setup made the state
    if state == "closed": quit_settings(); return
    sh(f"open '{pane if state == 'pane_open' else GENERAL}'"); [time.sleep(0.5) for _ in range(30) if not S._running()]; time.sleep(2.5)
    se("set visible to true\nset frontmost to true", APP); time.sleep(0.5)
    if state == "hidden": se("set visible to false", APP); time.sleep(1)
    if state == "other_app": sh("open -a Calculator"); [time.sleep(0.3) for _ in range(20) if front_app() == APP]
    time.sleep(0.5)
def clean(state): return state == "blocked" or not S._running() or S._blocking_sheet() is None  # blocked: the case's own dialog stays, checked as panel_kept
K = vkit.Kit("settings", S, APP, group, seed, S.SettingsError, start, clean)
# What the wallpaper store says the desktop shows (independent of the pane).
def desktop():
    d = plistlib.load(open(S.WALLPAPER_INDEX, "rb"))["AllSpacesAndDisplays"]
    part = d.get("Desktop") or d.get("Linked")
    c = part["Content"]["Choices"][0]
    files = [urllib.parse.unquote(os.path.basename(f.get("relative", ""))).rsplit(".", 1)[0] for f in c.get("Files", [])]
    return c["Provider"], files, str(part.get("LastSet"))
def shows(name):
    provider, files, _ = desktop()
    return name in files or provider == "com.apple.wallpaper.choice." + name.lower().replace(" ", "")
COLORS = sorted(n[:-4] for n in os.listdir("/System/Library/Desktop Pictures/Solid Colors") if n.endswith(".png"))
POOL = ["Sequoia", "Macintosh", "Sonoma", "iMac Blue", "iMac Pink", "iMac Silver", "iMac Purple", "iMac Orange", "iMac Green", "Radial Sky Blue"] + [c for c in COLORS if c != "Gold 2"]
def pick():
    while True:
        n = K.V.rng.choice(POOL)
        if not shows(n): return n
APPS = ["/System/Applications/Chess.app", "/System/Applications/Stickies.app", "/System/Applications/Tips.app", "/System/Applications/Dictionary.app",
        "/System/Applications/Font Book.app", "/System/Applications/Utilities/Grapher.app", "/System/Applications/Utilities/Script Editor.app",
        "/System/Applications/Image Capture.app", "/System/Applications/Photo Booth.app", "/System/Applications/Stocks.app", "/System/Applications/Clock.app"]
def items():
    try:
        out = osa('tell application "System Events" to get path of every login item')
        return [p.strip().rstrip("/") for p in out.split(", ") if p.strip()]
    except RuntimeError: return []
def se_add(path): osa(f'tell application "System Events" to make login item at end with properties {{path:"{path}", hidden:false}}')
def se_remove_all():
    for p in items():
        n = os.path.basename(p)[:-4]
        try: osa(f'tell application "System Events" to delete login item "{n}"')
        except RuntimeError: pass
used = {"i": 0}
def app():
    used["i"] += 1; return APPS[(used["i"] - 1) % len(APPS)]
WP = "x-apple.systempreferences:com.apple.Wallpaper-Settings.extension"; LI = "x-apple.systempreferences:com.apple.LoginItems-Settings.extension"
def state_cases(state):
    m = "ui"
    def wsetup():
        n = pick(); return {"name": n, "pane": WP, "last": desktop()[2]}
    K.case("wallpaper_set", m, state, "local", wsetup, lambda c: S.wallpaper_set(name=c["name"]),
           lambda c, b, a, r, e: {"no_error": e is None, "store_shows_it": shows(c["name"]), "store_changed": desktop()[2] != c["last"], "return": bool(r) and r["wallpaper"] == c["name"] and r["changed"]})
    K.case("wallpaper_list", m, state, "all", lambda: {"pane": WP, "now": desktop()}, lambda c: S.wallpaper_list(),
           lambda c, b, a, r, e: {"no_error": e is None, "colors_listed": bool(r) and set(COLORS) - {"Gold 2"} <= {w["name"] for w in r if w["on_this_mac"]},
                                  "one_current": bool(r) and len([w for w in r if w["current"]]) == 1 and shows([w for w in r if w["current"]][0]["name"]),
                                  "nothing_changed": desktop()[:2] == c["now"][:2]})
    def asetup():
        se_remove_all(); p = app(); return {"path": [p], "pane": LI}  # app paths in lists: the kit's test-folder guard is for str paths
    K.case("login_item_add", m, state, "app", asetup, lambda c: S.login_item_add(app_path=c["path"][0]),
           lambda c, b, a, r, e: {"no_error": e is None, "in_login_items": items() == c["path"], "return": bool(r) and r["path"] == c["path"][0] and r["kind"] == "Application"})
    def rsetup():
        se_remove_all(); p1, p2 = app(), app(); se_add(p1); se_add(p2); time.sleep(1); return {"p": [p1, p2], "pane": LI}
    K.case("login_item_remove", m, state, "one_of_two", rsetup, lambda c: S.login_item_remove(name=os.path.basename(c["p"][0])[:-4]),
           lambda c, b, a, r, e: {"no_error": e is None, "only_other_left": items() == [c["p"][1]], "app_kept": os.path.isdir(c["p"][0]), "return": bool(r) and r["removed"]})
    K.case("login_item_list", m, state, "two", rsetup, lambda c: S.login_item_list(),
           lambda c, b, a, r, e: {"no_error": e is None, "both": bool(r) and sorted(x["name"] for x in r) == sorted(os.path.basename(x)[:-4] for x in c["p"]), "unchanged": sorted(items()) == sorted(c["p"])})
def errors():
    m, st = "ui", "open"
    K.case("wallpaper_set", m, st, "not_found", lambda: {"now": desktop()}, lambda c: S.wallpaper_set(name=f"No Such Wallpaper {K.V.rng.randint(10, 999)}"), lambda c, b, a, r, e: {"raised": isinstance(e, S.NotFound), "unchanged": desktop()[:2] == c["now"][:2]})
    K.case("wallpaper_set", m, st, "remote", lambda: {"now": desktop()}, lambda c: S.wallpaper_set(name=K.V.rng.choice(["Monterey", "Big Sur", "Catalina", "The Lake", "Iceland Glacier"])),
           lambda c, b, a, r, e: {"raised_StateBlocked": isinstance(e, S.StateBlocked), "unchanged": desktop()[:2] == c["now"][:2]})
    K.case("wallpaper_set", m, st, "empty", lambda: {}, lambda c: S.wallpaper_set(name=" "), lambda c, b, a, r, e: {"raised": isinstance(e, ValueError)})
    def already():
        se_remove_all(); p = app(); se_add(p); time.sleep(1); return {"p": [p]}
    K.case("login_item_add", m, st, "already", already, lambda c: S.login_item_add(app_path=c["p"][0]), lambda c, b, a, r, e: {"raised": isinstance(e, S.AlreadyExists), "unchanged": items() == c["p"]})
    K.case("login_item_add", m, st, "no_app", lambda: {}, lambda c: S.login_item_add(app_path="/Applications/No Such App 41.app"), lambda c, b, a, r, e: {"raised": isinstance(e, S.NotFound)})
    K.case("login_item_add", m, st, "not_app", lambda: {}, lambda c: S.login_item_add(app_path=K.DATA), lambda c, b, a, r, e: {"raised": isinstance(e, ValueError)})
    K.case("login_item_remove", m, st, "not_found", already, lambda c: S.login_item_remove(name="Nothing Like It"), lambda c, b, a, r, e: {"raised": isinstance(e, S.NotFound), "unchanged": items() == c["p"]})
    def sheet():
        se_remove_all(); sh(f"open '{LI}'"); time.sleep(3); se("set frontmost to true", APP)
        add = next(x for x in S._walk(S._windows()[0]) if S._role(x) == "AXButton" and S._string(x, "AXDescription") == "Add"); S._press(add); time.sleep(2); return {"p": [app()]}
    def close_sheet(c):
        for w in S._windows():
            b = S._by_id(w, "CancelButton")
            if b is not None: S._press(b); time.sleep(1)
    K.case("login_item_add", m, "blocked", "open_panel", sheet, lambda c: S.login_item_add(app_path=c["p"][0]), lambda c, b, a, r, e: {"raised": isinstance(e, S.StateBlocked), "panel_kept": S._blocking_sheet() is not None, "nothing_added": items() == []},
           after=None)
    close_sheet({})
    for fn, call in (("wallpaper_set", lambda c: S.wallpaper_set(name="Plum", mode="background")), ("login_item_add", lambda c: S.login_item_add(app_path=APPS[0], mode="background"))):
        K.case(fn, "background", st, "not_supported", lambda: {}, call, lambda c, b, a, r, e: {"raised": isinstance(e, S.NotSupported)})
def large_clipboard():
    def asetup():
        se_remove_all(); return {"path": [app()], "pane": LI}
    K.case("login_item_add", "ui", "open", "large_clipboard", asetup, lambda c: S.login_item_add(app_path=c["path"][0]), lambda c, b, a, r, e: {"no_error": e is None, "in_login_items": items() == c["path"]}, big=True)
# Appearance (overnight): read back from the global preferences with defaults, separately from the pane.
AP = "x-apple.systempreferences:com.apple.Appearance-Settings.extension"
def look():
    d = lambda k: subprocess.run(["defaults", "read", "-g", k], capture_output=True, text=True).stdout.strip()
    if d("AppleInterfaceStyleSwitchesAutomatically") == "1": return "auto"
    return "dark" if d("AppleInterfaceStyle") == "Dark" else "light"
import subprocess
def appearance_cases(state):
    order = ["dark", "light", "auto", "light"] if state != "hidden" else ["auto", "dark", "light"]
    for want in order:
        K.case("appearance_set", "ui", state, want, lambda want=want: {"pane": AP, "was": look()}, lambda c, want=want: S.appearance_set(mode_name=want),
               lambda c, b, a, r, e, want=want: {"no_error": e is None, "set": look() == want, "return": bool(r) and r["appearance"] == want and r["changed"] == (c["was"] != want)})
def appearance_group():
    for st in ("closed", "open", "pane_open", "other_app", "hidden"): appearance_cases(st)
    K.case("appearance_set", "ui", "open", "again", lambda: (S.appearance_set(mode_name="dark"), {"pane": AP})[1], lambda c: S.appearance_set(mode_name="dark"),
           lambda c, b, a, r, e: {"no_error": e is None, "still": look() == "dark", "unchanged_flag": bool(r) and r["changed"] is False})
    K.case("appearance_set", "ui", "open", "bad", lambda: {"was": look()}, lambda c: S.appearance_set(mode_name="Dark Mode"), lambda c, b, a, r, e: {"raised": isinstance(e, ValueError), "unchanged": look() == c["was"]})
    K.case("appearance_set", "ui", "open", "large_clipboard", lambda: {"pane": AP}, lambda c: S.appearance_set(mode_name="light"), lambda c, b, a, r, e: {"no_error": e is None, "set": look() == "light"}, big=True)
    K.case("appearance_set", "background", "open", "not_supported", lambda: {}, lambda c: S.appearance_set(mode_name="dark", mode="background"), lambda c, b, a, r, e: {"raised": isinstance(e, S.NotSupported)})
# Dock (overnight): read back from the Dock's own preferences with defaults, separately from the pane.
DP = "x-apple.systempreferences:com.apple.Desktop-Settings.extension"
def dock():
    d = lambda k: subprocess.run(["defaults", "read", "com.apple.dock", k], capture_output=True, text=True).stdout.strip()
    return {"autohide": d("autohide") == "1", "position": d("orientation") or "bottom", "show_recents": d("show-recents") != "0"}
def dock_cases(state):
    plans = [{"autohide": True}, {"position": "left"}, {"show_recents": False}, {"autohide": False, "position": "bottom", "show_recents": True}]
    if state == "pane_open": plans = [{"position": "right"}, {"autohide": True, "position": "bottom"}, {"autohide": False}]
    for k, plan in enumerate(plans):
        def setup(plan=plan): return {"pane": DP, "was": dock()}
        K.case("dock_set", "ui", state, "_".join(f"{a}_{v}" for a, v in plan.items()).lower(), setup, lambda c, plan=plan: S.dock_set(**plan),
               lambda c, b, a, r, e, plan=plan: (lambda now: {"no_error": e is None, "set": all(now[x] == v for x, v in plan.items()),
                                                              "others_kept": all(now[x] == c["was"][x] for x in now if x not in plan),
                                                              "return": bool(r) and all(r[x] == v for x, v in plan.items()) and set(r["changed"]) == {x for x, v in plan.items() if c["was"][x] != v}})(dock()))
def dock_group():
    for st in ("closed", "open", "pane_open", "other_app", "hidden"): dock_cases(st)
    K.case("dock_set", "ui", "open", "nothing", lambda: {"was": dock()}, lambda c: S.dock_set(), lambda c, b, a, r, e: {"raised": isinstance(e, ValueError), "unchanged": dock() == c["was"]})
    K.case("dock_set", "ui", "open", "bad_position", lambda: {"was": dock()}, lambda c: S.dock_set(position="top"), lambda c, b, a, r, e: {"raised": isinstance(e, ValueError), "unchanged": dock() == c["was"]})
    K.case("dock_set", "ui", "open", "bad_flag", lambda: {"was": dock()}, lambda c: S.dock_set(autohide="yes"), lambda c, b, a, r, e: {"raised": isinstance(e, ValueError), "unchanged": dock() == c["was"]})
    K.case("dock_set", "background", "open", "not_supported", lambda: {}, lambda c: S.dock_set(autohide=True, mode="background"), lambda c, b, a, r, e: {"raised": isinstance(e, S.NotSupported)})
    K.case("dock_set", "ui", "open", "large_clipboard", lambda: {"pane": DP, "was": dock()}, lambda c: S.dock_set(position="right"), lambda c, b, a, r, e: {"no_error": e is None, "set": dock()["position"] == "right"}, big=True)
    S.dock_set(autohide=False, position="bottom", show_recents=True)
groups = [(s, (lambda s=s: state_cases(s))) for s in ("closed", "open", "pane_open", "other_app", "hidden")] + [("errors", errors), ("large_clipboard", large_clipboard), ("appearance", appearance_group), ("dock", dock_group)]
K.run(states, groups)
se_remove_all()
