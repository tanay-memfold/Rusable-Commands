"""verify_obs.py <group> <seed> <states...>: OBS's scene and recording commands, read back from OBS's own scene file and from the
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
    for t in ("Cancel", "No"):
        if (t == "Cancel" and shown("Please enter the name")) or (t == "No" and shown(O.BLANK)):
            b = button(t); b and ax.press(b); time.sleep(1)
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
def clean(state): return True if state == "blocked" else not (shown("Please enter the name") or shown(O.BLANK))
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
def sname(style):
    n["i"] += 1; w = K.word().capitalize()
    return {"plain": f"{w} {n['i']}", "special": f"{w} “Live” Café ☕ {n['i']}"}[style]
def state_cases(state):
    m = "ui"
    for style in ("plain", "special"):
        K.case("scene_add", m, state, style, lambda style=style: {"name": sname(style), "s0": scenes(), "movies0": movies()}, lambda c: O.scene_add(name=c["name"]),
               lambda c, b, a, r, e: {"no_error": e is None, "in_scene_file": scenes() == c["s0"] + [c["name"]], "return": bool(r) and r.get("name") == c["name"], "movies_same": movies_only_added(c)}, before=lambda c: c.update(movies0=movies()))
    def rec_started(c, b, a, r, e):
        now = movies(); new = [f for f in now if f not in c["movies0"]]
        grows = False
        if len(new) == 1:
            s1 = os.path.getsize(os.path.join(MOVIES, new[0])); time.sleep(3); grows = os.path.getsize(os.path.join(MOVIES, new[0])) > s1
        return {"no_error": e is None, "one_new_file": len(new) == 1, "file_grows": grows, "movies_rest_same": movies_only_added(c, 1), "return": bool(r) and r.get("recording") is True}
    K.case("recording_start", m, state, "allow_blank", lambda: {"movies0": movies()}, lambda c: O.recording_start(allow_blank=True), rec_started, before=lambda c: c.update(movies0=movies()))
    K.case("recording_start", m, state, "blank_refused", lambda: {"movies0": movies()}, lambda c: O.recording_start(),
           lambda c, b, a, r, e: {"raised": isinstance(e, O.StateBlocked), "no_new_file": movies_only_added(c, 0), "warning_closed": not shown(O.BLANK)}, before=lambda c: c.update(movies0=movies()))
    if state != "closed":
        def recording_running():
            start("open"); O.recording_start(allow_blank=True); time.sleep(4)  # setup through the library, itself tested above
            return {"movies0": movies(), "keep_recording": True}
        def rec_stopped(c, b, a, r, e):
            p = (r or {}).get("path", ""); now = movies()
            grew = [f for f in now if f in c["movies0"] and now[f] != c["movies0"][f]]
            stable = os.path.isfile(p) and (time.sleep(2) or True) and os.path.getsize(p) == (r or {}).get("bytes")
            return {"no_error": e is None, "the_recording_file": os.path.dirname(p) == MOVIES and os.path.basename(p) in c["movies0"], "stopped_growing": bool(stable),
                    "plays_over_3s": duration(p) > 3, "only_it_changed": set(grew) <= {os.path.basename(p)} and not [f for f in now if f not in c["movies0"]]}
        K.case("recording_stop", m, state, "after_recording", recording_running, lambda c: O.recording_stop(), rec_stopped)
def errors():
    m, st = "ui", "open"
    def existing():
        start("open"); nm = sname("plain"); O.scene_add(name=nm); return {"name": nm, "s0": scenes(), "movies0": movies()}
    K.case("scene_add", m, st, "exists", existing, lambda c: O.scene_add(name=c["name"]), lambda c, b, a, r, e: {"raised": isinstance(e, O.AlreadyExists), "unchanged": scenes() == c["s0"]})
    K.case("scene_add", m, st, "empty", lambda: {"s0": scenes()}, lambda c: O.scene_add(name=" "), lambda c, b, a, r, e: {"raised": isinstance(e, ValueError), "unchanged": scenes() == c["s0"]})
    K.case("recording_stop", m, st, "not_recording", lambda: {"movies0": movies()}, lambda c: O.recording_stop(), lambda c, b, a, r, e: {"raised": isinstance(e, O.StateBlocked), "no_new_file": movies_only_added(c, 0)}, before=lambda c: c.update(movies0=movies()))
    def already():
        start("open"); O.recording_start(allow_blank=True); time.sleep(2); return {"movies0": movies(), "keep_recording": True}
    K.case("recording_start", m, st, "already_recording", already, lambda c: O.recording_start(allow_blank=True),
           lambda c, b, a, r, e: {"raised": isinstance(e, O.StateBlocked), "still_one_recording": button("Stop Recording") is not None and len(movies()) == len(c["movies0"])})
    start("open")
    K.case("recording_stop", m, "closed", "not_running", lambda: {"movies0": movies()}, lambda c: O.recording_stop(), lambda c, b, a, r, e: {"raised": isinstance(e, O.StateBlocked), "no_new_file": movies_only_added(c, 0), "obs_not_started": not running()}, before=lambda c: c.update(movies0=movies()))
    def typed():
        start("open"); ax.press(button(desc="Add Scene")); time.sleep(2)
        f = next(e for e in elements() if ax.sattr(e, "AXRole") == "AXTextField"); ax.AS.AXUIElementSetAttributeValue(f, ax.cf("AXValue"), ax.cf("Half typed")); time.sleep(0.5)
        return {"name": sname("plain"), "s0": scenes()}
    K.case("scene_add", m, "blocked", "name_dialog_open", typed, lambda c: O.scene_add(name=c["name"]),
           lambda c, b, a, r, e: {"raised": isinstance(e, O.StateBlocked), "unchanged": scenes() == c["s0"], "dialog_kept": shown("Please enter the name")})
    dismiss()
    for fn, call in (("scene_add", lambda c: O.scene_add(name="Bg", mode="background")), ("recording_start", lambda c: O.recording_start(mode="background"))):
        K.case(fn, "background", st, "not_supported", lambda: {}, call, lambda c, b, a, r, e: {"raised": isinstance(e, O.NotSupported)})
def large_clipboard():
    K.case("scene_add", "ui", "open", "large_clipboard", lambda: {"name": sname("special"), "s0": scenes(), "movies0": movies()}, lambda c: O.scene_add(name=c["name"]),
           lambda c, b, a, r, e: {"no_error": e is None, "in_scene_file": scenes() == c["s0"] + [c["name"]]}, big=True)
groups = [(s, (lambda s=s: state_cases(s))) for s in ("closed", "open", "other_app", "hidden")] + [("errors", errors), ("large_clipboard", large_clipboard)]
K.run(states, groups)
