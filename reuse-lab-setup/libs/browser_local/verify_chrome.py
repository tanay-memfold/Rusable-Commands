"""Verify chrome.py inside the VM: python3 verify_chrome.py <group> <seed> <state|errors|blocked> ...
Tests only ever send Chrome to this script's own local server, and CHROME_ALLOWED_PREFIXES makes the library refuse anything else. A page's
result is read from the server's request log, which is separate from Chrome; titles and tabs are read from Chrome's window with
separate code, so those aren't independent of Chrome. Chrome itself still reaches Google for its New Tab page and updates."""
import ctypes, http.server, json, os, re, shutil, socketserver, sqlite3, sys, threading, time, traceback, urllib.parse
HOME = os.path.expanduser("~"); TOOLS = f"{HOME}/browser-test"; sys.path[:0] = [TOOLS]
PORT = 8731; BASE = f"http://127.0.0.1:{PORT}"
os.environ["CHROME_ALLOWED_PREFIXES"] = BASE + "/"
import ax, chrome as S
from vcommon import Recorder, Values, osa, se, sh, wait
GROUP, SEED, ONLY = sys.argv[1], int(sys.argv[2]), sys.argv[3:]
V = Values(SEED); APP = "Google Chrome"; FAILS = {}
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
# Chrome holds spare connections open, which mustn't keep this script alive after it finishes.
socketserver.ThreadingTCPServer.daemon_threads = True; socketserver.ThreadingTCPServer.block_on_close = False
SERVER = socketserver.ThreadingTCPServer(("127.0.0.1", PORT), H); threading.Thread(target=SERVER.serve_forever, daemon=True).start()
def url(t): return f"{BASE}/p/{urllib.parse.quote(t)}"
def tok(): return f"t{V.rng.randint(100000, 999999)}"
def running(): return bool(sh(f"pgrep -x '{APP}'"))
def A(): return ax.app(APP)
def wins(): return [c for c in ax.children(A()) if ax.sattr(c, "AXRole") == "AXWindow" and ax.sattr(c, "AXSubrole") == "AXStandardWindow"]
def win():
    w = [x for x in (ax.attr(A(), "AXMainWindow"), ax.attr(A(), "AXFocusedWindow")) if x and ax.sattr(x, "AXSubrole") == "AXStandardWindow"]
    return (w or wins() or [None])[0]
def title(): return re.sub(r" - Google Chrome$", "", ax.sattr(win(), "AXTitle")) if running() and win() else ""
def tabs():
    if not running() or not win(): return []
    found, stack = [], [win()]
    while stack:
        e = stack.pop()
        if ax.sattr(e, "AXSubrole") == "AXTabButton": found.append(re.sub(r" - Memory usage - .*$", "", ax.sattr(e, "AXTitle")))
        if ax.sattr(e, "AXRole") != "AXWebArea": stack.extend(reversed(ax.children(e)))
    return found
def menu(m, i): return se(f'click menu item "{i}" of menu "{m}" of menu bar item "{m}" of menu bar 1', APP)
def quit_app():
    if running():
        try: menu("Chrome", "Quit Google Chrome")
        except RuntimeError: pass
        wait(lambda: not running(), 15)
def open_page(t, path=None):
    n = len(LOG); sh(f"open -a 'Google Chrome' '{(BASE + path) if path else url(t)}'"); wait(lambda: len(LOG) > n, 12); time.sleep(0.8)
def front():
    sh("open -a 'Google Chrome'"); wait(running, 15); se("set visible to true\nset frontmost to true", APP); wait(wins, 8)
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
        if state == "launching": sh("open -a 'Google Chrome'")
        return
    front()
    if state == "other_tab": menu("File", "New Tab"); time.sleep(0.4); se("key code 53", APP)
    elif state == "hidden": se("set visible to false", APP)
    elif state == "minimized": ax.AS.AXUIElementSetAttributeValue(win(), ax.cf("AXMinimized"), ax.TRUE)
    elif state == "other_app": sh("open -a Calculator"); wait(lambda: se("return frontmost", APP) == "false", 8)
    elif state == "no_window":
        menu("File", "Close Window") if se('exists menu item "Close Window" of menu "File" of menu bar item "File" of menu bar 1', APP) == "true" else menu("File", "Close All Windows"); wait(lambda: not wins(), 5)
    elif state == "two_windows": menu("File", "New Window"); time.sleep(0.6); se("key code 53", APP)
    time.sleep(0.5)
def clean(): return not (running() and win() and any(ax.sattr(e, "AXRole") == "AXSheet" for e in ax.children(win())))
def case(fn, state, kind, setup, call, read):
    if ONLY_FNS and fn not in ONLY_FNS: return
    COUNT["n"] += 1
    if COUNT["n"] <= RESUME or FAILS.get(fn, 0) >= 3: return
    print(f"CASE {COUNT['n']} {fn} ui {state} {kind}", flush=True)
    try:
        ctx = setup() or {}
        start(state); n0 = len(LOG); tabs0 = tabs(); began = time.monotonic()
        try: res, err = call(ctx), None
        except (S.ChromeError, ValueError) as e: res, err = None, e
        secs = round(time.monotonic() - began, 1); end = time.monotonic() + 8
        while True:
            checks = read(ctx, res, err, LOG[n0:], tabs0, tabs())
            if all(checks.values()) or time.monotonic() > end: break
            time.sleep(0.4)
        checks["only_test_pages_requested"] = all(p.startswith(("/p/", "/q/", "/form", "/twins", "/favicon")) for p in LOG[n0:])
        checks["nothing_left_open"] = clean()
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
    enc = f"hello world {tok()}"
    case("page_go", state, "encoded_address", lambda: open_page(t["n"]), lambda c: S.page_go(url=url(enc)),
         lambda c, r, e, L, t0, t1: {"no_error": e is None, "server_got_it": "/p/" + urllib.parse.quote(enc) in L, "return": bool(r) and r["title"] == f"Test {enc}"})
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
def errors():
    st = "open"
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
    def try_all(place, read_typed, t0=None):
        before = list(LOG); hidden = t0 is not None; t0 = t0 or tabs()
        for fn, call in [("tab_open", lambda: S.tab_open(url=url(tok()))), ("page_go", lambda: S.page_go(url=url(tok()))), ("tab_list", lambda: S.tab_list()), ("tab_activate", lambda: S.tab_activate(match=t0[0])), ("tab_close", lambda: S.tab_close(match=t0[0])), ("page_info", lambda: S.page_info()), ("page_text", lambda: S.page_text()), ("page_links", lambda: S.page_links()), ("link_click", lambda: S.link_click(name="x")), ("page_back", lambda: S.page_back()), ("page_forward", lambda: S.page_forward()), ("page_reload", lambda: S.page_reload())]:
            try: call(); err = None
            except Exception as e: err = e
            REC.case(fn, "ui", "typed_text", f"blocked_{place}", {"raised_StateBlocked": isinstance(err, S.StateBlocked), "typed_kept": read_typed(), "no_new_request": LOG == before, "tabs_same": hidden or tabs() == t0}, repr(err)[:100])
    front(); open_page(tok()); menu("File", "Open Location…"); time.sleep(0.6); se('keystroke "half typed"', APP); time.sleep(0.5)
    def bar_val():
        f = ax.attr(A(), "AXFocusedUIElement"); return bool(f) and "half typed" in (ax.sattr(f, "AXValue") or "")
    try_all("address", bar_val); se("key code 53", APP); time.sleep(0.2); se("key code 53", APP); time.sleep(0.4)
    open_page("", f"/form/{tok()}"); time.sleep(0.8)
    f = next(e for e in ax.walk(win()) if ax.sattr(e, "AXRole") == "AXTextField" and ax.sattr(e, "AXDescription") != S.ADDRESS)
    ax.focus(f); time.sleep(0.4); se('keystroke "half typed"', APP); time.sleep(0.5)
    def box_val():
        g = ax.attr(A(), "AXFocusedUIElement"); return bool(g) and ax.sattr(g, "AXValue") == "half typed"
    try_all("form", box_val)
    # With the Find bar focused the tabs can't be read, so they're compared after it's closed.
    for place, text in (("find_empty", ""), ("find_text", "searching")):
        se("key code 53", APP); time.sleep(0.2); se("key code 53", APP); time.sleep(0.4)
        open_page(tok()); time.sleep(0.5); t0 = tabs()
        se('keystroke "f" using command down', APP); time.sleep(0.6); se('keystroke "a" using command down', APP); se("key code 51", APP); time.sleep(0.2)
        if text: se(f'keystroke "{text}"', APP); time.sleep(0.4)
        def find_val(want=text):
            g = ax.attr(A(), "AXFocusedUIElement"); return bool(g) and ax.sattr(g, "AXTitle") == "Find" and (ax.sattr(g, "AXValue") or "") == want
        try_all(place, find_val, t0)
        se("key code 53", APP); time.sleep(0.6)
        REC.case("tab_list", "ui", "find_bar", f"tabs_same_{place}", {"tabs_same": tabs() == t0}, None)
# Bookmarks (overnight): read back from Chrome's own Bookmarks file, separately from Chrome's window. Each case also sets a small
# clipboard and checks it comes back (the name is pasted), and one runs with a very large clipboard.
import bigclip
BM = f"{HOME}/Library/Application Support/Google/Chrome/Default/Bookmarks"
def chrome_bookmarks():
    try: roots = json.load(open(BM))["roots"]
    except (OSError, ValueError, KeyError): return []
    out = []
    for key, label in (("bookmark_bar", "Bookmarks Bar"), ("other", "Other Bookmarks")):
        out += [(label, c.get("name"), c.get("url")) for c in roots.get(key, {}).get("children", []) if c.get("type") == "url"]
    return out
def clip_set(text): subprocess.run(["pbcopy"], input=text.encode())
def clip(): return subprocess.run(["pbpaste"], capture_output=True).stdout.decode(errors="replace")
import subprocess
def bookmark_cases():
    for state in ("open", "hidden", "minimized", "other_app"):
        for folder, named in (("Other Bookmarks", False), ("Bookmarks Bar", True)):
            t = tok(); name = f"{V.special()} {t}" if named else None
            def setup(t=t):
                open_page(t); small = f"keep {V.word(1)}"; clip_set(small); return {"before": chrome_bookmarks(), "small": small}
            case("page_add_bookmark", state, f"{'bar' if folder == 'Bookmarks Bar' else 'other'}{'_named' if named else ''}", setup,
                 lambda c, folder=folder, name=name: S.page_add_bookmark(title=name, folder=folder),
                 lambda c, r, e, L, t0, t1, t=t, folder=folder, name=name: {"no_error": e is None,
                     "in_file": [b for b in chrome_bookmarks() if b not in c["before"]] == [(folder, name or f"Test {t}", url(t))],
                     "clipboard_kept": clip() == c["small"],
                     "return": bool(r) and r["title"] == f"Test {t}" and r["folder"] == folder and r["bookmark"] == (name or f"Test {t}")})
    st = "open"; t = tok()
    def twice(t=t):
        open_page(t); S.page_add_bookmark()
        wait(lambda: any(b[2] == url(t) for b in chrome_bookmarks()), 15)  # Chrome writes its Bookmarks file a moment later
        time.sleep(1); return {"before": chrome_bookmarks()}
    case("page_add_bookmark", st, "already", twice, lambda c: S.page_add_bookmark(title="Other name"), lambda c, r, e, L, t0, t1: {"raised": isinstance(e, S.AlreadyExists), "unchanged": chrome_bookmarks() == c["before"]})
    case("page_add_bookmark", st, "bad_folder", lambda: (open_page(tok()), {"before": chrome_bookmarks()})[1], lambda c: S.page_add_bookmark(folder="Mobile Bookmarks"),
         lambda c, r, e, L, t0, t1: {"raised": isinstance(e, ValueError), "unchanged": chrome_bookmarks() == c["before"]})
    case("page_add_bookmark", st, "empty_title", lambda: (open_page(tok()), {"before": chrome_bookmarks()})[1], lambda c: S.page_add_bookmark(title=" "),
         lambda c, r, e, L, t0, t1: {"raised": isinstance(e, ValueError), "unchanged": chrome_bookmarks() == c["before"]})
    case("page_add_bookmark", st, "not_supported", lambda: (open_page(tok()), {"before": chrome_bookmarks()})[1], lambda c: S.page_add_bookmark(mode="background"),
         lambda c, r, e, L, t0, t1: {"raised": isinstance(e, S.NotSupported), "unchanged": chrome_bookmarks() == c["before"]})
    t2 = tok()
    def big(t2=t2):
        open_page(t2); want = bigclip.fill(V.rng.randint(1, 10**9)); return {"before": chrome_bookmarks(), "want": want}
    case("page_add_bookmark", st, "large_clipboard", big, lambda c: S.page_add_bookmark(title=f"Big {t2}"),
         lambda c, r, e, L, t0, t1, t2=t2: {"no_error": e is None, "in_file": ("Other Bookmarks", f"Big {t2}", url(t2)) in chrome_bookmarks(), **bigclip.check(c["want"])})
# Saving a page (overnight): the saved file is read back here; the folder must gain only it, and Downloads must stay the same.
os.environ["CHROME_ALLOWED_ROOT"] = f"{TOOLS}/data"
SAVED = f"{TOOLS}/data/saved"; os.makedirs(SAVED, exist_ok=True)
DL = os.path.expanduser("~/Downloads")
def listing(d): return sorted(unicodedata.normalize("NFC", n) for n in os.listdir(d)) if os.path.isdir(d) else []
def saved_text(p):
    """The saved page as text: an .mhtml file is a MIME message, so its parts are decoded (quoted-printable) first."""
    if not os.path.isfile(p): return ""
    raw = open(p, "rb").read()
    if not p.endswith(".mhtml"): return raw.decode("utf-8", "replace")
    import email
    msg = email.message_from_bytes(raw)
    return "\n".join((part.get_payload(decode=True) or b"").decode(part.get_content_charset() or "utf-8", "replace") for part in msg.walk() if not part.is_multipart())
import unicodedata
def save_cases():
    for state in ("open", "hidden", "minimized", "other_app"):
        for suffix in (".html", ".mhtml"):
            t = tok()
            def setup(t=t, suffix=suffix):
                open_page(t); small = f"keep {V.word(1)}"; clip_set(small)
                return {"p": f"{SAVED}/{V.special().replace('/', '-')} {t}{suffix}", "files": listing(SAVED), "dl": listing(DL), "small": small}
            case("page_save", state, suffix[1:], setup, lambda c: S.page_save(path=c["p"]),
                 lambda c, r, e, L, t0, t1, t=t: {"no_error": e is None,
                     "file_has_page": f"Heading {t}" in saved_text(c["p"]),
                     "only_it": listing(SAVED) == sorted(c["files"] + [unicodedata.normalize("NFC", os.path.basename(c["p"]))]), "downloads_same": listing(DL) == c["dl"],
                     "clipboard_kept": clip() == c["small"], "no_bubble_left": not any(ax.sattr(w, "AXTitle") == "Recent Download History" for w in ax.children(A())),
                     "return": bool(r) and r["path"] == c["p"] and r["title"] == f"Test {t}"})
    st = "open"
    def taken():
        open_page(tok()); p = f"{SAVED}/taken {tok()}.html"; open(p, "w").write("keep"); return {"p": p}
    case("page_save", st, "exists", taken, lambda c: S.page_save(path=c["p"]), lambda c, r, e, L, t0, t1: {"raised": isinstance(e, S.AlreadyExists), "kept": open(c["p"]).read() == "keep"})
    case("page_save", st, "bad_suffix", lambda: (open_page(tok()), {})[1], lambda c: S.page_save(path=f"{SAVED}/x.pdf"), lambda c, r, e, L, t0, t1: {"raised": isinstance(e, ValueError)})
    case("page_save", st, "no_folder", lambda: (open_page(tok()), {})[1], lambda c: S.page_save(path=f"{SAVED}/none/x.html"), lambda c, r, e, L, t0, t1: {"raised": isinstance(e, S.NotFound)})
    case("page_save", st, "guard", lambda: (open_page(tok()), {})[1], lambda c: S.page_save(path="/tmp/outside-page.html"), lambda c, r, e, L, t0, t1: {"raised": isinstance(e, S.OutsideAllowedRoot), "nothing": not os.path.exists("/tmp/outside-page.html")})
    case("page_save", st, "not_supported", lambda: (open_page(tok()), {})[1], lambda c: S.page_save(path=f"{SAVED}/bg.html", mode="background"), lambda c, r, e, L, t0, t1: {"raised": isinstance(e, S.NotSupported)})
    t2 = tok()
    def big(t2=t2):
        open_page(t2); return {"p": f"{SAVED}/big {t2}.html", "want": bigclip.fill(V.rng.randint(1, 10**9))}
    case("page_save", st, "large_clipboard", big, lambda c: S.page_save(path=c["p"]),
         lambda c, r, e, L, t0, t1, t2=t2: {"no_error": e is None, "file_has_page": os.path.isfile(c["p"]) and f"Heading {t2}" in open(c["p"], "rb").read().decode("utf-8", "replace"), **bigclip.check(c["want"])})
STATES = ["closed", "launching", "open", "other_tab", "hidden", "minimized", "other_app", "no_window", "two_windows"]
try:
    for state in STATES:
        if state in ONLY:
            print(f"== state starts: {state} at {time.strftime('%H:%M:%S')}", flush=True); run_state(state)
    for label, fn in (("errors", errors), ("blocked", blocked), ("bookmarks", bookmark_cases), ("saving", save_cases)):
        if label in ONLY:
            print(f"== state starts: {label} at {time.strftime('%H:%M:%S')}", flush=True); fn()
finally:
    copy = f"{TOOLS}/History.copy"
    try:
        shutil.copy(f"{HOME}/Library/Application Support/Google/Chrome/Default/History", copy)
        REC.data["meta"]["history_non_test_rows"] = sqlite3.connect(copy).execute("select count(*) from urls where url not like ?", (BASE + "%",)).fetchone()[0]
    except Exception as e: REC.data["meta"]["history_non_test_rows"] = repr(e)[:60]
    REC.data["meta"]["requests_seen"] = len(LOG)
    REC.data["meta"]["finished"] = time.strftime("%Y-%m-%d %H:%M:%S"); REC.save(); print("DONE", flush=True)
