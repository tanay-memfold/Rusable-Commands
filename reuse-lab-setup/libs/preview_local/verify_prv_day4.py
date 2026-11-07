"""verify_prv_day4.py <group> <seed> <states...>: Preview's image_crop and image_adjust (day 4), read back from the files with
NSBitmapImageRep through separate code (sizes, corner colours, mean brightness and colour spread)."""
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
    quad_png(stem + ".png", 200, 160)
    if kind == "png": return {"p": stem + ".png"}
    subprocess.run(["sips", "-s", "format", "jpeg", stem + ".png", "--out", stem + ".jpg"], capture_output=True); os.unlink(stem + ".png"); return {"p": stem + ".jpg"}
MEAN = r"""ObjC.import("AppKit"); function run(argv) {
  const r = $.NSBitmapImageRep.imageRepWithData($.NSData.dataWithContentsOfFile(argv[0])); if (r.isNil()) return "null";
  const w = r.pixelsWide, h = r.pixelsHigh; let sum = 0, spread = 0, n = 0;
  for (let y = 2; y < h; y += Math.max(1, Math.floor(h / 20))) for (let x = 2; x < w; x += Math.max(1, Math.floor(w / 20))) {
    const c = r.colorAtXY(x, y); const v = [c.redComponent, c.greenComponent, c.blueComponent].map(z => z * 255);
    sum += (v[0] + v[1] + v[2]) / 3; spread += Math.max(...v) - Math.min(...v); n += 1; }
  return JSON.stringify({mean: sum / n, spread: spread / n});
}"""
def stats(p):
    try: return json.loads(osa(MEAN, p, lang="JavaScript"))
    except RuntimeError: return None
def others(c):
    return {x for x in K.tree() if x != vkit.nfc(c["p"])}
CROPS = {"center": ((0.25, 0.25, 0.75, 0.75), (100, 80), (RED, GREEN, BLUE, YELLOW)),
         "left_half": ((0.0, 0.0, 0.5, 1.0), (100, 160), (RED, RED, BLUE, BLUE)),
         "bottom_right": ((0.55, 0.6, 1.0, 1.0), (90, 64), (YELLOW, YELLOW, YELLOW, YELLOW))}
def cropped(c, b, a, r, e):
    q = pix(c["p"]); (w, h) = c["size"]; tl, tr, bl, br = c["corners"]
    return {"no_error": e is None, "size": bool(q) and abs(int(q["w"]) - w) <= 2 and abs(int(q["h"]) - h) <= 2,
            "corners": bool(q) and near(q["tl"], tl) and near(q["tr"], tr) and near(q["bl"], bl) and near(q["br"], br),
            "return": bool(r) and r.get("path") == vkit.nfc(c["p"])}
def state_cases(state):
    m = "ui"
    for kind, (box, size, cols) in CROPS.items():
        for fmt in (("png",) if kind != "center" else ("png", "jpeg")):
            def setup(fmt=fmt, size=size, cols=cols):
                c = img(fmt); c.update(size=size, corners=cols); return c
            K.case("image_crop", m, state, f"{kind}_{fmt}", setup, lambda c, box=box: P.image_crop(path=c["p"], left=box[0], top=box[1], right=box[2], bottom=box[3]),
                   cropped, lambda c: {vkit.nfc(c["p"])})
    def adj_setup(fmt="png"):
        c = img(fmt); c["s0"] = stats(c["p"]); return c
    K.case("image_adjust", m, state, "exposure_up", adj_setup, lambda c: P.image_adjust(path=c["p"], exposure=1.0),
           lambda c, b, a, r, e: {"no_error": e is None, "brighter": bool(stats(c["p"])) and stats(c["p"])["mean"] > c["s0"]["mean"] + 15, "same_size": bool(pix(c["p"])) and int(pix(c["p"])["w"]) == 200, "return": bool(r) and r.get("exposure") == 1.0}, lambda c: {vkit.nfc(c["p"])})
    K.case("image_adjust", m, state, "exposure_down", adj_setup, lambda c: P.image_adjust(path=c["p"], exposure=-1.0),
           lambda c, b, a, r, e: {"no_error": e is None, "darker": bool(stats(c["p"])) and stats(c["p"])["mean"] < c["s0"]["mean"] - 15}, lambda c: {vkit.nfc(c["p"])})
    if state == "open":
        K.case("image_adjust", m, state, "saturation_down", adj_setup, lambda c: P.image_adjust(path=c["p"], saturation=0.0),
               lambda c, b, a, r, e: {"no_error": e is None, "greyer": bool(stats(c["p"])) and stats(c["p"])["spread"] < c["s0"]["spread"] * 0.3}, lambda c: {vkit.nfc(c["p"])})
        K.case("image_adjust", m, state, "exposure_jpeg", lambda: adj_setup("jpeg"), lambda c: P.image_adjust(path=c["p"], exposure=0.8),
               lambda c, b, a, r, e: {"no_error": e is None, "brighter": bool(stats(c["p"])) and stats(c["p"])["mean"] > c["s0"]["mean"] + 10}, lambda c: {vkit.nfc(c["p"])})
def errors():
    m, st = "ui", "open"
    for kind, kw, exc in (("negative", {"left": -0.1, "top": 0, "right": 0.5, "bottom": 0.5}, ValueError), ("too_small", {"left": 0.5, "top": 0.5, "right": 0.52, "bottom": 0.9}, ValueError),
                          ("reversed", {"left": 0.8, "top": 0.1, "right": 0.2, "bottom": 0.9}, ValueError)):
        K.case("image_crop", m, st, kind, lambda: img("png"), lambda c, kw=kw: P.image_crop(path=c["p"], **kw), lambda c, b, a, r, e, exc=exc: {"raised": isinstance(e, exc), "unchanged": bool(pix(c["p"])) and int(pix(c["p"])["w"]) == 200})
    K.case("image_crop", m, st, "missing", lambda: {}, lambda c: P.image_crop(path=f"{K.DATA}/img/none.png", left=0, top=0, right=1, bottom=1), lambda c, b, a, r, e: {"raised": isinstance(e, P.NotFound)})
    K.case("image_adjust", m, st, "out_of_range", lambda: img("png"), lambda c: P.image_adjust(path=c["p"], exposure=5),
           lambda c, b, a, r, e: {"raised": isinstance(e, ValueError), "panel_closed": not any((ax.sattr(w, "AXTitle") or "").startswith("Adjust Color") for w in ax.children(ax.app(APP)))})
    K.case("image_adjust", m, st, "nothing_given", lambda: img("png"), lambda c: P.image_adjust(path=c["p"]), lambda c, b, a, r, e: {"raised": isinstance(e, ValueError)})
    for fn, call in (("image_crop", lambda c: P.image_crop(path=c["p"], left=0, top=0, right=1, bottom=1, mode="background")), ("image_adjust", lambda c: P.image_adjust(path=c["p"], exposure=1, mode="background"))):
        K.case(fn, "background", st, "not_supported", lambda: img("png"), call, lambda c, b, a, r, e: {"raised": isinstance(e, P.NotSupported)})
def large_clipboard():
    def setup():
        c = img("png"); c.update(size=(100, 80), corners=(RED, GREEN, BLUE, YELLOW)); return c
    K.case("image_crop", "ui", "open", "large_clipboard", setup, lambda c: P.image_crop(path=c["p"], left=0.25, top=0.25, right=0.75, bottom=0.75), cropped, lambda c: {vkit.nfc(c["p"])}, big=True)
    K.case("image_adjust", "ui", "open", "large_clipboard", lambda: (lambda c: (c.update(s0=stats(c["p"])), c)[1])(img("png")), lambda c: P.image_adjust(path=c["p"], exposure=1.0),
           lambda c, b, a, r, e: {"no_error": e is None, "brighter": bool(stats(c["p"])) and stats(c["p"])["mean"] > c["s0"]["mean"] + 15}, lambda c: {vkit.nfc(c["p"])}, big=True)
groups = [(s, (lambda s=s: state_cases(s))) for s in ("closed", "open", "other_app", "hidden", "minimized")] + [("errors", errors), ("large_clipboard", large_clipboard)]
K.run(states, groups)
