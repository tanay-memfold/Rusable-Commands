"""verify_notes15.py <group> <seed> <states...>: Notes' image attachment, read back from NoteStore.sqlite and Notes' stored media."""
import hashlib, html, os, sys, time, json, subprocess
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import notes as N, att_db as DB, vkit
from vcommon import osa, sh, se
group, seed, states = sys.argv[1], int(sys.argv[2]), sys.argv[3:]
APP = "Notes"
MAKE = r"""function run(argv) {
  const Notes = Application("Notes"); const a = JSON.parse(argv[0]);
  const acc = Notes.accounts.byName("On My Mac");
  let f = acc.folders.whose({name: a.folder})(); if (!f.length) { Notes.make({new: "folder", at: acc, withProperties: {name: a.folder}}); f = acc.folders.whose({name: a.folder})(); }
  return JSON.stringify(Notes.make({new: "note", at: f[0], withProperties: {body: "<div>" + a.title + "</div><div>" + a.body + "</div>"}}).id());
}"""
def running(): return bool(sh("pgrep -x Notes"))
def quit_app():
    if running(): osa('tell application "Notes" to quit'); [time.sleep(0.5) for _ in range(40) if running()]
def front_app():
    try: return osa('tell application "System Events" to return name of first process whose frontmost is true')
    except RuntimeError: return ""
def start(state):
    if state == "closed": quit_app(); return
    if not running(): sh("open -b com.apple.Notes"); [time.sleep(0.5) for _ in range(40) if not running()]; time.sleep(2)
    se("set visible to true\nset frontmost to true", APP); time.sleep(0.6)
    if state == "hidden": se("set visible to false", APP); time.sleep(0.6)
    elif state == "other_app": sh("open -a Calculator"); [time.sleep(0.3) for _ in range(20) if front_app() == APP]
K = vkit.Kit("notes15", N, APP, group, seed, N.NotesError, start)
FOLDER = f"Rusable Notes {K.V.rng.randint(1000, 9999)}"
IMG = f"{K.DATA}/img"; os.makedirs(IMG, exist_ok=True)
n = {"i": 0}
def sha(p): return hashlib.sha256(open(p, "rb").read()).hexdigest()
def image(kind):
    n["i"] += 1; stem = f"{IMG}/{K.word().replace(' ', '-')}-{n['i']}"
    vkit.png(stem + ".png", 30 + n["i"], 20 + n["i"] % 7, (n["i"] * 37 % 255, 90, 200))
    if kind == "png": return stem + ".png"
    sh(f"sips -s format {kind} '{stem}.png' --out '{stem}.{ {'jpeg': 'jpg'}.get(kind, kind) }' >/dev/null"); os.unlink(stem + ".png")
    return f"{stem}.{ {'jpeg': 'jpg'}.get(kind, kind) }"
def note(kind="png"):
    title = K.V.special() if n["i"] % 2 else K.V.word()
    if not running(): sh("open -g -j -b com.apple.Notes"); [time.sleep(0.5) for _ in range(40) if not running()]; time.sleep(2)
    osa(MAKE, json.dumps({"folder": FOLDER, "title": html.escape(title, quote=False), "body": "line " + K.word()}), lang="JavaScript")
    p = image(kind) if kind else None
    for _ in range(60):
        if DB.note_pk(title): break
        time.sleep(0.5)
    return {"title": title, "p": p, "snap": DB.notes_db.snapshot()}
def others_same(c):
    now = DB.notes_db.snapshot()["notes"]; was = c["snap"]["notes"]
    return {k: v for k, v in now.items() if v["title"] != c["title"]} == {k: v for k, v in was.items() if v["title"] != c["title"]}
UTI = {"png": "public.png", "jpeg": "public.jpeg", "gif": "com.compuserve.gif", "heic": "public.heic", "tiff": "public.tiff"}
def attached(c, kind, count=1):
    found = DB.attachments(c["title"])
    return bool(found) and len(found) == count and any(u == UTI[kind] and h == sha(c["p"]) for u, h in found)
def state_cases(state):
    m = "background"
    for kind in ("png", "jpeg", "gif", "heic", "tiff"):
        K.case("note_attach_image", m, state, kind, lambda kind=kind: note(kind), lambda c: N.note_attach_image(match=c["title"], path=c["p"], mode=m),
               lambda c, b, a, r, e, kind=kind: {"no_error": e is None, "db_attachment": attached(c, kind), "text_kept": (DB.text(c["title"]) or "").startswith(c["title"] + "\n"), "file_same": a.get(vkit.nfc(c["p"])) == b.get(vkit.nfc(c["p"])), "return": bool(r) and r["attached"] == os.path.basename(c["p"]) and r["title"] == c["title"], "others_same": others_same(c)})
    def two():
        c = note("png"); p2 = image("png"); N.note_attach_image(match=c["title"], path=p2, mode=m); c["p2"] = p2; c["snap"] = DB.notes_db.snapshot(); return c
    K.case("note_attach_image", m, state, "second", two, lambda c: N.note_attach_image(match=c["title"], path=c["p"], mode=m),
           lambda c, b, a, r, e: {"no_error": e is None, "both": attached(c, "png", 2) and any(h == sha(c["p2"]) for _, h in DB.attachments(c["title"])), "return": bool(r) and r["attached"] == os.path.basename(c["p"]), "others_same": others_same(c)})
def errors():
    m, st = "background", "open"
    K.case("note_attach_image", m, st, "not_found_note", lambda: {"p": image("png")}, lambda c: N.note_attach_image(match="No such note 4242", path=c["p"], mode=m), lambda c, b, a, r, e: {"raised_NotFound": isinstance(e, N.NotFound)})
    K.case("note_attach_image", m, st, "no_file", lambda: note(None), lambda c: N.note_attach_image(match=c["title"], path=f"{IMG}/none.png", mode=m), lambda c, b, a, r, e: {"raised_NotFound": isinstance(e, N.NotFound), "db_none": DB.attachments(c["title"]) == []})
    def txt():
        c = note(None); c["p"] = f"{IMG}/{K.word().replace(' ', '-')}.txt"; open(c["p"], "w").write("not an image"); return c
    K.case("note_attach_image", m, st, "not_image", txt, lambda c: N.note_attach_image(match=c["title"], path=c["p"], mode=m), lambda c, b, a, r, e: {"raised_ValueError": isinstance(e, ValueError), "db_none": DB.attachments(c["title"]) == []})
    K.case("note_attach_image", m, st, "relative", lambda: note(None), lambda c: N.note_attach_image(match=c["title"], path="img/x.png", mode=m), lambda c, b, a, r, e: {"raised_ValueError": isinstance(e, ValueError), "db_none": DB.attachments(c["title"]) == []})
    def twins():
        c = note("png"); osa(MAKE, json.dumps({"folder": FOLDER, "title": html.escape(c["title"], quote=False), "body": "twin"}), lang="JavaScript"); time.sleep(2); return c
    K.case("note_attach_image", m, st, "ambiguous", twins, lambda c: N.note_attach_image(match=c["title"], path=c["p"], mode=m), lambda c, b, a, r, e: {"raised_Ambiguous": isinstance(e, N.Ambiguous)})
    for fn, call in (("note_attach_image", lambda c: N.note_attach_image(match=c["title"], path=c["p"], mode="ui")),):
        K.case(fn, "ui", st, "ui_not_supported", lambda: note("png"), call, lambda c, b, a, r, e: {"raised_NotSupported": isinstance(e, N.NotSupported), "db_none": DB.attachments(c["title"]) == []}, clip=False)
def large_clipboard():
    K.case("note_attach_image", "background", "open", "large_clipboard", lambda: note("png"), lambda c: N.note_attach_image(match=c["title"], path=c["p"], mode="background"), lambda c, b, a, r, e: {"no_error": e is None, "db_attachment": attached(c, "png")}, big=True)
def large_clipboard_old():
    """Day 3b: the old UI paste (note_create) with a very large clipboard; the note is read back from NoteStore.sqlite."""
    def setup():
        t = f"Big clipboard {K.word()} {K.V.rng.randint(100, 999)}"; return {"title": t, "body": "line one ☕", "snap": DB.notes_db.snapshot()}
    K.case("note_create", "ui", "open", "large_clipboard", setup, lambda c: N.note_create(title=c["title"], body=c["body"], folder=FOLDER, mode="ui"),
           lambda c, b, a, r, e: {"no_error": e is None, "db_one_note": len(DB.notes_db.titled(DB.notes_db.snapshot(), c["title"])) == 1}, big=True)
# Export as PDF (overnight): the PDF's text is read back with PDFKit, and every note in NoteStore.sqlite must be unchanged.
PDF = f"{K.DATA}/pdf"; os.makedirs(PDF, exist_ok=True)
PDF_TEXT = r"""ObjC.import("Quartz"); function run(argv) { const d = $.PDFDocument.alloc.initWithURL($.NSURL.fileURLWithPath(argv[0])); return d.isNil() ? "" : (ObjC.unwrap(d.string) || ""); }"""
def pdf_text(p):
    try: return vkit.nfc(osa(PDF_TEXT, p, lang="JavaScript"))
    except RuntimeError: return ""
def pdf_note():
    c = note(None); c["word"] = f"line {K.word()}"  # note() writes "line <word>" as the body; read it back from the store
    c["body"] = (DB.text(c["title"]) or "").split("\n", 1)[-1].strip(); n["i"] += 1
    c["p"] = f"{PDF}/{(K.V.special() if n['i'] % 2 else K.V.word()).replace('/', '-')} {n['i']}.pdf"; c["files"] = sorted(os.listdir(PDF)); return c
def exported(c, b, a, r, e):
    def plain(x): return vkit.nfc(x).replace("\ufe0f", "").replace("\ufe0e", "").replace("\u00a0", " ")  # PDFKit's text drops emoji variation selectors
    t = plain(pdf_text(c["p"])); title = plain(c["title"]); body = plain(c["body"])
    return {"no_error": e is None, "pdf_has_title": title in t.replace("\u00a0", " "), "pdf_has_body": bool(body) and body in t.replace("\u00a0", " "),
            "only_it": sorted(map(vkit.nfc, os.listdir(PDF))) == sorted(map(vkit.nfc, c["files"] + [os.path.basename(c["p"])])), "notes_same": DB.notes_db.snapshot()["notes"] == c["snap"]["notes"],
            "return": bool(r) and r["path"] == c["p"] and r["title"] == c["title"]}
def pdf_group():
    for st in ("closed", "open", "other_app", "hidden"):
        K.case("note_export_pdf", "ui", st, "note", pdf_note, lambda c: N.note_export_pdf(match=c["title"], path=c["p"]), exported, lambda c: {vkit.nfc(c["p"])})
    K.case("note_export_pdf", "ui", "open", "large_clipboard", pdf_note, lambda c: N.note_export_pdf(match=c["title"], path=c["p"]), exported, lambda c: {vkit.nfc(c["p"])}, big=True)
    def taken():
        c = pdf_note(); open(c["p"], "w").write("keep"); return c
    K.case("note_export_pdf", "ui", "open", "exists", taken, lambda c: N.note_export_pdf(match=c["title"], path=c["p"]), lambda c, b, a, r, e: {"raised": isinstance(e, N.AlreadyExists), "kept": open(c["p"]).read() == "keep"})
    K.case("note_export_pdf", "ui", "open", "bad_type", pdf_note, lambda c: N.note_export_pdf(match=c["title"], path=c["p"][:-4] + ".txt"), lambda c, b, a, r, e: {"raised": isinstance(e, ValueError)})
    K.case("note_export_pdf", "ui", "open", "no_folder", pdf_note, lambda c: N.note_export_pdf(match=c["title"], path=f"{PDF}/none/x.pdf"), lambda c, b, a, r, e: {"raised": isinstance(e, N.NotFound)})
    K.case("note_export_pdf", "ui", "open", "no_note", lambda: {}, lambda c: N.note_export_pdf(match="No such note 5353", path=f"{PDF}/n.pdf"), lambda c, b, a, r, e: {"raised": isinstance(e, N.NotFound), "none": not os.path.exists(f"{PDF}/n.pdf")})
    def twins():
        c = pdf_note(); osa(MAKE, json.dumps({"folder": FOLDER, "title": html.escape(c["title"], quote=False), "body": "twin"}), lang="JavaScript"); time.sleep(2); return c
    K.case("note_export_pdf", "ui", "open", "ambiguous", twins, lambda c: N.note_export_pdf(match=c["title"], path=c["p"]), lambda c, b, a, r, e: {"raised": isinstance(e, N.Ambiguous), "none": not os.path.exists(c["p"])})
    K.case("note_export_pdf", "background", "open", "not_supported", pdf_note, lambda c: N.note_export_pdf(match=c["title"], path=c["p"], mode="background"), lambda c, b, a, r, e: {"raised": isinstance(e, N.NotSupported)})
def tidy():
    try: osa('on run argv\ntell application "Notes" to delete (every folder of account "On My Mac" whose name is (item 1 of argv))\nend run', FOLDER)
    except RuntimeError: pass
groups = [(s, (lambda s=s: state_cases(s))) for s in ("closed", "open", "other_app", "hidden")] + [("errors", errors), ("large_clipboard", large_clipboard), ("large_clipboard_old", large_clipboard_old), ("pdf", pdf_group)]
try: K.run(states, groups)
finally: tidy()
