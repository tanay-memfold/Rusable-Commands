"""verify_keka.py <group> <seed> <states...>: Keka's archive commands, read back with Python's zipfile and tarfile."""
import hashlib, os, subprocess, sys, tarfile, time, zipfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["KEKA_ALLOWED_ROOT"] = os.path.expanduser("~/keka-test")
import keka as KK, vkit, ax
from vcommon import osa, sh, se
group, seed, states = sys.argv[1], int(sys.argv[2]), sys.argv[3:]
APP = "Keka"
def running(): return bool(sh("pgrep -x Keka"))
def front_app():
    try: return osa('tell application "System Events" to return name of first process whose frontmost is true')
    except RuntimeError: return ""
def start(state):
    if state == "closed":
        if running():
            try: osa('tell application id "com.aone.keka" to quit')
            except RuntimeError: pass
            [time.sleep(0.5) for _ in range(30) if running()]
        return
    if not running(): sh("open -b com.aone.keka"); [time.sleep(0.5) for _ in range(30) if not running()]; time.sleep(2)
    se("set visible to true\nset frontmost to true", APP); time.sleep(0.5)
    if state == "hidden": se("set visible to false", APP)
    elif state == "minimized": se('set value of attribute "AXMinimized" of window 1 to true', APP)
    elif state == "other_app": sh("open -a Calculator"); [time.sleep(0.3) for _ in range(20) if front_app() == APP]
    time.sleep(0.5)
def clean(state):
    if not running(): return True
    return not any(ax.sattr(w, "AXIdentifier") in ("save-panel", "open-panel") for w in ax.children(ax.app(APP)) if ax.sattr(w, "AXRole") == "AXWindow")
K = vkit.Kit("keka", KK, APP, group, seed, KK.KekaError, start, clean)
n = {"i": 0}
def sha(p): return hashlib.sha256(open(p, "rb").read()).hexdigest()
def items(count):
    n["i"] += 1; d = f"{K.DATA}/k{n['i']}-{K.V.rng.randint(100, 999)}"; os.makedirs(d)
    ps = []
    for k in range(count):
        p = f"{d}/{(K.V.special() if (n['i'] + k) % 2 else K.V.word()).replace('/', '-')} {k}.txt"; open(p, "w").write("content " + K.V.word() * 20); ps.append(p)
    return {"d": d, "ps": ps, "h": {vkit.nfc(os.path.basename(p)): sha(p) for p in ps}}
def zip_ok(path, want):
    try:
        with zipfile.ZipFile(path) as z:
            got = {}
            for i in z.infolist():
                name = i.filename if i.flag_bits & 0x800 else i.filename.encode("cp437").decode("utf-8")
                if name.startswith("__MACOSX/") or name.endswith("/"): continue
                got[vkit.nfc(name)] = hashlib.sha256(z.read(i)).hexdigest()
        return got == want
    except (OSError, zipfile.BadZipFile, UnicodeError): return False
def tar_ok(path, want):
    try:
        raw = open(path, "rb").read(512)
        if raw[:2] in (b"\x1f\x8b", b"BZ") or raw[257:262] != b"ustar": return False  # plain, uncompressed TAR
        with tarfile.open(path, "r:") as t:
            got = {vkit.nfc(os.path.basename(m.name)): hashlib.sha256(t.extractfile(m).read()).hexdigest() for m in t.getmembers() if m.isfile() and "/._" not in "/" + m.name}
        return got == want
    except (OSError, tarfile.TarError): return False
def new_files(c, a, b): return sorted(p for p in set(a) - set(b))
def as_format(fmt):
    def before(c):
        if KK.archive_format()["format"] != fmt: KK.archive_set_format(format=fmt)  # setup through the commands tested on their own below
    return before
def state_cases(state):
    m = "ui"
    for fmt, reader in (("zip", zip_ok), ("tar", tar_ok)):
        for count in (1, 2):
            if fmt == "tar" and count == 1: continue
            def read(c, b, a, r, e, reader=reader, fmt=fmt):
                new = new_files(c, a, b)
                return {"no_error": e is None, "one_archive": len(new) == 1, "archive_has_items": len(new) == 1 and reader(new[0], c["h"]),
                        "items_kept": all(a.get(vkit.nfc(p)) == b.get(vkit.nfc(p)) for p in c["ps"]), "return": bool(r) and vkit.nfc(r["path"]) in new and r["format"] == fmt}
            if state in ("closed", "hidden"):
                # Left out: these refuse, because items handed to a closed or hidden Keka were dropped in testing.
                K.case("archive_create", m, state, f"{fmt}_{count}_refused", lambda count=count, fmt=fmt: (as_format(fmt)(None), items(count))[1], lambda c: KK.archive_create(paths=c["ps"]),
                       lambda c, b, a, r, e: {"raised_NotSupported": isinstance(e, KK.NotSupported), "nothing_new": set(a) == set(b)})
                continue
            K.case("archive_create", m, state, f"{fmt}_{count}", lambda count=count, fmt=fmt: (as_format(fmt)(None), items(count))[1], lambda c: KK.archive_create(paths=c["ps"]), read,
                   lambda c: set(new_files(c, K.tree(), {})) - {vkit.nfc(p) for p in c["ps"]} if False else {p for p in K.tree() if p.startswith(vkit.nfc(c["d"]) + "/")} - {vkit.nfc(p) for p in c["ps"]})
    for fmt in ("tar", "7z", "zip"):
        K.case("archive_set_format", m, state, fmt, lambda: {}, lambda c, fmt=fmt: KK.archive_set_format(format=fmt),
               lambda c, b, a, r, e, fmt=fmt: {"no_error": e is None, "shown": running() and any(ax.sattr(x, "AXDescription") == "Format Selector" and ax.sattr(x, "AXValue") == KK.FORMATS[fmt] for w in ax.children(ax.app(APP)) for x in ax.walk(w)), "return": bool(r) and r["format"] == fmt})
    K.case("archive_format", m, state, "zip", lambda: (as_format("zip")(None), {})[1], lambda c: KK.archive_format(), lambda c, b, a, r, e: {"no_error": e is None, "matches_window": bool(r) and r["format"] == "zip"})
def an_archive(kind):
    c = items(2); d = c["d"]
    if kind == "zip":
        z = f"{d}/pack {n['i']}.zip"
        with zipfile.ZipFile(z, "w") as f:
            for p in c["ps"]: f.write(p, os.path.basename(p))
    else:
        z = f"{d}/pack {n['i']}.tar"
        with tarfile.open(z, "w") as f:
            for p in c["ps"]: f.add(p, os.path.basename(p))
    for p in c["ps"]: os.unlink(p)
    c["z"] = z; return c
def extracted(c, a):
    """Names and hashes of the files that came out: next to the archive, or (Keka's way with several items) in one new folder named
    after the archive."""
    out = {}
    for p, h in a.items():
        if h is None or vkit.nfc(p) == vkit.nfc(c["z"]) or not p.startswith(vkit.nfc(c["d"]) + "/"): continue
        rel = p[len(vkit.nfc(c["d"])) + 1:]
        parts = rel.split("/")
        if len(parts) == 1 or (len(parts) == 2 and parts[0] == vkit.nfc(os.path.splitext(os.path.basename(c["z"]))[0])):
            out[parts[-1]] = h
    return out
def returned(c, r):
    names = sorted(vkit.nfc(x["name"]) for x in r["items"])
    return names == sorted(c["h"]) or names == [vkit.nfc(os.path.splitext(os.path.basename(c["z"]))[0])]
def new_under(c): return {p for p in K.tree() if p.startswith(vkit.nfc(c["d"]) + "/")} - {vkit.nfc(c["z"])}
def extract_cases(state):
    m = "ui"
    for kind in ("zip", "tar"):
        if state in ("closed", "hidden"):
            K.case("archive_extract", m, state, f"{kind}_refused", lambda kind=kind: an_archive(kind), lambda c: KK.archive_extract(path=c["z"]),
                   lambda c, b, a, r, e: {"raised_NotSupported": isinstance(e, KK.NotSupported), "nothing_new": set(a) == set(b)})
            continue
        K.case("archive_extract", m, state, kind, lambda kind=kind: an_archive(kind), lambda c: KK.archive_extract(path=c["z"]),
               lambda c, b, a, r, e: {"no_error": e is None, "items_back": extracted(c, a) == c["h"],
                                      "archive_kept": a.get(vkit.nfc(c["z"])) == b.get(vkit.nfc(c["z"])), "return": bool(r) and returned(c, r)},
               lambda c: new_under(c))
def extract_errors():
    m, st = "ui", "open"
    def txt():
        c = items(1); return {"p": c["ps"][0]}
    K.case("archive_extract", m, st, "not_archive", txt, lambda c: KK.archive_extract(path=c["p"]), lambda c, b, a, r, e: {"raised": isinstance(e, ValueError)})
    K.case("archive_extract", m, st, "not_found", lambda: {}, lambda c: KK.archive_extract(path=f"{K.DATA}/none.zip"), lambda c, b, a, r, e: {"raised": isinstance(e, KK.NotFound)})
    K.case("archive_extract", m, st, "guard", lambda: {}, lambda c: KK.archive_extract(path="/tmp/outside.zip"), lambda c, b, a, r, e: {"raised_Outside": isinstance(e, KK.OutsideAllowedRoot)})
    K.case("archive_extract", "background", st, "not_supported", lambda: {}, lambda c: KK.archive_extract(path=f"{K.DATA}/x.zip", mode="background"), lambda c, b, a, r, e: {"raised": isinstance(e, KK.NotSupported)})
    K.case("archive_extract", m, st, "large_clipboard", lambda: an_archive("zip"), lambda c: KK.archive_extract(path=c["z"]),
           lambda c, b, a, r, e: {"no_error": e is None, "items_back": extracted(c, a) == c["h"]}, lambda c: new_under(c), big=True)
def errors():
    m, st = "ui", "open"
    def two_folders():
        a, b = items(1), items(1); return {"ps": [a["ps"][0], b["ps"][0]]}
    K.case("archive_create", m, st, "two_folders", two_folders, lambda c: KK.archive_create(paths=c["ps"]), lambda c, b, a, r, e: {"raised": isinstance(e, ValueError), "nothing_new": set(a) == set(b)})
    K.case("archive_create", m, st, "not_found", lambda: {}, lambda c: KK.archive_create(paths=[f"{K.DATA}/none.txt"]), lambda c, b, a, r, e: {"raised": isinstance(e, KK.NotFound)})
    K.case("archive_create", m, st, "empty", lambda: {}, lambda c: KK.archive_create(paths=[]), lambda c, b, a, r, e: {"raised": isinstance(e, ValueError)})
    K.case("archive_create", m, st, "guard", lambda: {}, lambda c: KK.archive_create(paths=["/tmp/outside.txt"]), lambda c, b, a, r, e: {"raised_Outside": isinstance(e, KK.OutsideAllowedRoot)})
    def taken():
        as_format("zip")(None); c = items(2); open(f"{c['d']}/Archive.zip", "w").write("keep"); return c
    K.case("archive_create", m, st, "name_taken", taken, lambda c: KK.archive_create(paths=c["ps"]),
           lambda c, b, a, r, e: {"no_error": e is None, "old_kept": open(f"{c['d']}/Archive.zip").read() == "keep", "new_archive": len(new_files(c, a, b)) == 1 and zip_ok(new_files(c, a, b)[0], c["h"])},
           lambda c: {p for p in K.tree() if p.startswith(vkit.nfc(c["d"]) + "/")} - {vkit.nfc(p) for p in c["ps"]} - {vkit.nfc(f"{c['d']}/Archive.zip")})
    K.case("archive_set_format", m, st, "bad", lambda: {}, lambda c: KK.archive_set_format(format="rar"), lambda c, b, a, r, e: {"raised": isinstance(e, ValueError)})
    for fn, call in (("archive_create", lambda c: KK.archive_create(paths=[f"{K.DATA}/x.txt"], mode="background")), ("archive_set_format", lambda c: KK.archive_set_format(format="zip", mode="background"))):
        K.case(fn, "background", st, "not_supported", lambda: {}, call, lambda c, b, a, r, e: {"raised": isinstance(e, KK.NotSupported)})
def large_clipboard():
    K.case("archive_create", "ui", "open", "large_clipboard", lambda: (as_format("zip")(None), items(2))[1], lambda c: KK.archive_create(paths=c["ps"]),
           lambda c, b, a, r, e: {"no_error": e is None, "archive_has_items": len(new_files(c, a, b)) == 1 and zip_ok(new_files(c, a, b)[0], c["h"])},
           lambda c: {p for p in K.tree() if p.startswith(vkit.nfc(c["d"]) + "/")} - {vkit.nfc(p) for p in c["ps"]}, big=True)
groups = [(s, (lambda s=s: state_cases(s))) for s in ("closed", "open", "other_app", "hidden", "minimized")] + [("extract_" + s, (lambda s=s: extract_cases(s))) for s in ("closed", "open", "other_app", "hidden", "minimized")] + [("errors", errors), ("extract_errors", extract_errors), ("large_clipboard", large_clipboard)]
K.run(states, groups)
