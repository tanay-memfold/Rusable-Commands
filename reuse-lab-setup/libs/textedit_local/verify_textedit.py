"""Verify textedit.py inside the VM: python3 verify_textedit.py <group> <seed> <state|errors|guard|blocked|large_clipboard> ...
Everything happens inside ~/textedit-test. Every path a test uses is checked to be inside it first, and TEXTEDIT_ALLOWED_ROOT makes the
library refuse anything else. Results are read from the files with plain file reads (and textutil for .rtf), never through TextEdit.
Every other test file is compared by content, and the top level of home is compared by name and modified time."""
import hashlib, json, os, subprocess, sys, time, traceback, unicodedata
HOME = os.path.expanduser("~"); ROOT = f"{HOME}/textedit-test"; TOOLS = f"{ROOT}/_tools"; DATA = f"{ROOT}/data"
os.environ["TEXTEDIT_ALLOWED_ROOT"] = ROOT
sys.path[:0] = [TOOLS]
import ax, bigclip, textedit as T
from vcommon import Recorder, Values, osa, se, sh, wait
GROUP, SEED, ONLY = sys.argv[1], int(sys.argv[2]), sys.argv[3:]
V = Values(SEED); APP = "TextEdit"; FAILS = {}; COUNT = {"n": 0}
REC = Recorder(GROUP, {"versions": T._versions(), "code_sha": hashlib.sha256(open(T.__file__, "rb").read()).hexdigest()[:12], "seed": SEED, "started": time.strftime("%Y-%m-%d %H:%M:%S")})
RESUME = int(os.environ.get("RESUME", "0")); ONLY_FNS = set(filter(None, os.environ.get("FNS", "").split(",")))
open(f"{TOOLS}/verifier.pid", "w").write(str(os.getpid()))
class Outside(BaseException): pass
def inside(path):
    real = os.path.realpath(path)
    if not (real == ROOT or real.startswith(ROOT + os.sep)): raise Outside(f"a test path is outside ~/textedit-test: {path}")
    return path
def outside_view():
    out = {}
    for n in os.listdir(HOME):
        if n in ("textedit-test", "Library") or n.startswith("."): continue
        try: out[n] = os.lstat(os.path.join(HOME, n)).st_mtime
        except OSError: out[n] = None
    return out
OUTSIDE0 = outside_view()
def check_outside(where):
    now = outside_view()
    if now != OUTSIDE0: raise Outside(f"something outside ~/textedit-test changed at {where}: {sorted(k for k in set(now) | set(OUTSIDE0) if now.get(k) != OUTSIDE0.get(k))}")
def nfc(p): return unicodedata.normalize("NFC", p)
def tree():
    out = {}
    for base, dirs, files in os.walk(DATA):
        for n in files:
            if n == ".DS_Store" or os.path.islink(os.path.join(base, n)): continue
            p = os.path.join(base, n); out[nfc(p)] = hashlib.sha256(open(p, "rb").read()).hexdigest()
    return out
def read_file(p):
    if p.endswith(".rtf"): return subprocess.run(["textutil", "-convert", "txt", "-stdout", p], capture_output=True, text=True).stdout
    return open(p, "rb").read().decode("utf-8")
def body_is(p, text):
    try: got = read_file(p)
    except (OSError, UnicodeDecodeError): return False
    return nfc(got).rstrip("\n") == nfc(text).rstrip("\n") if p.endswith(".rtf") else nfc(got) == nfc(text)
def write(p, text):
    inside(p); os.makedirs(os.path.dirname(p), exist_ok=True)
    if p.endswith(".rtf"):
        t = p + ".tmp.txt"; open(t, "w").write(text); subprocess.run(["textutil", "-convert", "rtf", "-output", p, t], check=True); os.unlink(t)
    else: open(p, "w", encoding="utf-8").write(text)
    return p
def running(): return bool(sh(f"pgrep -x {APP}"))
def wins(): return [c for c in ax.children(ax.app(APP)) if ax.sattr(c, "AXRole") == "AXWindow"] if running() else []
def is_doc(w):
    """While minimized, or while TextEdit is hidden, a document window reports itself as a dialog."""
    r = ax.sattr(w, "AXSubrole")
    return r == "AXStandardWindow" or (r == "AXDialog" and any(ax.sattr(e, "AXRole") == "AXTextArea" for e in ax.walk(w))
                                       and (ax.attr(w, "AXMinimized") == ax.TRUE.value or ax.attr(ax.app(APP), "AXHidden") == ax.TRUE.value))
def docs(): return [w for w in wins() if is_doc(w)]
def url_path(w):
    import urllib.parse as u
    d = ax.sattr(w, "AXDocument"); return nfc(u.unquote(u.urlparse(d).path)) if d else None
def win_of(p): return next((w for w in docs() if url_path(w) == nfc(p)), None)
def sheet(w): return next((c for c in ax.children(w) if ax.sattr(c, "AXRole") == "AXSheet"), None)
def menu(m, i): return se(f'click menu item "{i}" of menu "{m}" of menu bar item "{m}" of menu bar 1', APP)
def forward(): se("set visible to true\nset frontmost to true", APP); wait(lambda: se("return frontmost", APP) == "true", 5)
def raise_win(w):
    forward()
    if ax.attr(w, "AXMinimized") == ax.TRUE.value: se('set value of attribute "AXMinimized" of window 1 to false', APP)
    ax.AS.AXUIElementPerformAction(w, ax.cf("AXRaise")); time.sleep(0.4)
def tidy():
    """Back to nothing open, without saving what a test left behind in an unsaved window."""
    if not running(): return
    for _ in range(3):
        try:
            for w in wins():
                if ax.sattr(w, "AXSubrole") == "AXDialog" and not is_doc(w):
                    c = ax.find(w, "AXButton", "Cancel", exact=True); c and ax.press(c); time.sleep(0.4)
                s = sheet(w)
                if s:
                    c = ax.find(s, "AXButton", "Cancel", exact=True); c and ax.press(c); time.sleep(0.5)
            forward()
            for w in docs():
                ax.AS.AXUIElementPerformAction(w, ax.cf("AXRaise")); time.sleep(0.1)
                menu("File", "Close"); time.sleep(0.4)
                for x in docs():
                    s = sheet(x)
                    if s:
                        c = ax.find(s, "AXButton", "Delete", exact=True) or ax.find(s, "AXButton", "Cancel", exact=True); c and ax.press(c); time.sleep(0.5)
        except Exception: time.sleep(0.5)
        if not docs(): return
def quit_app():
    tidy()
    if running():
        menu("TextEdit", "Quit TextEdit"); wait(lambda: not running(), 15)
    if running(): raise RuntimeError("TextEdit didn't quit")
def open_doc(p):
    subprocess.run(["open", "-a", "TextEdit", inside(p)]); wait(lambda: win_of(p) and next((e for e in ax.walk(win_of(p)) if ax.sattr(e, "AXRole") == "AXTextArea"), None), 10); time.sleep(0.4)
def type_at_end(w, text):
    raise_win(w); ta = next(e for e in ax.walk(w) if ax.sattr(e, "AXRole") == "AXTextArea"); ax.focus(ta); time.sleep(0.2); se("key code 125 using command down", APP); subprocess.run(["pbcopy"], input=text.encode()); se('keystroke "v" using command down', APP); time.sleep(0.4)  # pasted: typing stalls TextEdit's text checking in this VM
BASE, OTHER, FAR = f"{DATA}/base/base.txt", f"{DATA}/base/other.txt", f"{DATA}/base/closed.rtf"
def base():
    write(BASE, "base doc\n"); write(OTHER, "other doc\n"); write(FAR, "never opened\n"); os.makedirs(f"{DATA}/new", exist_ok=True)
def start(state, target=None, edit=False):
    """The target (if any) is open behind whatever the state puts in front."""
    if state in ("closed", "launching"):
        quit_app()
        if state == "launching": sh("open -b com.apple.TextEdit")
        return
    tidy()
    if state == "no_window":
        if not running(): sh("open -b com.apple.TextEdit"); wait(running, 10); time.sleep(1); tidy()
        return
    if target:
        open_doc(target)
        if edit: type_at_end(win_of(target), "zqk")
    if state in ("open", "selected", "hidden", "minimized", "other_app", "find_open") and not target: open_doc(BASE)
    if state in ("other_doc", "edited_other", "other_sheet"): open_doc(OTHER); raise_win(win_of(OTHER))
    forward()
    if state == "selected": menu("Edit", "Select All")
    elif state == "hidden": se("set visible to false", APP)
    elif state == "minimized": ax.AS.AXUIElementSetAttributeValue(docs()[0], ax.cf("AXMinimized"), ax.TRUE)
    elif state == "other_app": sh("open -a Calculator"); wait(lambda: se("return frontmost", APP) == "false", 8)
    elif state == "find_open": se('keystroke "f" using command down', APP); time.sleep(0.6); se('keystroke "zq"', APP)
    elif state == "edited_other": type_at_end(win_of(OTHER), "zqk")
    elif state == "other_sheet": menu("File", "Save As…"); wait(lambda: sheet(win_of(OTHER)), 5)
    elif state == "open_panel": menu("File", "Open…"); wait(lambda: any(ax.sattr(w, "AXSubrole") == "AXDialog" for w in wins()), 5)
    time.sleep(0.5)
def clean(state):
    for w in wins():
        if ax.sattr(w, "AXSubrole") == "AXDialog" and not is_doc(w): return False
        if sheet(w) and not (state == "other_sheet" and url_path(w) == nfc(OTHER)): return False
    return True
def front():
    try: return osa('tell application "System Events" to return name of first process whose frontmost is true')
    except RuntimeError: return ""  # nothing in front, as after quitting the only app
CLOSED_OUT = ("document_open", "document_read", "document_replace_text", "document_append")
def case(fn, mode, state, kind, setup, call, read, changes=lambda c: set(), target=None, after=None, before_call=None, big=False, edit=False):
    if ONLY_FNS and fn not in ONLY_FNS: return
    if state == "closed" and mode == "background" and fn in CLOSED_OUT:
        # Left out: these refuse, because TextEdit came to the front when started this way.
        kind += "_refused"; changes = lambda c: set(); after = None
        read = lambda c, b, a, r, e: {"raised_NotSupported": isinstance(e, T.NotSupported), "not_started": not running(), "files_same": a == b}
    COUNT["n"] += 1
    if COUNT["n"] <= RESUME or FAILS.get((fn, mode), 0) >= 3: return
    print(f"CASE {COUNT['n']} {fn} {mode} {state} {kind}", flush=True)
    try:
        ctx = setup() or {}
        for v in ctx.values():
            if isinstance(v, str) and v.startswith("/"): inside(v)
        t = ctx.get("p") if target else None
        start(state, t, edit)
        if before_call: before_call(ctx)
        other_text = None
        if state == "edited_other": other_text = ax.sattr(next(e for e in ax.walk(win_of(OTHER)) if ax.sattr(e, "AXRole") == "AXTextArea"), "AXValue")
        want = bigclip.fill(V.rng.randint(1, 10**9)) if big else None
        small = None
        if not big:
            small = f"keep {V.word(1)}"; subprocess.run(["pbcopy"], input=small.encode())
        before = tree(); front0 = front(); began = time.monotonic()
        try: res, err = call(ctx), None
        except (T.TextEditError, ValueError) as e: res, err = None, e
        secs = round(time.monotonic() - began, 1)
        front1 = front()  # before the test's own save, which brings TextEdit forward
        if after and err is None: after(ctx)
        end = time.monotonic() + 8
        while True:
            now = tree(); checks = read(ctx, before, now, res, err)
            if all(checks.values()) or time.monotonic() > end: break
            time.sleep(0.4)
        allowed = changes(ctx) | ({nfc(OTHER)} if state in ("edited_other",) else set())
        others = [p for p in set(before) | set(now) if before.get(p) != now.get(p) and p not in {nfc(x) for x in allowed}]
        checks["others_unchanged"] = not others
        if want: checks.update(bigclip.check(want))
        else: checks["clipboard_kept"] = subprocess.run(["pbpaste"], capture_output=True).stdout.decode() == small
        if other_text is not None:
            w = win_of(OTHER); checks["other_edit_kept"] = bool(w) and ax.sattr(next(e for e in ax.walk(w) if ax.sattr(e, "AXRole") == "AXTextArea"), "AXValue") == other_text
        if state == "other_sheet":
            checks["other_dialog_kept"] = bool(win_of(OTHER)) and bool(sheet(win_of(OTHER)))
        if mode == "ui": checks["nothing_left_open"] = clean(state)
        elif state not in ("other_sheet", "open_panel"): checks["front_app_unchanged"] = front1 == front0 and (after is not None or front() == front0)
        REC.case(fn, mode, state, kind, checks, repr(err)[:160] if err else None, secs)
        if not all(checks.values()): FAILS[(fn, mode)] = FAILS.get((fn, mode), 0) + 1
    except Outside: raise
    except Exception:
        REC.case(fn, mode, state, kind, {"harness": False}, traceback.format_exc()[-300:]); FAILS[(fn, mode)] = FAILS.get((fn, mode), 0) + 1
def stem(i): return nfc((V.special() if i % 2 else V.word()).replace("/", "-"))
def words(i): return (V.special() if i % 2 else V.word()) + "\nsecond line é ✨\n" + V.word(1) + ' "quoted" -- end'
def fresh(i, suffix=".txt", text=None): return write(f"{DATA}/new/{stem(i)}{suffix}", text if text is not None else f"start {V.word()}\n")
def save_now(c):
    """A plain Cmd-S, not the library, so the text reaches the file to be read."""
    w = win_of(c["p"]); raise_win(w); se('keystroke "s" using command down', APP); time.sleep(0.5)
def script_save(c):
    w = win_of(c["p"]); raise_win(w); se('keystroke "s" using command down', APP); time.sleep(0.5)
NOT_OPEN_OK = ("closed", "launching", "no_window")
def run_state(state, i):
    for mode in os.environ.get("MODES", "background,ui").split(","):
        tt = words(i); rt = words(i + 1)
        case("document_create", mode, state, "txt", lambda: {"p": f"{DATA}/new/{stem(i)}.txt"}, lambda c: T.document_create(path=c["p"], text=tt, mode=mode),
             lambda c, b, a, r, e: {"no_error": e is None, "file": body_is(c["p"], tt), "only_it": set(a) - set(b) == {nfc(c["p"])}, "return": bool(r) and r["path"] == c["p"]}, lambda c: {c["p"]})
        case("document_create", mode, state, "rtf", lambda: {"p": f"{DATA}/new/{stem(i)}.rtf"}, lambda c: T.document_create(path=c["p"], text=rt, mode=mode),
             lambda c, b, a, r, e: {"no_error": e is None, "file": body_is(c["p"], rt), "is_rtf": os.path.exists(c["p"]) and open(c["p"], "rb").read(5) == b"{\\rtf", "only_it": set(a) - set(b) == {nfc(c["p"])}}, lambda c: {c["p"]})
        case("document_create", mode, state, "empty", lambda: {"p": f"{DATA}/new/{stem(i)}.txt"}, lambda c: T.document_create(path=c["p"], mode=mode),
             lambda c, b, a, r, e: {"no_error": e is None, "empty_file": os.path.exists(c["p"]) and os.path.getsize(c["p"]) == 0}, lambda c: {c["p"]})
        case("document_open", mode, state, "txt", lambda: {"p": fresh(i)}, lambda c: T.document_open(path=c["p"], mode=mode),
             lambda c, b, a, r, e: {"no_error": e is None, "window": bool(win_of(c["p"])), "same_file": a[nfc(c["p"])] == b[nfc(c["p"])], "return": bool(r) and r["path"] == c["p"]})
        case("document_open", mode, state, "rtf", lambda: {"p": fresh(i, ".rtf")}, lambda c: T.document_open(path=c["p"], mode=mode),
             lambda c, b, a, r, e: {"no_error": e is None, "window": bool(win_of(c["p"]))})
        if state not in NOT_OPEN_OK:
            case("document_open", mode, state, "already_open", lambda: {"p": fresh(i)}, lambda c: T.document_open(path=c["p"], mode=mode),
                 lambda c, b, a, r, e: {"no_error": e is None, "one_window": len([w for w in docs() if url_path(w) == nfc(c["p"])]) == 1}, target=True)
        body = words(i); body2 = words(i + 1)
        case("document_read", mode, state, "txt", lambda: {"p": fresh(i, text=body)}, lambda c: T.document_read(path=c["p"], mode=mode),
             lambda c, b, a, r, e: {"no_error": e is None, "text_is_file": bool(r) and nfc(r["text"]) == nfc(read_file(c["p"])), "file_same": a[nfc(c["p"])] == b[nfc(c["p"])]})
        case("document_read", mode, state, "rtf", lambda: {"p": fresh(i, ".rtf", body2)}, lambda c: T.document_read(path=c["p"], mode=mode),
             lambda c, b, a, r, e: {"no_error": e is None, "text_is_file": bool(r) and nfc(r["text"]).rstrip("\n") == nfc(read_file(c["p"])).rstrip("\n")})
        new1, new2, new3, add1, add2 = words(i), words(i + 1), V.word(), words(i), words(i + 1)
        for suffix, new, kind in ((".txt", new1, "txt"), (".rtf", new2, "rtf")):
            for opened in ((True, False) if state not in NOT_OPEN_OK else (False,)):
                case("document_replace_text", mode, state, kind + ("_open" if opened else "_not_open"), lambda: {"p": fresh(i, suffix)}, lambda c, new=new: T.document_replace_text(path=c["p"], text=new, mode=mode),
                     lambda c, b, a, r, e, new=new: {"no_error": e is None, "file": body_is(c["p"], new), "return": bool(r) and r["text"] == new}, lambda c: {c["p"]}, target=opened, after=save_now)
        case("document_replace_text", mode, state, "empty", lambda: {"p": fresh(i)}, lambda c: T.document_replace_text(path=c["p"], text="", mode=mode),
             lambda c, b, a, r, e: {"no_error": e is None, "empty_file": body_is(c["p"], "")}, lambda c: {c["p"]}, after=save_now)
        old1 = f"start {V.word()}\n"; old2 = f"start {V.word()}\n"
        case("document_append", mode, state, "txt", lambda: {"p": fresh(i, text=old1)}, lambda c: T.document_append(path=c["p"], text=add1, mode=mode),
             lambda c, b, a, r, e: {"no_error": e is None, "file": body_is(c["p"], old1 + add1), "return": bool(r) and r["text"] == old1 + add1}, lambda c: {c["p"]}, after=save_now)
        case("document_append", mode, state, "rtf", lambda: {"p": fresh(i, ".rtf", old2)}, lambda c: T.document_append(path=c["p"], text=add2, mode=mode),
             lambda c, b, a, r, e: {"no_error": e is None, "file": body_is(c["p"], old2 + add2)}, lambda c: {c["p"]}, after=save_now)
        if state in NOT_OPEN_OK: continue
        o3 = f"start {V.word()}\n"
        edit = lambda c: type_at_end(win_of(c["p"]), "zqk")
        # In the plain open state nothing has made TextEdit write yet, so the save is what writes the file.
        for suffix, kind in ((".txt", "edited_txt"), (".rtf", "edited_rtf")):
            def setup_edit(suffix=suffix):
                return {"p": fresh(i, suffix, o3)}
            case("document_save", mode, state, kind, setup_edit, lambda c: T.document_save(path=c["p"], mode=mode),
                 lambda c, b, a, r, e: {"no_error": e is None, "file": body_is(c["p"], o3 + "zqk"), "return": bool(r) and r["saved"]}, lambda c: {c["p"]}, target=True, edit=True)
        case("document_save", mode, state, "no_change", lambda: {"p": fresh(i)}, lambda c: T.document_save(path=c["p"], mode=mode),
             lambda c, b, a, r, e: {"no_error": e is None, "file_same": a[nfc(c["p"])] == b[nfc(c["p"])]}, lambda c: {c["p"]}, target=True)
        for suffix, kind in ((".txt", "txt"), (".rtf", "rtf")):
            case("document_save_as", mode, state, kind, lambda suffix=suffix: {"p": fresh(i, suffix, o3), "to": f"{DATA}/new/{stem(i)}{suffix}"}, lambda c: T.document_save_as(path=c["p"], to=c["to"], mode=mode),
                 lambda c, b, a, r, e: {"no_error": e is None, "new_file": body_is(c["to"], o3), "old_same": a.get(nfc(c["p"])) == b.get(nfc(c["p"])), "window_moved": bool(win_of(c["to"])) and not win_of(c["p"]), "return": bool(r) and r["path"] == c["to"] and r["from"] == c["p"]}, lambda c: {c["to"]}, target=True)
        def setup_as():
            return {"p": fresh(i, ".txt", o3), "to": f"{DATA}/new/{stem(i)}.txt"}
        case("document_save_as", mode, state, "edited", setup_as, lambda c: T.document_save_as(path=c["p"], to=c["to"], mode=mode),
             lambda c, b, a, r, e: {"no_error": e is None, "new_has_edit": body_is(c["to"], o3 + "zqk"), "old_has_edit": body_is(c["p"], o3 + "zqk")}, lambda c: {c["to"], c["p"]}, target=True, edit=True)
        case("document_close", mode, state, "normal", lambda: {"p": fresh(i)}, lambda c: T.document_close(path=c["p"], mode=mode),
             lambda c, b, a, r, e: {"no_error": e is None, "window_gone": not win_of(c["p"]), "file_same": a[nfc(c["p"])] == b[nfc(c["p"])], "return": bool(r) and r["closed"]}, lambda c: {c["p"]}, target=True)
        def setup_close():
            return {"p": fresh(i, ".txt", o3)}
        case("document_close", mode, state, "edited", setup_close, lambda c: T.document_close(path=c["p"], mode=mode),
             lambda c, b, a, r, e: {"no_error": e is None, "window_gone": not win_of(c["p"]), "file_kept_edit": body_is(c["p"], o3 + "zqk")}, lambda c: {c["p"]}, target=True, edit=True)
    for mode in os.environ.get("MODES", "background,ui").split(","):
        def listed(c, b, a, r, e):
            want = sorted(nfc(url_path(w)) for w in docs() if url_path(w)) if running() else []
            return {"no_error": e is None, "paths_match": r is not None and sorted(nfc(x["path"]) for x in r if x["path"]) == want, "target_listed": state in NOT_OPEN_OK or (r is not None and nfc(c["p"]) in [nfc(x["path"]) for x in r if x["path"]])}
        case("document_list", mode, state, "normal", lambda: {"p": fresh(i)}, lambda c: T.document_list(mode=mode), listed, target=state not in NOT_OPEN_OK)
def errors():
    st = "other_doc"; N = f"{DATA}/new"
    base_txt = lambda: write(f"{N}/exists.txt", "exists\n")
    base_txt()
    for mode in ("background", "ui"):
        nope = f"{N}/nope.txt"
        for fn, call in [("document_open", lambda c: T.document_open(path=nope, mode=mode)), ("document_read", lambda c: T.document_read(path=nope, mode=mode)), ("document_replace_text", lambda c: T.document_replace_text(path=nope, text="x", mode=mode)), ("document_append", lambda c: T.document_append(path=nope, text="x", mode=mode))]:
            case(fn, mode, st, "not_found", lambda: {}, call, lambda c, b, a, r, e: {"raised_NotFound": isinstance(e, T.NotFound), "not_made": not os.path.exists(nope)})
        for fn, call in [("document_save", lambda c: T.document_save(path=FAR, mode=mode)), ("document_save_as", lambda c: T.document_save_as(path=FAR, to=f"{N}/never.rtf", mode=mode)), ("document_close", lambda c: T.document_close(path=FAR, mode=mode))]:
            case(fn, mode, st, "not_open", lambda: {}, call, lambda c, b, a, r, e: {"raised_NotFound": isinstance(e, T.NotFound)})
        case("document_create", mode, st, "already_exists", lambda: {}, lambda c: T.document_create(path=f"{N}/exists.txt", text="no", mode=mode), lambda c, b, a, r, e: {"raised": isinstance(e, T.AlreadyExists), "kept": body_is(f"{N}/exists.txt", "exists\n")})
        case("document_create", mode, st, "no_folder", lambda: {}, lambda c: T.document_create(path=f"{N}/no folder/x.txt", mode=mode), lambda c, b, a, r, e: {"raised": isinstance(e, T.NotFound)})
        case("document_create", mode, st, "bad_type", lambda: {}, lambda c: T.document_create(path=f"{N}/x.doc", mode=mode), lambda c, b, a, r, e: {"raised": isinstance(e, ValueError), "not_made": not os.path.exists(f"{N}/x.doc")})
        case("document_save_as", mode, st, "already_exists", lambda: {"p": BASE}, lambda c: T.document_save_as(path=BASE, to=f"{N}/exists.txt", mode=mode), lambda c, b, a, r, e: {"raised": isinstance(e, T.AlreadyExists), "kept": body_is(f"{N}/exists.txt", "exists\n")}, target=True)
        case("document_save_as", mode, st, "other_type", lambda: {"p": BASE}, lambda c: T.document_save_as(path=BASE, to=f"{N}/x.rtf", mode=mode), lambda c, b, a, r, e: {"raised": isinstance(e, ValueError)}, target=True)
        case("document_append", mode, st, "empty_text", lambda: {}, lambda c: T.document_append(path=BASE, text="", mode=mode), lambda c, b, a, r, e: {"raised": isinstance(e, ValueError)})
    case("document_list", "ui", st, "bad_mode", lambda: {}, lambda c: T.document_list(mode="sideways"), lambda c, b, a, r, e: {"raised": isinstance(e, ValueError)})
def guard():
    link = f"{DATA}/new/out-link.txt"; os.symlink("/tmp/outside-target.txt", link)
    bad = [f"{ROOT}/../outside-target.txt", "/tmp/outside-target.txt", "~/outside-target.txt", link]
    for mode in ("background", "ui"):
        for i, p in enumerate(bad):
            for fn, call in [("document_create", lambda c, p=p: T.document_create(path=p, mode=mode)), ("document_open", lambda c, p=p: T.document_open(path=p, mode=mode)), ("document_read", lambda c, p=p: T.document_read(path=p, mode=mode)), ("document_replace_text", lambda c, p=p: T.document_replace_text(path=p, text="x", mode=mode)), ("document_append", lambda c, p=p: T.document_append(path=p, text="x", mode=mode)), ("document_save", lambda c, p=p: T.document_save(path=p, mode=mode)), ("document_close", lambda c, p=p: T.document_close(path=p, mode=mode)), ("document_save_as", lambda c, p=p: T.document_save_as(path=BASE, to=p, mode=mode))]:
                case(fn, mode, "other_doc", f"guard_{i}", lambda: {}, call, lambda c, b, a, r, e: {"raised_Outside": isinstance(e, T.OutsideAllowedRoot), "nothing_outside": not os.path.exists("/tmp/outside-target.txt")})
    os.unlink(link)
def blocked():
    """A Save As dialog with a typed name on the document: the UI commands leave it alone."""
    tidy(); p = fresh(1); open_doc(p); w = win_of(p); raise_win(w); menu("File", "Save As…"); s = wait(lambda: sheet(w), 5); time.sleep(0.4); se('keystroke "half typed"', APP); time.sleep(0.5)
    before = tree(); name = lambda: next((ax.sattr(e, "AXValue") for e in ax.walk(sheet(w)) if ax.sattr(e, "AXIdentifier") == "saveAsNameTextField"), None) if sheet(w) else None
    typed = name()
    for fn, call in [("document_open", lambda: T.document_open(path=p, mode="ui")), ("document_replace_text", lambda: T.document_replace_text(path=p, text="never", mode="ui")), ("document_append", lambda: T.document_append(path=p, text="never", mode="ui")), ("document_save", lambda: T.document_save(path=p, mode="ui")), ("document_save_as", lambda: T.document_save_as(path=p, to=f"{DATA}/new/never.txt", mode="ui")), ("document_close", lambda: T.document_close(path=p, mode="ui"))]:
        if ONLY_FNS and fn not in ONLY_FNS: continue
        try: call(); err = None
        except Exception as e: err = e
        REC.case(fn, "ui", "typed_text", "blocked", {"raised_StateBlocked": isinstance(err, T.StateBlocked), "typed_kept": name() == typed and "half typed" in (typed or ""), "nothing_changed": tree() == before}, repr(err)[:120])
    r = T.document_read(path=p, mode="ui"); REC.case("document_read", "ui", "typed_text", "works_and_leaves_it", {"text_is_file": nfc(r["text"]) == nfc(read_file(p)), "typed_kept": name() == typed}, None)
    tidy()
def copying():
    for mode in ("ui", "background"):
        for state in ("open", "other_doc", "hidden", "minimized", "other_app", "find_open", "edited_other"):
            t = words(1)
            case("document_copy_to_new", mode, state, "txt", lambda: {"p": fresh(1, text=t), "to": f"{DATA}/new/{stem(0)}.txt"}, lambda c: T.document_copy_to_new(path=c["p"], to=c["to"], mode=mode),
                 lambda c, b, a, r, e: {"no_error": e is None, "new_file": body_is(c["to"], t), "old_same": a.get(nfc(c["p"])) == b.get(nfc(c["p"])), "return": bool(r) and r["path"] == c["to"]}, lambda c: {c["to"]})
            t2 = words(0)
            case("document_copy_to_new", mode, state, "rtf", lambda: {"p": fresh(0, ".rtf", t2), "to": f"{DATA}/new/{stem(0)}.rtf"}, lambda c: T.document_copy_to_new(path=c["p"], to=c["to"], mode=mode),
                 lambda c, b, a, r, e: {"no_error": e is None, "new_file": body_is(c["to"], t2)}, lambda c: {c["to"]})
        t3 = words(0)
        case("document_copy_to_new", mode, "other_doc", "large_clipboard", lambda: {"p": fresh(0, text=t3), "to": f"{DATA}/new/{stem(0)}.txt"}, lambda c: T.document_copy_to_new(path=c["p"], to=c["to"], mode=mode), lambda c, b, a, r, e: {"no_error": e is None, "new_file": body_is(c["to"], t3)}, lambda c: {c["to"]}, big=True)
        case("document_copy_to_new", mode, "other_doc", "empty", lambda: {"p": fresh(2, text=""), "to": f"{DATA}/new/{stem(2)}-copy.txt"}, lambda c: T.document_copy_to_new(path=c["p"], to=c["to"], mode=mode), lambda c, b, a, r, e: {"raised": isinstance(e, ValueError), "not_made": not os.path.exists(c["to"])})
        case("document_copy_to_new", mode, "other_doc", "not_found", lambda: {}, lambda c: T.document_copy_to_new(path=f"{DATA}/new/nope.txt", to=f"{DATA}/new/n.txt", mode=mode), lambda c, b, a, r, e: {"raised": isinstance(e, T.NotFound)})
        case("document_copy_to_new", mode, "other_doc", "already_exists", lambda: {}, lambda c: T.document_copy_to_new(path=BASE, to=OTHER, mode=mode), lambda c, b, a, r, e: {"raised": isinstance(e, T.AlreadyExists), "kept": a[nfc(OTHER)] == b[nfc(OTHER)]})
        case("document_copy_to_new", mode, "other_doc", "guard", lambda: {}, lambda c: T.document_copy_to_new(path=BASE, to="/tmp/outside-target.txt", mode=mode), lambda c, b, a, r, e: {"raised": isinstance(e, T.OutsideAllowedRoot), "nothing_outside": not os.path.exists("/tmp/outside-target.txt")})
PDF_TEXT = r"""ObjC.import("Quartz"); function run(argv) { const d = $.PDFDocument.alloc.initWithURL($.NSURL.fileURLWithPath(argv[0])); return d.isNil() ? "" : ObjC.unwrap(d.string); }"""
def pdf_text(p):
    try: return nfc(osa(PDF_TEXT, p, lang="JavaScript"))
    except RuntimeError: return ""
def exporting():
    os.makedirs(f"{DATA}/pdf", exist_ok=True)
    for state in ("open", "other_doc", "hidden", "minimized", "other_app", "find_open", "closed"):
        w1, w2 = V.word(), V.word()
        for suffix in (".txt", ".rtf"):
            case("document_export_pdf", "ui", state, suffix[1:], lambda suffix=suffix: {"p": fresh(1, suffix, f"{w1}\nsecond {w2}\n"), "to": f"{DATA}/pdf/{stem(0)}.pdf"},
                 lambda c: T.document_export_pdf(path=c["p"], to=c["to"]),
                 lambda c, b, a, r, e: {"no_error": e is None, "pdf_has_text": w1 in pdf_text(c["to"]) and f"second {w2}" in pdf_text(c["to"]), "doc_file_same": a.get(nfc(c["p"])) == b.get(nfc(c["p"])), "return": bool(r) and r["path"] == c["to"]},
                 lambda c: {c["to"]})
    case("document_export_pdf", "ui", "other_doc", "exists", lambda: (write(f"{DATA}/pdf/taken.pdf", "keep"), {})[1], lambda c: T.document_export_pdf(path=BASE, to=f"{DATA}/pdf/taken.pdf"), lambda c, b, a, r, e: {"raised": isinstance(e, T.AlreadyExists), "kept": read_file(f"{DATA}/pdf/taken.pdf") == "keep"})
    case("document_export_pdf", "ui", "other_doc", "not_pdf", lambda: {}, lambda c: T.document_export_pdf(path=BASE, to=f"{DATA}/pdf/x.txt"), lambda c, b, a, r, e: {"raised": isinstance(e, ValueError)})
    case("document_export_pdf", "ui", "other_doc", "guard", lambda: {}, lambda c: T.document_export_pdf(path=BASE, to="/tmp/outside-target.pdf"), lambda c, b, a, r, e: {"raised": isinstance(e, T.OutsideAllowedRoot), "nothing_outside": not os.path.exists("/tmp/outside-target.pdf")})
    case("document_export_pdf", "background", "other_doc", "not_supported", lambda: {}, lambda c: T.document_export_pdf(path=BASE, to=f"{DATA}/pdf/bg.pdf", mode="background"), lambda c, b, a, r, e: {"raised": isinstance(e, T.NotSupported)})
    t3 = V.word()
    case("document_export_pdf", "ui", "other_doc", "large_clipboard", lambda: {"p": fresh(0, text=t3 + "\n"), "to": f"{DATA}/pdf/big-{stem(1)}.pdf"}, lambda c: T.document_export_pdf(path=c["p"], to=c["to"]), lambda c, b, a, r, e: {"no_error": e is None, "pdf_has_text": t3 in pdf_text(c["to"])}, lambda c: {c["to"]}, big=True)
def rich(p, text):
    """A styled .rtf (bold and italic words) made by textutil from HTML, whose plain text is text."""
    inside(p); os.makedirs(os.path.dirname(p), exist_ok=True)
    import html as _h
    lines = text.split("\n"); body = "".join(f"<p><b>{_h.escape(l.split(' ')[0])}</b> <i>{_h.escape(' '.join(l.split(' ')[1:]))}</i></p>" if l else "" for l in lines)
    t = p + ".tmp.html"; open(t, "w", encoding="utf-8").write('<meta charset="utf-8">' + body)
    subprocess.run(["textutil", "-inputencoding", "UTF-8", "-convert", "rtf", "-output", p, t], check=True); os.unlink(t)
    return read_file(p)
def converting():
    os.makedirs(f"{DATA}/conv", exist_ok=True)
    for state in ("closed", "open", "other_doc", "hidden", "minimized", "other_app", "find_open", "edited_other"):
        def r2t():
            p = f"{DATA}/conv/{stem(1)} {V.rng.randint(10, 99999)}.rtf"; plain = rich(p, f"{V.word()} two\nsecond {V.special()}")
            return {"p": p, "to": f"{DATA}/conv/{stem(0)} {V.rng.randint(10, 99999)}.txt", "plain": plain}
        case("document_convert", "ui", state, "rtf_to_txt", r2t, lambda c: T.document_convert(path=c["p"], to=c["to"]),
             lambda c, b, a, r, e: {"no_error": e is None, "plain_file": os.path.isfile(c["to"]) and nfc(open(c["to"], encoding="utf-8").read()).rstrip("\n") == nfc(c["plain"]).rstrip("\n"),
                                    "no_rtf_left": os.path.isfile(c["to"]) and not open(c["to"], encoding="utf-8").read().startswith("{\\rtf"), "return": bool(r) and r["path"] == c["to"] and r["from"] == c["p"]}, lambda c: {c["to"]})
        def t2r():
            t = f"{V.word()}\nline é ✨ \"{V.word(1)}\""; p = write(f"{DATA}/conv/{stem(0)} {V.rng.randint(10, 99999)}.txt", t)
            return {"p": p, "to": f"{DATA}/conv/{stem(1)} {V.rng.randint(10, 99999)}.rtf", "plain": t}
        case("document_convert", "ui", state, "txt_to_rtf", t2r, lambda c: T.document_convert(path=c["p"], to=c["to"]),
             lambda c, b, a, r, e: {"no_error": e is None, "rtf_file": os.path.isfile(c["to"]) and open(c["to"], encoding="utf-8", errors="replace").read().startswith("{\\rtf") and body_is(c["to"], c["plain"]),
                                    "return": bool(r) and r["path"] == c["to"]}, lambda c: {c["to"]})
    case("document_convert", "ui", "other_doc", "same_type", lambda: {"p": fresh(1)}, lambda c: T.document_convert(path=c["p"], to=f"{DATA}/conv/x.txt"), lambda c, b, a, r, e: {"raised": isinstance(e, ValueError)})
    case("document_convert", "ui", "other_doc", "exists", lambda: {"p": fresh(1), "to": write(f"{DATA}/conv/taken {V.word(1)}.rtf", "keep")}, lambda c: T.document_convert(path=c["p"], to=c["to"]),
         lambda c, b, a, r, e: {"raised": isinstance(e, T.AlreadyExists), "kept": a.get(nfc(c["to"])) == b.get(nfc(c["to"]))})
    case("document_convert", "ui", "other_doc", "not_found", lambda: {}, lambda c: T.document_convert(path=f"{DATA}/conv/nope.rtf", to=f"{DATA}/conv/n.txt"), lambda c, b, a, r, e: {"raised": isinstance(e, T.NotFound)})
    case("document_convert", "ui", "other_doc", "guard", lambda: {"p": fresh(1)}, lambda c: T.document_convert(path=c["p"], to="/tmp/outside-conv.rtf"), lambda c, b, a, r, e: {"raised": isinstance(e, T.OutsideAllowedRoot), "nothing_outside": not os.path.exists("/tmp/outside-conv.rtf")})
    case("document_convert", "background", "other_doc", "not_supported", lambda: {"p": fresh(1)}, lambda c: T.document_convert(path=c["p"], to=f"{DATA}/conv/bg.rtf", mode="background"), lambda c, b, a, r, e: {"raised": isinstance(e, T.NotSupported)})
    def big():
        p = f"{DATA}/conv/{stem(1)} big.rtf"; plain = rich(p, f"{V.word()} big\nmore {V.word(1)}"); return {"p": p, "to": f"{DATA}/conv/{stem(0)} big.txt", "plain": plain}
    case("document_convert", "ui", "other_doc", "large_clipboard", big, lambda c: T.document_convert(path=c["p"], to=c["to"]),
         lambda c, b, a, r, e: {"no_error": e is None, "plain_file": os.path.isfile(c["to"]) and nfc(open(c["to"], encoding="utf-8").read()).rstrip("\n") == nfc(c["plain"]).rstrip("\n")}, lambda c: {c["to"]}, big=True)
def large_clipboard():
    N = f"{DATA}/new"; st = "other_doc"; text, r1, a1 = words(1), words(0), words(1)
    for mode in ("ui", "background"):
        case("document_create", mode, st, "large_clipboard", lambda: {"p": f"{N}/{stem(1)}.txt"}, lambda c: T.document_create(path=c["p"], text=text, mode=mode), lambda c, b, a, r, e: {"no_error": e is None, "file": body_is(c["p"], text)}, lambda c: {c["p"]}, big=True)
        case("document_open", mode, st, "large_clipboard", lambda: {"p": fresh(0)}, lambda c: T.document_open(path=c["p"], mode=mode), lambda c, b, a, r, e: {"no_error": e is None, "window": bool(win_of(c["p"]))}, big=True)
        case("document_replace_text", mode, st, "large_clipboard", lambda: {"p": fresh(0)}, lambda c: T.document_replace_text(path=c["p"], text=r1, mode=mode), lambda c, b, a, r, e: {"no_error": e is None, "file": body_is(c["p"], r1)}, lambda c: {c["p"]}, after=save_now, big=True)
        old = f"start {V.word()}\n"
        case("document_append", mode, st, "large_clipboard", lambda old=old: {"p": fresh(0, text=old)}, lambda c: T.document_append(path=c["p"], text=a1, mode=mode), lambda c, b, a, r, e, old=old: {"no_error": e is None, "file": body_is(c["p"], old + a1)}, lambda c: {c["p"]}, after=save_now, big=True)
        case("document_save", mode, st, "large_clipboard", lambda: {"p": fresh(0)}, lambda c: T.document_save(path=c["p"], mode=mode), lambda c, b, a, r, e: {"no_error": e is None}, lambda c: {c["p"]}, target=True, big=True)
        old2 = f"start {V.word()}\n"
        case("document_save_as", mode, st, "large_clipboard", lambda old2=old2: {"p": fresh(0, text=old2), "to": f"{N}/{stem(0)}.txt"}, lambda c: T.document_save_as(path=c["p"], to=c["to"], mode=mode), lambda c, b, a, r, e, old2=old2: {"no_error": e is None, "new_file": body_is(c["to"], old2)}, lambda c: {c["to"]}, target=True, big=True)
        case("document_close", mode, st, "large_clipboard", lambda: {"p": fresh(0)}, lambda c: T.document_close(path=c["p"], mode=mode), lambda c, b, a, r, e: {"no_error": e is None, "window_gone": not win_of(c["p"])}, lambda c: {c["p"]}, target=True, big=True)
STATES = ["closed", "launching", "no_window", "open", "selected", "other_doc", "edited_other", "other_sheet", "open_panel", "hidden", "minimized", "other_app", "find_open"]
try:
    try:
        check_outside("start"); base()
        for i, state in enumerate(STATES):
            if state in ONLY:
                print(f"== state starts: {state} at {time.strftime('%H:%M:%S')}", flush=True); run_state(state, i); check_outside(state)
        for label, fn in (("errors", errors), ("guard", guard), ("blocked", blocked), ("large_clipboard", large_clipboard), ("copying", copying), ("exporting", exporting), ("converting", converting)):
            if label in ONLY:
                print(f"== state starts: {label} at {time.strftime('%H:%M:%S')}", flush=True); fn(); check_outside(label)
        tidy()
    except Outside as o:
        REC.data["meta"]["outside"] = str(o); print("OUTSIDE", o, flush=True)
finally:
    REC.data["meta"]["finished"] = time.strftime("%Y-%m-%d %H:%M:%S"); REC.save(); print("DONE", flush=True)
