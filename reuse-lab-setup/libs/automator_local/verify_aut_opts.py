"""verify_aut_opts.py <group> <seed> <states...>: Automator's action options and runs (day 4), read back from the saved workflow's
document.wflow (each action's stored settings) and from the files a run makes, not through Automator's window."""
import glob, os, plistlib, struct, sys, time, zlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["AUTOMATOR_ALLOWED_ROOT"] = os.path.expanduser("~/automator-test")
import automator as A, vkit, ax
from vcommon import osa, sh, se
group, seed, states = sys.argv[1], int(sys.argv[2]), sys.argv[3:]
APP = "Automator"
def running(): return bool(sh("pgrep -x Automator"))
def front_app():
    try: return osa('tell application "System Events" to return name of first process whose frontmost is true')
    except RuntimeError: return ""
def windows(): return [w for w in ax.children(ax.app(APP)) if ax.sattr(w, "AXRole") == "AXWindow"] if running() else []
def start(state, ctx=None):
    if state == "no_workflow":
        if running():
            for w in windows():
                for s in [c for c in ax.children(w) if ax.sattr(c, "AXRole") == "AXSheet"]:
                    b = ax.find(s, "AXButton", "Cancel", exact=True) or ax.find(s, "AXButton", "Delete", exact=True); b and ax.press(b)
            sh("pkill -x Automator"); [time.sleep(0.5) for _ in range(30) if running()]
        return
    se("set visible to true\nset frontmost to true", APP); time.sleep(0.5)
    if state == "other_app": sh("open -a Calculator"); [time.sleep(0.3) for _ in range(20) if front_app() == APP]
    if state == "hidden": se("set visible to false", APP); time.sleep(1)
    time.sleep(0.5)
def clean(state): return not any(ax.sattr(c, "AXRole") == "AXSheet" for w in windows() for c in ax.children(w)) and len([w for w in windows() if ax.find(w, "AXButton", "Choose", exact=True)]) == 0
K = vkit.Kit("automator", A, APP, group, seed, A.AutomatorError, start, clean)
D = K.DATA; n = {"i": 0}
def fresh(name):
    n["i"] += 1; p = f"{D}/{name} {n['i']}"; os.makedirs(p, exist_ok=True); return p
def png(path, w, h):
    def chunk(t, d): return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    raw = b"".join(b"\x00" + bytes([30, 140, 200]) * w for _ in range(h))
    open(path, "wb").write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))
def png_size(p):
    b = open(p, "rb").read(24); return struct.unpack(">II", b[16:24])
def tilde(p): return "~" + p[len(os.path.expanduser("~")):] if p.startswith(os.path.expanduser("~")) else p
def params(c):
    """The saved workflow's actions: [(bundle id, ActionParameters)], saved with workflow_save (verified on its own)."""
    p = f"{fresh('saved')}/check.workflow"; A.workflow_save(path=p); c.setdefault("saved", []).append(os.path.dirname(p))
    d = plistlib.load(open(f"{p}/Contents/document.wflow", "rb"))
    return [(a["action"].get("BundleIdentifier"), a["action"].get("ActionParameters") or {}) for a in d["actions"]]
def build(names, copy=()):
    A.workflow_new()
    for nm in names: A.workflow_add_action(name=nm, copy_first=nm in copy)
def changes(c): return {vkit.nfc(x) for x in c.get("allowed", [])} | {vkit.nfc(x) for x in c.get("saved", [])}
def state_cases(state):
    m = "ui"
    # action_add_items: a folder, and a file with a special name
    def add_setup(kind):
        def s():
            build(["Get Specified Finder Items"]); f = fresh("items")
            target = f if kind == "folder" else f"{f}/{K.V.special().replace('/', '-')}.txt"
            if kind == "file": open(target, "w").write("x")
            return {"target": target}
        return s
    for kind in ("folder", "file"):
        K.case("action_add_items", m, state, kind, add_setup(kind), lambda c: A.action_add_items(paths=[c["target"]]),
               lambda c, b, a, r, e: {"no_error": e is None, "saved_item": any(bid == "com.apple.Automator.SpecifiedFiles" and vkit.nfc(tilde(c["target"])) in [vkit.nfc(x) for x in p.get("fileNames", [])] for bid, p in params(c))}, changes)
    # action_set_folder: Copy and Move's To:, New Text File's Where:
    for action, option in (("Copy Finder Items", "To"), ("Move Finder Items", "To"), ("New Text File", "Where")):
        def fsetup(action=action):
            build([action]); return {"folder": fresh(f"dest {K.word()}")}
        K.case("action_set_folder", m, state, action.split()[0].lower(), fsetup, lambda c, action=action, option=option: A.action_set_folder(action=action, folder=c["folder"], option=option),
               lambda c, b, a, r, e, action=action: {"no_error": e is None, "saved_folder": any(vkit.nfc(tilde(c["folder"])) in [vkit.nfc(str(v)) for v in p.values()] for bid, p in params(c))}, changes)
    # action_set_option: Save as and the subfolder checkbox, read from the saved workflow
    K.case("action_set_option", m, state, "save_as", lambda: (build(["New Text File"]), {"name": f"{K.word()} list é.txt"})[1], lambda c: A.action_set_option(action="New Text File", option="Save as", value=c["name"]),
           lambda c, b, a, r, e: {"no_error": e is None, "saved_name": any(vkit.nfc(p.get("newFileName", "")) == vkit.nfc(c["name"]) for bid, p in params(c))}, changes)
    K.case("action_set_option", m, state, "subfolders", lambda: (build(["Get Folder Contents"]), {})[1], lambda c: A.action_set_option(action="Get Folder Contents", option="Repeat for each subfolder found", value=True),
           lambda c, b, a, r, e: {"no_error": e is None, "saved_recurse": any(p.get("recurse") is True or p.get("recurse") == 1 for bid, p in params(c) if bid == "com.apple.Automator.GetFolderContents")}, changes)
    # Whole MacArena-style workflows, built with the commands and run; read from the files they make
    def flow_png():
        src, dst = fresh("To Convert"), fresh("Converted"); png(f"{src}/{K.word()}.png", 40, 30); png(f"{src}/{K.word()} b.png", 50, 20)
        build(["Get Specified Finder Items"]); A.action_add_items(paths=[src]); A.workflow_add_action(name="Get Folder Contents")
        A.workflow_add_action(name="Change Type of Images", copy_first=True); A.action_set_folder(action="Copy Finder Items", folder=dst)
        return {"src": src, "dst": dst, "allowed": [src, dst], "src0": sorted(os.listdir(src))}
    def png_done(c, b, a, r, e):
        out = sorted(os.listdir(c["dst"]))
        return {"no_error": e is None, "jpegs": len(out) == 2 and all(f.endswith(".jpg") and open(f"{c['dst']}/{f}", "rb").read(3) == b"\xff\xd8\xff" for f in out), "sources_kept": sorted(os.listdir(c["src"])) == c["src0"]}
    K.case("action_set_option", m, state, "to_type_jpeg", flow_png, lambda c: A.action_set_option(action="Change Type of Images", option="To Type", value="JPEG"), png_done, changes, after=lambda c: A.workflow_run())
    def flow_scale():
        img = fresh("Images"); png(f"{img}/{K.word()}.png", 1200, 400); png(f"{img}/{K.word()} 2.png", 900, 300)
        build(["Get Specified Finder Items"]); A.action_add_items(paths=[img]); A.workflow_add_action(name="Get Folder Contents"); A.workflow_add_action(name="Scale Images", copy_first=False)
        return {"img": img, "allowed": [img]}
    K.case("action_set_option", m, state, "scale_600", flow_scale, lambda c: A.action_set_option(action="Scale Images", option="Size", value=600),
           lambda c, b, a, r, e: {"no_error": e is None, "all_600_wide": sorted(png_size(f"{c['img']}/{f}") for f in os.listdir(c["img"])) == [(600, 200), (600, 200)]}, changes, after=lambda c: A.workflow_run())
    def flow_old():
        dl, arc = fresh("Downloads x"), fresh("Archived")
        for nm, age in ((f"{K.word()} old.txt", 45), (f"{K.word()} older.pdf", 200), (f"{K.word()} new.txt", 3)):
            open(f"{dl}/{nm}", "w").write(nm); t0 = time.time() - age * 86400; os.utime(f"{dl}/{nm}", (t0, t0))
        build(["Get Specified Finder Items"]); A.action_add_items(paths=[dl]); A.workflow_add_action(name="Get Folder Contents"); A.workflow_add_action(name="Filter Finder Items")
        A.workflow_add_action(name="Move Finder Items"); A.action_set_folder(action="Move Finder Items", folder=arc)
        return {"dl": dl, "arc": arc, "allowed": [dl, arc]}
    K.case("action_set_filter", m, state, "older_than_30_days", flow_old, lambda c: A.action_set_filter(attribute="Date last modified", operator="is not in the last", value=30, unit="days"),
           lambda c, b, a, r, e: {"no_error": e is None, "old_moved": sorted(f.split()[-1] for f in os.listdir(c["arc"])) == ["old.txt", "older.pdf"], "new_kept": [f.split()[-1] for f in os.listdir(c["dl"])] == ["new.txt"]}, changes, after=lambda c: A.workflow_run())
    def flow_list():
        pr, out = fresh("Projects"), fresh("Out"); names = [f"{K.word()}.md", f"{K.V.special().replace('/', '-')}.txt", f"{K.word()} plan.xlsx"]
        for nm in names: open(f"{pr}/{nm}", "w").write("x")
        build(["Get Specified Finder Items"]); A.action_add_items(paths=[pr]); A.workflow_add_action(name="Get Folder Contents"); A.workflow_add_action(name="New Text File")
        A.action_set_option(action="New Text File", option="Save as", value="Project_File_List.txt"); A.action_set_folder(action="New Text File", folder=out, option="Where")
        return {"pr": pr, "out": out, "names": names, "allowed": [pr, out]}
    def listed(c, b, a, r, e):
        p = f"{c['out']}/Project_File_List.txt"
        lines = open(p, encoding="utf-8").read().splitlines() if os.path.isfile(p) else []
        return {"no_error": e is None, "ran": bool(r) and r.get("ran") is True, "list_has_every_file": sorted(vkit.nfc(os.path.basename(x)) for x in lines) == sorted(vkit.nfc(x) for x in c["names"])}
    K.case("workflow_run", m, state, "file_list", flow_list, lambda c: A.workflow_run(), listed, changes)
def errors():
    m, st = "ui", "open"
    K.case("action_set_option", m, st, "no_such_action", lambda: (build(["Get Folder Contents"]), {})[1], lambda c: A.action_set_option(action="Scale Images", option="Size", value=5), lambda c, b, a, r, e: {"raised": isinstance(e, A.NotFound)})
    K.case("action_set_option", m, st, "no_such_option", lambda: (build(["Get Folder Contents"]), {})[1], lambda c: A.action_set_option(action="Get Folder Contents", option="Colour", value=5), lambda c, b, a, r, e: {"raised": isinstance(e, A.NotFound)})
    K.case("action_set_filter", m, st, "bad_attribute", lambda: (build(["Filter Finder Items"]), {})[1], lambda c: A.action_set_filter(attribute="Mood", operator="is"), lambda c, b, a, r, e: {"raised": isinstance(e, ValueError)})
    K.case("action_set_folder", m, st, "not_a_folder", lambda: (build(["Copy Finder Items"]), {"f": (lambda p: (open(p, "w").write("x"), p)[1])(f"{fresh('nf')}/x.txt")})[1], lambda c: A.action_set_folder(action="Copy Finder Items", folder=c["f"]), lambda c, b, a, r, e: {"raised": isinstance(e, ValueError)})
    K.case("action_set_folder", m, st, "guard", lambda: (build(["Copy Finder Items"]), {})[1], lambda c: A.action_set_folder(action="Copy Finder Items", folder="/tmp"), lambda c, b, a, r, e: {"raised_Outside": isinstance(e, A.OutsideAllowedRoot)})
    K.case("action_add_items", m, st, "missing", lambda: (build(["Get Specified Finder Items"]), {})[1], lambda c: A.action_add_items(paths=[f"{D}/none here"]), lambda c, b, a, r, e: {"raised": isinstance(e, A.NotFound)})
    def failing():
        # Moving into a folder that can't be written makes the run stop with an error.
        src, dst = fresh("bad src"), fresh("read only")
        open(f"{src}/stay.txt", "w").write("x"); os.chmod(dst, 0o555)
        build(["Get Specified Finder Items", "Move Finder Items"]); A.action_add_items(paths=[f"{src}/stay.txt"]); A.action_set_folder(action="Move Finder Items", folder=dst)
        return {"allowed": [src, dst], "src": src, "dst": dst}
    K.case("workflow_run", m, st, "action_fails", failing, lambda c: A.workflow_run(),
           lambda c, b, a, r, e: {"raised_UIError": isinstance(e, A.UIError), "file_stayed": os.listdir(c["src"]) == ["stay.txt"] and os.listdir(c["dst"]) == []}, changes)
    for fn, call in (("workflow_run", lambda c: A.workflow_run(mode="background")), ("action_set_option", lambda c: A.action_set_option(action="x", option="y", value=1, mode="background"))):
        K.case(fn, "background", st, "not_supported", lambda: {}, call, lambda c, b, a, r, e: {"raised": isinstance(e, A.NotSupported)})
def large_clipboard():
    m = "ui"
    def s():
        build(["Copy Finder Items"]); return {"folder": fresh("big dest")}
    K.case("action_set_folder", m, "open", "large_clipboard", s, lambda c: A.action_set_folder(action="Copy Finder Items", folder=c["folder"]),
           lambda c, b, a, r, e: {"no_error": e is None, "saved_folder": any(vkit.nfc(tilde(c["folder"])) in [vkit.nfc(str(v)) for v in p.values()] for bid, p in params(c))}, changes, big=True)
    K.case("action_set_option", m, "open", "large_clipboard", lambda: (build(["New Text File"]), {"name": "big clip list.txt"})[1], lambda c: A.action_set_option(action="New Text File", option="Save as", value=c["name"]),
           lambda c, b, a, r, e: {"no_error": e is None, "saved_name": any(p.get("newFileName") == c["name"] for bid, p in params(c))}, changes, big=True)
def closed_last():
    """Run last: force-quitting Automator makes it restore every test window on its next launch."""
    K.case("workflow_run", "ui", "no_workflow", "no_workflow", lambda: {}, lambda c: A.workflow_run(), lambda c, b, a, r, e: {"raised": isinstance(e, A.NotFound), "not_started": not running()})
groups = [(s, (lambda s=s: state_cases(s))) for s in ("open", "other_app", "hidden")] + [("errors", errors), ("large_clipboard", large_clipboard), ("closed_last", closed_last)]
K.run(states, groups)
