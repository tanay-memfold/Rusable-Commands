"""Verify contacts.py inside the VM: python3 verify_contacts.py <group> <seed> <state|errors|blocked> ...
Every case: set up with plain scripting (never contacts.py), put Contacts into a start state, call the function with fresh made-up
values, read Contacts' own database, check every field, that nothing else changed, and the screen."""
import ctypes, hashlib, json, os, sys, time, traceback
HOME = os.path.expanduser("~"); TOOLS = f"{HOME}/contacts-test"; sys.path[:0] = [TOOLS]
import ax, bigclip, con_db as D, contacts as C
from vcommon import Recorder, Values, osa, se, sh, wait
GROUP, SEED, ONLY = sys.argv[1], int(sys.argv[2]), sys.argv[3:]
V = Values(SEED); APP = "Contacts"; FAILS = {}
REC = Recorder(GROUP, {"versions": C._versions(), "code_sha": hashlib.sha256(open(C.__file__, "rb").read()).hexdigest()[:12], "seed": SEED, "started": time.strftime("%Y-%m-%d %H:%M:%S")})
RESUME = int(os.environ.get("RESUME", "0")); ONLY_FNS = set(filter(None, os.environ.get("FNS", "").split(",")))
COUNT = {"n": 0}; open(f"{TOOLS}/verifier.pid", "w").write(str(os.getpid()))
PREP = r"""function run(argv) {
  const C = Application("Contacts"), a = JSON.parse(argv[1]);
  switch (argv[0]) {
    case "person": { const p = C.Person({firstName: a.first, lastName: a.last || ""}); if (a.company) p.organization = a.company; if (a.note) p.note = a.note; C.people.push(p);
      if (a.email) p.emails.push(C.Email({label: "work", value: a.email})); if (a.phone) p.phones.push(C.Phone({label: "mobile", value: a.phone})); C.save();
      if (a.group) { C.add(p, {to: C.groups().find(g => g.name() === a.group)}); C.save(); } return "ok"; }
    case "group": C.groups.push(C.Group({name: a.name})); C.save(); return "ok";
    case "sweep": { for (const g of C.groups()) if (!a.groups.includes(g.name())) C.delete(g);
      for (const p of C.people()) if (!a.people.includes(p.name())) C.delete(p); C.save(); return "ok"; }
  }}"""
def prep(op, **a): return osa(PREP, op, json.dumps(a), lang="JavaScript")
A = lambda: ax.app(APP)
def running(): return bool(sh(f"pgrep -x {APP}"))
def win(): return next((c for c in ax.children(A()) if ax.sattr(c, "AXRole") == "AXWindow"), None)
def sheets(): return [e for e in ax.children(win()) if ax.sattr(e, "AXRole") == "AXSheet"] if win() else []
def menu(m, i): return se(f'click menu item "{i}" of menu "{m}" of menu bar item "{m}" of menu bar 1', APP)
def outline(t): return next(e for e in ax.walk(win()) if ax.sattr(e, "AXRole") == "AXOutline" and ax.sattr(e, "AXTitle") == t)
def row(o, n): return next((x for x in ax.children(o) if ax.sattr(x, "AXRole") == "AXRow" and any(ax.sattr(y, "AXValue") == n for y in ax.walk(x))), None)
def pick(t, n):
    o = outline(t); ax.focus(o); time.sleep(0.2); ax.AS.AXUIElementSetAttributeValue(row(o, n), ax.cf("AXSelected"), ax.TRUE); time.sleep(0.5)
def done_btn(): return win() and next((e for e in ax.walk(win()) if ax.sattr(e, "AXRole") == "AXButton" and ax.sattr(e, "AXTitle") == "Done"), None)
def quit_app():
    if running(): sh("osascript -e 'tell application \"Contacts\" to quit'"); wait(lambda: not running(), 15)
def front():
    sh("open -b com.apple.AddressBook"); wait(running, 15); sh("osascript -e 'tell application \"Contacts\" to activate'"); se("set visible to true", APP); wait(win, 10)
    w = win()
    if w and ax.attr(w, "AXMinimized") == ax.TRUE.value:
        ax.AS.AXUIElementSetAttributeValue(w, ax.cf("AXMinimized"), ctypes.c_void_p.in_dll(ax.CF, "kCFBooleanFalse")); time.sleep(0.6)
    if not win(): sh("open -b com.apple.AddressBook"); wait(win, 10)
    for s in sheets():
        c = ax.find(s, "AXButton", "Cancel", exact=True)
        if c: ax.press(c); time.sleep(0.6)
    d = done_btn()
    if d: ax.press(d); time.sleep(0.8)
    s = next((e for e in ax.walk(win()) if ax.sattr(e, "AXSubrole") == "AXSearchField"), None)
    if s and ax.sattr(s, "AXValue"):
        c = ax.find(s, "AXButton", "cancel"); c and ax.press(c); se("key code 53", APP); time.sleep(0.4)
def start(state):
    if state in ("closed", "launching"):
        quit_app()
        if state == "launching": sh("open -b com.apple.AddressBook")
        return
    front(); wait(lambda: row(outline("Contact Lists List"), "All Contacts"), 5)
    if state == "open": pick("Contact Lists List", "All Contacts")
    elif state == "other_view": pick("Contact Lists List", "Base Team")
    elif state == "hidden": se("set visible to false", APP)
    elif state == "minimized": ax.AS.AXUIElementSetAttributeValue(win(), ax.cf("AXMinimized"), ax.TRUE)
    elif state == "other_app": sh("open -a Calculator"); wait(lambda: se("return frontmost", APP) == "false", 8)
    elif state == "search_text":
        s = next(e for e in ax.walk(win()) if ax.sattr(e, "AXSubrole") == "AXSearchField"); ax.focus(s); time.sleep(0.3); se('keystroke "half typed"', APP)
    elif state == "selected_row": pick("Contact Lists List", "All Contacts"); pick("Contact List", "Standup Person")
    elif state == "no_window": menu("File", "Close"); wait(lambda: not win(), 5)
    time.sleep(0.6)
BASE_P, BASE_G = ["Standup Person", "Standup Personal", "Dentist Clinic"], ["Base Team", "Base Family"]
def base():
    if all(n in D.snapshot()["groups"].values() for n in BASE_G): return
    for g in BASE_G: prep("group", name=g)
    prep("person", first="Standup", last="Person", group="Base Team", email="standup@example.com", phone="+1 555 0101")
    prep("person", first="Standup", last="Personal", note="keep me"); prep("person", first="Dentist", last="Clinic", company="Room 4", group="Base Family")
    prep("person", first="Twin", last="Same"); prep("person", first="Twin", last="Same")
    wait(lambda: len(D.snapshot()["people"]) >= 5, 15)
def sweep(): prep("sweep", groups=BASE_G, people=BASE_P + ["Twin Same"])
def clean():
    if not running() or not win(): return True
    return not (sheets() or done_btn() or any(ax.sattr(e, "AXRole") == "AXMenu" for e in ax.walk(win())))
def case(fn, mode, state, kind, setup, call, read, watched=()):
    if ONLY_FNS and fn not in ONLY_FNS: return
    COUNT["n"] += 1
    if COUNT["n"] <= RESUME or FAILS.get((fn, mode), 0) >= 3: return
    print(f"CASE {COUNT['n']} {fn} {mode} {state} {kind}", flush=True)
    try:
        names = setup() or []
        time.sleep(0.4); start(state)
        before = D.snapshot(); was = se("return frontmost", APP) if running() else "false"
        began = time.monotonic()
        try: res, err = call(), None
        except (C.ContactsError, ValueError) as e: res, err = None, e
        secs = round(time.monotonic() - began, 1); end = time.monotonic() + 12
        while True:
            snap = D.snapshot(); last = read(snap, res, err)
            if all(last.values()) or time.monotonic() > end: break
            time.sleep(0.5)
        last["others_unchanged"] = not D.others(before, snap, set(names) | set(watched))
        last["base_lists_kept"] = all(n in snap["groups"].values() for n in BASE_G)
        if mode == "ui": last["nothing_left_open"] = clean()
        else: last["stayed_in_background"] = not running() or se("return frontmost", APP) == was
        REC.case(fn, mode, state, kind, last, repr(err)[:160] if err else None, secs)
        if not all(last.values()): FAILS[(fn, mode)] = FAILS.get((fn, mode), 0) + 1
    except Exception:
        REC.case(fn, mode, state, kind, {"harness": False}, traceback.format_exc()[-300:]); FAILS[(fn, mode)] = FAILS.get((fn, mode), 0) + 1
SP = ["Zoë", "Jürgen", 'Ana "Q"', "O'Neil", "Renée ✨"]
def nm(i):
    w = V.rng.choice(SP) if i % 2 else V.rng.choice(["Quartz", "Larch", "Maple", "Copper", "Harbor"])
    return f"{w}{V.rng.randint(100, 9999)}", f"Family{V.rng.randint(100, 9999)}"
def text(i): return V.special() if i % 2 else V.word()
def run_state(state, i):
    for mode in os.environ.get("MODES", "background,ui").split(","):
        f, l = nm(i); full = f"{f} {l}"; em = f"t{V.rng.randint(1000, 9999)}@example.com"; ph = f"+1 555 {V.rng.randint(1000, 9999)}"; note = f"note {V.word(1)}\nsecond line {i}"
        case("contact_create", mode, state, "all_fields", lambda: [full], lambda: C.contact_create(first=f, last=l, company="Quartz & Co", email=em, phone=ph, note=note, mode=mode),
             lambda s, r, e: (lambda p: {"no_error": e is None, "one": len(p) == 1, "company": bool(p) and p[0]["company"] == "Quartz & Co", "email": bool(p) and p[0]["emails"] == [em], "phone": bool(p) and [x.replace(" ", "") for x in p[0]["phones"]] == [ph.replace(" ", "")], "note": bool(p) and p[0]["note"] == note, "return": bool(r) and r["name"] == full})(D.named(s, full)))
        co = f"Company {V.rng.randint(1000, 9999)}"
        case("contact_create", mode, state, "company_only", lambda: [co], lambda: C.contact_create(company=co, mode=mode),
             lambda s, r, e: (lambda p: {"no_error": e is None, "one": len(p) == 1, "no_names": bool(p) and not p[0]["first"] and not p[0]["last"]})(D.named(s, co)))
        uf, ul = nm(i + 1); uold = f"{uf} {ul}"; nf = nm(i)[0]; unew = f"{nf} {ul}"
        case("contact_update", mode, state, "fields", lambda: prep("person", first=uf, last=ul, email="old@example.com", phone="+1 555 0000", note="old") and [uold, unew], lambda: C.contact_update(match=uold, first=nf, company="Harbor Ltd", email="new@example.com", note="line one\nline two", mode=mode),
             lambda s, r, e: (lambda p: {"no_error": e is None, "old_gone": not D.named(s, uold), "company": bool(p) and p[0]["company"] == "Harbor Ltd", "email": bool(p) and p[0]["emails"] == ["new@example.com"], "phone_kept": bool(p) and len(p[0]["phones"]) == 1, "note": bool(p) and p[0]["note"] == "line one\nline two", "last_kept": bool(p) and p[0]["last"] == ul})(D.named(s, unew)))
        df, dl = nm(i); dn = f"{df} {dl}"
        case("contact_delete", mode, state, "normal", lambda: prep("person", first=df, last=dl, group="Base Team") and [dn], lambda: C.contact_delete(match=dn, mode=mode),
             lambda s, r, e: {"no_error": e is None, "gone": not D.named(s, dn), "return": bool(r) and r["deleted"]})
        g1, g2, g3, g4 = text(i), text(i + 1), text(i), text(i + 1)
        mf, ml = nm(i); mn = f"{mf} {ml}"
        case("group_create", mode, state, "normal", lambda: [], lambda: C.group_create(name=g1, mode=mode), lambda s, r, e: {"no_error": e is None, "one": list(s["groups"].values()).count(g1) == 1, "return": bool(r) and r["name"] == g1})
        case("group_rename", mode, state, "with_member", lambda: prep("group", name=g2) and prep("person", first=mf, last=ml, group=g2) and [mn], lambda: C.group_rename(name=g2, to=g3, mode=mode),
             lambda s, r, e: (lambda p: {"no_error": e is None, "renamed": g3 in s["groups"].values() and g2 not in s["groups"].values(), "member_kept": bool(p) and p[0]["groups"] == [g3]})(D.named(s, mn)))
        kf, kl = nm(i); kn = f"{kf} {kl}"
        case("group_delete", mode, state, "keeps_cards", lambda: prep("group", name=g4) and prep("person", first=kf, last=kl, group=g4) and [kn], lambda: C.group_delete(name=g4, mode=mode),
             lambda s, r, e: (lambda p: {"no_error": e is None, "gone": g4 not in s["groups"].values(), "card_kept": len(p) == 1 and p[0]["groups"] == []})(D.named(s, kn)))
        if mode == "background":
            case("contact_list", mode, state, "all", lambda: [], lambda: C.contact_list(fields="name,company", limit=500, mode=mode), lambda s, r, e: {"no_error": e is None, "names_match_db": r is not None and sorted(x["name"] for x in r) == sorted(p["name"] for p in s["people"].values()), "only_fields": bool(r) and set(r[0]) == {"name", "company"}})
            case("contact_list", mode, state, "group", lambda: [], lambda: C.contact_list(group="Base Family", mode=mode), lambda s, r, e: {"no_error": e is None, "match_db": r is not None and sorted(x["name"] for x in r) == sorted(p["name"] for p in s["people"].values() if "Base Family" in p["groups"])})
            q = f"Needle{V.rng.randint(1000, 9999)}"
            case("contact_search", mode, state, "by_note", lambda: prep("person", first="Search", last=f"T{q}x", note=f"has {q.lower()} inside") and [], lambda: C.contact_search(query=q, mode=mode), lambda s, r, e: {"no_error": e is None, "found_it": bool(r) and len(r) == 1})
            gf, gl = nm(i); gn = f"{gf} {gl}"
            case("contact_get", mode, state, "normal", lambda: prep("person", first=gf, last=gl, email="g@example.com", phone="+1 555 0123", note="got it", company="Co") and [], lambda: C.contact_get(match=gn, mode=mode),
                 lambda s, r, e: (lambda p: {"no_error": e is None, "fields_match_db": bool(r) and bool(p) and all(r[k] == p[0][k] for k in ("first", "last", "company", "note", "emails"))})(D.named(s, gn)))
            case("group_list", mode, state, "normal", lambda: [], lambda: C.group_list(mode=mode), lambda s, r, e: {"no_error": e is None, "names_match_db": r is not None and sorted(x["name"] for x in r) == sorted(s["groups"].values())})
            af, al = nm(i); an = f"{af} {al}"
            case("group_add", mode, state, "normal", lambda: prep("person", first=af, last=al) and [an], lambda: C.group_add(match=an, group="Base Family", mode=mode), lambda s, r, e: (lambda p: {"no_error": e is None, "added": bool(p) and p[0]["groups"] == ["Base Family"]})(D.named(s, an)))
            bf, bl = nm(i); bn = f"{bf} {bl}"
            case("group_remove", mode, state, "normal", lambda: prep("person", first=bf, last=bl, group="Base Team") and [bn], lambda: C.group_remove(match=bn, group="Base Team", mode=mode), lambda s, r, e: (lambda p: {"no_error": e is None, "removed_card_kept": len(p) == 1 and p[0]["groups"] == []})(D.named(s, bn)))
    sweep()
def errors():
    st = "other_view"; nope = "No Such Person 58291"
    for mode in ("background", "ui"):
        for fn, call in [("contact_update", lambda: C.contact_update(match=nope, company="x", mode=mode)), ("contact_delete", lambda: C.contact_delete(match=nope, mode=mode)), ("group_rename", lambda: C.group_rename(name=nope, to="x y", mode=mode)), ("group_delete", lambda: C.group_delete(name=nope, mode=mode))]:
            case(fn, mode, st, "not_found", lambda: [], call, lambda s, r, e: {"raised_NotFound": isinstance(e, C.NotFound)})
        for fn, call in [("contact_update", lambda: C.contact_update(match="Twin Same", company="x", mode=mode)), ("contact_delete", lambda: C.contact_delete(match="Twin Same", mode=mode))]:
            case(fn, mode, st, "ambiguous", lambda: [], call, lambda s, r, e: {"raised_Ambiguous": isinstance(e, C.Ambiguous), "both_kept": len(D.named(s, "Twin Same")) == 2 and not any(p["company"] for p in D.named(s, "Twin Same"))})
        case("group_create", mode, st, "already_exists", lambda: [], lambda: C.group_create(name="Base Team", mode=mode), lambda s, r, e: {"raised": isinstance(e, C.AlreadyExists), "one": list(s["groups"].values()).count("Base Team") == 1})
        case("group_rename", mode, st, "already_exists", lambda: [], lambda: C.group_rename(name="Base Team", to="Base Family", mode=mode), lambda s, r, e: {"raised": isinstance(e, C.AlreadyExists), "kept": "Base Team" in s["groups"].values()})
        case("contact_create", mode, st, "no_name", lambda: [], lambda: C.contact_create(email="x@example.com", mode=mode), lambda s, r, e: {"raised": isinstance(e, ValueError)})
    for fn, call in [("group_add", lambda: C.group_add(match="Standup Person", group="Base Family", mode="ui")), ("group_remove", lambda: C.group_remove(match="Standup Person", group="Base Team", mode="ui")), ("contact_get", lambda: C.contact_get(match="Standup Person", mode="ui"))]:
        case(fn, "ui", st, "not_supported", lambda: [], call, lambda s, r, e: {"raised": isinstance(e, C.NotSupported)})
    for fn, call in [("contact_get", lambda: C.contact_get(match=nope)), ("group_add", lambda: C.group_add(match=nope, group="Base Team")), ("group_add", lambda: C.group_add(match="Standup Person", group=nope))]:
        case(fn, "background", st, f"not_found_{COUNT['n']}", lambda: [], call, lambda s, r, e: {"raised_NotFound": isinstance(e, C.NotFound)})
    case("contact_get", "background", st, "ambiguous", lambda: [], lambda: C.contact_get(match="Twin Same"), lambda s, r, e: {"raised_Ambiguous": isinstance(e, C.Ambiguous)})
    sweep()
def big(fn, setup, call, read):
    """A very large clipboard before the call: the call must work and the clipboard must come back exactly."""
    box = {}
    def prepare():
        names = setup() or []; box["want"] = bigclip.fill(V.rng.randint(1, 10**9)); return names
    def checks(s, r, e):
        c = read(s, r, e); c.update(bigclip.check(box["want"])); return c
    case(fn, "ui", "other_view", "large_clipboard", prepare, call, checks)
def details():
    """The details commands (background) in several start states, read back from the database and, for vCard, from the file."""
    os.makedirs(f"{TOOLS}/vcf", exist_ok=True)
    for state in ("closed", "other_view", "hidden", "other_app"):
        i = V.rng.randint(1, 3)
        def person(**k):
            f, l = nm(i); prep("person", first=f, last=l, **k); return f"{f} {l}"
        def one(n, fn): return (lambda d: fn(d[0]) if len(d) == 1 else False)(D.details(n))
        a = person(phone="+1 555 0111", email="keep@example.com"); job = f"Lead {V.word(1)}"
        case("contact_set_job_title", "background", state, "normal", lambda: [a], lambda: C.contact_set_job_title(match=a, job_title=job), lambda s, r, e: {"no_error": e is None, "db": one(a, lambda d: d["job"] == job), "others_on_card_kept": one(a, lambda d: len(d["phones"]) == 1 and len(d["emails"]) == 1), "return": bool(r) and r["job_title"] == job})
        b = person(phone="+1 555 0112"); hn = f"+1 555 {V.rng.randint(1000, 9999)}"
        case("contact_add_phone", "background", state, "home", lambda: [b], lambda: C.contact_add_phone(match=b, number=hn, label="home"), lambda s, r, e: {"no_error": e is None, "db_both": one(b, lambda d: ("home", hn) in d["phones"] and len(d["phones"]) == 2), "return": bool(r) and {"label": "home", "value": hn} in r["phones"]})
        c0 = person(); c = c0; n1, n2 = f"+1 555 {V.rng.randint(1000, 9999)}", f"+1 555 {V.rng.randint(1000, 9999)}"
        C.contact_add_phone(match=c, number=n1, label="home"); C.contact_add_phone(match=c, number="+1 555 0113", label="mobile")
        case("contact_set_phone", "background", state, "home_only", lambda: [c], lambda: C.contact_set_phone(match=c, label="home", number=n2), lambda s, r, e: {"no_error": e is None, "home_changed": one(c, lambda d: ("home", n2) in d["phones"] and ("home", n1) not in d["phones"]), "mobile_kept": one(c, lambda d: ("mobile", "+1 555 0113") in d["phones"])})
        d0 = person(); C.contact_add_phone(match=d0, number="+1 555 0114", label="home"); C.contact_add_phone(match=d0, number="+1 555 0115", label="mobile")
        case("contact_remove_phone", "background", state, "mobile", lambda: [d0], lambda: C.contact_remove_phone(match=d0, label="mobile"), lambda s, r, e: {"no_error": e is None, "gone": one(d0, lambda d: not [x for x in d["phones"] if x[0] == "mobile"]), "home_kept": one(d0, lambda d: ("home", "+1 555 0114") in d["phones"])})
        e0 = person(email="first@example.com"); em = f"t{V.rng.randint(1000, 9999)}@example.com"
        case("contact_add_email", "background", state, "second", lambda: [e0], lambda: C.contact_add_email(match=e0, address=em, label="home"), lambda s, r, e: {"no_error": e is None, "db_both": one(e0, lambda d: ("home", em) in d["emails"] and len(d["emails"]) == 2)})
        g0 = person(email="w@example.com"); C.contact_add_email(match=g0, address="h@example.com", label="home")
        case("contact_remove_email", "background", state, "home", lambda: [g0], lambda: C.contact_remove_email(match=g0, label="home"), lambda s, r, e: {"no_error": e is None, "gone": one(g0, lambda d: not [x for x in d["emails"] if x[0] == "home"]), "work_kept": one(g0, lambda d: ("work", "w@example.com") in d["emails"])})
        h0 = person(phone="+1 555 0116", email="q@example.com"); C.contact_set_job_title(match=h0, job_title="Keeper")
        case("contact_details", "background", state, "normal", lambda: [], lambda: C.contact_details(match=h0), lambda s, r, e: (lambda d: {"no_error": e is None, "job": bool(r) and r["job_title"] == d["job"], "phones": bool(r) and [x["value"] for x in r["phones"]] == [x[1] for x in d["phones"]], "emails": bool(r) and [(x["label"], x["value"]) for x in r["emails"]] == d["emails"]})(D.details(h0)[0]))
        p1, p2 = f"{TOOLS}/vcf/{V.word(1)}.vcf", f"{TOOLS}/vcf/{V.word(1)}.vcf"; i0 = person(email="v@example.com")
        case("contact_export_vcard", "background", state, "one", lambda: [], lambda: C.contact_export_vcard(path=p1, match=i0), lambda s, r, e: (lambda t: {"no_error": e is None, "one_card": t.count("BEGIN:VCARD") == 1 and t.count("END:VCARD") == 1, "right_card": i0.split()[0].replace(",", "") in t and "v@example.com" in t, "return": bool(r) and r["count"] == 1})(open(p1, encoding="utf-8").read() if os.path.exists(p1) else ""))
        case("contact_export_vcard", "background", state, "all", lambda: [], lambda: C.contact_export_vcard(path=p2), lambda s, r, e: (lambda t: {"no_error": e is None, "count_matches_db": t.count("BEGIN:VCARD") == len(s["people"]), "return": bool(r) and r["count"] == len(s["people"])})(open(p2, encoding="utf-8").read() if os.path.exists(p2) else ""))
        sweep()
    st = "other_view"; nope = "No Such Person 58291"
    for fn, call in [("contact_details", lambda: C.contact_details(match=nope)), ("contact_set_job_title", lambda: C.contact_set_job_title(match=nope, job_title="x")), ("contact_add_phone", lambda: C.contact_add_phone(match=nope, number="1")), ("contact_set_phone", lambda: C.contact_set_phone(match="Standup Personal", label="home", number="1")), ("contact_remove_phone", lambda: C.contact_remove_phone(match="Standup Personal", label="home")), ("contact_add_email", lambda: C.contact_add_email(match=nope, address="x")), ("contact_remove_email", lambda: C.contact_remove_email(match="Standup Personal", label="home")), ("contact_export_vcard", lambda: C.contact_export_vcard(path=f"{TOOLS}/vcf/z.vcf", match=nope))]:
        case(fn, "background", st, "not_found", lambda: [], call, lambda s, r, e: {"raised_NotFound": isinstance(e, C.NotFound)})
    case("contact_set_job_title", "background", st, "ambiguous", lambda: [], lambda: C.contact_set_job_title(match="Twin Same", job_title="x"), lambda s, r, e: {"raised": isinstance(e, C.Ambiguous)})
    open(f"{TOOLS}/vcf/taken.vcf", "w").write("keep")
    case("contact_export_vcard", "background", st, "already_exists", lambda: [], lambda: C.contact_export_vcard(path=f"{TOOLS}/vcf/taken.vcf"), lambda s, r, e: {"raised": isinstance(e, C.AlreadyExists), "kept": open(f"{TOOLS}/vcf/taken.vcf").read() == "keep"})
    case("contact_export_vcard", "background", st, "bad_type", lambda: [], lambda: C.contact_export_vcard(path=f"{TOOLS}/vcf/x.txt"), lambda s, r, e: {"raised": isinstance(e, ValueError)})
    sweep()
def merging():
    for state in ("closed", "other_view", "hidden", "minimized", "other_app", "search_text", "selected_row", "no_window"):
        f, l = nm(0); n = f"{f} {l}"; e1, e2 = f"a{V.rng.randint(1000, 9999)}@example.com", f"b{V.rng.randint(1000, 9999)}@example.com"; p1, p2 = f"+1 555 {V.rng.randint(1000, 9999)}", f"+1 555 {V.rng.randint(1000, 9999)}"
        case("contact_merge", "ui", state, "two_cards", lambda: prep("person", first=f, last=l, email=e1, phone=p1) and prep("person", first=f, last=l, email=e2, phone=p2, company="Merged Co") and [n], lambda: C.contact_merge(match=n),
             lambda s, r, e: (lambda p: {"no_error": e is None, "one_card": len(p) == 1, "both_emails": bool(p) and set(p[0]["emails"]) == {e1, e2}, "both_phones": bool(p) and {x.replace(" ", "") for x in p[0]["phones"]} == {p1.replace(" ", ""), p2.replace(" ", "")}, "company": bool(p) and p[0]["company"] == "Merged Co"})(D.named(s, n)))
    f, l = nm(0); n = f"{f} {l}"
    case("contact_merge", "ui", "other_view", "three_cards", lambda: prep("person", first=f, last=l, email="c1@example.com") and prep("person", first=f, last=l, email="c2@example.com") and prep("person", first=f, last=l, email="c3@example.com") and [n], lambda: C.contact_merge(match=n), lambda s, r, e: (lambda p: {"no_error": e is None, "one_card": len(p) == 1, "all_emails": bool(p) and len(p[0]["emails"]) == 3})(D.named(s, n)))
    case("contact_merge", "ui", "other_view", "not_found", lambda: [], lambda: C.contact_merge(match="No Such Person 58291"), lambda s, r, e: {"raised": isinstance(e, C.NotFound)})
    case("contact_merge", "ui", "other_view", "only_one", lambda: [], lambda: C.contact_merge(match="Dentist Clinic"), lambda s, r, e: {"raised": isinstance(e, ValueError), "kept": len(D.named(s, "Dentist Clinic")) == 1})
    sweep()
def large_clipboard():
    f, l = nm(1); full = f"{f} {l}"; note = f"note {V.word(1)}\nsecond line"; uf, ul = nm(0); uold = f"{uf} {ul}"; nf = nm(1)[0]; unew = f"{nf} {ul}"; df, dl = nm(0); dn = f"{df} {dl}"
    g1, g2, g3, g4 = V.special(), V.word(), V.special(), V.word()
    big("contact_create", lambda: [full], lambda: C.contact_create(first=f, last=l, company="Quartz & Co", note=note, mode="ui"),
        lambda s, r, e: (lambda p: {"no_error": e is None, "one": len(p) == 1, "company": bool(p) and p[0]["company"] == "Quartz & Co", "note": bool(p) and p[0]["note"] == note})(D.named(s, full)))
    big("contact_update", lambda: prep("person", first=uf, last=ul) and [uold, unew], lambda: C.contact_update(match=uold, first=nf, company="Harbor Ltd", mode="ui"),
        lambda s, r, e: (lambda p: {"no_error": e is None, "old_gone": not D.named(s, uold), "company": bool(p) and p[0]["company"] == "Harbor Ltd"})(D.named(s, unew)))
    big("contact_delete", lambda: prep("person", first=df, last=dl) and [dn], lambda: C.contact_delete(match=dn, mode="ui"), lambda s, r, e: {"no_error": e is None, "gone": not D.named(s, dn)})
    big("group_create", lambda: [], lambda: C.group_create(name=g1, mode="ui"), lambda s, r, e: {"no_error": e is None, "one": list(s["groups"].values()).count(g1) == 1})
    big("group_rename", lambda: prep("group", name=g2) and [], lambda: C.group_rename(name=g2, to=g3, mode="ui"), lambda s, r, e: {"no_error": e is None, "renamed": g3 in s["groups"].values() and g2 not in s["groups"].values()})
    big("group_delete", lambda: prep("group", name=g4) and [], lambda: C.group_delete(name=g4, mode="ui"), lambda s, r, e: {"no_error": e is None, "gone": g4 not in s["groups"].values()})
    mf, ml = nm(0); mn = f"{mf} {ml}"
    big("contact_merge", lambda: prep("person", first=mf, last=ml, email="m1@example.com") and prep("person", first=mf, last=ml, email="m2@example.com") and [mn], lambda: C.contact_merge(match=mn),
        lambda s, r, e: (lambda p: {"no_error": e is None, "one_card": len(p) == 1, "both_emails": bool(p) and set(p[0]["emails"]) == {"m1@example.com", "m2@example.com"}})(D.named(s, mn)))
    sweep()
def blocked():
    front(); menu("File", "New Card"); wait(done_btn, 5); time.sleep(0.6); se('keystroke "half typed"', APP); time.sleep(0.6)
    before = D.snapshot()
    for fn, call in [("contact_create", lambda: C.contact_create(first="Never", mode="ui")), ("contact_update", lambda: C.contact_update(match="Dentist Clinic", company="Never", mode="ui")), ("contact_delete", lambda: C.contact_delete(match="Dentist Clinic", mode="ui")), ("group_create", lambda: C.group_create(name="Never L", mode="ui")), ("group_rename", lambda: C.group_rename(name="Base Family", to="Never L", mode="ui")), ("group_delete", lambda: C.group_delete(name="Base Family", mode="ui"))]:
        try: call(); err = None
        except Exception as e: err = e
        f = next((e for e in ax.walk(win()) if ax.sattr(e, "AXDescription") == "First"), None)
        REC.case(fn, "ui", "typed_text", "blocked", {"raised_StateBlocked": isinstance(err, C.StateBlocked), "typed_kept": bool(f) and ax.sattr(f, "AXValue") == "half typed", "nothing_changed": not D.others(before, D.snapshot(), ())}, repr(err)[:120])
    d = done_btn()
    # Leaves the half-typed test card to be swept.
    if d: ax.press(d); time.sleep(1)
    sweep()
STATES = ["closed", "launching", "open", "other_view", "hidden", "minimized", "other_app", "search_text", "selected_row", "no_window"]
try:
    base()
    for i, state in enumerate(STATES):
        if state in ONLY:
            print(f"== state starts: {state} at {time.strftime('%H:%M:%S')}", flush=True); run_state(state, i)
    for label, fn in (("errors", errors), ("blocked", blocked), ("large_clipboard", large_clipboard), ("details", details), ("merging", merging)):
        if label in ONLY:
            print(f"== state starts: {label} at {time.strftime('%H:%M:%S')}", flush=True); fn()
finally:
    REC.data["meta"]["finished"] = time.strftime("%Y-%m-%d %H:%M:%S"); REC.save(); print("DONE", flush=True)
