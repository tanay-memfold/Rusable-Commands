"""Verify gmail.py inside one clone. Acts only on messages it created (unique made-up subjects). Every result is read back
after a page reload by the separate reader below, not by gmail.py. Other rows are stored only as hashes.
   python3 verify_gmail.py <group> <seed> <max_sends> [state ...]"""
import hashlib, json, os, random, re, subprocess, sys, time
HOME = os.path.expanduser("~")
sys.path[:0] = [f"{HOME}/gm", f"{HOME}/probe"]
import ax
import gmail as G
GROUP, SEED, MAX_SENDS = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
ONLY = set(sys.argv[4:])
rng = random.Random(SEED)
ACCOUNT = open(f"{HOME}/probe/account.txt").read().strip()
os.environ["GMAIL_ALLOWED_RECIPIENTS"] = ACCOUNT
OUT = f"{HOME}/verify-out"; os.makedirs(OUT, exist_ok=True)
DATA = {"group": GROUP, "meta": {"versions": G._versions(), "started": time.strftime("%Y-%m-%d %H:%M:%S"), "seed": SEED}, "cases": []}
STATE_FILE = f"{OUT}/sends.json"
sends = json.load(open(STATE_FILE)) if os.path.exists(STATE_FILE) else {"count": 0, "last": 0, "subjects": []}
SUBJECTS = sends["subjects"]
WORDS = ["Larch", "Fjord", "Ember", "Cobalt", "Tide", "Juniper", "Saffron", "Basalt", "Willow", "Marble", "Orchid", "Harbor"]
class Stop(BaseException): pass  # not caught by the "except Exception" around each case
def save():
    json.dump(DATA, open(f"{OUT}/{GROUP}.json", "w"), indent=1, ensure_ascii=False)
    sends["subjects"] = SUBJECTS
    json.dump(sends, open(STATE_FILE, "w"), ensure_ascii=False)
def record(function, state, kind, checks, detail=None, seconds=None):
    ok = bool(checks) and all(checks.values())
    DATA["cases"].append({"function": function, "mode": "ui", "state": state, "kind": kind, "passed": ok, "checks": checks, "detail": detail, "seconds": seconds})
    print(("PASS " if ok else "FAIL ") + f"{function} {state} {kind} {[k for k, v in checks.items() if not v] or ''} {detail if not ok else ''}", flush=True)
    save()
def new_subject(special):
    n = rng.randint(100000, 999999)
    s = f'Café "{rng.choice(WORDS)}" ✨ {n}' if special else f"{rng.choice(WORDS)} {rng.choice(WORDS)} {n}"
    SUBJECTS.append(s); save(); return s
def new_body(special):
    n = rng.randint(1000, 9999)
    return f'Zoë said "hi" ☕ {n}\nsecond line {n}' if special else f"plain body {n}"
def gap():
    if sends["count"] >= MAX_SENDS:
        raise Stop(f"reached the limit of {MAX_SENDS} sends")
    wait_for = 31 - (time.time() - sends["last"])
    if wait_for > 0: time.sleep(wait_for)

# Every press of Send goes through here: this is the send count, and the hard stop. Results don't affect it.
FAULT = {"mode": None, "presses": 0}
real_press = G._press
def is_send(e): return G._role(e) == "AXButton" and G._name(e).startswith("Send") and "options" not in G._name(e)
def is_save(e): return G._role(e) == "AXButton" and G._name(e).startswith("Save & close")
PRESSES = {"n": 0}
def press_hook(e):
    PRESSES["n"] += 1
    if is_send(e) or is_save(e):
        if FAULT["mode"]:   # no real send or save: the command must not report success
            FAULT["presses"] += 1
            if FAULT["mode"] == "discard":
                real_press(ax.find(win(), "AXButton", "Discard draft"))
            return
    if is_send(e):
        if sends["count"] >= MAX_SENDS: raise Stop(f"hard stop: {MAX_SENDS} real sends reached; Send was not pressed")
        wait_for = 31 - (time.time() - sends["last"])
        if wait_for > 0: time.sleep(wait_for)
        sends["count"] += 1; sends["last"] = time.time(); save()
    real_press(e)
G._press = press_hook

# Reader: independent of gmail.py --------------------------------------------------------------------------------------
def se(body):
    r = subprocess.run(["osascript", "-e", 'tell application "System Events" to tell process "Safari"\n%s\nend tell' % body], capture_output=True, text=True)
    return r.stdout.strip() or r.stderr.strip()[:160]
def running(): return subprocess.run(["pgrep", "-x", "Safari"], capture_output=True).returncode == 0
def root(): return ax.app("Safari")
def win():
    a = root(); return ax.attr(a, "AXFocusedWindow") or next(iter(ax.children(a)), None)
def title(): return (ax.sattr(win(), "AXTitle") or "") if running() and win() else ""
def until(fn, s=20):
    end = time.monotonic() + s
    while time.monotonic() < end:
        try: v = fn()
        except Exception: v = None
        if v: return v
        time.sleep(0.3)
def guard():
    bar = ax.find(win(), "AXTextField", "smart search field") if win() else None
    url = (ax.sattr(bar, "AXValue") or "") if bar else ""
    t = title()
    if "accounts.google" in url or "challenge" in url or "verify it" in t.lower() or "sign in" in t.lower():
        raise Stop(f"Google showed a sign-in or challenge page: stopping (title: {t[:40]})")
    if ACCOUNT not in t and " - Gmail" in t:
        raise Stop("the signed-in address changed: stopping")
def front_gmail():
    subprocess.run(["open", "-a", "Safari"]); until(running)
    se("set visible to true\nset frontmost to true")
    for w in [e for e in ax.children(root()) if ax.sattr(e, "AXRole") == "AXWindow"]:
        ax.AS.AXUIElementSetAttributeValue(w, ax.cf("AXMinimized"), ctypes_false)
    if " - Gmail" not in title():
        for g in [e for e in ax.walk(win()) if ax.sattr(e, "AXRole") == "AXTabGroup"]:
            for tab in ax.children(g):
                if " - Gmail" in (ax.sattr(tab, "AXTitle") or ""): ax.press(tab)
    if " - Gmail" not in title():
        subprocess.run(["open", "-a", "Safari", "https://mail.google.com/"])
    until(lambda: " - Gmail" in title() and ax.find(win(), "AXTextField", "Search mail"), 40)
    guard()
import ctypes
ctypes_false = ctypes.c_void_p.in_dll(ax.CF, "kCFBooleanFalse")
def paste(text):
    subprocess.run(["pbcopy"], input=text, text=True); se('keystroke "v" using command down')
def reload_page():
    se('click menu item "Reload Page" of menu "View" of menu bar item "View" of menu bar 1')
    time.sleep(2); until(lambda: ax.find(win(), "AXTextField", "Search mail"), 30); guard()
def main_area(): return next((e for e in ax.walk(win()) if ax.sattr(e, "AXSubrole") == "AXLandmarkMain"), win())
def rows():
    return [e for e in ax.walk(main_area()) if ax.sattr(e, "AXRole") == "AXRow" and any(ax.sattr(x, "AXRole") == "AXLink" for x in ax.walk(e))]
def query_words(subject): return " ".join(re.sub(r"[^\w\s]", " ", subject).split())
def lookup(scope, subject, reload_first=True):
    """Rows (their accessibility names) for this subject in a Gmail scope, after a reload."""
    front_gmail()
    if reload_first: reload_page()
    f = ax.find(win(), "AXTextField", "Search mail"); ax.focus(f); time.sleep(0.2)
    se('keystroke "a" using command down'); paste(f'{scope} subject:"{query_words(subject)}"'); se("key code 36")
    time.sleep(3); until(lambda: rows() or any((ax.sattr(e, "AXValue") or "").startswith("No messages matched") for e in ax.walk(main_area())), 12)
    time.sleep(0.8)
    return [ax.names(r)[0] for r in rows() if subject in ax.names(r)[0] or subject.replace("✨", "").strip() in ax.names(r)[0]]
def poll(test, seconds=45):
    end = time.monotonic() + seconds
    while True:
        try: ok = test()
        except Stop: raise
        except Exception: ok = False
        if ok or time.monotonic() > end: return bool(ok)
        time.sleep(4)
def own_heading(token):
    return any(ax.sattr(e, "AXRole") == "AXHeading" and token in " ".join(ax.names(e) + [ax.sattr(e, "AXValue") or ""]) for e in ax.walk(main_area()))
def body_after_reload(subject):
    token = query_words(subject).split()[-1]
    front_gmail(); reload_page()
    # A reload on an open message brings the same message back, and repeating its search wouldn't leave it. Read it there.
    if not until(lambda: ax.find(main_area(), "AXPopUpButton", "Show details") and own_heading(token), 12):
        lookup("", subject, reload_first=False)
        row = until(lambda: next((r for r in rows() if token in ax.names(r)[0]), None), 30)
        if not row: raise RuntimeError("own row not found after reload")
        ax.press(next(e for e in ax.walk(row) if ax.sattr(e, "AXRole") == "AXLink"))
        until(lambda: ax.find(main_area(), "AXPopUpButton", "Show details"), 15)
    time.sleep(0.6)
    items = list(ax.walk(main_area()))
    start = max(i for i, e in enumerate(items) if ax.sattr(e, "AXRole") == "AXPopUpButton" and "Show details" in ax.names(e))
    text = []
    for e in items[start + 1:]:
        r = ax.sattr(e, "AXRole")
        if r == "AXLink" and "Reply" in ax.names(e)[1]: break
        if r == "AXStaticText": text.append(ax.sattr(e, "AXValue") or "")
        if r == "AXImage": text.append(ax.names(e)[0])
    return "".join(text)
def in_drafts_folder(subject):
    front_gmail(); reload_page()
    ax.press(ax.find(win(), "AXLink", "Drafts")); until(lambda: "#drafts" in (ax.sattr(ax.find(win(), "AXTextField", "smart search field"), "AXValue") or ""), 10); time.sleep(3)
    return [ax.names(r)[0] for r in rows() if query_words(subject).split()[-1] in ax.names(r)[0]]
STABLE = "Quartz Harbor 250132"   # a test message from before these runs; only its own row is ever opened
PAGE = 50
FLAGS = re.compile(r"^(starred, )?(unread, )?")
def own_name(n): return any(query_words(s).split()[-1] in n for s in SUBJECTS)
def fingerprint():
    """Other Inbox rows in order, as a hash of the row without its flags, plus the flags. Never stored as text.
    A read counts only when the list holds a full page and hasn't changed over three reads."""
    front_gmail(); f = ax.find(win(), "AXTextField", "Search mail"); ax.focus(f); time.sleep(0.2)
    se('keystroke "a" using command down'); paste("in:inbox"); se("key code 36"); time.sleep(2)
    end, last, steady, names = time.monotonic() + 30, None, 0, []
    while time.monotonic() < end and steady < 3:
        names = [ax.names(r)[0] for r in rows()]
        steady = steady + 1 if names == last and len(names) == PAGE else 0
        last = names; time.sleep(1)
    out = [[hashlib.sha256(FLAGS.sub("", n).encode()).hexdigest()[:16], bool(re.match(r"(starred, )?unread, ", n)), n.startswith("starred, ")] for n in names if not own_name(n)]
    return {"valid": steady >= 3, "rows": out, "own": sum(own_name(n) for n in names), "read": len(names)}
def compare(state, before, after):
    """Pushed off the page is not a change: rows may leave only from the bottom, and only as many as came in on top."""
    with open(f"{OUT}/hashes-{GROUP}.jsonl", "a") as h: h.write(json.dumps({"state": state, "before": before, "after": after}) + "\n")
    if not (before["valid"] and after["valid"]):
        record("other_messages", state, "unchanged", {"read_valid": False}, {"invalid_read": True, "rows_read": [before["read"], after["read"]]}); return
    a, b = {r[0]: r[1:] for r in before["rows"]}, {r[0]: r[1:] for r in after["rows"]}
    flags = sum(a[k] != b[k] for k in a if k in b)
    gone = [k for k in a if k not in b]; came = [k for k in b if k not in a]
    tail = {r[0] for r in before["rows"][-len(gone):]} if gone else set()
    allowed = max(0, after["own"] - before["own"]) + len(came)
    unexplained = max(0, len(gone) - allowed) + sum(k not in tail for k in gone)
    record("other_messages", state, "unchanged", {"read_valid": True, "flags_unchanged": flags == 0, "no_unexplained_rows": unexplained == 0},
           {"flags_changed": flags, "left_page": len(gone), "came_on_page": len(came), "own_added": after["own"] - before["own"], "unexplained": unexplained})
def inbox_unread():
    m = re.match(r"Inbox \((\d+)\)", title()); return int(m.group(1)) if m else None

# Start states: plain AX and shell only, never gmail.py ------------------------------------------------------------
def quit_safari():
    if running():
        se('click menu item "Quit Safari" of menu "Safari" of menu bar item "Safari" of menu bar 1')
        until(lambda: not running(), 15)
def close_other_tabs_keep_gmail():
    front_gmail()
    for _ in range(4):
        groups = [e for e in ax.walk(win()) if ax.sattr(e, "AXRole") == "AXTabGroup"]
        tabs = [t for g in groups[:1] for t in ax.children(g) if ax.sattr(t, "AXRole") in ("AXRadioButton", "AXButton")]
        others = [t for t in tabs if " - Gmail" not in (ax.sattr(t, "AXTitle") or "") and ax.sattr(t, "AXTitle")]
        if not others: return
        ax.press(others[0]); time.sleep(0.6)
        se('click menu item "Close Tab" of menu "File" of menu bar item "File" of menu bar 1'); time.sleep(0.6)
def start(state, own=None):
    if state == "closed": quit_safari(); return
    if state == "launching": quit_safari(); subprocess.run(["open", "-a", "Safari"]); return
    close_other_tabs_keep_gmail(); guard()
    if state == "hidden": se("set visible to false")
    elif state == "minimized": ax.AS.AXUIElementSetAttributeValue(win(), ax.cf("AXMinimized"), ctypes.c_void_p.in_dll(ax.CF, "kCFBooleanTrue"))
    elif state == "other_app": subprocess.run(["open", "-a", "Calculator"]); until(lambda: se('return frontmost') == "false", 6)
    elif state == "other_tab":
        subprocess.run(["open", "-a", "Safari", "https://example.com/"]); until(lambda: " - Gmail" not in title(), 10)
    elif state == "not_open":
        se('click menu item "Close Tab" of menu "File" of menu bar item "File" of menu bar 1'); time.sleep(0.8)
        subprocess.run(["open", "-a", "Safari", "https://example.com/"]); until(lambda: "xample" in title(), 12)
        close_gmail = [t for g in [e for e in ax.walk(win()) if ax.sattr(e, "AXRole") == "AXTabGroup"][:1] for t in ax.children(g) if " - Gmail" in (ax.sattr(t, "AXTitle") or "")]
        for t in close_gmail:
            ax.press(t); time.sleep(0.6); se('click menu item "Close Tab" of menu "File" of menu bar item "File" of menu bar 1'); time.sleep(0.6)
    elif state == "other_label":
        ax.press(ax.find(win(), "AXLink", "Sent", exact=True)); time.sleep(2)
    elif state == "message_open":
        target = own or STABLE; token = query_words(target).split()[-1]
        lookup("", target, reload_first=False)
        r = next((x for x in rows() if token in ax.names(x)[0]), None)
        if not r: raise RuntimeError("no row holds the test's unique value, so nothing was opened")
        ax.press(next(e for e in ax.walk(r) if ax.sattr(e, "AXRole") == "AXLink")); until(lambda: ax.find(main_area(), "AXPopUpButton", "Show details"), 10)
    elif state == "search_text":
        f = ax.find(win(), "AXTextField", "Search mail"); ax.focus(f); time.sleep(0.2); se('keystroke "a" using command down'); paste("half typed search")
    elif state == "popup_open":
        ax.press(ax.find(win(), "AXPopUpButton", "Support")); until(lambda: any(ax.sattr(e, "AXRole") == "AXMenu" for e in ax.walk(win())), 5)
    elif state == "compose_empty":
        ax.press(ax.find(win(), "AXButton", "Compose")); until(lambda: ax.find(win(), "AXTextArea", "Message Body"), 8); time.sleep(0.8)
    time.sleep(0.8)
def clean():
    forms = [e for e in ax.walk(win()) if ax.sattr(e, "AXRole") == "AXTextArea" and "Message Body" in ax.names(e)[0]]
    menus = any(ax.sattr(e, "AXRole") == "AXMenu" for e in ax.walk(win()))
    return not forms and not menus

FORCE = {"on": False}
KEEP = {"other_label", "compose_typed"}   # error cases' fixed start states, kept when a run names states
LIMIT_MB = 2500
SAME = {"key": None, "count": 0}
def same_failure(checks, error):
    """Three failures in a row with the same cause stop the run, rather than repeating them through the whole set."""
    failed = [k for k, v in checks.items() if not v]
    key = (str(error)[:60] if error else None, tuple(failed)) if failed else None
    SAME["count"] = SAME["count"] + 1 if key and key == SAME["key"] else (1 if key else 0)
    SAME["key"] = key
    if SAME["count"] >= 3: raise Stop(f"the same failure three times in a row: {key}")
def safari_mb():
    ps = subprocess.run(["ps", "-axo", "rss,comm"], capture_output=True, text=True).stdout.splitlines()
    return sum(int(l.split()[0]) for l in ps if "com.apple.WebKit" in l or l.endswith("/Safari")) // 1024
def page_processes():
    return subprocess.run(["ps", "-axo", "comm"], capture_output=True, text=True).stdout.count("WebKit.WebContent")
def restart_if_large():
    """Page reloads here grow Safari by about 45 MB each, so the verifier restarts it. gmail.py never does this."""
    mb = safari_mb()
    if mb > LIMIT_MB:
        DATA["meta"].setdefault("safari_restarts", []).append({"mb": mb, "page_processes": page_processes()}); save()
        quit_safari(); front_gmail()
def run(function, state, kind, call, check, own=None):
    """start state -> call -> read back. check(result, error) -> checks dict."""
    if ONLY and state not in ONLY and state not in KEEP and not FORCE["on"]: return None
    try:
        restart_if_large()
        start(state, own)
        began = time.monotonic()
        try: result, error = call(), None
        except G.GmailError as e: result, error = None, e
        except Exception as e: result, error = None, e
        seconds = round(time.monotonic() - began, 1)
        if isinstance(error, G.SignedOut): raise Stop("Gmail is signed out: stopping")
        checks = check(result, error)
        record(function, state, kind, checks, {"error": type(error).__name__ + ": " + str(error)[:160] if error else None}, seconds)
        same_failure(checks, error)
        return result
    except Exception as e:
        record(function, state, kind, {"harness": False}, repr(e)[:240]); same_failure({"harness": False}, e); return None

STATES = ["closed", "launching", "hidden", "minimized", "other_app", "not_open", "other_tab", "other_label", "message_open", "search_text", "popup_open", "compose_empty"]
REPLY_IN = {"closed", "other_app", "message_open", "popup_open"}

def state_group(state, index):
    special = index % 2 == 1
    subject, body = new_subject(special), new_body(special)
    before = fingerprint(); unread0 = inbox_unread()
    gap()
    r = run("message_send", state, "normal", lambda: G.message_send(to=ACCOUNT, subject=subject, body=body),
            lambda res, err: {"no_error": err is None, "in_sent": poll(lambda: lookup("in:sent", subject)), "arrived_in_inbox": poll(lambda: lookup("in:inbox", subject)),
                              "return_matches": bool(res) and res["subject"] == subject and res["to"] == [ACCOUNT]})
    run("message_search", state, "normal", lambda: G.message_search(query=f'subject:"{query_words(subject)}"', fields="subject,sender,unread,snippet"),
        lambda res, err: {"no_error": err is None, "found": bool(res) and any(x["subject"] == subject for x in res), "only_asked_fields": bool(res) and set(res[0]) == {"subject", "sender", "unread", "snippet"}, "snippet_has_body": bool(res) and body.split("\n")[0][:10] in res[0]["snippet"]}, own=subject)
    run("message_list", state, "normal", lambda: G.message_list(label="Inbox", limit=50, fields="subject,unread"),
        lambda res, err: {"no_error": err is None, "own_message_listed": bool(res) and any(x["subject"] == subject for x in res)}, own=subject)
    run("message_star", state, "normal", lambda: G.message_star(match=subject),
        lambda res, err: {"no_error": err is None, "starred": poll(lambda: any(n.startswith("starred") for n in lookup("is:starred", subject))), "return_matches": bool(res) and res["starred"]}, own=subject)
    run("message_mark_read", state, "normal", lambda: G.message_mark_read(match=subject),
        lambda res, err: {"no_error": err is None, "read": poll(lambda: (lambda n: n and not re.match(r"(starred, )?unread", n[0]))(lookup("", subject))), "return_matches": bool(res) and res["unread"] is False}, own=subject)
    run("message_get", state, "normal", lambda: G.message_get(match=subject, fields="subject,sender,sender_address,body"),
        lambda res, err: {"no_error": err is None, "subject": bool(res) and res["subject"] == subject, "address": bool(res) and res["sender_address"] == ACCOUNT,
                          "body_exact": bool(res) and res["body"].strip() == body.strip(), "body_matches_page": bool(res) and "".join(res["body"].split("\n")).replace(" ", "") == body_after_reload(subject).replace("\n", "").replace(" ", "")}, own=subject)
    if state in REPLY_IN and (not ONLY or state in ONLY):
        reply = "reply " + new_body(special)
        gap()
        rr = run("message_reply", state, "normal", lambda: G.message_reply(match=subject, body=reply),
            lambda res, err: {"no_error": err is None, "reply_in_conversation": poll(lambda: reply.split("\n")[0][:18] in body_after_reload(subject)), "return_matches": bool(res) and res["to"] == [ACCOUNT]}, own=subject)
    draft = new_subject(special)
    run("draft_create", state, "normal", lambda: G.draft_create(to=ACCOUNT, subject=draft, body=new_body(special)),
        lambda res, err: {"no_error": err is None, "in_drafts": poll(lambda: in_drafts_folder(draft)), "not_sent": not lookup("in:sent", draft), "return_matches": bool(res) and res["draft"]}, own=subject)
    run("message_archive", state, "normal", lambda: G.message_archive(match=subject),
        lambda res, err: {"no_error": err is None, "left_inbox": poll(lambda: not lookup("in:inbox", subject)), "still_exists": bool(lookup("", subject)), "return_matches": bool(res) and res["archived"]}, own=subject)
    run("message_trash", state, "normal", lambda: G.message_trash(match=subject),
        lambda res, err: {"no_error": err is None, "in_bin": poll(lambda: lookup("in:trash", subject)), "not_in_mail": not lookup("", subject), "return_matches": bool(res) and res["trashed"]}, own=subject)
    compare(state, before, fingerprint())

def errors():
    target = new_subject(False)
    gap(); G.message_send(to=ACCOUNT, subject=target, body="error case target")
    for fn, call in [("message_get", lambda: G.message_get(match="No Such Subject 58291")), ("message_star", lambda: G.message_star(match="No Such Subject 58291")),
                     ("message_archive", lambda: G.message_archive(match="No Such Subject 58291")), ("message_trash", lambda: G.message_trash(match="No Such Subject 58291")),
                     ("message_mark_read", lambda: G.message_mark_read(match="No Such Subject 58291")), ("message_reply", lambda: G.message_reply(match="No Such Subject 58291", body="x"))]:
        run(fn, "other_label", "not_found", call, lambda res, err: {"raised_NotFound": isinstance(err, G.NotFound)})
    lookup("", target)
    run("message_star", "other_label", "wrong_sender", lambda: G.message_star(match=target, sender="Someone Else"), lambda res, err: {"raised_NotFound": isinstance(err, G.NotFound), "unchanged": not any(n.startswith("starred") for n in lookup("", target))})
    twin = new_subject(False)
    for i in (1, 2):
        gap(); G.message_send(to=ACCOUNT, subject=twin, body=f"twin {i}")
    poll(lambda: len(lookup("in:inbox", twin)) == 2, 60)
    if len(lookup("in:inbox", twin)) == 2:
        for fn, call in [("message_get", lambda: G.message_get(match=twin)), ("message_star", lambda: G.message_star(match=twin)), ("message_archive", lambda: G.message_archive(match=twin)),
                         ("message_trash", lambda: G.message_trash(match=twin)), ("message_mark_read", lambda: G.message_mark_read(match=twin)), ("message_reply", lambda: G.message_reply(match=twin, body="x"))]:
            run(fn, "other_label", "ambiguous", call, lambda res, err: {"raised_Ambiguous": isinstance(err, G.Ambiguous), "both_in_inbox": len(lookup("in:inbox", twin)) == 2, "both_unstarred": not any(n.startswith("starred") for n in lookup("", twin))})
    else:
        record("message_get", "other_label", "ambiguous", {"gmail_kept_them_apart": False}, "same-subject self-sent messages were joined into one conversation")
    # Guard: nothing may leave the account
    unset = os.environ.pop("GMAIL_ALLOWED_RECIPIENTS")
    probe = new_subject(False)
    run("message_send", "other_label", "guard_unset", lambda: G.message_send(to=ACCOUNT, subject=probe, body="never"), lambda res, err: {"raised": isinstance(err, G.RecipientNotAllowed), "nothing_sent": not lookup("in:sent", probe)})
    run("message_reply", "other_label", "guard_unset", lambda: G.message_reply(match=target, body="never unset"), lambda res, err: {"raised": isinstance(err, G.RecipientNotAllowed), "no_reply": "never unset" not in body_after_reload(target)})
    os.environ["GMAIL_ALLOWED_RECIPIENTS"] = unset
    probe2 = new_subject(False)
    run("message_send", "other_label", "guard_other", lambda: G.message_send(to="someone@example.com", subject=probe2, body="never"), lambda res, err: {"raised": isinstance(err, G.RecipientNotAllowed), "nothing_sent": not lookup("in:sent", probe2)})
    run("message_send", "other_label", "guard_mixed", lambda: G.message_send(to=[ACCOUNT, "someone@example.com"], subject=probe2, body="never"), lambda res, err: {"raised": isinstance(err, G.RecipientNotAllowed), "nothing_sent": not lookup("in:sent", probe2)})
    os.environ["GMAIL_ALLOWED_RECIPIENTS"] = "someone@example.com"
    run("message_reply", "other_label", "guard_other", lambda: G.message_reply(match=target, body="never allowed"), lambda res, err: {"raised": isinstance(err, G.RecipientNotAllowed), "no_reply": "never allowed" not in body_after_reload(target), "no_form_left": clean()})
    os.environ["GMAIL_ALLOWED_RECIPIENTS"] = unset
    # Empty body, and repeats
    empty = new_subject(True)
    gap()
    if run("message_send", "other_label", "empty_body", lambda: G.message_send(to=ACCOUNT, subject=empty), lambda res, err: {"no_error": err is None, "in_sent": poll(lambda: lookup("in:sent", empty))}): pass
    run("message_star", "other_label", "repeat", lambda: (G.message_star(match=empty), G.message_star(match=empty))[1], lambda res, err: {"no_error": err is None, "starred": bool(res) and res["starred"]})
    run("message_mark_read", "other_label", "repeat", lambda: (G.message_mark_read(match=empty), G.message_mark_read(match=empty))[1], lambda res, err: {"no_error": err is None, "read": bool(res) and res["unread"] is False})
    run("message_archive", "other_label", "repeat", lambda: (G.message_archive(match=empty), G.message_archive(match=empty))[1], lambda res, err: {"no_error": err is None})
    # A compose window with typed text blocks everything and stays
    def typed_compose(subject):
        front_gmail(); ax.press(ax.find(win(), "AXButton", "Compose")); until(lambda: ax.find(win(), "AXTextField", "Subject"), 8); time.sleep(0.5)
        ax.focus(ax.find(win(), "AXTextField", "Subject")); time.sleep(0.2); paste(subject); time.sleep(1)
    held = new_subject(False)
    typed_compose(held)
    for fn, call in [("message_send", lambda: G.message_send(to=ACCOUNT, subject="Never " + held, body="x")), ("draft_create", lambda: G.draft_create(to=ACCOUNT, subject="Never " + held)),
                     ("message_star", lambda: G.message_star(match=target)), ("message_archive", lambda: G.message_archive(match=target)), ("message_trash", lambda: G.message_trash(match=target)),
                     ("message_mark_read", lambda: G.message_mark_read(match=target)), ("message_reply", lambda: G.message_reply(match=target, body="never blocked")), ("message_get", lambda: G.message_get(match=target)),
                     ("message_search", lambda: G.message_search(query="x")), ("message_list", lambda: G.message_list())]:
        began = time.monotonic()
        try: call(); err = None
        except Exception as e: err = e
        f = ax.find(win(), "AXTextField", "Subject")
        record(fn, "compose_typed", "blocked", {"raised_StateBlocked": isinstance(err, G.StateBlocked), "typed_text_kept": bool(f) and ax.sattr(f, "AXValue") == held}, repr(err)[:120], round(time.monotonic() - began, 1))
    d = ax.find(win(), "AXButton", "Discard draft");  d and ax.press(d); time.sleep(1.5)
    SUBJECTS.remove(held)
    return target

def discard_open():
    d = ax.find(win(), "AXButton", "Discard draft")
    if d: real_press(d); time.sleep(1.5)
def no_send(race=True):
    """Commands that must not report success. Send and Save & close are never really pressed, so nothing leaves the account."""
    for mode in ("no_effect", "discard"):
        s1, s2 = new_subject(False), new_subject(True); text = f"never sent {rng.randint(1000, 9999)}"
        for fn, call, check in [
                ("message_send", lambda: G.message_send(to=ACCOUNT, subject=s1, body="never"), lambda: {"nothing_in_sent": not lookup("in:sent", s1)}),
                ("draft_create", lambda: G.draft_create(to=ACCOUNT, subject=s2, body="never"), lambda: {} if mode == "no_effect" else {"nothing_in_drafts": not in_drafts_folder(s2)}),
                ("message_reply", lambda: G.message_reply(match=STABLE, body=text), lambda: {"no_reply": text not in body_after_reload(STABLE)})]:
            restart_if_large(); front_gmail(); FAULT["mode"] = mode; FAULT["presses"] = 0; began = time.monotonic()
            try: call(); err = None
            except G.GmailError as e: err = e
            finally: FAULT["mode"] = None
            seconds = round(time.monotonic() - began, 1); pressed = FAULT["presses"]
            discard_open(); checks = {"raised_NotConfirmed": isinstance(err, G.NotConfirmed), "press_intercepted": pressed == 1}; checks.update(check())
            record(fn, "other_label", f"must_not_succeed_{mode}", checks, repr(err)[:120], seconds)
            front_gmail(); discard_open()
    # gm-4's lost draft: does reloading straight after Save & close lose it?
    for i in range(3 if race else 0):
        d = new_subject(False); quit_safari(); front_gmail(); G._ready(); form = G._compose([ACCOUNT], d, "reload race")
        real_press(next(e for e in ax.walk(form) if is_save(e))); until(lambda: G._closed(form), 10); reload_page()
        time.sleep(8)
        print("draft reloaded at once:", d, "in Drafts afterwards:", bool(in_drafts_folder(d)), flush=True)

def is_mine(name, subject): return query_words(subject) in query_words(name)
def reader_body(subject):
    """The reader's copy of the page, or None with what it saw. Counts and test values only."""
    try: return body_after_reload(subject)
    except RuntimeError as e:
        f = ax.find(win(), "AXTextField", "Search mail"); token = query_words(subject).split()[-1]
        print("READER", subject, str(e), "rows", len(rows()), "own", sum(token in ax.names(r)[0] for r in rows()), "field-has-subject", query_words(subject) in query_words(ax.sattr(f, "AXValue") or "") if f else None,
              "message-open", bool(ax.find(main_area(), "AXPopUpButton", "Show details")), "title-gmail", " - Gmail" in title(), flush=True)
        return None
def final():
    """Everything left, with no sends: the run's send limit equals the current count, so Send can't be pressed."""
    FORCE["on"] = True
    target = SUBJECTS[86]; body = "error case target"; token = query_words(target).split()[-1]
    # Empty bodies are refused before anything runs
    for fn, call in [("message_send", lambda b: G.message_send(to=ACCOUNT, subject="Never empty 58291", body=b)), ("draft_create", lambda b: G.draft_create(to=ACCOUNT, subject="Never empty 58291", body=b))]:
        for label, b in (("empty", ""), ("whitespace", " \n\t ")):
            front_gmail(); presses = PRESSES["n"]; count = sends["count"]
            try: call(b); err = None
            except Exception as e: err = e
            record(fn, "other_label", f"refused_{label}_body", {"raised_ValueError": isinstance(err, ValueError), "nothing_pressed": PRESSES["n"] == presses, "no_compose": not G._compose_forms(), "no_send_counted": sends["count"] == count}, repr(err)[:80])
    # Repeats, on a test message that isn't the empty-body one
    def starred(): return any(n.startswith("starred") for n in lookup("is:starred", target))
    def read(): return (lambda n: bool(n) and not re.match(r"(starred, )?unread", n[0]))(lookup("", target))
    run("message_star", "other_label", "repeat", lambda: (G.message_star(match=target), G.message_star(match=target))[1], lambda res, err: {"no_error": err is None, "starred": bool(res) and res["starred"], "read_back": poll(starred)})
    run("message_mark_read", "other_label", "repeat", lambda: (G.message_mark_read(match=target), G.message_mark_read(match=target))[1], lambda res, err: {"no_error": err is None, "read": bool(res) and res["unread"] is False, "read_back": poll(read)})
    # message_get: its own result is kept whether or not the reader manages to read the page
    for state in ("hidden", "minimized", "other_app", "other_label", "message_open", "search_text", "popup_open", "compose_empty"):
        before = fingerprint()
        def check(res, err):
            checks = {"no_error": err is None, "subject": bool(res) and res["subject"] == target, "address": bool(res) and res["sender_address"] == ACCOUNT, "body_exact": bool(res) and res["body"].strip() == body}
            page = reader_body(target)
            checks["reader_found_row"] = page is not None
            checks["body_matches_page"] = page is not None and bool(res) and "".join(res["body"].split("\n")).replace(" ", "") == page.replace("\n", "").replace(" ", "")
            return checks
        run("message_get", state, "normal", lambda: G.message_get(match=target, fields="subject,sender,sender_address,body"), check, own=target)
        compare(state, before, fingerprint())
    # Archive twice: the second finds it by subject outside the Inbox
    run("message_archive", "other_label", "repeat", lambda: (G.message_archive(match=target), G.message_archive(match=target))[1], lambda res, err: {"no_error": err is None, "left_inbox": poll(lambda: not lookup("in:inbox", target)), "still_exists": bool(lookup("", target))})
    # A typed compose blocks draft_create. The earlier case passed no body, which is now refused first.
    held = new_subject(False); front_gmail(); ax.press(ax.find(win(), "AXButton", "Compose")); until(lambda: ax.find(win(), "AXTextField", "Subject"), 8); time.sleep(0.5)
    ax.focus(ax.find(win(), "AXTextField", "Subject")); time.sleep(0.2); paste(held); time.sleep(1)
    try: G.draft_create(to=ACCOUNT, subject="Never " + held, body="x"); err = None
    except Exception as e: err = e
    f = ax.find(win(), "AXTextField", "Subject")
    record("draft_create", "compose_typed", "blocked", {"raised_StateBlocked": isinstance(err, G.StateBlocked), "typed_text_kept": bool(f) and ax.sattr(f, "AXValue") == held}, repr(err)[:120])
    d = ax.find(win(), "AXButton", "Discard draft");  d and ax.press(d); time.sleep(1.5); SUBJECTS.remove(held)
    no_send(race=False)

def cleanup():
    """Trash test messages still outside the Bin, and discard test drafts. Each row must hold the test's whole subject."""
    print("cleanup", flush=True)
    done = {"trashed": 0, "drafts": 0, "left": []}
    for i, subject in enumerate(list(SUBJECTS)):
        if i % 10 == 0: restart_if_large()
        for _ in range(4):
            try:
                front_gmail(); lookup("", subject, reload_first=False)
                mine = [r for r in rows() if is_mine(ax.names(r)[0], subject)]
                if not mine: break
                ax.press(next(e for e in ax.walk(mine[0]) if ax.sattr(e, "AXRole") == "AXCheckBox")); time.sleep(0.8)
                ax.press(ax.find(win(), "AXButton", "Delete", exact=True)); done["trashed"] += 1; time.sleep(2)
            except Exception as e:
                print("cleanup problem", subject, repr(e)[:80], flush=True); break
    for subject in SUBJECTS:
        try:
            front_gmail(); lookup("", subject, reload_first=False)
            if any(is_mine(ax.names(r)[0], subject) for r in rows()): done["left"].append(subject)
        except Exception: done["left"].append(subject)
    front_gmail(); reload_page(); ax.press(ax.find(win(), "AXLink", "Drafts")); time.sleep(4)
    def my_drafts(): return [r for r in rows() if any(is_mine(ax.names(r)[0], s) for s in SUBJECTS)]
    for _ in range(40):
        mine = my_drafts()
        if not mine: break
        ax.press(next(e for e in ax.walk(mine[0]) if ax.sattr(e, "AXRole") == "AXCheckBox")); time.sleep(0.8)
        b = ax.find(win(), "AXButton", "Discard drafts")
        if not b: break
        ax.press(b); done["drafts"] += 1; time.sleep(2)
    done["drafts_left_mine"] = len(my_drafts()); done["drafts_left_other"] = len(rows()) - done["drafts_left_mine"]
    DATA["cleanup"] = done; save(); print(done, flush=True)

try:
    front_gmail()
    button = ax.find(win(), "AXButton", "Google Account:")
    if not button or ACCOUNT not in ax.names(button)[0]: raise Stop("signed-in address doesn't match")
    print("account matches", flush=True)
    names = ["Compose", "Search mail", "Delete", "Archive", "Mark as read", "Send", "Save & close", "Discard draft", "Reply", "Pop-out reply", "Show details", "Not starred", "To recipients", "Subject", "Message Body", "Google Account:"]
    DATA["meta"]["names_used"] = names; DATA["meta"]["language_hint"] = "Minimise" if ax.find(win(), "AXLink", "Starred") else "?"
    for i, state in enumerate(STATES):
        if ONLY and state not in ONLY: continue
        DATA["meta"].setdefault("safari_at_state", []).append({"state": state, "mb": safari_mb(), "page_processes": page_processes()})
        state_group(state, i)
    if "no_send" in ONLY: no_send()
    if "final" in ONLY: final()
    if not ONLY or "errors" in ONLY: errors()
    if not ONLY or "cleanup" in ONLY: cleanup()
    DATA["meta"]["finished"] = time.strftime("%Y-%m-%d %H:%M:%S"); DATA["meta"]["sends"] = sends["count"]; save()
    print("DONE sends", sends["count"], flush=True)
except Stop as stop:
    DATA["meta"]["stopped"] = str(stop); DATA["meta"]["sends"] = sends["count"]; save(); print("STOPPED", stop, "sends", sends["count"], flush=True)
