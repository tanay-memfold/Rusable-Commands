"""Verify safari.py inside the VM: python3 verify_safari.py <group> <seed> <state|errors|blocked> ...
Safari only ever loads this script's own local server, and SAFARI_ALLOWED_PREFIXES makes the library refuse anything else. A page's
result is read from the server's request log, which is separate from Safari; titles and tabs are read from Safari's window with
separate code, so those aren't independent of Safari."""
import unicodedata, ctypes, http.server, json, os, socketserver, sqlite3, subprocess, sys, threading, time, traceback, urllib.parse
HOME = os.path.expanduser("~"); TOOLS = f"{HOME}/browser-test"; sys.path[:0] = [TOOLS]
PORT = 8731; BASE = f"http://127.0.0.1:{PORT}"
os.environ["SAFARI_ALLOWED_PREFIXES"] = BASE + "/"
import ax, bigclip, safari as S
from vcommon import Recorder, Values, osa, se, sh, wait
GROUP, SEED, ONLY = sys.argv[1], int(sys.argv[2]), sys.argv[3:]
V = Values(SEED); APP = "Safari"; FAILS = {}
REC = Recorder(GROUP, {"versions": S._versions(), "seed": SEED, "started": time.strftime("%Y-%m-%d %H:%M:%S")})
RESUME = int(os.environ.get("RESUME", "0")); ONLY_FNS = set(filter(None, os.environ.get("FNS", "").split(",")))
COUNT = {"n": 0}; open(f"{TOOLS}/verifier.pid", "w").write(str(os.getpid()))
LOG = []
SPECIAL = 'Café "crème" ✨ Zoë'
class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        LOG.append(self.path); t = urllib.parse.unquote(self.path.strip("/").split("/")[-1])
        extra = ""
        if self.path.startswith("/form"): extra = "<form><input id='f' name='f' type='text' aria-label='Typed box' autofocus></form>"
        if self.path.startswith("/twins"): extra = "<a href='/p/one1'>Same name</a> <a href='/p/two2'>Same name</a>"
        body = (f"<!doctype html><html><head><meta charset='utf-8'><title>Test {t}</title></head><body><h1>Heading {t}</h1><p>Body {SPECIAL} {t}</p>"
                f"<a href='/p/next-{t}'>Next {t}</a> <a href='http://outside.invalid/x'>Outside link</a>{extra}</body></html>").encode()
        self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.send_header("Cache-Control", "no-store"); self.end_headers(); self.wfile.write(body)
socketserver.TCPServer.allow_reuse_address = True
SERVER = socketserver.ThreadingTCPServer(("127.0.0.1", PORT), H); threading.Thread(target=SERVER.serve_forever, daemon=True).start()
def url(t): return f"{BASE}/p/{urllib.parse.quote(t)}"
def tok(): return f"t{V.rng.randint(100000, 999999)}"
def running(): return bool(sh(f"pgrep -x {APP}"))
def A(): return ax.app(APP)
def wins(): return [c for c in ax.children(A()) if ax.sattr(c, "AXRole") == "AXWindow"]
def win(): return ax.attr(A(), "AXMainWindow") or ax.attr(A(), "AXFocusedWindow") or (wins() or [None])[0]
def title(): return ax.sattr(win(), "AXTitle") if running() and win() else ""
def tabs():
    if not running() or not win(): return []
    g = next((e for e in ax.children(win()) if ax.sattr(e, "AXRole") == "AXGroup" and ax.sattr(e, "AXTitle") == "tab bar"), None)
    return [ax.sattr(t, "AXTitle") for t in ax.children(g) if ax.sattr(t, "AXSubrole") == "AXTabButton"] if g else [title()]
def menu(m, i): return se(f'click menu item "{i}" of menu "{m}" of menu bar item "{m}" of menu bar 1', APP)
def quit_app():
    if running():
        try: menu("Safari", "Quit Safari")
        except RuntimeError: pass
        wait(lambda: not running(), 15)
def open_page(t, path=None):
    n = len(LOG); sh(f"open -a Safari '{(BASE + path) if path else url(t)}'"); wait(lambda: len(LOG) > n, 12); time.sleep(0.8)
def front():
    sh("open -a Safari"); wait(running, 15); se("set visible to true\nset frontmost to true", APP); wait(wins, 8)
    for w in wins():
        if ax.attr(w, "AXMinimized") == ax.TRUE.value:
            ax.AS.AXUIElementSetAttributeValue(w, ax.cf("AXMinimized"), ctypes.c_void_p.in_dll(ax.CF, "kCFBooleanFalse")); time.sleep(0.5)
    if not wins(): menu("File", "New Window"); wait(wins, 6)
    for w in wins():
        for s in [e for e in ax.children(w) if ax.sattr(e, "AXRole") == "AXSheet"]:
            c = ax.find(s, "AXButton", "Cancel", exact=True)
            if c: ax.AS.AXUIElementPerformAction(c, ax.cf("AXPress")); time.sleep(0.5)
    f = ax.attr(A(), "AXFocusedUIElement")
    if f and ax.sattr(f, "AXRole") in ("AXTextField", "AXTextArea") and ax.sattr(f, "AXValue"): se("key code 53", APP); time.sleep(0.2); se("key code 53", APP); time.sleep(0.3)
def start(state):
    if state in ("closed", "launching"):
        quit_app()
        if state == "launching": sh("open -a Safari")
        return
    front()
    if state == "other_tab": menu("File", "New Tab"); time.sleep(0.4); se("key code 53", APP)
    elif state == "hidden": se("set visible to false", APP)
    elif state == "minimized": ax.AS.AXUIElementSetAttributeValue(win(), ax.cf("AXMinimized"), ax.TRUE)
    elif state == "other_app": sh("open -a Calculator"); wait(lambda: se("return frontmost", APP) == "false", 8)
    elif state == "no_window":
        menu("File", "Close Window") if se('exists menu item "Close Window" of menu "File" of menu bar item "File" of menu bar 1', APP) == "true" else menu("File", "Close All Windows"); wait(lambda: not wins(), 5)
    elif state == "two_windows": menu("File", "New Window"); time.sleep(0.6); se("key code 53", APP)
    elif state == "find_open": se('keystroke "f" using command down', APP); time.sleep(0.5)
    time.sleep(0.5)
def clean(): return not (running() and win() and any(ax.sattr(e, "AXRole") == "AXSheet" for e in ax.children(win())))
PDF = f"{TOOLS}/data/pdf"; os.makedirs(PDF, exist_ok=True)
PDF_TEXT = r"""ObjC.import("Quartz"); function run(argv) { const d = $.PDFDocument.alloc.initWithURL($.NSURL.fileURLWithPath(argv[0])); return d.isNil() ? "" : JSON.stringify({pages: d.pageCount, text: ObjC.unwrap(d.string)}); }"""
def pdf_text(p):
    try:
        out = osa(PDF_TEXT, p, lang="JavaScript"); d = json.loads(out) if out else None
        if d: d["text"] = unicodedata.normalize("NFC", d["text"] or "")
        return d
    except RuntimeError: return None
PDF_SPECIAL = ('Café "crème"', "Zoë")  # PDF text extraction doesn't give back the emoji glyph
def pdf_files(): return sorted(unicodedata.normalize("NFC", n) for n in os.listdir(PDF))
def case(fn, state, kind, setup, call, read, big=False):
    if ONLY_FNS and fn not in ONLY_FNS: return
    COUNT["n"] += 1
    if COUNT["n"] <= RESUME or FAILS.get(fn, 0) >= 3: return
    print(f"CASE {COUNT['n']} {fn} ui {state} {kind}", flush=True)
    try:
        ctx = setup() or {}
        start(state)
        want = bigclip.fill(V.rng.randint(1, 10**9)) if big else None
        small = None if big else f"keep {V.word(1)}"
        if small: subprocess.run(["pbcopy"], input=small.encode())
        n0 = len(LOG); tabs0 = tabs(); began = time.monotonic()
        try: res, err = call(ctx), None
        except (S.SafariError, ValueError) as e: res, err = None, e
        secs = round(time.monotonic() - began, 1); end = time.monotonic() + (20 if fn in ("page_add_to_reading_list", "page_add_bookmark") else 8)  # Safari writes its Reading List a little later
        while True:
            checks = read(ctx, res, err, LOG[n0:], tabs0, tabs())
            if all(checks.values()) or time.monotonic() > end: break
            time.sleep(0.4)
        checks["only_test_pages_requested"] = all(p.startswith(("/p/", "/q/", "/form", "/twins", "/favicon")) for p in LOG[n0:])
        checks["nothing_left_open"] = clean()
        if want: checks.update(bigclip.check(want))
        else: checks["clipboard_kept"] = subprocess.run(["pbpaste"], capture_output=True).stdout.decode(errors="replace") == small
        REC.case(fn, "ui", state, kind, checks, repr(err)[:160] if err else None, secs)
        if not all(checks.values()): FAILS[fn] = FAILS.get(fn, 0) + 1
    except Exception:
        REC.case(fn, "ui", state, kind, {"harness": False}, traceback.format_exc()[-300:]); FAILS[fn] = FAILS.get(fn, 0) + 1
def run_state(state):
    t = {k: tok() for k in "abcdefghijklmn"}
    def req(path): return lambda L: path in L
    case("tab_open", state, "normal", lambda: None, lambda c: S.tab_open(url=url(t["a"])),
         lambda c, r, e, L, t0, t1: {"no_error": e is None, "server_got_it": f"/p/{t['a']}" in L, "shown": f"Test {t['a']}" in t1, "one_more_tab": len(t1) == len(t0) + 1 or state in ("closed", "launching", "no_window"), "return": bool(r) and r["title"] == f"Test {t['a']}"})
    case("page_go", state, "normal", lambda: open_page(t["b"]), lambda c: S.page_go(url=url(t["c"])),
         lambda c, r, e, L, t0, t1: {"no_error": e is None, "server_got_it": f"/p/{t['c']}" in L, "return": bool(r) and r["title"] == f"Test {t['c']}" and r["url"].endswith(t["c"])})
    case("page_info", state, "normal", lambda: open_page(t["d"]), lambda c: S.page_info(),
         lambda c, r, e, L, t0, t1: {"no_error": e is None, "title": bool(r) and (r["title"] == f"Test {t['d']}" or state in ("closed", "launching", "no_window", "other_tab", "two_windows") and r["title"] != "")})
    case("page_text", state, "normal", lambda: open_page(t["e"]), lambda c: S.page_text() if state not in ("closed", "launching", "no_window", "other_tab", "two_windows") else S.tab_open(url=url(t["e"])) and S.page_text(),
         lambda c, r, e, L, t0, t1: {"no_error": e is None, "has_heading": bool(r) and f"Heading {t['e']}" in r["text"], "has_special": bool(r) and SPECIAL in r["text"]})
    case("page_links", state, "normal", lambda: open_page(t["f"]), lambda c: S.page_links() if state not in ("closed", "launching", "no_window", "other_tab", "two_windows") else S.tab_open(url=url(t["f"])) and S.page_links(),
         lambda c, r, e, L, t0, t1: {"no_error": e is None, "next_link": bool(r) and any(x["name"] == f"Next {t['f']}" and x["url"] == f"{BASE}/p/next-{t['f']}" for x in r), "outside_listed": bool(r) and any(x["url"].startswith("http://outside.invalid") for x in r)})
    def click(c):
        if state in ("closed", "launching", "no_window", "other_tab", "two_windows"): S.tab_open(url=url(t["g"]))
        return S.link_click(name=f"Next {t['g']}")
    case("link_click", state, "normal", lambda: open_page(t["g"]), click,
         lambda c, r, e, L, t0, t1: {"no_error": e is None, "server_got_it": f"/p/next-{t['g']}" in L, "return": bool(r) and r["title"] == f"Test next-{t['g']}"})
    def hist(c):
        if state in ("closed", "launching", "no_window", "other_tab", "two_windows"):
            S.tab_open(url=url(t["h"])); S.page_go(url=url(t["i"]))
        return S.page_back()
    def hist_setup():
        open_page(t["h"]); S.page_go(url=url(t["i"])); time.sleep(0.5)
    case("page_back", state, "normal", hist_setup, hist, lambda c, r, e, L, t0, t1: {"no_error": e is None, "server_got_it": f"/p/{t['h']}" in L, "return": bool(r) and r["title"] == f"Test {t['h']}"})
    def fwd(c):
        if state in ("closed", "launching", "no_window", "other_tab", "two_windows"):
            S.tab_open(url=url(t["j"])); S.page_go(url=url(t["k"])); S.page_back()
        return S.page_forward()
    def fwd_setup():
        open_page(t["j"]); S.page_go(url=url(t["k"])); S.page_back(); time.sleep(0.5)
    case("page_forward", state, "normal", fwd_setup, fwd, lambda c, r, e, L, t0, t1: {"no_error": e is None, "window_shows_it": title() == f"Test {t['k']}", "return": bool(r) and r["title"] == f"Test {t['k']}"})
    def rel(c):
        if state in ("closed", "launching", "no_window", "other_tab", "two_windows"): S.tab_open(url=url(t["l"]))
        n = LOG.count(f"/p/{t['l']}"); COUNT["before"] = n; return S.page_reload()
    case("page_reload", state, "normal", lambda: open_page(t["l"]), rel, lambda c, r, e, L, t0, t1: {"no_error": e is None, "server_got_again": LOG.count(f"/p/{t['l']}") > COUNT.get("before", 0), "return": bool(r) and r["title"] == f"Test {t['l']}"})
    case("tab_list", state, "normal", lambda: open_page(t["m"]), lambda c: S.tab_list(),
         lambda c, r, e, L, t0, t1: {"no_error": e is None, "matches_window": r is not None and [x["title"] for x in r] == t1, "one_active": r is not None and sum(x["active"] for x in r) >= 1})
    A1, A2 = f"Test {tok()}", f"Test {tok()}"
    def two():
        open_page(A1[5:]); open_page(A2[5:])
    def act(c):
        if state in ("closed", "launching", "no_window", "two_windows"):
            S.tab_open(url=url(A1[5:])); S.tab_open(url=url(A2[5:]))
        return S.tab_activate(match=A1)
    case("tab_activate", state, "normal", two, act, lambda c, r, e, L, t0, t1: {"no_error": e is None, "window_shows_it": title() == A1, "return": bool(r) and r["title"] == A1})
    C1, C2 = f"Test {tok()}", f"Test {tok()}"
    def two2():
        open_page(C1[5:]); open_page(C2[5:])
    def cl(c):
        if state in ("closed", "launching", "no_window", "two_windows"):
            S.tab_open(url=url(C1[5:])); S.tab_open(url=url(C2[5:]))
        return S.tab_close(match=C1)
    case("tab_close", state, "normal", two2, cl, lambda c, r, e, L, t0, t1: {"no_error": e is None, "gone": C1 not in tabs(), "other_stays": C2 in tabs(), "return": bool(r) and r["closed"]})
    tp = tok(); tq = tok()
    def pdf_setup(token, name):
        open_page(token); return {"p": f"{PDF}/{name}.pdf", "t": token, "files": pdf_files()}
    for kind, name in (("plain", tp), ("special_name", f"{SPECIAL} {tq}")):
        token = tp if kind == "plain" else tq
        case("page_save_pdf", state, kind, lambda token=token, name=name: pdf_setup(token, name) if state not in ("closed", "launching", "no_window", "other_tab", "two_windows") else {"p": f"{PDF}/{name}.pdf", "t": token, "files": pdf_files()},
             (lambda c: S.page_save_pdf(path=c["p"])) if state not in ("closed", "launching", "no_window", "other_tab", "two_windows") else (lambda c: S.tab_open(url=url(c["t"])) and S.page_save_pdf(path=c["p"])),
             lambda c, r, e, L, t0, t1: {"no_error": e is None, "pdf_has_page": bool(pdf_text(c["p"])) and f"Heading {c['t']}" in pdf_text(c["p"])["text"] and all(x in pdf_text(c["p"])["text"] for x in PDF_SPECIAL),
                                         "only_it": pdf_files() == sorted(c["files"] + [unicodedata.normalize("NFC", os.path.basename(c["p"]))]),
                                         "return": bool(r) and r["path"] == c["p"] and r["title"] == f"Test {c['t']}"})
def errors():
    st = "open"
    for kind, path, exc in (("exists", None, S.AlreadyExists), ("not_pdf", f"{PDF}/x.txt", ValueError), ("no_folder", f"{PDF}/none/x.pdf", S.NotFound), ("relative", "pdf/x.pdf", ValueError)):
        def pre(path=path):
            open_page(tok())
            if path is None:
                p = f"{PDF}/exists-{tok()}.pdf"; open(p, "wb").write(b"%PDF-1.4 kept"); return {"p": p, "files": pdf_files()}
            return {"p": path, "files": pdf_files()}
        case("page_save_pdf", st, kind, pre, lambda c: S.page_save_pdf(path=c["p"]),
             lambda c, r, e, L, t0, t1, exc=exc: {"raised": isinstance(e, exc), "no_new_file": pdf_files() == c["files"], "kept": not c["p"].startswith(PDF + "/exists") or open(c["p"], "rb").read() == b"%PDF-1.4 kept"})
    def outside(c):
        os.environ["SAFARI_ALLOWED_ROOT"] = f"{TOOLS}/data/elsewhere"
        try: return S.page_save_pdf(path=c["p"])
        finally: os.environ.pop("SAFARI_ALLOWED_ROOT", None)
    case("page_save_pdf", st, "outside_root", lambda: (open_page(tok()), {"p": f"{PDF}/out-{tok()}.pdf", "files": pdf_files()})[1], outside,
         lambda c, r, e, L, t0, t1: {"raised": isinstance(e, S.OutsideAllowedRoot), "no_new_file": pdf_files() == c["files"]})
    def inside(c):
        os.environ["SAFARI_ALLOWED_ROOT"] = f"{TOOLS}/data"
        try: return S.page_save_pdf(path=c["p"])
        finally: os.environ.pop("SAFARI_ALLOWED_ROOT", None)
    ti = tok()
    case("page_save_pdf", st, "inside_root", lambda: (open_page(ti), {"p": f"{PDF}/in-{ti}.pdf"})[1], inside,
         lambda c, r, e, L, t0, t1: {"no_error": e is None, "pdf_has_page": bool(pdf_text(c["p"])) and f"Heading {ti}" in pdf_text(c["p"])["text"]})
    for bad, kind in [("https://example.com/", "not_on_list"), ("javascript:alert(1)", "javascript"), ("file:///etc/hosts", "file"), ("example.com", "no_scheme"), (BASE.replace("127.0.0.1", "127.0.0.2") + "/x", "near_miss")]:
        for fn, call in [("tab_open", lambda c, b=bad: S.tab_open(url=b)), ("page_go", lambda c, b=bad: S.page_go(url=b))]:
            case(fn, st, f"refused_{kind}", lambda: open_page(tok()), call, lambda c, r, e, L, t0, t1: {"raised": isinstance(e, S.UrlNotAllowed), "no_request": L == [], "tabs_same": t0 == t1})
    tk = tok()
    case("link_click", st, "refused_outside", lambda: open_page(tk), lambda c: S.link_click(name="Outside link"), lambda c, r, e, L, t0, t1: {"raised": isinstance(e, S.UrlNotAllowed), "stayed": title() == f"Test {tk}"})
    case("link_click", st, "not_found", lambda: open_page(tok()), lambda c: S.link_click(name="No Such Link 58291"), lambda c, r, e, L, t0, t1: {"raised": isinstance(e, S.NotFound), "no_request": L == []})
    case("link_click", st, "ambiguous", lambda: open_page("", f"/twins/{tok()}"), lambda c: S.link_click(name="Same name"), lambda c, r, e, L, t0, t1: {"raised": isinstance(e, S.Ambiguous), "no_request": L == []})
    case("tab_activate", st, "not_found", lambda: open_page(tok()), lambda c: S.tab_activate(match="No Such Tab 58291"), lambda c, r, e, L, t0, t1: {"raised": isinstance(e, S.NotFound)})
    case("tab_close", st, "not_found", lambda: open_page(tok()), lambda c: S.tab_close(match="No Such Tab 58291"), lambda c, r, e, L, t0, t1: {"raised": isinstance(e, S.NotFound), "tabs_same": t0 == t1})
    dup = tok()
    def twins():
        open_page("", f"/p/{dup}"); open_page("", f"/q/{dup}")
    case("tab_activate", st, "ambiguous", twins, lambda c: S.tab_activate(match=f"Test {dup}"), lambda c, r, e, L, t0, t1: {"raised": isinstance(e, S.Ambiguous)})
    case("tab_close", st, "ambiguous", lambda: None, lambda c: S.tab_close(match=f"Test {dup}"), lambda c, r, e, L, t0, t1: {"raised": isinstance(e, S.Ambiguous), "both_kept": t1.count(f"Test {dup}") == 2})
def blocked():
    def try_all(place, read_typed):
        before = list(LOG); t0 = tabs()
        for fn, call in [("tab_open", lambda: S.tab_open(url=url(tok()))), ("page_go", lambda: S.page_go(url=url(tok()))), ("tab_list", lambda: S.tab_list()), ("tab_activate", lambda: S.tab_activate(match=t0[0])), ("tab_close", lambda: S.tab_close(match=t0[0])), ("page_info", lambda: S.page_info()), ("page_text", lambda: S.page_text()), ("page_links", lambda: S.page_links()), ("link_click", lambda: S.link_click(name="x")), ("page_back", lambda: S.page_back()), ("page_forward", lambda: S.page_forward()), ("page_reload", lambda: S.page_reload()), ("page_save_pdf", lambda: S.page_save_pdf(path=f"{PDF}/blocked-{tok()}.pdf")), ("page_add_to_reading_list", lambda: S.page_add_to_reading_list())]:
            try: call(); err = None
            except Exception as e: err = e
            REC.case(fn, "ui", "typed_text", f"blocked_{place}", {"raised_StateBlocked": isinstance(err, S.StateBlocked), "typed_kept": read_typed(), "no_new_request": LOG == before, "tabs_same": tabs() == t0}, repr(err)[:100])
    front(); open_page(tok()); menu("File", "Open Location…"); time.sleep(0.6); se('keystroke "half typed"', APP); time.sleep(0.5)
    def bar_val():
        f = ax.attr(A(), "AXFocusedUIElement"); return bool(f) and "half typed" in (ax.sattr(f, "AXValue") or "")
    try_all("address", bar_val); se("key code 53", APP); time.sleep(0.2); se("key code 53", APP); time.sleep(0.4)
    open_page("", f"/form/{tok()}"); time.sleep(0.8)
    f = next(e for e in ax.walk(win()) if ax.sattr(e, "AXRole") == "AXTextField" and ax.sattr(e, "AXDescription") != "smart search field")
    ax.focus(f); time.sleep(0.4); se('keystroke "half typed"', APP); time.sleep(0.5)
    def box_val():
        g = ax.attr(A(), "AXFocusedUIElement"); return bool(g) and ax.sattr(g, "AXValue") == "half typed"
    try_all("form", box_val)
import plistlib
def reading_list():
    """URLs in Safari's Reading List, read from its Bookmarks.plist, separately from Safari."""
    try: data = plistlib.load(open(f"{HOME}/Library/Safari/Bookmarks.plist", "rb"))
    except (OSError, plistlib.InvalidFileException): return []
    out = []
    for child in data.get("Children", []):
        if child.get("Title") == "com.apple.ReadingList":
            out += [x.get("URLString") for x in child.get("Children", [])]
    return out
def reading_cases():
    # Another tab or window in front would put a different page in front, so those states aren't used here.
    for state in ("open", "hidden", "minimized", "other_app", "find_open"):
        t = tok()
        case("page_add_to_reading_list", state, "page", lambda t=t: open_page(t), lambda c: S.page_add_to_reading_list(),
             lambda c, r, e, L, t0, t1, t=t: {"no_error": e is None, "in_reading_list": url(t) in reading_list() or url(t) + "/" in reading_list(), "return": bool(r) and r["title"] == f"Test {t}"})
def bookmarks():
    """(folder, title, url) of every bookmark, read from Safari's Bookmarks.plist, separately from Safari. Favorites is BookmarksBar;
    "Bookmarks" is the top level."""
    try: data = plistlib.load(open(f"{HOME}/Library/Safari/Bookmarks.plist", "rb"))
    except (OSError, plistlib.InvalidFileException): return []
    out = []
    for child in data.get("Children", []):
        if child.get("WebBookmarkType") == "WebBookmarkTypeLeaf": out.append(("Bookmarks", child.get("URIDictionary", {}).get("title"), child.get("URLString")))
        elif child.get("Title") == "BookmarksBar": out += [("Favorites", x.get("URIDictionary", {}).get("title"), x.get("URLString")) for x in child.get("Children", []) if x.get("WebBookmarkType") == "WebBookmarkTypeLeaf"]
    return out
def bookmark_cases():
    for state in ("open", "hidden", "minimized", "other_app", "find_open"):
        for folder, named in (("Favorites", False), ("Bookmarks", True)):
            t = tok(); name = f"{V.special()} {t}" if named else None
            def setup(t=t):
                open_page(t); return {"before": bookmarks()}
            case("page_add_bookmark", state, f"{folder.lower()}{'_named' if named else ''}", setup, lambda c, folder=folder, name=name: S.page_add_bookmark(title=name, folder=folder),
                 lambda c, r, e, L, t0, t1, t=t, folder=folder, name=name: {"no_error": e is None,
                     # Safari writes its default Favorites when it first creates the file, so only test-server bookmarks are counted.
                     "in_file": (lambda new: new == [(folder, name or f"Test {t}", url(t))])([b for b in bookmarks() if b not in c["before"] and (b[2] or "").startswith(BASE)]),
                     "return": bool(r) and r["title"] == f"Test {t}" and r["folder"] == folder and r["bookmark"] == (name or f"Test {t}")})
    st = "open"
    case("page_add_bookmark", st, "bad_folder", lambda: (open_page(tok()), {"before": bookmarks()})[1], lambda c: S.page_add_bookmark(folder="Bookmarks Menu"),
         lambda c, r, e, L, t0, t1: {"raised": isinstance(e, ValueError), "nothing_added": bookmarks() == c["before"]})
    case("page_add_bookmark", st, "empty_title", lambda: (open_page(tok()), {"before": bookmarks()})[1], lambda c: S.page_add_bookmark(title="  "),
         lambda c, r, e, L, t0, t1: {"raised": isinstance(e, ValueError), "nothing_added": bookmarks() == c["before"]})
    t = tok()
    case("page_add_bookmark", st, "large_clipboard", lambda t=t: (open_page(t), {"before": bookmarks()})[1], lambda c: S.page_add_bookmark(title=f"Big {t}"),
         lambda c, r, e, L, t0, t1, t=t: {"no_error": e is None, "in_file": ("Favorites", f"Big {t}", url(t)) in bookmarks()}, big=True)
    try: S.page_add_bookmark(mode="background"); err = None
    except Exception as e: err = e
    REC.case("page_add_bookmark", "background", st, "not_supported", {"raised": isinstance(err, S.NotSupported)}, repr(err)[:100])
# Saving a page (overnight): each saved file is read back here by its kind; the folder must gain only it.
SAVED = f"{TOOLS}/data/saved"; os.makedirs(SAVED, exist_ok=True)
def saved_ok(p, t):
    try: data = open(p, "rb").read()
    except OSError: return False
    if p.endswith(".png"):
        dims = subprocess.run(["sips", "-g", "pixelWidth", "-g", "pixelHeight", p], capture_output=True, text=True).stdout
        return data[:8] == b"\x89PNG\r\n\x1a\n" and "pixelWidth: " in dims and int(dims.split("pixelWidth: ")[1].split()[0]) > 100
    if p.endswith(".webarchive"):
        try: main = plistlib.loads(data)["WebMainResource"]
        except Exception: return False
        return f"Heading {t}" in main.get("WebResourceData", b"").decode("utf-8", "replace") and main.get("WebResourceURL", "").endswith(t)
    return f"Heading {t}" in data.decode("utf-8", "replace")
def names(): return sorted(unicodedata.normalize("NFC", n) for n in os.listdir(SAVED))
def save_cases():
    for state in ("open", "hidden", "minimized", "other_app", "find_open"):
        for suffix in (".html", ".webarchive", ".png"):
            t = tok()
            def setup(t=t, suffix=suffix):
                open_page(t); return {"p": f"{SAVED}/{V.special().replace('/', '-')} {t}{suffix}", "files": names()}
            case("page_save", state, suffix[1:], lambda t=t, suffix=suffix: setup(t, suffix), lambda c: S.page_save(path=c["p"]),
                 lambda c, r, e, L, t0, t1, t=t: {"no_error": e is None, "file_is_the_page": saved_ok(c["p"], t),
                     "only_it": names() == sorted(c["files"] + [unicodedata.normalize("NFC", os.path.basename(c["p"]))]),
                     "return": bool(r) and r["path"] == c["p"] and r["title"] == f"Test {t}"})
    st = "open"
    def taken():
        open_page(tok()); p = f"{SAVED}/taken {tok()}.html"; open(p, "w").write("keep"); return {"p": p}
    case("page_save", st, "exists", taken, lambda c: S.page_save(path=c["p"]), lambda c, r, e, L, t0, t1: {"raised": isinstance(e, S.AlreadyExists), "kept": open(c["p"]).read() == "keep"})
    case("page_save", st, "bad_suffix", lambda: (open_page(tok()), {})[1], lambda c: S.page_save(path=f"{SAVED}/x.txt"), lambda c, r, e, L, t0, t1: {"raised": isinstance(e, ValueError)})
    case("page_save", st, "no_folder", lambda: (open_page(tok()), {})[1], lambda c: S.page_save(path=f"{SAVED}/none/x.html"), lambda c, r, e, L, t0, t1: {"raised": isinstance(e, S.NotFound)})
    case("page_save", st, "relative", lambda: (open_page(tok()), {})[1], lambda c: S.page_save(path="x.html"), lambda c, r, e, L, t0, t1: {"raised": isinstance(e, ValueError)})
    t2 = tok()
    case("page_save", st, "large_clipboard", lambda t2=t2: (open_page(t2), {"p": f"{SAVED}/big {t2}.webarchive"})[1], lambda c: S.page_save(path=c["p"]),
         lambda c, r, e, L, t0, t1, t2=t2: {"no_error": e is None, "file_is_the_page": saved_ok(c["p"], t2)}, big=True)
    try: S.page_save(path=f"{SAVED}/bg.html", mode="background"); err = None
    except Exception as x: err = x
    REC.case("page_save", "background", st, "not_supported", {"raised": isinstance(err, S.NotSupported)}, repr(err)[:100])
def large_clipboard():
    st = "open"
    case("tab_open", st, "large_clipboard", lambda: open_page(tok()), lambda c: S.tab_open(url=url(tok())), lambda c, r, e, L, t0, t1: {"no_error": e is None}, big=True)
    case("page_go", st, "large_clipboard", lambda: open_page(tok()), lambda c: S.page_go(url=url(tok())), lambda c, r, e, L, t0, t1: {"no_error": e is None}, big=True)
    tl = tok()
    case("page_save_pdf", st, "large_clipboard", lambda: (open_page(tl), {"p": f"{PDF}/big-{tl}.pdf"})[1], lambda c: S.page_save_pdf(path=c["p"]), lambda c, r, e, L, t0, t1: {"no_error": e is None, "pdf_has_page": bool(pdf_text(c["p"])) and f"Heading {tl}" in pdf_text(c["p"])["text"]}, big=True)
STATES = ["closed", "launching", "open", "other_tab", "hidden", "minimized", "other_app", "no_window", "two_windows", "find_open"]
try:
    for state in STATES:
        if state in ONLY:
            print(f"== state starts: {state} at {time.strftime('%H:%M:%S')}", flush=True); run_state(state)
    for label, fn in (("errors", errors), ("blocked", blocked), ("large_clipboard", large_clipboard), ("reading", reading_cases), ("bookmarks", bookmark_cases), ("saving", save_cases)):
        if label in ONLY:
            print(f"== state starts: {label} at {time.strftime('%H:%M:%S')}", flush=True); fn()
finally:
    h = sqlite3.connect(f"file:{HOME}/Library/Safari/History.db?mode=ro", uri=True)
    try: REC.data["meta"]["history_non_test_rows"] = h.execute("select count(*) from history_items where url not like ? and url not like ?", (BASE + "%", "http://127.0.0.2%")).fetchone()[0]
    except Exception as e: REC.data["meta"]["history_non_test_rows"] = repr(e)[:60]
    REC.data["meta"]["requests_seen"] = len(LOG)
    REC.data["meta"]["finished"] = time.strftime("%Y-%m-%d %H:%M:%S"); REC.save(); print("DONE", flush=True)
