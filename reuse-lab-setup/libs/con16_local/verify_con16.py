"""verify_con16.py <group> <seed> <states...>: Contacts' birthday and address commands, read back from Contacts' database."""
import datetime, json, os, sqlite3, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import contacts as C, vkit
from vcommon import osa, sh, se
group, seed, states = sys.argv[1], int(sys.argv[2]), sys.argv[3:]
APP = "Contacts"
DBP = os.path.expanduser("~/Library/Application Support/AddressBook/AddressBook-v22.abcddb")
EPOCH = datetime.datetime(2001, 1, 1)
def card(first, last):
    """[(birthday, [(label, street, city, zip, country)])] for the cards with this name, straight from the database."""
    db = sqlite3.connect(f"file:{DBP}?mode=ro", uri=True, timeout=5)
    try:
        out = []
        for pk, b in db.execute("select Z_PK, ZBIRTHDAY from ZABCDRECORD where ZFIRSTNAME = ? and ZLASTNAME = ?", (first, last)):
            day = (EPOCH + datetime.timedelta(seconds=b)).date().isoformat() if b is not None else None  # stored at noon, so the date is safe
            adds = [((l or "").replace("_$!<", "").replace(">!$_", "").lower(), s or "", c or "", z or "", n or "")
                    for l, s, c, z, n in db.execute("select ZLABEL, ZSTREET, ZCITY, ZZIPCODE, ZCOUNTRYNAME from ZABCDPOSTALADDRESS where ZOWNER = ? order by Z_PK", (pk,))]
            out.append((day, adds))
        return out
    finally: db.close()
def running(): return bool(sh("pgrep -x Contacts"))
def front_app():
    try: return osa('tell application "System Events" to return name of first process whose frontmost is true')
    except RuntimeError: return ""
def start(state):
    if state == "closed":
        if running(): osa('tell application "Contacts" to quit'); [time.sleep(0.5) for _ in range(30) if running()]
        return
    if not running(): sh("open -b com.apple.AddressBook"); [time.sleep(0.5) for _ in range(30) if not running()]; time.sleep(2)
    se("set visible to true\nset frontmost to true", APP); time.sleep(0.5)
    if state == "hidden": se("set visible to false", APP)
    elif state == "other_app": sh("open -a Calculator"); [time.sleep(0.3) for _ in range(20) if front_app() == APP]
    time.sleep(0.5)
K = vkit.Kit("con16", C, APP, group, seed, C.ContactsError, start)
MAKE = r"""function run(argv) { const C = Application("Contacts"), a = JSON.parse(argv[0]); for (let i = 0; i < a.n; i++) C.people.push(C.Person({firstName: a.first, lastName: a.last})); C.save(); return "ok"; }"""
n = {"i": 0}
def person(twin=False):
    n["i"] += 1; first = K.V.special().split()[0] if n["i"] % 2 else K.V.word(1).split()[0]; last = f"Tester{n['i']}{K.V.rng.randint(100, 999)}"
    if not running(): sh("open -g -j -b com.apple.AddressBook"); [time.sleep(0.5) for _ in range(30) if not running()]; time.sleep(2)
    osa(MAKE, json.dumps({"first": first, "last": last, "n": 2 if twin else 1}), lang="JavaScript")
    for _ in range(40):
        if len(card(first, last)) == (2 if twin else 1): break
        time.sleep(0.5)
    return {"f": first, "l": last, "name": f"{first} {last}"}
def state_cases(state):
    m = "background"
    for kind, day in (("plain", "1987-06-15"), ("leap", "2000-02-29"), ("new_year", "1979-01-01")):
        K.case("contact_set_birthday", m, state, kind, lambda: person(), lambda c, day=day: C.contact_set_birthday(match=c["name"], date=day),
               lambda c, b, a, r, e, day=day: {"no_error": e is None, "db_birthday": card(c["f"], c["l"]) == [(day, [])], "return": bool(r) and r["birthday"] == day})
    street = "12 Café Lane\nFlat 3"
    K.case("contact_add_address", m, state, "home_full", lambda: person(), lambda c: C.contact_add_address(match=c["name"], street=street, city="Pune", zip="411001", country="India"),
           lambda c, b, a, r, e: {"no_error": e is None, "db_address": card(c["f"], c["l"]) == [(None, [("home", street, "Pune", "411001", "India")])], "return": bool(r) and len(r["addresses"]) == 1})
    def with_home():
        c = person(); C.contact_add_address(match=c["name"], street="1 Old St", city="Delhi"); return c
    K.case("contact_add_address", m, state, "second_work", with_home, lambda c: C.contact_add_address(match=c["name"], street="9 Work Rd", city="Mumbai", label="work"),
           lambda c, b, a, r, e: {"no_error": e is None, "db_both": card(c["f"], c["l"]) == [(None, [("home", "1 Old St", "Delhi", "", ""), ("work", "9 Work Rd", "Mumbai", "", "")])]})
def errors():
    m, st = "background", "open"
    for fn, call in (("contact_set_birthday", lambda c: C.contact_set_birthday(match="No Such Person 58291", date="1990-01-01")), ("contact_add_address", lambda c: C.contact_add_address(match="No Such Person 58291", street="x", city="y"))):
        K.case(fn, m, st, "not_found", lambda: {}, call, lambda c, b, a, r, e: {"raised": isinstance(e, C.NotFound)})
    K.case("contact_set_birthday", m, st, "ambiguous", lambda: person(twin=True), lambda c: C.contact_set_birthday(match=c["name"], date="1990-01-01"), lambda c, b, a, r, e: {"raised": isinstance(e, C.Ambiguous), "neither": card(c["f"], c["l"]) == [(None, []), (None, [])]})
    K.case("contact_set_birthday", m, st, "bad_date", lambda: person(), lambda c: C.contact_set_birthday(match=c["name"], date="31/02/1990"), lambda c, b, a, r, e: {"raised": isinstance(e, ValueError), "same": card(c["f"], c["l"]) == [(None, [])]})
    K.case("contact_add_address", m, st, "empty_city", lambda: person(), lambda c: C.contact_add_address(match=c["name"], street="x", city=" "), lambda c, b, a, r, e: {"raised": isinstance(e, ValueError), "same": card(c["f"], c["l"]) == [(None, [])]})
    for fn, call in (("contact_set_birthday", lambda c: C.contact_set_birthday(match=c["name"], date="1990-01-01", mode="ui")), ("contact_add_address", lambda c: C.contact_add_address(match=c["name"], street="x", city="y", mode="ui"))):
        K.case(fn, "ui", st, "ui_not_supported", lambda: person(), call, lambda c, b, a, r, e: {"raised": isinstance(e, C.NotSupported)}, clip=False)
# Import (overnight): made-up .vcf files; cards are read back from the database.
def everyone():
    """Every card's content: name, company, emails and phones. (Not its modification time: in testing, each import updated it on the
    previous import's cards without changing them.)"""
    db = sqlite3.connect(f"file:{DBP}?mode=ro", uri=True, timeout=5)
    try:
        out = []
        for pk, f, l, o in db.execute("select Z_PK, ZFIRSTNAME, ZLASTNAME, ZORGANIZATION from ZABCDRECORD where ZFIRSTNAME is not null or ZLASTNAME is not null"):
            mails = tuple(sorted(x or "" for (x,) in db.execute("select ZADDRESS from ZABCDEMAILADDRESS where ZOWNER = ?", (pk,))))
            phones = tuple(sorted(x or "" for (x,) in db.execute("select ZFULLNUMBER from ZABCDPHONENUMBER where ZOWNER = ?", (pk,))))
            out.append((f or "", l or "", o or "", (mails, phones)))
        return sorted(out)
    finally: db.close()
VCF = f"{K.DATA}/vcf"; os.makedirs(VCF, exist_ok=True)
def vcf(people):
    def esc(x): return x.replace("\\", "\\\\").replace(",", "\\,").replace(";", "\\;")
    cards = []
    for f, l, o in people:
        cards += ["BEGIN:VCARD", "VERSION:3.0", f"N:{esc(l)};{esc(f)};;;", f"FN:{esc(f)} {esc(l)}"] + ([f"ORG:{esc(o)};"] if o else []) + ["END:VCARD"]
    n["i"] += 1; p = f"{VCF}/{(K.V.special() if n['i'] % 2 else K.V.word()).replace('/', '-')} {n['i']}.vcf"
    open(p, "w", encoding="utf-8").write("\r\n".join(cards) + "\r\n"); return p
def new_people(k):
    out = []
    for j in range(k):
        n["i"] += 1; out.append((K.V.special().split()[0] if j % 2 else K.V.word(1).split()[0], f"Imported{n['i']}{K.V.rng.randint(100, 999)}", K.V.word() if j == 0 else ""))
    return out
def import_setup(k=2):
    if not running(): sh("open -g -j -b com.apple.AddressBook"); [time.sleep(0.5) for _ in range(30) if not running()]; time.sleep(2)
    ppl = new_people(k); return {"p": vcf(ppl), "people": ppl, "before": everyone()}
def imported(c, b, a, r, e):
    now = everyone(); added = [x for x in now if x not in c["before"]]
    return {"no_error": e is None, "cards_added": sorted((f, l, o) for f, l, o, _ in added) == sorted(c["people"]),
            "others_same": [x for x in now if x[:3] not in c["people"]] == [x for x in c["before"] if x[:3] not in c["people"]],
            "return": bool(r) and r["count"] == len(c["people"]) and r["path"] == c["p"]}
def import_group():
    for st in ("closed", "open", "other_app", "hidden"):
        K.case("contact_import_vcard", "ui", st, "two_cards", import_setup, lambda c: C.contact_import_vcard(path=c["p"]), imported)
    K.case("contact_import_vcard", "ui", "open", "one_card", lambda: import_setup(1), lambda c: C.contact_import_vcard(path=c["p"]), imported)
    K.case("contact_import_vcard", "ui", "open", "four_cards", lambda: import_setup(4), lambda c: C.contact_import_vcard(path=c["p"]), imported)
    K.case("contact_import_vcard", "ui", "open", "large_clipboard", import_setup, lambda c: C.contact_import_vcard(path=c["p"]), imported, big=True)
    def dup():
        c = person(); p = vcf([(c["f"], c["l"], "")] + new_people(1)); return {"p": p, "before": everyone()}
    K.case("contact_import_vcard", "ui", "open", "duplicate", dup, lambda c: C.contact_import_vcard(path=c["p"]),
           lambda c, b, a, r, e: {"raised": isinstance(e, C.AlreadyExists), "nothing_changed": everyone() == c["before"], "no_dialog_left": not C._sheets()})
    K.case("contact_import_vcard", "ui", "open", "no_file", lambda: {}, lambda c: C.contact_import_vcard(path=f"{VCF}/none.vcf"), lambda c, b, a, r, e: {"raised": isinstance(e, C.NotFound)})
    K.case("contact_import_vcard", "ui", "open", "bad_type", lambda: {}, lambda c: C.contact_import_vcard(path=f"{VCF}/x.txt"), lambda c, b, a, r, e: {"raised": isinstance(e, ValueError)})
    def empty():
        p = f"{VCF}/empty {K.word()}.vcf"; open(p, "w").write("nothing here\n"); return {"p": p}
    K.case("contact_import_vcard", "ui", "open", "no_cards", empty, lambda c: C.contact_import_vcard(path=c["p"]), lambda c, b, a, r, e: {"raised": isinstance(e, ValueError)})
    K.case("contact_import_vcard", "background", "open", "not_supported", lambda: {}, lambda c: C.contact_import_vcard(path=f"{VCF}/x.vcf", mode="background"), lambda c, b, a, r, e: {"raised": isinstance(e, C.NotSupported)})
# Exporting a list (overnight): the written vCards are parsed here and compared with the list's members in the database.
GMAKE = r"""function run(argv) { const C = Application("Contacts"), a = JSON.parse(argv[0]); const g = C.Group({name: a.group}); C.groups.push(g); C.save();
  const grp = C.groups.whose({name: a.group})()[0];
  for (const [f, l] of a.people) { const p = C.Person({firstName: f, lastName: l}); C.people.push(p); C.save(); C.add(C.people.whose({lastName: l})()[0], {to: grp}); }
  for (const [f, l] of a.outside) { C.people.push(C.Person({firstName: f, lastName: l})); }
  C.save(); return "ok"; }"""
def group_members(group):
    db = sqlite3.connect(f"file:{DBP}?mode=ro", uri=True, timeout=5)
    try:
        gpk = db.execute("select Z_PK from ZABCDRECORD where ZNAME = ?", (group,)).fetchall()
        if len(gpk) != 1: return None
        # The join table between cards and lists is the PARENTGROUPS table that has a CONTACTS column (the other links lists to lists).
        for (t,) in db.execute("select name from sqlite_master where type='table' and name like 'Z_%PARENTGROUPS'"):
            cols = [c[1] for c in db.execute(f"pragma table_info({t})")]
            cm = [c for c in cols if c.endswith("CONTACTS")]; cg = [c for c in cols if "PARENTGROUPS" in c]
            if cm and cg:
                return sorted((f or "", l or "") for f, l in db.execute(f"select r.ZFIRSTNAME, r.ZLASTNAME from {t} j join ZABCDRECORD r on r.Z_PK = j.{cm[0]} where j.{cg[0]} = ?", (gpk[0][0],)))
        return None
    finally: db.close()
def vcf_names(p):
    import re as _re
    out = []
    for card in open(p, encoding="utf-8").read().split("BEGIN:VCARD")[1:]:
        n = _re.search(r"^N:([^;\r\n]*);([^;\r\n]*)", card, _re.M)
        out.append((n.group(2), n.group(1)) if n else ("?", "?"))
    return sorted(out)
def gx_setup(k=3):
    if not running(): sh("open -g -j -b com.apple.AddressBook"); [time.sleep(0.5) for _ in range(30) if not running()]; time.sleep(2)
    n["i"] += 1; grp = f"Crew {K.V.word(1)} {n['i']}"
    ppl = [(K.V.word(1).split()[0], f"Member{n['i']}x{j}{K.V.rng.randint(100, 999)}") for j in range(k)]
    outside = [(K.V.word(1).split()[0], f"Outsider{n['i']}{K.V.rng.randint(100, 999)}")]
    osa(GMAKE, json.dumps({"group": grp, "people": ppl, "outside": outside}), lang="JavaScript"); time.sleep(2)
    return {"g": grp, "people": sorted(ppl), "p": f"{VCF}/{grp}.vcf", "before": everyone()}
def gx_done(c, b, a, r, e):
    return {"no_error": e is None, "cards_are_the_members": os.path.isfile(c["p"]) and vcf_names(c["p"]) == c["people"] == (group_members(c["g"]) or []),
            "contacts_unchanged": everyone() == c["before"], "return": bool(r) and r["count"] == len(c["people"]) and r["path"] == c["p"]}
def gexport_group():
    for st in ("closed", "open", "other_app", "hidden"):
        K.case("group_export_vcard", "background", st, "three", gx_setup, lambda c: C.group_export_vcard(name=c["g"], path=c["p"]), gx_done, lambda c: {vkit.nfc(c["p"])})
    m, st = "background", "open"
    K.case("group_export_vcard", m, st, "one", lambda: gx_setup(1), lambda c: C.group_export_vcard(name=c["g"], path=c["p"]), gx_done, lambda c: {vkit.nfc(c["p"])})
    K.case("group_export_vcard", m, st, "no_list", lambda: {}, lambda c: C.group_export_vcard(name="No Such List 7171", path=f"{VCF}/n.vcf"), lambda c, b, a, r, e: {"raised": isinstance(e, C.NotFound), "none": not os.path.exists(f"{VCF}/n.vcf")})
    def taken():
        c = gx_setup(1); open(c["p"], "w").write("keep"); return c
    K.case("group_export_vcard", m, st, "exists", taken, lambda c: C.group_export_vcard(name=c["g"], path=c["p"]), lambda c, b, a, r, e: {"raised": isinstance(e, C.AlreadyExists), "kept": open(c["p"]).read() == "keep"})
    K.case("group_export_vcard", m, st, "bad_suffix", lambda: {}, lambda c: C.group_export_vcard(name="X", path=f"{VCF}/x.txt"), lambda c, b, a, r, e: {"raised": isinstance(e, ValueError)})
    K.case("group_export_vcard", "ui", st, "not_supported", lambda: {}, lambda c: C.group_export_vcard(name="X", path=f"{VCF}/x.vcf", mode="ui"), lambda c, b, a, r, e: {"raised": isinstance(e, C.NotSupported)}, clip=False)
    K.case("group_export_vcard", m, st, "large_clipboard", gx_setup, lambda c: C.group_export_vcard(name=c["g"], path=c["p"]), gx_done, lambda c: {vkit.nfc(c["p"])}, big=True)
# Web addresses (overnight): read back from the database's URL table, with the label as Contacts stores it.
def urls_of(first, last):
    db = sqlite3.connect(f"file:{DBP}?mode=ro", uri=True, timeout=5)
    try:
        out = []
        for (pk,) in db.execute("select Z_PK from ZABCDRECORD where ZFIRSTNAME = ? and ZLASTNAME = ?", (first, last)):
            out += [((l or "").replace("_$!<", "").replace(">!$_", "").lower(), u or "") for l, u in db.execute("select ZLABEL, ZURL from ZABCDURLADDRESS where ZOWNER = ? order by Z_PK", (pk,))]
        return out
    finally: db.close()
def url_cases(state):
    for label in ("homepage", "work"):
        def setup(label=label):
            c = person(); c["url"] = f"https://{K.word().lower()}.example.test/{K.V.rng.randint(10, 9999)}?q=é"; c["before"] = everyone(); return c
        K.case("contact_add_url", "background", state, label, setup, lambda c, label=label: C.contact_add_url(match=c["name"], url=c["url"], label=label),
               lambda c, b, a, r, e, label=label: {"no_error": e is None, "db_url": urls_of(c["f"], c["l"]) == [(label, c["url"])],
                                                   "others_same": [x for x in everyone() if x[:2] != (c["f"], c["l"])] == [x for x in c["before"] if x[:2] != (c["f"], c["l"])],
                                                   "return": bool(r) and r["urls"] == [{"label": label, "url": c["url"]}]})
def url_group():
    for st in ("closed", "open", "other_app", "hidden"): url_cases(st)
    m, st = "background", "open"
    def second():
        c = person(); C.contact_add_url(match=c["name"], url="https://first.example.test/"); c["url"] = "https://second.example.test/x"; return c
    K.case("contact_add_url", m, st, "second", second, lambda c: C.contact_add_url(match=c["name"], url=c["url"], label="work"),
           lambda c, b, a, r, e: {"no_error": e is None, "both": urls_of(c["f"], c["l"]) == [("homepage", "https://first.example.test/"), ("work", c["url"])]})
    def dup():
        c = person(); C.contact_add_url(match=c["name"], url="https://same.example.test/"); return c
    K.case("contact_add_url", m, st, "already", dup, lambda c: C.contact_add_url(match=c["name"], url="https://same.example.test/"), lambda c, b, a, r, e: {"raised": isinstance(e, C.AlreadyExists), "one": len(urls_of(c["f"], c["l"])) == 1})
    K.case("contact_add_url", m, st, "bad_url", lambda: person(), lambda c: C.contact_add_url(match=c["name"], url="javascript:alert(1)"), lambda c, b, a, r, e: {"raised": isinstance(e, ValueError), "none": urls_of(c["f"], c["l"]) == []})
    K.case("contact_add_url", m, st, "no_card", lambda: {}, lambda c: C.contact_add_url(match="Nobody Here 9191", url="https://x.example.test/"), lambda c, b, a, r, e: {"raised": isinstance(e, C.NotFound)})
    K.case("contact_add_url", m, st, "ambiguous", lambda: person(twin=True), lambda c: C.contact_add_url(match=c["name"], url="https://x.example.test/"), lambda c, b, a, r, e: {"raised": isinstance(e, C.Ambiguous), "none": urls_of(c["f"], c["l"]) == []})
    K.case("contact_add_url", "ui", st, "not_supported", lambda: person(), lambda c: C.contact_add_url(match=c["name"], url="https://x.example.test/", mode="ui"), lambda c, b, a, r, e: {"raised": isinstance(e, C.NotSupported)}, clip=False)
    K.case("contact_add_url", m, st, "large_clipboard", lambda: (lambda c: (c.update(url="https://big.example.test/"), c)[1])(person()), lambda c: C.contact_add_url(match=c["name"], url=c["url"]),
           lambda c, b, a, r, e: {"no_error": e is None, "db_url": urls_of(c["f"], c["l"]) == [("homepage", c["url"])]}, big=True)
groups = [(s, (lambda s=s: state_cases(s))) for s in ("closed", "open", "other_app", "hidden")] + [("errors", errors), ("import", import_group), ("gexport", gexport_group), ("urls", url_group)]
K.run(states, groups)
