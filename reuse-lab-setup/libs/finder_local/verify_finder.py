"""Verify finder.py inside the VM: python3 verify_finder.py <group> <seed> <state|errors|blocked|guard> ...

Everything happens inside ~/finder-test. Every path a test uses is checked to be inside it first, and FINDER_ALLOWED_ROOT makes the
library refuse anything else. Results are read from the file system with os calls, never through Finder. After every state,
the top level of the home folder is compared by name and modified time, opening nothing; any change stops Finder testing."""
import ctypes, hashlib, json, os, random, subprocess, sys, time, traceback, unicodedata, zipfile
HOME = os.path.expanduser("~"); ROOT = f"{HOME}/finder-test"; TOOLS = f"{ROOT}/_tools"; DATA = f"{ROOT}/data"
os.environ["FINDER_ALLOWED_ROOT"] = ROOT
sys.path[:0] = [TOOLS]
import ax, bigclip, finder as F
from vcommon import Recorder, Values, osa, se, sh, wait
GROUP, SEED, ONLY = sys.argv[1], int(sys.argv[2]), sys.argv[3:]
V = Values(SEED); APP = "Finder"; TRASH = f"{HOME}/.Trash"
REC = Recorder(GROUP, {"versions": F._versions(), "seed": SEED, "started": time.strftime("%Y-%m-%d %H:%M:%S")})
RESUME = int(os.environ.get("RESUME", "0")); ONLY_FNS = set(filter(None, os.environ.get("FNS", "").split(",")))
COUNT = {"n": 0}; FAILS = {}
open(f"{TOOLS}/verifier.pid", "w").write(str(os.getpid()))
class Outside(BaseException): pass
def inside(path):
    real = os.path.realpath(path)
    if not (real == ROOT or real.startswith(ROOT + os.sep)): raise Outside(f"a test path is outside ~/finder-test: {path}")
    return path
def outside_view():
    """Top level of home by name and modified time, leaving out the test folder, the Trash, Library and dot-files. Opens nothing."""
    out = {}
    for n in os.listdir(HOME):
        if n in ("finder-test", "Library") or n.startswith("."): continue
        try: out[n] = os.lstat(os.path.join(HOME, n)).st_mtime
        except OSError: out[n] = None
    return out
OUTSIDE0 = outside_view()
def check_outside(where):
    now = outside_view()
    if now != OUTSIDE0:
        changed = sorted(k for k in set(now) | set(OUTSIDE0) if now.get(k) != OUTSIDE0.get(k))
        raise Outside(f"something outside ~/finder-test changed at {where}: {changed}")
def nfc(p): return unicodedata.normalize("NFC", p)
def tree():
    """Paths in one Unicode form, because Finder can store a pasted name in another; the file is still the same."""
    out = {}
    for base, dirs, files in os.walk(DATA):
        for n in dirs: out[nfc(os.path.join(base, n))] = None
        for n in files:
            if n == ".DS_Store": continue
            p = os.path.join(base, n)
            out[nfc(p)] = "link:" + os.readlink(p) if os.path.islink(p) else hashlib.sha256(open(p, "rb").read()).hexdigest()
    return out
def write(path, text):
    inside(path); os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as h: h.write(text)
def base():
    for n in ("Inbox", "Archive", "Invoices", "Photos"): os.makedirs(inside(f"{DATA}/{n}"), exist_ok=True)
    write(f"{DATA}/Inbox/notes.txt", "keep me\n"); write(f"{DATA}/Inbox/notes copy.txt", "similar name\n")
    write(f"{DATA}/Archive/notes.txt", "same name elsewhere\n"); write(f"{DATA}/Photos/readme.md", "# photos\n")
def wins():
    a = ax.app(APP); return [c for c in ax.children(a) if ax.sattr(c, "AXRole") == "AXWindow"]
def close_windows():
    se('''repeat with x in windows
  try
    click (first button of x whose subrole is "AXCloseButton")
  end try
end repeat''', APP); time.sleep(0.5)
def escape_all():
    for _ in range(3):
        try: se("key code 53", APP)
        except RuntimeError: pass
    for w in wins():
        for s in [e for e in ax.children(w) if ax.sattr(e, "AXRole") == "AXSheet"]:
            c = ax.find(s, "AXButton", "Cancel", exact=True)
            if c: ax.press(c); time.sleep(0.4)
        if ax.sattr(w, "AXSubrole") == "AXDialog":
            c = ax.find(w, "AXButton", "Cancel", exact=True)
            if c: ax.press(c); time.sleep(0.4)
def reveal_with_open(path): sh(f"open -R '{inside(path)}'"); time.sleep(0.8)
def start(state):
    escape_all()
    if state == "closed": close_windows(); return
    sh(f"open '{inside(DATA + '/Photos')}'"); time.sleep(0.8)
    se("set visible to true\nset frontmost to true", APP)
    if state == "hidden": se("set visible to false", APP)
    elif state == "minimized": se('set value of attribute "AXMinimized" of window 1 to true', APP)
    elif state == "other_app":
        sh("open -a Calculator"); wait(lambda: se("return frontmost", APP) == "false", 8)
    elif state == "search_text":
        se('keystroke "f" using command down', APP); time.sleep(0.7); se('keystroke "zq"', APP)
    elif state == "selected": reveal_with_open(f"{DATA}/Photos/readme.md")
    elif state == "two_windows": sh(f"open '{inside(DATA + '/Inbox')}'")
    elif state == "alert_open":
        se('click menu item "Go to Folder…" of menu "Go" of menu bar item "Go" of menu bar 1', APP); time.sleep(0.8)
        se('keystroke "a" using command down', APP); se("key code 51", APP); time.sleep(0.4)  # empty: text there would rightly block
    time.sleep(0.7)
def clean():
    for w in wins():
        if any(ax.sattr(e, "AXRole") == "AXSheet" for e in ax.children(w)) or ax.sattr(w, "AXSubrole") == "AXDialog": return False
    return True
def front(): return osa('tell application "System Events" to return name of first process whose frontmost is true')
def case(fn, mode, state, kind, setup, call, read, changes=lambda ctx: set(), big=False):
    """read(ctx, before, after, res, err, gone) -> checks. changes(ctx): the only paths allowed to change."""
    if ONLY_FNS and fn not in ONLY_FNS: return
    COUNT["n"] += 1
    if COUNT["n"] <= RESUME or FAILS.get((fn, mode), 0) >= 3: return
    print(f"CASE {COUNT['n']} {fn} {mode} {state} {kind}", flush=True)
    try:
        ctx = setup() or {}
        for v in ctx.values():
            if isinstance(v, str) and v.startswith("/"): inside(v)
        start(state)
        want = bigclip.fill(V.rng.randint(1, 10**9)) if big else None
        small = None if big else f"keep {V.word(1)}"
        if small: subprocess.run(["pbcopy"], input=small.encode())
        before, trash0 = tree(), set(os.listdir(TRASH)) if os.path.isdir(TRASH) else set()
        front0 = front(); began = time.monotonic()
        try: res, err = call(ctx), None
        except (F.FinderError, ValueError) as e: res, err = None, e
        secs = round(time.monotonic() - began, 1)
        end = time.monotonic() + 8
        while True:
            after = tree(); gone = (set(os.listdir(TRASH)) if os.path.isdir(TRASH) else set()) - trash0
            checks = read(ctx, before, after, res, err, gone)
            if all(checks.values()) or time.monotonic() > end: break
            time.sleep(0.4)
        allowed = changes(ctx)
        others = [p for p in set(before) | set(after) if before.get(p) != after.get(p) and p not in allowed]
        checks["others_unchanged"] = not others
        if want: checks.update(bigclip.check(want))
        else: checks["clipboard_kept"] = subprocess.run(["pbpaste"], capture_output=True).stdout.decode(errors="replace") == small
        if mode == "ui" and kind != "blocked": checks["nothing_left_open"] = clean()
        if mode == "background" and state != "alert_open": checks["front_app_unchanged"] = front() == front0
        REC.case(fn, mode, state, kind, checks, repr(err)[:160] if err else None, secs)
        if not all(checks.values()): FAILS[(fn, mode)] = FAILS.get((fn, mode), 0) + 1
    except Outside: raise
    except Exception:
        REC.case(fn, mode, state, kind, {"harness": False}, traceback.format_exc()[-300:]); FAILS[(fn, mode)] = FAILS.get((fn, mode), 0) + 1
def name(i, suffix=".txt"): return nfc((V.special() if i % 2 else V.word()).replace("/", "-") + suffix)
def infile(folder, i, text=None):
    p = f"{DATA}/{folder}/{name(i)}"; write(p, text or ("content " + V.word())); return p
def run_state(state, i):
    AR, INV, IN = f"{DATA}/Archive", f"{DATA}/Invoices", f"{DATA}/Inbox"
    for mode in os.environ.get("MODES", "background,ui").split(","):
        case("folder_create", mode, state, "normal", lambda: {"p": f"{AR}/{name(i, '')}"}, lambda c: F.folder_create(path=c["p"], mode=mode),
             lambda c, b, a, r, e, g: {"no_error": e is None, "made": os.path.isdir(c["p"]), "only_it": set(a) - set(b) == {c["p"]}, "return": bool(r) and r["path"] == c["p"] and r["kind"] == "folder"}, lambda c: {c["p"]})
        case("file_copy", mode, state, "file", lambda: {"p": infile("Inbox", i)}, lambda c: F.file_copy(path=c["p"], to_folder=AR, mode=mode),
             lambda c, b, a, r, e, g: (lambda t: {"no_error": e is None, "copy_same": a.get(t) == b.get(c["p"]), "original_kept": a.get(c["p"]) == b.get(c["p"]), "return": bool(r) and r["path"] == t})(f"{AR}/{os.path.basename(c['p'])}"), lambda c: {f"{AR}/{os.path.basename(c['p'])}"})
        def folder_fix():
            d = f"{IN}/{name(i, '')}"; os.makedirs(inside(d)); write(f"{d}/inner.txt", "inner " + V.word()); return {"p": d}
        case("file_copy", mode, state, "folder", folder_fix, lambda c: F.file_copy(path=c["p"], to_folder=AR, mode=mode),
             lambda c, b, a, r, e, g: (lambda t: {"no_error": e is None, "inner_same": a.get(t + "/inner.txt") == b.get(c["p"] + "/inner.txt"), "original_kept": c["p"] in a})(f"{AR}/{os.path.basename(c['p'])}"), lambda c: {f"{AR}/{os.path.basename(c['p'])}", f"{AR}/{os.path.basename(c['p'])}/inner.txt"})
        case("file_move", mode, state, "file", lambda: {"p": infile("Inbox", i + 1)}, lambda c: F.file_move(path=c["p"], to_folder=INV, mode=mode),
             lambda c, b, a, r, e, g: (lambda t: {"no_error": e is None, "moved_same": a.get(t) == b.get(c["p"]), "original_gone": c["p"] not in a, "return": bool(r) and r["path"] == t})(f"{INV}/{os.path.basename(c['p'])}"), lambda c: {c["p"], f"{INV}/{os.path.basename(c['p'])}"})
        def ren_fix():
            return {"p": infile("Inbox", i), "to": name(i + 1)}
        case("file_rename", mode, state, "normal", ren_fix, lambda c: F.file_rename(path=c["p"], to=c["to"], mode=mode),
             lambda c, b, a, r, e, g: (lambda t: {"no_error": e is None, "renamed_same": a.get(t) == b.get(c["p"]), "old_gone": c["p"] not in a, "return": bool(r) and r["name"] == c["to"]})(f"{IN}/{c['to']}"), lambda c: {c["p"], f"{IN}/{c['to']}"})
        case("file_trash", mode, state, "normal", lambda: {"p": infile("Inbox", i)}, lambda c: F.file_trash(path=c["p"], mode=mode),
             lambda c, b, a, r, e, g: {"no_error": e is None, "gone": c["p"] not in a, "in_trash": any(n.startswith(os.path.splitext(os.path.basename(c["p"]))[0][:12]) for n in g), "return": bool(r) and r["trashed"]}, lambda c: {c["p"]})
        if mode == "background":
            case("file_list", mode, state, "normal", lambda: {}, lambda c: F.file_list(folder=IN, fields="name,kind,size", mode=mode),
                 lambda c, b, a, r, e, g: {"no_error": e is None, "names": r is not None and [x["name"] for x in r] == sorted(n for n in os.listdir(IN) if not n.startswith(".")), "sizes": r is not None and all(x["size"] == os.path.getsize(f"{IN}/{x['name']}") for x in r if x["kind"] == "file")})
            q = f"needle{V.rng.randint(1000, 9999)}"
            case("file_find", mode, state, "normal", lambda: {"p": (write(f"{AR}/{q} one.txt", "x"), f"{AR}/{q} one.txt")[1]}, lambda c: F.file_find(query=q.upper(), folder=DATA, fields="path", mode=mode),
                 lambda c, b, a, r, e, g: {"no_error": e is None, "found_only_it": r is not None and [x["path"] for x in r] == [c["p"]]})
            case("file_find", mode, state, "pattern", lambda: {}, lambda c: F.file_find(query="*.md", folder=DATA, fields="path", mode=mode),
                 lambda c, b, a, r, e, g: {"no_error": e is None, "matches": r is not None and sorted(x["path"] for x in r) == sorted(p for p in a if p.endswith(".md"))})
            case("file_info", mode, state, "normal", lambda: {"p": infile("Inbox", i, "12345")}, lambda c: F.file_info(path=c["p"], fields="name,path,kind,size", mode=mode),
                 lambda c, b, a, r, e, g: {"no_error": e is None, "fields": bool(r) and r["size"] == 5 and r["kind"] == "file" and r["path"] == c["p"] and r["name"] == os.path.basename(c["p"])})
        else:
            def shown(path):
                """Read from Finder's window through Accessibility: nothing about these two commands is on disk."""
                w = next((x for x in wins() if ax.sattr(x, "AXSubrole") == "AXStandardWindow"), None)
                return bool(w) and ax.sattr(w, "AXTitle") == os.path.basename(path)
            def selected(path):
                for w in wins():
                    for e in ax.walk(w):
                        if ax.sattr(e, "AXRole") == "AXRow" and ax.attr(e, "AXSelected") == ax.TRUE.value and any(ax.sattr(f, "AXValue") == os.path.basename(path) for f in ax.walk(e)): return True
                return False
            case("file_reveal", mode, state, "normal", lambda: {"p": infile("Archive", i)}, lambda c: F.file_reveal(path=c["p"], mode=mode),
                 lambda c, b, a, r, e, g: {"no_error": e is None, "window_shows_folder": shown(AR), "row_selected": selected(c["p"]), "return": bool(r) and r["revealed"]})
            case("folder_open", mode, state, "normal", lambda: {}, lambda c: F.folder_open(path=INV, mode=mode),
                 lambda c, b, a, r, e, g: {"no_error": e is None, "window_shows_folder": shown(INV), "return": bool(r) and r["opened"]})
def errors():
    st = "other_view"; IN, AR = f"{DATA}/Inbox", f"{DATA}/Archive"
    for mode in ("background", "ui"):
        nope = f"{IN}/nope.txt"
        for fn, call in [("file_move", lambda c: F.file_move(path=nope, to_folder=AR, mode=mode)), ("file_copy", lambda c: F.file_copy(path=nope, to_folder=AR, mode=mode)), ("file_rename", lambda c: F.file_rename(path=nope, to="x.txt", mode=mode)), ("file_trash", lambda c: F.file_trash(path=nope, mode=mode)), ("folder_create", lambda c: F.folder_create(path=f"{IN}/no parent/x", mode=mode))]:
            case(fn, mode, st, "not_found", lambda: {}, call, lambda c, b, a, r, e, g: {"raised_NotFound": isinstance(e, F.NotFound)})
        for fn, call in [("file_copy", lambda c: F.file_copy(path=f"{IN}/notes.txt", to_folder=AR, mode=mode)), ("file_move", lambda c: F.file_move(path=f"{IN}/notes.txt", to_folder=AR, mode=mode)), ("file_rename", lambda c: F.file_rename(path=f"{IN}/notes.txt", to="notes copy.txt", mode=mode)), ("folder_create", lambda c: F.folder_create(path=AR, mode=mode))]:
            case(fn, mode, st, "already_exists", lambda: {}, call, lambda c, b, a, r, e, g: {"raised": isinstance(e, F.AlreadyExists), "kept": a.get(f"{AR}/notes.txt") == b.get(f"{AR}/notes.txt")})
        case("file_rename", mode, st, "bad_name", lambda: {}, lambda c: F.file_rename(path=f"{IN}/notes.txt", to="../up.txt", mode=mode), lambda c, b, a, r, e, g: {"raised": isinstance(e, ValueError)})
    for fn, call in [("file_reveal", lambda c: F.file_reveal(path=f"{IN}/notes.txt", mode="background")), ("folder_open", lambda c: F.folder_open(path=IN, mode="background"))]:
        case(fn, "background", st, "not_supported", lambda: {}, call, lambda c, b, a, r, e, g: {"raised": isinstance(e, F.NotSupported)})
    for fn, call in [("file_list", lambda c: F.file_list(folder=f"{IN}/notes.txt")), ("file_info", lambda c: F.file_info(path=f"{IN}/nope.txt"))]:
        case(fn, "background", st, "not_found", lambda: {}, call, lambda c, b, a, r, e, g: {"raised_NotFound": isinstance(e, F.NotFound)})
def guard():
    """The path guard: none of these touches anything; each must be refused before it starts. The targets don't need to exist."""
    link = f"{DATA}/Inbox/out-link"
    os.symlink("/tmp", link)
    outsiders = [f"{ROOT}/../outside-target.txt", "/tmp/outside-target.txt", "~/outside-target.txt", f"{link}/x.txt", link]
    for mode in ("background", "ui"):
        for i, bad in enumerate(outsiders):
            for fn, call in [("file_trash", lambda c, b=bad: F.file_trash(path=b, mode=mode)), ("file_move", lambda c, b=bad: F.file_move(path=b, to_folder=f"{DATA}/Archive", mode=mode)), ("file_copy", lambda c, b=bad: F.file_copy(path=f"{DATA}/Inbox/notes.txt", to_folder=b, mode=mode)), ("file_rename", lambda c, b=bad: F.file_rename(path=b, to="x.txt", mode=mode)), ("folder_create", lambda c, b=bad: F.folder_create(path=b, mode=mode))]:
                case(fn, mode, "other_view", f"guard_{i}", lambda: {}, call, lambda c, b, a, r, e, g: {"raised_Outside": isinstance(e, F.OutsideAllowedRoot)})
    for i, bad in enumerate(outsiders[:3]):
        for fn, call in [("file_list", lambda c, b=bad: F.file_list(folder=b)), ("file_find", lambda c, b=bad: F.file_find(query="x", folder=b)), ("file_info", lambda c, b=bad: F.file_info(path=b))]:
            case(fn, "background", "other_view", f"guard_{i}", lambda: {}, call, lambda c, b, a, r, e, g: {"raised_Outside": isinstance(e, F.OutsideAllowedRoot)})
    for fn, call in [("file_reveal", lambda c: F.file_reveal(path="/tmp", mode="ui")), ("folder_open", lambda c: F.folder_open(path="/tmp", mode="ui"))]:
        case(fn, "ui", "other_view", "guard", lambda: {}, call, lambda c, b, a, r, e, g: {"raised_Outside": isinstance(e, F.OutsideAllowedRoot)})
    os.unlink(link)
def blocked():
    IN = f"{DATA}/Inbox"
    start("selected"); se("key code 36", APP); time.sleep(0.7); se('keystroke "half typed"', APP); time.sleep(0.5)
    before = tree()
    for fn, call in [("file_trash", lambda: F.file_trash(path=f"{IN}/notes.txt", mode="ui")), ("folder_create", lambda: F.folder_create(path=f"{DATA}/Archive/never", mode="ui")), ("file_copy", lambda: F.file_copy(path=f"{IN}/notes.txt", to_folder=f"{DATA}/Invoices", mode="ui")), ("file_move", lambda: F.file_move(path=f"{IN}/notes.txt", to_folder=f"{DATA}/Invoices", mode="ui")), ("file_rename", lambda: F.file_rename(path=f"{IN}/notes.txt", to="never.txt", mode="ui")), ("file_reveal", lambda: F.file_reveal(path=f"{IN}/notes.txt", mode="ui")), ("folder_open", lambda: F.folder_open(path=IN, mode="ui")), ("file_compress", lambda: F.file_compress(paths=[f"{IN}/notes.txt"])), ("file_duplicate", lambda: F.file_duplicate(path=f"{IN}/notes.txt")), ("file_add_tag", lambda: F.file_add_tag(path=f"{IN}/notes.txt", tag="Never")), ("folder_new_with_selection", lambda: F.folder_new_with_selection(paths=[f"{IN}/notes.txt", f"{IN}/notes copy.txt"], name="Never"))]:
        if ONLY_FNS and fn not in ONLY_FNS: continue
        try: call(); err = None
        except Exception as e: err = e
        REC.case(fn, "ui", "typed_text", "blocked", {"raised_StateBlocked": isinstance(err, F.StateBlocked), "nothing_changed": tree() == before}, repr(err)[:120])
    escape_all()
PDF_INFO = r"""ObjC.import("Quartz"); function run(argv) { const d = $.PDFDocument.alloc.initWithURL($.NSURL.fileURLWithPath(argv[0])); return d.isNil() ? "null" : JSON.stringify({pages: d.pageCount}); }"""
TAGS = r"""ObjC.import("Foundation"); function run(argv) { const u = $.NSURL.fileURLWithPath(argv[0]); const out = Ref(); u.getResourceValueForKeyError(out, $.NSURLTagNamesKey, null); return JSON.stringify(ObjC.deepUnwrap(out[0]) || []); }"""
def pdf_pages(p):
    try: return (json.loads(osa(PDF_INFO, p, lang="JavaScript")) or {}).get("pages")
    except RuntimeError: return None
def tags_of(p):
    try: return json.loads(osa(TAGS, p, lang="JavaScript"))
    except RuntimeError: return None
def finder_trash(p):
    """Through Finder's own scripting, so Finder knows where it came from (setup only, not the library)."""
    osa('on run argv\ntell application "Finder" to delete (POSIX file (item 1 of argv) as alias)\nend run', inside(p)); time.sleep(0.8)
def zip_names(p):
    try:
        with zipfile.ZipFile(p) as z:
            # Archive Utility writes UTF-8 names without the zip's UTF-8 flag, so Python reads them as code page 437.
            names = [i.filename if i.flag_bits & 0x800 else i.filename.encode("cp437").decode("utf-8") for i in z.infolist()]
            return sorted(nfc(n) for n in names if not n.startswith("__MACOSX/"))
    except (OSError, zipfile.BadZipFile): return None
def png(p, w, h, rgb):
    import zlib, struct
    def chunk(t, d): return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    raw = b"".join(b"\0" + bytes(rgb) * w for _ in range(h))
    inside(p); open(p, "wb").write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))
def fresh_dir(tag):
    d = f"{DATA}/More/{tag}-{V.rng.randint(1000, 99999)}"; os.makedirs(inside(d)); return d
def under(d): return lambda c: {p for p in set(tree()) | set(c.get("_before", {})) if p.startswith(c["d"] + "/") or p == c["d"]}
def more_state(state, i):
    m = "ui"
    def one_file():
        d = fresh_dir("c1"); p = f"{d}/{name(i)}"; write(p, "zip me " + V.word()); return {"d": d, "p": p}
    case("file_compress", m, state, "one", one_file, lambda c: F.file_compress(paths=[c["p"]]),
         lambda c, b, a, r, e, g: (lambda z: {"no_error": e is None, "zip_has_it": zip_names(z) == [nfc(os.path.basename(c["p"]))], "original_kept": a.get(nfc(c["p"])) == b.get(nfc(c["p"])), "return": bool(r) and nfc(r["path"]) == nfc(z)})(c["p"] + ".zip"),
         lambda c: {nfc(c["p"] + ".zip")})
    def two_files():
        d = fresh_dir("c2"); ps = [f"{d}/{name(i)}", f"{d}/{name(i + 1)}"]; [write(p, "zip " + V.word()) for p in ps]; return {"d": d, "ps": ps}
    case("file_compress", m, state, "two", two_files, lambda c: F.file_compress(paths=c["ps"]),
         lambda c, b, a, r, e, g: {"no_error": e is None, "zip_has_both": zip_names(f"{c['d']}/Archive.zip") == sorted(nfc(os.path.basename(p)) for p in c["ps"]), "originals_kept": all(a.get(nfc(p)) == b.get(nfc(p)) for p in c["ps"])},
         lambda c: {nfc(f"{c['d']}/Archive.zip")})
    def a_zip():
        d = fresh_dir("x"); inner = name(i); src = f"{d}/{inner}"; write(src, "inside " + V.word()); h = hashlib.sha256(open(src, "rb").read()).hexdigest()
        z = f"{d}/{V.word().replace(' ', '-')}.zip"
        with zipfile.ZipFile(z, "w") as f: f.write(src, inner)
        os.unlink(src); return {"d": d, "z": z, "inner": inner, "h": h}
    case("file_extract", m, state, "one_file", a_zip, lambda c: F.file_extract(path=c["z"]),
         lambda c, b, a, r, e, g: {"no_error": e is None, "extracted_same": a.get(nfc(f"{c['d']}/{c['inner']}")) == c["h"], "zip_kept": a.get(nfc(c["z"])) == b.get(nfc(c["z"])), "return": bool(r) and len(r["items"]) == 1},
         lambda c: {nfc(f"{c['d']}/{c['inner']}")})
    def dup_fix():
        d = fresh_dir("d"); p = f"{d}/{name(i)}"; write(p, "dup " + V.word()); return {"d": d, "p": p}
    case("file_duplicate", m, state, "file", dup_fix, lambda c: F.file_duplicate(path=c["p"]),
         lambda c, b, a, r, e, g: (lambda new: {"no_error": e is None, "one_copy_same": len(new) == 1 and a[new[0]] == b[nfc(c["p"])] and " copy" in new[0], "original_kept": a.get(nfc(c["p"])) == b.get(nfc(c["p"])), "return": bool(r) and nfc(r["path"]) in new})(sorted(set(a) - set(b))),
         lambda c: {p for p in set(tree()) if p.startswith(nfc(c["d"]) + "/")} - {nfc(c["p"])})
    def trashed():
        d = fresh_dir("pb"); p = f"{d}/{name(i)}"; write(p, "back " + V.word()); h = hashlib.sha256(open(p, "rb").read()).hexdigest(); finder_trash(p)
        n = os.path.basename(p) if os.path.exists(f"{TRASH}/{os.path.basename(p)}") else None
        return {"d": d, "p": p, "h": h, "n": n or os.path.basename(p)}
    case("file_put_back", m, state, "file", trashed, lambda c: F.file_put_back(name=c["n"]),
         lambda c, b, a, r, e, g: {"no_error": e is None, "back_same": a.get(nfc(c["p"])) == c["h"], "not_in_trash": not os.path.exists(f"{TRASH}/{c['n']}"), "return": bool(r) and r["put_back"]},
         lambda c: {nfc(c["p"])})
    tag = f"Tag {V.word(1)}"
    def tag_fix():
        d = fresh_dir("t"); p = f"{d}/{name(i)}"; write(p, "tag " + V.word()); return {"d": d, "p": p}
    case("file_add_tag", m, state, "new_tag", tag_fix, lambda c: F.file_add_tag(path=c["p"], tag=tag),
         lambda c, b, a, r, e, g: {"no_error": e is None, "tagged": tags_of(c["p"]) == [tag], "content_same": a.get(nfc(c["p"])) == b.get(nfc(c["p"])), "return": bool(r) and r["tags"] == [tag]})
    def tag2():
        c = tag_fix(); subprocess.run(["osascript", "-l", "JavaScript", "-e", 'ObjC.import("Foundation"); function run(a) { $.NSURL.fileURLWithPath(a[0]).setResourceValueForKeyError($(["Kept"]), $.NSURLTagNamesKey, null); return "ok"; }', c["p"]], capture_output=True); return c
    case("file_add_tag", m, state, "second_tag", tag2, lambda c: F.file_add_tag(path=c["p"], tag="Red"),
         lambda c, b, a, r, e, g: {"no_error": e is None, "both": sorted(tags_of(c["p"]) or []) == ["Kept", "Red"]})
    def sel():
        d = fresh_dir("nf"); ps = [f"{d}/{name(i)}", f"{d}/{name(i + 1)}"]; [write(p, "move " + V.word()) for p in ps]; keep = f"{d}/stay {V.word()}.txt"; write(keep, "stay"); return {"d": d, "ps": ps, "keep": keep, "to": name(i + 2, "")}
    case("folder_new_with_selection", m, state, "two", sel, lambda c: F.folder_new_with_selection(paths=c["ps"], name=c["to"]),
         lambda c, b, a, r, e, g: {"no_error": e is None, "moved_same": all(a.get(nfc(f"{c['d']}/{c['to']}/{os.path.basename(p)}")) == b.get(nfc(p)) for p in c["ps"]), "originals_gone": not any(nfc(p) in a for p in c["ps"]), "other_stays": a.get(nfc(c["keep"])) == b.get(nfc(c["keep"])), "return": bool(r) and nfc(r["path"]) == nfc(f"{c['d']}/{c['to']}")},
         lambda c: {nfc(p) for p in c["ps"]} | {nfc(f"{c['d']}/{c['to']}")} | {nfc(f"{c['d']}/{c['to']}/{os.path.basename(p)}") for p in c["ps"]})
RESOLVE = r"""ObjC.import("Foundation"); function run(argv) { const u = $.NSURL.fileURLWithPath(argv[0]); const v = Ref(); u.getResourceValueForKeyError(v, $.NSURLIsAliasFileKey, null);
  if (!ObjC.unwrap(v[0])) return "not alias"; const r = $.NSURL.URLByResolvingAliasFileAtURLOptionsError(u, 0, null); return r.isNil() ? "unresolved" : ObjC.unwrap(r.path); }"""
def resolves_to(p):
    try: return osa(RESOLVE, p, lang="JavaScript")
    except RuntimeError: return None
def alias_state(state, i):
    def fix():
        d = fresh_dir("al"); p = f"{d}/{name(i)}"; write(p, "alias me " + V.word()); return {"d": d, "p": p}
    case("file_make_alias", "ui", state, "file", fix, lambda c: F.file_make_alias(path=c["p"]),
         lambda c, b, a, r, e, g: (lambda new: {"no_error": e is None, "one_alias": len(new) == 1 and nfc(resolves_to(new[0]) or "") == nfc(os.path.realpath(c["p"])),
                                                 "original_kept": a.get(nfc(c["p"])) == b.get(nfc(c["p"])), "return": bool(r) and nfc(r["path"]) in new})(sorted(set(a) - set(b))),
         lambda c: {p for p in set(tree()) if p.startswith(nfc(c["d"]) + "/")} - {nfc(c["p"])})
    def dfix():
        d = fresh_dir("ald"); sub = f"{d}/{name(i + 1, '')}"; os.makedirs(inside(sub)); write(f"{sub}/in.txt", "in"); return {"d": d, "p": sub}
    case("file_make_alias", "ui", state, "folder", dfix, lambda c: F.file_make_alias(path=c["p"]),
         lambda c, b, a, r, e, g: (lambda new: {"no_error": e is None, "one_alias": len(new) == 1 and nfc(resolves_to(new[0]) or "") == nfc(os.path.realpath(c["p"]))})(sorted(p for p in set(a) - set(b) if os.path.dirname(p) == nfc(c["d"]))),
         lambda c: {p for p in set(tree()) if p.startswith(nfc(c["d"]) + "/")} - {nfc(c["p"]), nfc(c["p"]) + "/in.txt"})
def more_errors():
    m, st = "ui", "other_view"
    d0 = fresh_dir("e"); a1 = f"{d0}/a.txt"; write(a1, "a"); write(f"{d0}/a.txt.zip", "taken"); d1 = fresh_dir("e2"); b1 = f"{d1}/b.txt"; write(b1, "b")
    case("file_compress", m, st, "already_exists", lambda: {}, lambda c: F.file_compress(paths=[a1]), lambda c, b, a, r, e, g: {"raised": isinstance(e, F.AlreadyExists), "kept": a.get(nfc(f"{d0}/a.txt.zip")) == b.get(nfc(f"{d0}/a.txt.zip"))})
    case("file_compress", m, st, "two_folders", lambda: {}, lambda c: F.file_compress(paths=[a1, b1]), lambda c, b, a, r, e, g: {"raised": isinstance(e, ValueError)})
    case("file_compress", m, st, "not_found", lambda: {}, lambda c: F.file_compress(paths=[f"{d0}/none.txt"]), lambda c, b, a, r, e, g: {"raised": isinstance(e, F.NotFound)})
    case("file_compress", m, st, "empty", lambda: {}, lambda c: F.file_compress(paths=[]), lambda c, b, a, r, e, g: {"raised": isinstance(e, ValueError)})
    case("file_extract", m, st, "not_zip", lambda: {}, lambda c: F.file_extract(path=a1), lambda c, b, a, r, e, g: {"raised": isinstance(e, ValueError)})
    case("file_extract", m, st, "not_found", lambda: {}, lambda c: F.file_extract(path=f"{d0}/none.zip"), lambda c, b, a, r, e, g: {"raised": isinstance(e, F.NotFound)})
    case("file_duplicate", m, st, "not_found", lambda: {}, lambda c: F.file_duplicate(path=f"{d0}/none.txt"), lambda c, b, a, r, e, g: {"raised": isinstance(e, F.NotFound)})
    case("file_put_back", m, st, "not_found", lambda: {}, lambda c: F.file_put_back(name="No Such Item 58291.txt"), lambda c, b, a, r, e, g: {"raised": isinstance(e, F.NotFound)})
    case("file_put_back", m, st, "bad_name", lambda: {}, lambda c: F.file_put_back(name="../x"), lambda c, b, a, r, e, g: {"raised": isinstance(e, ValueError)})
    t1 = f"{d0}/tagged.txt"; write(t1, "t")
    subprocess.run(["osascript", "-l", "JavaScript", "-e", 'ObjC.import("Foundation"); function run(a) { $.NSURL.fileURLWithPath(a[0]).setResourceValueForKeyError($(["Here"]), $.NSURLTagNamesKey, null); return "ok"; }', t1], capture_output=True)
    case("file_add_tag", m, st, "already_exists", lambda: {}, lambda c: F.file_add_tag(path=t1, tag="Here"), lambda c, b, a, r, e, g: {"raised": isinstance(e, F.AlreadyExists), "kept": tags_of(t1) == ["Here"]})
    case("file_add_tag", m, st, "bad_tag", lambda: {}, lambda c: F.file_add_tag(path=a1, tag="a,b"), lambda c, b, a, r, e, g: {"raised": isinstance(e, ValueError), "none": tags_of(a1) == []})
    case("folder_new_with_selection", m, st, "one_item", lambda: {}, lambda c: F.folder_new_with_selection(paths=[a1], name="Never"), lambda c, b, a, r, e, g: {"raised": isinstance(e, ValueError)})
    write(f"{d0}/c.txt", "c"); os.makedirs(f"{d0}/Taken", exist_ok=True)
    case("folder_new_with_selection", m, st, "already_exists", lambda: {}, lambda c: F.folder_new_with_selection(paths=[a1, f"{d0}/c.txt"], name="Taken"), lambda c, b, a, r, e, g: {"raised": isinstance(e, F.AlreadyExists), "kept": nfc(a1) in a})
    case("file_make_alias", m, st, "not_found", lambda: {}, lambda c: F.file_make_alias(path=f"{d0}/none.txt"), lambda c, b, a, r, e, g: {"raised": isinstance(e, F.NotFound)})
    case("file_make_alias", m, st, "guard", lambda: {}, lambda c: F.file_make_alias(path="/tmp"), lambda c, b, a, r, e, g: {"raised_Outside": isinstance(e, F.OutsideAllowedRoot)})
    case("file_make_alias", "background", st, "not_supported", lambda: {}, lambda c: F.file_make_alias(path=a1, mode="background"), lambda c, b, a, r, e, g: {"raised": isinstance(e, F.NotSupported)})
    for fn, call in [("file_compress", lambda c: F.file_compress(paths=["/tmp/outside-target.txt"])), ("file_extract", lambda c: F.file_extract(path="/tmp/outside.zip")), ("file_duplicate", lambda c: F.file_duplicate(path="/tmp/outside-target.txt")), ("file_add_tag", lambda c: F.file_add_tag(path="/tmp", tag="x")), ("folder_new_with_selection", lambda c: F.folder_new_with_selection(paths=["/tmp/a", "/tmp/b"], name="x"))]:
        case(fn, m, st, "guard", lambda: {}, call, lambda c, b, a, r, e, g: {"raised_Outside": isinstance(e, F.OutsideAllowedRoot)})
    for fn, call in [("file_compress", lambda c: F.file_compress(paths=[a1], mode="background")), ("file_duplicate", lambda c: F.file_duplicate(path=a1, mode="background")), ("file_add_tag", lambda c: F.file_add_tag(path=a1, tag="x", mode="background"))]:
        case(fn, "background", st, "not_supported", lambda: {}, call, lambda c, b, a, r, e, g: {"raised": isinstance(e, F.NotSupported)})
def large_clipboard():
    st = "other_view"; IN, AR = f"{DATA}/Inbox", f"{DATA}/Archive"
    case("folder_create", "ui", st, "large_clipboard", lambda: {"p": f"{AR}/{name(7, '')}"}, lambda c: F.folder_create(path=c["p"], mode="ui"), lambda c, b, a, r, e, g: {"no_error": e is None, "made": os.path.isdir(c["p"])}, lambda c: {c["p"]}, big=True)
    case("file_rename", "ui", st, "large_clipboard", lambda: {"p": infile("Inbox", 7), "to": name(8)}, lambda c: F.file_rename(path=c["p"], to=c["to"], mode="ui"), lambda c, b, a, r, e, g: {"no_error": e is None, "renamed": f"{IN}/{c['to']}" in a}, lambda c: {c["p"], f"{IN}/{c['to']}"}, big=True)
    def dup_fix():
        d = fresh_dir("bd"); p = f"{d}/{name(9)}"; write(p, "dup"); return {"d": d, "p": p}
    case("file_duplicate", "ui", st, "large_clipboard", dup_fix, lambda c: F.file_duplicate(path=c["p"]), lambda c, b, a, r, e, g: {"no_error": e is None, "one_copy": len(set(a) - set(b)) == 1}, lambda c: {p for p in set(tree()) if p.startswith(nfc(c["d"]) + "/")} - {nfc(c["p"])}, big=True)
    def tag_fix():
        d = fresh_dir("bt"); p = f"{d}/{name(10)}"; write(p, "tag"); return {"d": d, "p": p}
    case("file_add_tag", "ui", st, "large_clipboard", tag_fix, lambda c: F.file_add_tag(path=c["p"], tag="Big"), lambda c, b, a, r, e, g: {"no_error": e is None, "tagged": tags_of(c["p"]) == ["Big"]}, big=True)
# Open With (overnight): which documents the app has open is read from the app itself (TextEdit's scripting; Preview's and
# ColorSync Utility's windows through Accessibility), separately from the library.
def quit_viewers():
    for a in ("TextEdit", "Preview", "ColorSync Utility"):
        if sh(f"pgrep -x '{a}'"):
            try: osa(f'tell application "{a}" to quit')
            except RuntimeError: pass
    time.sleep(1)
def opened_in(app):
    if app == "TextEdit":
        try: return [nfc(x) for x in osa('tell application "TextEdit" to get path of every document').split(", ") if x]
        except RuntimeError: return []
    pid = sh(f"pgrep -x '{app}'").split()
    if not pid: return []
    out = []
    for w in ax.children(ax.AS.AXUIElementCreateApplication(int(pid[0]))):
        d = ax.sattr(w, "AXDocument") or ""
        if d.startswith("file://"): out.append(nfc(urllib.parse.unquote(urllib.parse.urlparse(d).path)))
    return out
import urllib.parse
def openwith_state(state, i):
    for kind, suffix, app in (("txt_textedit", ".txt", "TextEdit"), ("png_preview", ".png", "Preview"), ("png_colorsync", ".png", "ColorSync Utility")):
        def fix(suffix=suffix):
            quit_viewers(); d = fresh_dir("ow"); p = f"{d}/{name(i, suffix)}"
            if suffix == ".png": png(p, 24, 16, (200, 40, 60))
            else: write(p, "open me " + V.word())
            return {"d": d, "p": p}
        case("file_open_with", "ui", state, kind, fix, lambda c, app=app: F.file_open_with(path=c["p"], app=app),
             lambda c, b, a, r, e, g, app=app: {"no_error": e is None, "open_in_app": nfc(os.path.realpath(c["p"])) in [nfc(os.path.realpath(x)) for x in opened_in(app)],
                                                "app_in_front": front() == app, "file_same": a.get(nfc(c["p"])) == b.get(nfc(c["p"])),
                                                "return": bool(r) and r["app"] == app and r["default"] == (app != "ColorSync Utility")})
def openwith_errors():
    m, st = "ui", "other_view"; d = fresh_dir("owe"); t = f"{d}/plain.txt"; write(t, "x")
    case("file_open_with", m, st, "not_offered", lambda: {}, lambda c: F.file_open_with(path=t, app="Preview"), lambda c, b, a, r, e, g: {"raised": isinstance(e, F.NotFound)})
    case("file_open_with", m, st, "other_item", lambda: {}, lambda c: F.file_open_with(path=t, app="Other…"), lambda c, b, a, r, e, g: {"raised": isinstance(e, ValueError)})
    case("file_open_with", m, st, "folder", lambda: {}, lambda c: F.file_open_with(path=d, app="TextEdit"), lambda c, b, a, r, e, g: {"raised": isinstance(e, ValueError)})
    case("file_open_with", m, st, "not_found", lambda: {}, lambda c: F.file_open_with(path=f"{d}/none.txt", app="TextEdit"), lambda c, b, a, r, e, g: {"raised": isinstance(e, F.NotFound)})
    case("file_open_with", m, st, "guard", lambda: {}, lambda c: F.file_open_with(path="/etc/hosts", app="TextEdit"), lambda c, b, a, r, e, g: {"raised_Outside": isinstance(e, F.OutsideAllowedRoot)})
    case("file_open_with", "background", st, "not_supported", lambda: {}, lambda c: F.file_open_with(path=t, app="TextEdit", mode="background"), lambda c, b, a, r, e, g: {"raised": isinstance(e, F.NotSupported)})
    def big():
        quit_viewers(); d2 = fresh_dir("owb"); p = f"{d2}/{name(3)}"; write(p, "big " + V.word()); return {"d": d2, "p": p}
    case("file_open_with", m, st, "large_clipboard", big, lambda c: F.file_open_with(path=c["p"], app="TextEdit"),
         lambda c, b, a, r, e, g: {"no_error": e is None, "open_in_app": nfc(os.path.realpath(c["p"])) in [nfc(os.path.realpath(x)) for x in opened_in("TextEdit")]}, big=True)
# Locking (overnight): the lock is read from the item's own flags (os.lstat st_flags, UF_IMMUTABLE), separately from Finder.
import stat as _stat
def is_locked(p): return bool(os.lstat(p).st_flags & _stat.UF_IMMUTABLE)
def lock_state(state, i):
    for mode in ("ui", "background"):
        for kind, folder in (("file", False), ("folder", True)):
            def fix(folder=folder):
                d = fresh_dir("lk"); p = f"{d}/{name(i, '' if folder else '.txt')}"
                if folder: os.makedirs(inside(p)); write(f"{p}/in.txt", "in")
                else: write(p, "lock me " + V.word())
                return {"d": d, "p": p}
            case("file_set_locked", mode, state, f"lock_{kind}", fix, lambda c, mode=mode: F.file_set_locked(path=c["p"], locked=True, mode=mode),
                 lambda c, b, a, r, e, g: {"no_error": e is None, "locked": is_locked(c["p"]), "return": bool(r) and r["locked"] is True and r["changed"] is True})
        def locked_fix():
            d = fresh_dir("ul"); p = f"{d}/{name(i + 1)}"; write(p, "unlock me"); os.chflags(p, os.lstat(p).st_flags | _stat.UF_IMMUTABLE); return {"d": d, "p": p}
        case("file_set_locked", mode, state, "unlock", locked_fix, lambda c, mode=mode: F.file_set_locked(path=c["p"], locked=False, mode=mode),
             lambda c, b, a, r, e, g: {"no_error": e is None, "unlocked": not is_locked(c["p"]), "return": bool(r) and r["locked"] is False and r["changed"] is True})
def lock_errors():
    st = "other_view"
    for mode in ("ui", "background"):
        def already():
            d = fresh_dir("la"); p = f"{d}/{name(3)}"; write(p, "x"); os.chflags(p, os.lstat(p).st_flags | _stat.UF_IMMUTABLE); return {"d": d, "p": p}
        case("file_set_locked", mode, st, "already_locked", already, lambda c, mode=mode: F.file_set_locked(path=c["p"], locked=True, mode=mode),
             lambda c, b, a, r, e, g: {"no_error": e is None, "still_locked": is_locked(c["p"]), "unchanged_flag": bool(r) and r["changed"] is False})
        case("file_set_locked", mode, st, "not_found", lambda: {}, lambda c, mode=mode: F.file_set_locked(path=f"{DATA}/More/none.txt", mode=mode), lambda c, b, a, r, e, g: {"raised": isinstance(e, F.NotFound)})
        case("file_set_locked", mode, st, "bad_flag", lambda: {}, lambda c, mode=mode: F.file_set_locked(path=f"{DATA}/More", locked="yes", mode=mode), lambda c, b, a, r, e, g: {"raised": isinstance(e, ValueError)})
        case("file_set_locked", mode, st, "guard", lambda: {}, lambda c, mode=mode: F.file_set_locked(path="/tmp", mode=mode), lambda c, b, a, r, e, g: {"raised_Outside": isinstance(e, F.OutsideAllowedRoot)})
    def big():
        d = fresh_dir("lb"); p = f"{d}/{name(4)}"; write(p, "big"); return {"d": d, "p": p}
    case("file_set_locked", "ui", st, "large_clipboard", big, lambda c: F.file_set_locked(path=c["p"], locked=True), lambda c, b, a, r, e, g: {"no_error": e is None, "locked": is_locked(c["p"])}, big=True)
STATES = ["closed", "other_view", "hidden", "minimized", "other_app", "search_text", "selected", "two_windows", "alert_open"]
try:
    try:
        check_outside("start"); base()
        for i, state in enumerate(STATES):
            if state in ONLY:
                print(f"== state starts: {state} at {time.strftime('%H:%M:%S')}", flush=True); run_state(state, i); check_outside(state)
        for i, state in enumerate(STATES):
            if "alias_" + state in ONLY:
                print(f"== state starts: alias_{state} at {time.strftime('%H:%M:%S')}", flush=True); alias_state(state, i + 40); check_outside("alias_" + state)
        for i, state in enumerate(STATES):
            if "more_" + state in ONLY:
                print(f"== state starts: more_{state} at {time.strftime('%H:%M:%S')}", flush=True); more_state(state, i + 20); check_outside("more_" + state)
        for i, state in enumerate(STATES):
            if "lock_" + state in ONLY:
                print(f"== state starts: lock_{state} at {time.strftime('%H:%M:%S')}", flush=True); lock_state(state, i + 80); check_outside("lock_" + state)
        for i, state in enumerate(STATES):
            if "openwith_" + state in ONLY:
                print(f"== state starts: openwith_{state} at {time.strftime('%H:%M:%S')}", flush=True); openwith_state(state, i + 60); check_outside("openwith_" + state)
        for label, fn in (("errors", errors), ("guard", guard), ("blocked", blocked), ("more_errors", more_errors), ("large_clipboard", large_clipboard), ("openwith_errors", openwith_errors), ("lock_errors", lock_errors)):
            if label in ONLY:
                print(f"== state starts: {label} at {time.strftime('%H:%M:%S')}", flush=True); fn(); check_outside(label)
    except Outside as o:
        REC.data["meta"]["outside"] = str(o); print("OUTSIDE", o, flush=True)
finally:
    REC.data["meta"]["finished"] = time.strftime("%Y-%m-%d %H:%M:%S"); REC.save(); print("DONE", flush=True)
