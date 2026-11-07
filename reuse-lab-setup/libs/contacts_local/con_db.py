"""Read-only view of Contacts' own database, separate from the library and from scripting. Never writes."""
import os, sqlite3
PATH = os.path.expanduser("~/Library/Application Support/AddressBook/AddressBook-v22.abcddb")
def snapshot() -> dict:
    db = sqlite3.connect(f"file:{PATH}?mode=ro", uri=True, timeout=5)
    try:
        ents = dict(db.execute("select Z_NAME, Z_ENT from Z_PRIMARYKEY"))
        emails, phones, notes, members = {}, {}, {}, {}
        for o, v in db.execute("select ZOWNER, ZADDRESS from ZABCDEMAILADDRESS order by Z_PK"): emails.setdefault(o, []).append(v)
        for o, v in db.execute("select ZOWNER, ZFULLNUMBER from ZABCDPHONENUMBER order by Z_PK"): phones.setdefault(o, []).append(v)
        for o, v in db.execute("select ZCONTACT, ZTEXT from ZABCDNOTE"): notes[o] = v
        groups = {pk: n for pk, n in db.execute("select Z_PK, ZNAME from ZABCDRECORD where Z_ENT = ?", (ents["ABCDGroup"],))}
        for c, g in db.execute("select Z_22CONTACTS, Z_19PARENTGROUPS1 from Z_22PARENTGROUPS"): members.setdefault(c, []).append(groups.get(g))
        people = {}
        for pk, first, last, org in db.execute("select Z_PK, ZFIRSTNAME, ZLASTNAME, ZORGANIZATION from ZABCDRECORD where Z_ENT = ?", (ents["ABCDContact"],)):
            people[pk] = {"first": first or "", "last": last or "", "company": org or "", "emails": emails.get(pk, []), "phones": phones.get(pk, []), "note": notes.get(pk) or "", "groups": sorted(members.get(pk, []))}
            people[pk]["name"] = " ".join(x for x in (first, last) if x) or (org or "")
        return {"people": people, "groups": groups}
    finally:
        db.close()
def details(pk_name):
    """Job title and labelled phones and emails for the cards with this name, straight from the database."""
    db = sqlite3.connect(f"file:{PATH}?mode=ro", uri=True, timeout=5)
    try:
        ents = dict(db.execute("select Z_NAME, Z_ENT from Z_PRIMARYKEY")); out = []
        for pk, first, last, org, job in db.execute("select Z_PK, ZFIRSTNAME, ZLASTNAME, ZORGANIZATION, ZJOBTITLE from ZABCDRECORD where Z_ENT = ?", (ents["ABCDContact"] if "ABCDContact" in ents else ents["ABCDPerson"],)):
            if (" ".join(x for x in (first, last) if x) or (org or "")) != pk_name: continue
            clean = lambda l: (l or "").replace("_$!<", "").replace(">!$_", "").lower()
            out.append({"job": job or "", "phones": [(clean(l), n) for l, n in db.execute("select ZLABEL, ZFULLNUMBER from ZABCDPHONENUMBER where ZOWNER = ? order by Z_PK", (pk,))], "emails": [(clean(l), n) for l, n in db.execute("select ZLABEL, ZADDRESS from ZABCDEMAILADDRESS where ZOWNER = ? order by Z_PK", (pk,))]})
        return out
    finally:
        db.close()
def named(snap, name): return [p for p in snap["people"].values() if p["name"] == name]
def others(before, after, names):
    a, b = before["people"], after["people"]
    return [k for k in set(a) | set(b) if a.get(k) != b.get(k) and (a.get(k) or {}).get("name") not in names and (b.get(k) or {}).get("name") not in names]
