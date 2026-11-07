"""verify_preview.py <group> <seed> <states...>: Preview commands, read back from the files with ImageIO/PDFKit through separate code."""
import json, os, struct, subprocess, sys, time, zlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["PREVIEW_ALLOWED_ROOT"] = os.path.expanduser("~/preview-test")
import preview as P, vkit, ax
from vcommon import osa, sh, se
group, seed, states = sys.argv[1], int(sys.argv[2]), sys.argv[3:]
APP = "Preview"
PIX = r"""ObjC.import("AppKit"); function run(argv) {
  const r = $.NSBitmapImageRep.imageRepWithData($.NSData.dataWithContentsOfFile(argv[0]));
  if (r.isNil()) return "null";
  const w = r.pixelsWide, h = r.pixelsHigh, at = (x, y) => { const c = r.colorAtXY(x, y); return [Math.round(c.redComponent * 255), Math.round(c.greenComponent * 255), Math.round(c.blueComponent * 255)]; };
  return JSON.stringify({w: w, h: h, tl: at(1, 1), tr: at(w - 2, 1), bl: at(1, h - 2), br: at(w - 2, h - 2)});
}"""
PDF = r"""ObjC.import("Quartz"); function run(argv) { const d = $.PDFDocument.alloc.initWithURL($.NSURL.fileURLWithPath(argv[0])); if (d.isNil()) return "null";
  const out = []; for (let i = 0; i < d.pageCount; i++) out.push(ObjC.unwrap(d.pageAtIndex(i).string) || ""); return JSON.stringify(out); }"""
def pix(p):
    try: return json.loads(osa(PIX, p, lang="JavaScript"))
    except RuntimeError: return None
def pdf_pages(p):
    try: return json.loads(osa(PDF, p, lang="JavaScript"))
    except RuntimeError: return None
RED, GREEN, BLUE, YELLOW = (220, 30, 30), (30, 200, 30), (30, 30, 220), (230, 220, 30)
def quad_png(p, w=60, h=40):
    """Top-left red, top-right green, bottom-left blue, bottom-right yellow."""
    def chunk(t, d): return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    rows = []
    for y in range(h):
        row = b"\0"
        for x in range(w):
            row += bytes((RED if x < w // 2 else GREEN) if y < h // 2 else (BLUE if x < w // 2 else YELLOW))
        rows.append(row)
    open(p, "wb").write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(b"".join(rows))) + chunk(b"IEND", b""))
def near(a, b): return a is not None and all(abs(x - y) <= 40 for x, y in zip(a, b))
def corners(p, tl, tr, bl, br, w, h):
    q = pix(p); return bool(q) and int(q["w"]) == w and int(q["h"]) == h and near(q["tl"], tl) and near(q["tr"], tr) and near(q["bl"], bl) and near(q["br"], br)
def running(): return bool(sh("pgrep -x Preview"))
def docs(): return [w for w in ax.children(ax.app(APP)) if ax.sattr(w, "AXRole") == "AXWindow" and ax.sattr(w, "AXDocument")] if running() else []
def open_paths(): return sorted(vkit.nfc(__import__("urllib.parse").parse.unquote(ax.sattr(w, "AXDocument").split("file://", 1)[-1])) for w in docs())
def front_app():
    try: return osa('tell application "System Events" to return name of first process whose frontmost is true')
    except RuntimeError: return ""
def quit_app():
    if running():
        try: osa('tell application "Preview" to quit')
        except RuntimeError: pass
        [time.sleep(0.5) for _ in range(30) if running()]
K = None
def start(state):
    if state == "closed": quit_app(); return
    other = f"{K.DATA}/base/other.png"
    if not running() or not any(p.endswith("other.png") for p in open_paths()):
        sh(f"open -a Preview '{other}'"); [time.sleep(0.4) for _ in range(30) if not docs()]; time.sleep(1)
    se("set visible to true\nset frontmost to true", APP); time.sleep(0.5)
    if state == "hidden": se("set visible to false", APP)
    elif state == "minimized": se('set value of attribute "AXMinimized" of window 1 to true', APP)
    elif state == "other_app": sh("open -a Calculator"); [time.sleep(0.3) for _ in range(20) if front_app() == APP]
    time.sleep(0.6)
def clean(state):
    for w in (ax.children(ax.app(APP)) if running() else []):
        if ax.sattr(w, "AXRole") == "AXWindow" and any(ax.sattr(e, "AXRole") == "AXSheet" for e in ax.children(w)): return False
    return True
K = vkit.Kit("preview", P, APP, group, seed, P.PreviewError, start, clean)
os.makedirs(f"{K.DATA}/base", exist_ok=True); quad_png(f"{K.DATA}/base/other.png", 30, 30)
n = {"i": 0}
def img(kind="png"):
    n["i"] += 1; d = f"{K.DATA}/img"; os.makedirs(d, exist_ok=True)
    stem = f"{d}/{(K.V.special() if n['i'] % 2 else K.V.word()).replace('/', '-')} {n['i']}"
    quad_png(stem + ".png")
    if kind == "png": return {"p": stem + ".png"}
    subprocess.run(["sips", "-s", "format", "jpeg", stem + ".png", "--out", stem + ".jpg"], capture_output=True); os.unlink(stem + ".png"); return {"p": stem + ".jpg"}
def state_cases(state):
    m = "ui"
    for kind in ("png", "jpeg"):
        K.case("image_rotate", m, state, f"right_{kind}", lambda kind=kind: img(kind), lambda c: P.image_rotate(path=c["p"], direction="right"),
               lambda c, b, a, r, e: {"no_error": e is None, "rotated_right": corners(c["p"], BLUE, RED, YELLOW, GREEN, 40, 60), "return": bool(r) and r["path"] == c["p"]}, lambda c: {c["p"]})
        K.case("image_rotate", m, state, f"left_{kind}", lambda kind=kind: img(kind), lambda c: P.image_rotate(path=c["p"], direction="left"),
               lambda c, b, a, r, e: {"no_error": e is None, "rotated_left": corners(c["p"], GREEN, YELLOW, RED, BLUE, 40, 60)}, lambda c: {c["p"]})
        K.case("image_flip", m, state, f"horizontal_{kind}", lambda kind=kind: img(kind), lambda c: P.image_flip(path=c["p"], axis="horizontal"),
               lambda c, b, a, r, e: {"no_error": e is None, "flipped": corners(c["p"], GREEN, RED, YELLOW, BLUE, 60, 40)}, lambda c: {c["p"]})
        K.case("image_flip", m, state, f"vertical_{kind}", lambda kind=kind: img(kind), lambda c: P.image_flip(path=c["p"], axis="vertical"),
               lambda c, b, a, r, e: {"no_error": e is None, "flipped": corners(c["p"], BLUE, YELLOW, RED, GREEN, 60, 40)}, lambda c: {c["p"]})
    K.case("document_open", m, state, "png", lambda: img(), lambda c: P.document_open(path=c["p"]),
           lambda c, b, a, r, e: {"no_error": e is None, "window": vkit.nfc(c["p"]) in open_paths(), "file_same": a.get(vkit.nfc(c["p"])) == b.get(vkit.nfc(c["p"]))})
    def opened():
        c = img(); sh(f"open -a Preview '{c['p']}'"); [time.sleep(0.4) for _ in range(30) if vkit.nfc(c["p"]) not in open_paths()]; return c
    if state == "closed":
        K.case("document_close", m, state, "not_open", lambda: img(), lambda c: P.document_close(path=c["p"]),
               lambda c, b, a, r, e: {"raised_NotFound": isinstance(e, P.NotFound), "not_started": not running()})
    else:
        K.case("document_close", m, state, "png", opened, lambda c: P.document_close(path=c["p"]),
               lambda c, b, a, r, e: {"no_error": e is None, "window_gone": vkit.nfc(c["p"]) not in open_paths(), "file_same": a.get(vkit.nfc(c["p"])) == b.get(vkit.nfc(c["p"]))})
    K.case("document_list", m, state, "normal", lambda: {}, lambda c: P.document_list(),
           lambda c, b, a, r, e: {"no_error": e is None, "paths_match": r is not None and sorted(vkit.nfc(x["path"]) for x in r if x["path"]) == open_paths()})
def make_pdf(p, texts):
    """A small PDF with one line of Helvetica text per page."""
    objs = ["<< /Type /Catalog /Pages 2 0 R >>", None, "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    kids = []
    for t in texts:
        stream = f"BT /F1 24 Tf 40 700 Td ({t}) Tj ET".encode()
        objs.append(f"<< /Length {len(stream)} >>\nstream\n".encode().decode() + stream.decode() + "\nendstream")
        objs.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents {len(objs)} 0 R /Resources << /Font << /F1 3 0 R >> >> >>")
        kids.append(f"{len(objs)} 0 R")
    objs[1] = f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {len(kids)} >>"
    out, offs = b"%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        offs.append(len(out)); out += f"{i} 0 obj\n{o}\nendobj\n".encode()
    x = len(out); out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode() + "".join(f"{o:010d} 00000 n \n" for o in offs).encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{x}\n%%EOF\n".encode()
    open(p, "wb").write(out)
def pdfs(count, tag):
    d = f"{K.DATA}/pdf"; os.makedirs(d, exist_ok=True); n["i"] += 1
    texts = [f"{tag}{n['i']}page{k + 1}" for k in range(count)]; p = f"{d}/{K.V.word().replace(' ', '-')} {n['i']}.pdf"; make_pdf(p, texts); return p, texts
def page_texts(p):
    got = pdf_pages(p); return None if got is None else [t.strip() for t in got]
def pdf_cases(state):
    m = "ui"
    for page in (1, 2, 3):
        def setup(page=page):
            p, t = pdfs(3, "Del"); return {"p": p, "t": t}
        K.case("pdf_delete_page", m, state, f"page_{page}_of_3", setup, lambda c, page=page: P.pdf_delete_page(path=c["p"], page=page),
               lambda c, b, a, r, e, page=page: {"no_error": e is None, "pages_left": page_texts(c["p"]) == [t for k, t in enumerate(c["t"]) if k != page - 1], "return": bool(r) and r["pages"] == 2}, lambda c: {c["p"]})
    for page, to in ((1, 2), (3, 1), (2, 1)):
        def mv(page=page, to=to):
            p, t = pdfs(3, "Mv"); return {"p": p, "t": t}
        def want(t, page, to):
            rest = [x for k, x in enumerate(t) if k != page - 1]; rest.insert(to - 1, t[page - 1]); return rest
        K.case("pdf_move_page", m, state, f"page_{page}_to_{to}", mv, lambda c, page=page, to=to: P.pdf_move_page(path=c["p"], page=page, to=to),
               lambda c, b, a, r, e, page=page, to=to: {"no_error": e is None, "new_order": page_texts(c["p"]) == want(c["t"], page, to), "return": bool(r) and r["pages"] == 3}, lambda c: {c["p"]})
    def two():
        p, t = pdfs(2, "Base"); q, u = pdfs(2, "Add"); return {"p": p, "t": t, "q": q, "u": u}
    K.case("pdf_append_file", m, state, "two_plus_two", two, lambda c: P.pdf_append_file(path=c["p"], add=c["q"]),
           lambda c, b, a, r, e: {"no_error": e is None, "combined_in_order": page_texts(c["p"]) == c["t"] + c["u"], "added_file_same": a.get(vkit.nfc(c["q"])) == b.get(vkit.nfc(c["q"])), "return": bool(r) and r["pages"] == 4}, lambda c: {c["p"]})
def pdf_errors():
    m, st = "ui", "open"
    K.case("pdf_delete_page", m, st, "out_of_range", lambda: dict(zip(("p", "t"), pdfs(2, "Rng"))), lambda c: P.pdf_delete_page(path=c["p"], page=5), lambda c, b, a, r, e: {"raised": isinstance(e, ValueError), "same": page_texts(c["p"]) == c["t"]})
    K.case("pdf_delete_page", m, st, "only_page", lambda: dict(zip(("p", "t"), pdfs(1, "One"))), lambda c: P.pdf_delete_page(path=c["p"], page=1), lambda c, b, a, r, e: {"raised": isinstance(e, ValueError), "same": page_texts(c["p"]) == c["t"]})
    K.case("pdf_delete_page", m, st, "not_pdf", lambda: img(), lambda c: P.pdf_delete_page(path=c["p"], page=1), lambda c, b, a, r, e: {"raised": isinstance(e, ValueError)})
    K.case("pdf_move_page", m, st, "to_end", lambda: dict(zip(("p", "t"), pdfs(3, "End"))), lambda c: P.pdf_move_page(path=c["p"], page=1, to=3), lambda c, b, a, r, e: {"raised": isinstance(e, ValueError), "same": page_texts(c["p"]) == c["t"]})
    K.case("pdf_move_page", m, st, "same_place", lambda: dict(zip(("p", "t"), pdfs(3, "Sp"))), lambda c: P.pdf_move_page(path=c["p"], page=2, to=2), lambda c, b, a, r, e: {"raised": isinstance(e, ValueError), "same": page_texts(c["p"]) == c["t"]})
    K.case("pdf_append_file", m, st, "same_file", lambda: dict(zip(("p", "t"), pdfs(2, "Same"))), lambda c: P.pdf_append_file(path=c["p"], add=c["p"]), lambda c, b, a, r, e: {"raised": isinstance(e, ValueError), "same": page_texts(c["p"]) == c["t"]})
    K.case("pdf_append_file", m, st, "not_found", lambda: dict(zip(("p", "t"), pdfs(2, "Nf"))), lambda c: P.pdf_append_file(path=c["p"], add=f"{K.DATA}/pdf/none.pdf"), lambda c, b, a, r, e: {"raised": isinstance(e, P.NotFound), "same": page_texts(c["p"]) == c["t"]})
def fmt_of(p):
    out = sh(f"sips -g format '{p}' 2>/dev/null").split("format:")
    return out[-1].strip() if len(out) > 1 else None
EXP = [("png", "jpeg", ".jpg", "jpeg"), ("png", "pdf", ".pdf", "pdf"), ("jpeg", "png", ".png", "png"), ("png", "heic", ".heic", "heic"), ("png", "tiff", ".tiff", "tiff")]
def export_cases(state):
    for src, fmt, suf, sips_name in EXP:
        def setup(src=src, suf=suf):
            c = img(src); c["to"] = f"{K.DATA}/out/{K.V.word().replace(' ', '-')}{suf}"; os.makedirs(f"{K.DATA}/out", exist_ok=True); return c
        def read(c, b, a, r, e, fmt=fmt, sips_name=sips_name):
            ok = os.path.exists(c["to"])
            if fmt == "pdf": content = ok and pdf_pages(c["to"]) is not None and len(pdf_pages(c["to"])) == 1
            else: content = ok and fmt_of(c["to"]) == sips_name and corners(c["to"], RED, GREEN, BLUE, YELLOW, 60, 40)
            return {"no_error": e is None, "exported": bool(content), "original_same": a.get(vkit.nfc(c["p"])) == b.get(vkit.nfc(c["p"])), "return": bool(r) and r["path"] == c["to"]}
        K.case("document_export", "ui", state, f"{src}_to_{fmt}", setup, lambda c, fmt=fmt: P.document_export(path=c["p"], to=c["to"], format=fmt), read, lambda c: {c["to"]})
def errors():
    m, st = "ui", "open"
    for fn, call in (("image_rotate", lambda c: P.image_rotate(path=f"{K.DATA}/img/none.png")), ("image_flip", lambda c: P.image_flip(path=f"{K.DATA}/img/none.png")), ("document_open", lambda c: P.document_open(path=f"{K.DATA}/img/none.png"))):
        K.case(fn, m, st, "not_found", lambda: {}, call, lambda c, b, a, r, e: {"raised_NotFound": isinstance(e, P.NotFound)})
    K.case("document_close", m, st, "not_open", lambda: img(), lambda c: P.document_close(path=c["p"]), lambda c, b, a, r, e: {"raised_NotFound": isinstance(e, P.NotFound)})
    K.case("image_rotate", m, st, "bad_direction", lambda: img(), lambda c: P.image_rotate(path=c["p"], direction="up"), lambda c, b, a, r, e: {"raised": isinstance(e, ValueError), "same": a == b})
    K.case("image_flip", m, st, "bad_axis", lambda: img(), lambda c: P.image_flip(path=c["p"], axis="diagonal"), lambda c, b, a, r, e: {"raised": isinstance(e, ValueError), "same": a == b})
    def txt():
        p = f"{K.DATA}/img/x.txt"; open(p, "w").write("x"); return {"p": p}
    K.case("document_open", m, st, "bad_type", txt, lambda c: P.document_open(path=c["p"]), lambda c, b, a, r, e: {"raised": isinstance(e, ValueError)})
    for fn, call in (("image_rotate", lambda c: P.image_rotate(path="/tmp/outside.png")), ("document_open", lambda c: P.document_open(path="/tmp/outside.png"))):
        K.case(fn, m, st, "guard", lambda: {}, call, lambda c, b, a, r, e: {"raised_Outside": isinstance(e, P.OutsideAllowedRoot)})
    for fn, call in (("image_rotate", lambda c: P.image_rotate(path=c["p"], mode="background")), ("document_list", lambda c: P.document_list(mode="background"))):
        K.case(fn, "background", st, "not_supported", lambda: img(), call, lambda c, b, a, r, e: {"raised": isinstance(e, P.NotSupported)})
def export_errors():
    m, st = "ui", "open"
    def taken():
        c = img(); c["to"] = f"{K.DATA}/out/taken.jpg"; os.makedirs(f"{K.DATA}/out", exist_ok=True); open(c["to"], "w").write("keep"); return c
    K.case("document_export", m, st, "already_exists", taken, lambda c: P.document_export(path=c["p"], to=c["to"], format="jpeg"), lambda c, b, a, r, e: {"raised": isinstance(e, P.AlreadyExists), "kept": open(c["to"]).read() == "keep"})
    K.case("document_export", m, st, "wrong_suffix", lambda: img(), lambda c: P.document_export(path=c["p"], to=f"{K.DATA}/out/x.png", format="jpeg"), lambda c, b, a, r, e: {"raised": isinstance(e, ValueError), "none": not os.path.exists(f"{K.DATA}/out/x.png")})
    K.case("document_export", m, st, "bad_format", lambda: img(), lambda c: P.document_export(path=c["p"], to=f"{K.DATA}/out/x.bmp", format="bmp"), lambda c, b, a, r, e: {"raised": isinstance(e, ValueError)})
    K.case("document_export", m, st, "no_folder", lambda: img(), lambda c: P.document_export(path=c["p"], to=f"{K.DATA}/none/x.jpg", format="jpeg"), lambda c, b, a, r, e: {"raised": isinstance(e, P.NotFound)})
    K.case("document_export", m, st, "guard", lambda: img(), lambda c: P.document_export(path=c["p"], to="/tmp/outside.jpg", format="jpeg"), lambda c, b, a, r, e: {"raised_Outside": isinstance(e, P.OutsideAllowedRoot), "none": not os.path.exists("/tmp/outside.jpg")})
def large_clipboard():
    def setup():
        c = img(); c["to"] = f"{K.DATA}/out/big-{K.V.rng.randint(1000, 9999)}.jpg"; os.makedirs(f"{K.DATA}/out", exist_ok=True); return c
    def two():
        p, t = pdfs(2, "Bb"); q, u = pdfs(1, "Bc"); return {"p": p, "t": t, "q": q, "u": u}
    K.case("pdf_append_file", "ui", "open", "large_clipboard", two, lambda c: P.pdf_append_file(path=c["p"], add=c["q"]), lambda c, b, a, r, e: {"no_error": e is None, "combined": page_texts(c["p"]) == c["t"] + c["u"]}, lambda c: {c["p"]}, big=True)
    K.case("pdf_move_page", "ui", "open", "large_clipboard", lambda: dict(zip(("p", "t"), pdfs(3, "Bm"))), lambda c: P.pdf_move_page(path=c["p"], page=3, to=1), lambda c, b, a, r, e: {"no_error": e is None, "moved": page_texts(c["p"]) == [c["t"][2], c["t"][0], c["t"][1]]}, lambda c: {c["p"]}, big=True)
    K.case("document_export", "ui", "open", "large_clipboard", setup, lambda c: P.document_export(path=c["p"], to=c["to"], format="jpeg"), lambda c, b, a, r, e: {"no_error": e is None, "exported": fmt_of(c["to"]) == "jpeg"}, lambda c: {c["to"]}, big=True)
    K.case("image_rotate", "ui", "open", "large_clipboard", lambda: img(), lambda c: P.image_rotate(path=c["p"]), lambda c, b, a, r, e: {"no_error": e is None, "rotated_right": corners(c["p"], BLUE, RED, YELLOW, GREEN, 40, 60)}, lambda c: {c["p"]}, big=True)
STATES = ("closed", "open", "other_app", "hidden", "minimized")
# Blank page (overnight): read back with PDFKit; the new page must have no text and sit right after the page asked for.
def blank_cases(state):
    for after in (1, 2, 3):
        def setup():
            p, t = pdfs(3, "Blk"); return {"p": p, "t": t}
        K.case("pdf_insert_blank_page", "ui", state, f"after_{after}_of_3", setup, lambda c, after=after: P.pdf_insert_blank_page(path=c["p"], after=after),
               lambda c, b, a, r, e, after=after: {"no_error": e is None, "blank_in_place": page_texts(c["p"]) == c["t"][:after] + [""] + c["t"][after:],
                                                   "return": bool(r) and r["pages"] == 4 and r["blank_page"] == after + 1}, lambda c: {c["p"]})
def blank_errors():
    m, st = "ui", "open"
    K.case("pdf_insert_blank_page", m, st, "out_of_range", lambda: dict(zip(("p", "t"), pdfs(2, "Brng"))), lambda c: P.pdf_insert_blank_page(path=c["p"], after=5), lambda c, b, a, r, e: {"raised": isinstance(e, ValueError), "same": page_texts(c["p"]) == c["t"]})
    K.case("pdf_insert_blank_page", m, st, "zero", lambda: dict(zip(("p", "t"), pdfs(2, "Bz"))), lambda c: P.pdf_insert_blank_page(path=c["p"], after=0), lambda c, b, a, r, e: {"raised": isinstance(e, ValueError), "same": page_texts(c["p"]) == c["t"]})
    K.case("pdf_insert_blank_page", m, st, "not_pdf", lambda: img(), lambda c: P.pdf_insert_blank_page(path=c["p"], after=1), lambda c, b, a, r, e: {"raised": isinstance(e, ValueError)})
    K.case("pdf_insert_blank_page", m, st, "missing", lambda: {}, lambda c: P.pdf_insert_blank_page(path=f"{K.DATA}/pdf/none.pdf", after=1), lambda c, b, a, r, e: {"raised": isinstance(e, P.NotFound)})
    K.case("pdf_insert_blank_page", "background", st, "not_supported", lambda: dict(zip(("p", "t"), pdfs(2, "Bbg"))), lambda c: P.pdf_insert_blank_page(path=c["p"], after=1, mode="background"), lambda c, b, a, r, e: {"raised": isinstance(e, P.NotSupported)})
    K.case("pdf_insert_blank_page", m, st, "large_clipboard", lambda: dict(zip(("p", "t"), pdfs(2, "Bbig"))), lambda c: P.pdf_insert_blank_page(path=c["p"], after=1),
           lambda c, b, a, r, e: {"no_error": e is None, "blank_in_place": page_texts(c["p"]) == c["t"][:1] + [""] + c["t"][1:]}, lambda c: {c["p"]}, big=True)
# Rotate one page (overnight): every page's rotation read back with PDFKit through this test's own script.
ROT = r"""ObjC.import("Quartz"); function run(argv) { const d = $.PDFDocument.alloc.initWithURL($.NSURL.fileURLWithPath(argv[0])); if (d.isNil()) return "null"; const o = []; for (let i = 0; i < d.pageCount; i++) o.push(Number(d.pageAtIndex(i).rotation)); return JSON.stringify(o); }"""
def turns(p):
    try: return json.loads(osa(ROT, p, lang="JavaScript"))
    except (RuntimeError, ValueError): return None
def rotate_cases(state):
    for page, dr in ((1, "right"), (2, "left"), (3, "right")):
        def setup():
            p, t = pdfs(3, "Rot"); return {"p": p, "t": t}
        want = [0, 0, 0]; want[page - 1] = 90 if dr == "right" else 270
        K.case("pdf_rotate_page", "ui", state, f"page_{page}_{dr}", setup, lambda c, page=page, dr=dr: P.pdf_rotate_page(path=c["p"], page=page, direction=dr),
               lambda c, b, a, r, e, want=want, page=page: {"no_error": e is None, "only_that_page_turned": turns(c["p"]) == want, "text_same": page_texts(c["p"]) == c["t"],
                                                           "return": bool(r) and r["page"] == page and r["pages"] == 3}, lambda c: {c["p"]})
def rotate_errors():
    m, st = "ui", "open"
    K.case("pdf_rotate_page", m, st, "out_of_range", lambda: dict(zip(("p", "t"), pdfs(2, "Rr"))), lambda c: P.pdf_rotate_page(path=c["p"], page=4), lambda c, b, a, r, e: {"raised": isinstance(e, ValueError), "unturned": turns(c["p"]) == [0, 0]})
    K.case("pdf_rotate_page", m, st, "bad_direction", lambda: dict(zip(("p", "t"), pdfs(2, "Rd"))), lambda c: P.pdf_rotate_page(path=c["p"], page=1, direction="up"), lambda c, b, a, r, e: {"raised": isinstance(e, ValueError), "unturned": turns(c["p"]) == [0, 0]})
    K.case("pdf_rotate_page", m, st, "not_pdf", lambda: img(), lambda c: P.pdf_rotate_page(path=c["p"], page=1), lambda c, b, a, r, e: {"raised": isinstance(e, ValueError)})
    K.case("pdf_rotate_page", "background", st, "not_supported", lambda: dict(zip(("p", "t"), pdfs(2, "Rb"))), lambda c: P.pdf_rotate_page(path=c["p"], page=1, mode="background"), lambda c, b, a, r, e: {"raised": isinstance(e, P.NotSupported)})
    K.case("pdf_rotate_page", m, st, "large_clipboard", lambda: dict(zip(("p", "t"), pdfs(2, "Rbig"))), lambda c: P.pdf_rotate_page(path=c["p"], page=2),
           lambda c, b, a, r, e: {"no_error": e is None, "turned": turns(c["p"]) == [0, 90]}, lambda c: {c["p"]}, big=True)
# Extract one page (overnight): the new file read back with PDFKit (one page, that page's text); the original unchanged; no
# untitled window left.
def untitled_left():
    return any((ax.sattr(w, "AXTitle") or "").startswith("Untitled") and not ax.sattr(w, "AXDocument") for w in ax.children(ax.app(APP))) if running() else False
def extract_cases(state):
    for page in (1, 2, 3):
        def setup():
            p, t = pdfs(3, "Ext"); n["i"] += 1; return {"p": p, "t": t, "to": f"{K.DATA}/pdf/{K.V.special().replace('/', '-')} page {n['i']}.pdf"}
        K.case("pdf_extract_page", "ui", state, f"page_{page}_of_3", setup, lambda c, page=page: P.pdf_extract_page(path=c["p"], page=page, to=c["to"]),
               lambda c, b, a, r, e, page=page: {"no_error": e is None, "one_page_with_its_text": page_texts(c["to"]) == [c["t"][page - 1]], "original_same": page_texts(c["p"]) == c["t"],
                                                 "no_untitled_left": not untitled_left(), "return": bool(r) and r["page"] == page and r["path"] == c["to"]}, lambda c: {vkit.nfc(c["to"])})
def extract_errors():
    m, st = "ui", "open"
    K.case("pdf_extract_page", m, st, "out_of_range", lambda: (lambda pt: {"p": pt[0], "t": pt[1], "to": f"{K.DATA}/pdf/x {n['i']}.pdf"})(pdfs(2, "Exr")), lambda c: P.pdf_extract_page(path=c["p"], page=5, to=c["to"]),
           lambda c, b, a, r, e: {"raised": isinstance(e, ValueError), "nothing_written": not os.path.exists(c["to"])})
    def taken():
        p, t = pdfs(2, "Ext"); q = f"{K.DATA}/pdf/taken {n['i']}.pdf"; open(q, "w").write("keep"); return {"p": p, "to": q}
    K.case("pdf_extract_page", m, st, "exists", taken, lambda c: P.pdf_extract_page(path=c["p"], page=1, to=c["to"]), lambda c, b, a, r, e: {"raised": isinstance(e, P.AlreadyExists), "kept": open(c["to"]).read() == "keep"})
    K.case("pdf_extract_page", m, st, "bad_suffix", lambda: (lambda pt: {"p": pt[0]})(pdfs(2, "Exs")), lambda c: P.pdf_extract_page(path=c["p"], page=1, to=f"{K.DATA}/pdf/x.png"), lambda c, b, a, r, e: {"raised": isinstance(e, ValueError)})
    K.case("pdf_extract_page", m, st, "not_pdf", lambda: img(), lambda c: P.pdf_extract_page(path=c["p"], page=1, to=f"{K.DATA}/pdf/y.pdf"), lambda c, b, a, r, e: {"raised": isinstance(e, ValueError)})
    K.case("pdf_extract_page", "background", st, "not_supported", lambda: (lambda pt: {"p": pt[0]})(pdfs(2, "Exb")), lambda c: P.pdf_extract_page(path=c["p"], page=1, to=f"{K.DATA}/pdf/z.pdf", mode="background"), lambda c, b, a, r, e: {"raised": isinstance(e, P.NotSupported)})
    def big():
        p, t = pdfs(2, "Exbig"); return {"p": p, "t": t, "to": f"{K.DATA}/pdf/big {n['i']}.pdf"}
    K.case("pdf_extract_page", m, st, "large_clipboard", big, lambda c: P.pdf_extract_page(path=c["p"], page=2, to=c["to"]),
           lambda c, b, a, r, e: {"no_error": e is None, "one_page_with_its_text": page_texts(c["to"]) == [c["t"][1]]}, lambda c: {vkit.nfc(c["to"])}, big=True)
groups = [("extract_" + s, (lambda s=s: extract_cases(s))) for s in STATES] + [("extract_errors", extract_errors)]
groups += [("rotate_" + s, (lambda s=s: rotate_cases(s))) for s in STATES] + [("rotate_errors", rotate_errors)]
groups += [("blank_" + s, (lambda s=s: blank_cases(s))) for s in STATES] + [("blank_errors", blank_errors)] + [(s, (lambda s=s: state_cases(s))) for s in STATES] + [("export_" + s, (lambda s=s: export_cases(s))) for s in STATES] + [("pdf_" + s, (lambda s=s: pdf_cases(s))) for s in STATES] + [("errors", errors), ("export_errors", export_errors), ("pdf_errors", pdf_errors), ("large_clipboard", large_clipboard)]
K.run(states, groups)
