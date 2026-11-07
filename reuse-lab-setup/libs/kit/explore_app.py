"""python3 explore_app.py <process name> <bundle id or app path> [menus...]: start the app, print its menus and window elements, leave it running."""
import os, sys, time, subprocess
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ax
from vcommon import osa, se, sh, wait
proc, target = sys.argv[1], sys.argv[2]
if target.startswith("/"): subprocess.run(["open", "-a", target])
else: subprocess.run(["open", "-b", target])
wait(lambda: sh(f"pgrep -x '{proc}'"), 25); time.sleep(5)
try:
    se("set frontmost to true", proc); time.sleep(1)
    names = se('return name of menu bar items of menu bar 1', proc).split(", ")
    print("MENUS", names)
    for m in names[1:] if len(sys.argv) < 4 else sys.argv[3:]:
        try: print(" ", m, ":", se(f'return name of menu items of menu "{m}" of menu bar item "{m}" of menu bar 1', proc)[:900])
        except Exception as e: print(" ", m, "ERR", str(e)[:80])
except Exception as e: print("MENU ERR", str(e)[:200])
def brief(e, d=0, maxd=5):
    r = ax.sattr(e, "AXRole") or ""
    if r in ("AXMenuBar", "AXRulerMarker", "AXScrollBar", "AXImage"): return
    t = [ax.sattr(e, n) for n in ("AXTitle", "AXDescription", "AXValue", "AXIdentifier")]
    if any(t) or r in ("AXWindow", "AXSheet"): print(" " * d + r, ax.sattr(e, "AXSubrole") or "", [str(x)[:40] for x in t if x][:3])
    if d < maxd:
        for c in ax.children(e)[:40]: brief(c, d + 1, maxd)
try:
    for w in ax.children(ax.app(proc)): brief(w, 0)
except Exception as e: print("AX ERR", str(e)[:200])
