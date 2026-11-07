"""verify_obs_src.py <group> <seed> <states...>: OBS's source_add (and recording with a source), read back from OBS's own scene file and from the
recording files themselves (sizes over time, and their duration read with AVFoundation), not through OBS's window or the library."""
import json, os, re, subprocess, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import obs as O, vkit, ax
from vcommon import osa, sh, se
group, seed, states = sys.argv[1], int(sys.argv[2]), sys.argv[3:]
APP = "OBS"; MOVIES = os.path.expanduser("~/Movies")
SCENES = os.path.expanduser("~/Library/Application Support/obs-studio/basic/scenes/Untitled.json")
def running(): return bool(sh("pgrep -x OBS"))
def front_app():
    try: return osa('tell application "System Events" to return name of first process whose frontmost is true')
    except RuntimeError: return ""
def elements(): return [e for w in ax.children(ax.app(APP)) for e in ax.walk(w)] if running() else []
def button(title=None, desc=None):
    return next((e for e in elements() if ax.sattr(e, "AXRole") == "AXButton" and (title is None or ax.sattr(e, "AXTitle") == title) and (desc is None or ax.sattr(e, "AXDescription") == desc)), None)
def shown(part): return any(part in ((ax.sattr(e, "AXValue") or "") + (ax.sattr(e, "AXTitle") or "")) for e in elements() if ax.sattr(e, "AXRole") == "AXStaticText")
def scenes():
    try: return [s["name"] for s in json.load(open(SCENES, encoding="utf-8"))["sources"] if s.get("id") == "scene"]
    except (OSError, ValueError, KeyError): return []
def movies(): return {f: os.path.getsize(os.path.join(MOVIES, f)) for f in os.listdir(MOVIES)} if os.path.isdir(MOVIES) else {}
def duration(path):
    """The recording's length, read from the file by Apple's afinfo (its audio track), not through OBS."""
    out = subprocess.run(["afinfo", path], capture_output=True, text=True).stdout
    m = re.search(r"estimated duration: ([0-9.]+) sec", out)
    return float(m.group(1)) if m else 0.0
def setup_stop():
    """Setup only: stop a recording left running by an earlier case, with OBS's own button."""
    b = button("Stop Recording")
    if b: ax.press(b); [time.sleep(0.5) for _ in range(30) if button("Start Recording") is None]; time.sleep(2)
def dismiss():
    for _ in range(3):
        if shown(O.BLANK): b = button("No"); b and ax.press(b); time.sleep(1)
        elif dialog_seen(1):
            b = button("Cancel"); b and ax.AS.AXUIElementPerformAction(b, ax.cf("AXPress")); time.sleep(1)
def start(state, ctx=None):
    if state == "blocked": return
    if state == "closed":
        if running():
            setup_stop(); dismiss()
            # Quit from OBS's menu, so it doesn't ask about Safe Mode next time; force it only if that didn't work.
            try: se('click menu item "Quit OBS" of menu "OBS" of menu bar item "OBS" of menu bar 1', APP)
            except RuntimeError: pass
            [time.sleep(0.5) for _ in range(40) if running()]
            if running(): sh("pkill -x OBS"); [time.sleep(0.5) for _ in range(20) if running()]
        return
    if not running(): sh("open -b com.obsproject.obs-studio"); [time.sleep(0.5) for _ in range(90) if not (running() and button("Start Recording") or button("Stop Recording"))]; time.sleep(3)
    b = button("Don’t Check"); b and ax.press(b); time.sleep(0.5)
    dismiss()
    if not (ctx or {}).get("keep_recording"): setup_stop()
    se("set visible to true\nset frontmost to true", APP); time.sleep(0.5)
    if state == "other_app": sh("open -a Calculator"); [time.sleep(0.3) for _ in range(20) if front_app() == APP]
    if state == "hidden": se("set visible to false", APP); time.sleep(1)
    time.sleep(0.5)
def dialog_signs():
    return any((ax.sattr(e, "AXRole") == "AXButton" and ax.sattr(e, "AXTitle") in ("OK", "Defaults")) or
               (ax.sattr(e, "AXRole") == "AXRadioButton" and ax.sattr(e, "AXTitle") in ("Create new", "Add Existing")) or
               (ax.sattr(e, "AXRole") == "AXCheckBox" and ax.sattr(e, "AXTitle") == "Make source visible") for e in elements())
def dialog_seen(seconds=4):
    end = time.time() + seconds
    while time.time() < end:
        if dialog_signs(): return True
        time.sleep(0.3)
    return False
def clean(state): return True if state == "blocked" else not (shown("Please enter the name") or shown(O.BLANK) or button("OK") is not None)
K = vkit.Kit("obs", O, APP, group, seed, O.OBSError, start, clean)
# ~/Movies is where OBS records, so the kit's whole-home check leaves it out and each case checks it precisely instead.
_ov = K.outside_view
def outside_view():
    v = _ov(); v.pop("Movies", None); return v
K.outside_view = outside_view; K.outside0 = outside_view()
def movies_only_added(c, allowed=0):
    now = movies(); old = c["movies0"]
    changed = [f for f in old if now.get(f) != old[f]]
    added = [f for f in now if f not in old]
    return not changed and len(added) <= allowed and all(f.lower().endswith(O.VIDEO) for f in added)
n = {"i": 0}
def sources(): 
    try: return json.load(open(SCENES, encoding="utf-8"))["sources"]
    except (OSError, ValueError, KeyError): return []
def current(): 
    try: return json.load(open(SCENES, encoding="utf-8")).get("current_scene", "")
    except (OSError, ValueError): return ""
def items(scene):
    s = next((x for x in sources() if x.get("id") == "scene" and x.get("name") == scene), None)
    return [i.get("name") for i in (s or {}).get("settings", {}).get("items", [])]
def others(name):
    return sorted((s.get("name"), s.get("id"), json.dumps(s.get("settings", {}), sort_keys=True)) for s in sources() if s.get("name") != name and s.get("id") != "scene")
def srcname(style):
    n["i"] += 1; w = K.word().capitalize()
    return {"plain": f"{w} Backdrop {n['i']}", "special": f"{w} “Caption” Café ☕ {n['i']}"}[style]
TEXTS = ["Live in 5 — stay tuned", "Line one\nLine “two” ☕ é", "Score: 3–1 (final)"]
def snap(c):
    c.update(movies0=movies(), scene=current(), others0=others(c["name"]), items0=items(current()))
def added(c, b, a, r, e):
    s = next((x for x in sources() if x.get("name") == c["name"]), None)
    ok_kind = bool(s) and s.get("id") == {"color": "color_source", "text": "text_ft2_source"}[c["kind"]]
    checks = {"no_error": e is None, "in_scene_file": ok_kind, "in_current_scene": items(c["scene"]) == c["items0"] + [c["name"]],
              "others_same": others(c["name"]) == c["others0"], "return": bool(r) and r.get("name") == c["name"] and r.get("scene") == c["scene"]}
    if c["kind"] == "text": checks["text_exact"] = bool(s) and s.get("settings", {}).get("text") == c["text"]
    return checks
def state_cases(state):
    m = "ui"
    for kind, style in (("color", "plain"), ("text", "special")):
        def setup(kind=kind, style=style):
            c = {"name": srcname(style), "kind": kind}
            if kind == "text": c["text"] = TEXTS[n["i"] % len(TEXTS)]
            return c
        call = (lambda c: O.source_add(name=c["name"], kind="color")) if kind == "color" else (lambda c: O.source_add(name=c["name"], kind="text", text=c["text"]))
        K.case("source_add", m, state, kind, setup, call, added, before=snap)
    if state == "open":
        # With a source in the scene there is no blank-screen question: recording starts without allow_blank.
        def rec_started(c, b, a, r, e):
            now = movies(); new = [f for f in now if f not in c["movies0"]]
            grows = False
            if len(new) == 1:
                s1 = os.path.getsize(os.path.join(MOVIES, new[0])); time.sleep(3); grows = os.path.getsize(os.path.join(MOVIES, new[0])) > s1
            return {"no_error": e is None, "one_new_file": len(new) == 1, "file_grows": grows, "no_blank_question": not shown(O.BLANK)}
        K.case("recording_start", m, state, "with_source", lambda: {"name": "-"}, lambda c: O.recording_start(), rec_started, before=snap)
        K.case("recording_stop", m, state, "with_source", lambda: {"name": "-", "keep_recording": True}, lambda c: O.recording_stop(),
               lambda c, b, a, r, e: {"no_error": e is None, "plays_over_2s": duration((r or {}).get("path", "")) > 2}, before=snap)
def errors():
    m, st = "ui", "open"
    def existing():
        start("open"); nm = srcname("plain"); O.source_add(name=nm, kind="color"); return {"name": nm}
    K.case("source_add", m, st, "exists", existing, lambda c: O.source_add(name=c["name"], kind="text", text="x"),
           lambda c, b, a, r, e: {"raised": isinstance(e, O.AlreadyExists), "others_same": others("\0") == c["others_all"]}, before=lambda c: c.update(others_all=others("\0")))
    for kind, kw in (("bad_kind", {"name": "K1", "kind": "image"}), ("empty_name", {"name": " ", "kind": "color"}), ("no_text", {"name": "T1", "kind": "text"}), ("text_on_color", {"name": "T2", "kind": "color", "text": "x"})):
        K.case("source_add", m, st, kind, lambda: {}, lambda c, kw=kw: O.source_add(**kw), lambda c, b, a, r, e: {"raised": isinstance(e, ValueError), "others_same": others("\0") == c["others_all"]}, before=lambda c: c.update(others_all=others("\0")))
    def typed():
        start("open"); ax.AS.AXUIElementPerformAction(button(desc="Add Source"), ax.cf("AXPress")); time.sleep(1.5)
        it = next(e for e in elements() if ax.sattr(e, "AXRole") == "AXMenuItem" and ax.sattr(e, "AXTitle") == "Color Source"); ax.AS.AXUIElementPerformAction(it, ax.cf("AXPress")); time.sleep(2)
        return {"name": srcname("plain")}
    def cancel_typed():
        for _ in range(15):
            b = button("Cancel")
            if b: ax.AS.AXUIElementPerformAction(b, ax.cf("AXPress")); time.sleep(1)
            if not dialog_seen(1): break
    K.case("source_add", m, "blocked", "source_dialog_open", typed, lambda c: O.source_add(name=c["name"], kind="color"),
           lambda c, b, a, r, e: {"raised": isinstance(e, O.StateBlocked), "not_added": not any(s.get("name") == c["name"] for s in sources()), "dialog_kept": dialog_seen()})
    cancel_typed()
    K.case("source_add", "background", st, "not_supported", lambda: {}, lambda c: O.source_add(name="Bg", kind="color", mode="background"), lambda c, b, a, r, e: {"raised": isinstance(e, O.NotSupported)})
def large_clipboard():
    K.case("source_add", "ui", "open", "large_clipboard", lambda: {"name": srcname("special"), "kind": "text", "text": TEXTS[1]},
           lambda c: O.source_add(name=c["name"], kind="text", text=c["text"]), added, before=snap, big=True)
groups = [(s, (lambda s=s: state_cases(s))) for s in ("closed", "open", "other_app", "hidden")] + [("errors", errors), ("large_clipboard", large_clipboard)]
K.run(states, groups)
