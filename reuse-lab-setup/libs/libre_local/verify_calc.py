"""verify_calc.py <group> <seed> <states...>: LibreOffice Calc's CSV sort, read back from the saved files."""
import csv, os, sys, time, unicodedata
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["CALC_ALLOWED_ROOT"] = os.path.expanduser("~/libre-test")
import calc as C, vkit, lo_close
from vcommon import osa, sh, se
group, seed, states = sys.argv[1], int(sys.argv[2]), sys.argv[3:]
APP = "soffice"
def front_app():
    try: return osa('tell application "System Events" to return name of first process whose frontmost is true')
    except RuntimeError: return ""
def start(state):
    lo_close.close_all()  # each case starts with no LibreOffice documents open (their names are new anyway)
    if state == "closed":
        if C._running():
            sh("osascript -e 'tell application \"LibreOffice\" to quit'"); [time.sleep(0.5) for _ in range(40) if C._running()]
        return
    if not C._running(): sh("open -a LibreOffice"); [time.sleep(0.5) for _ in range(40) if not C._running()]; time.sleep(4)
    C._close_welcome()
    if state == "other_doc":  # another document is open in front
        p = f"{K.DATA}/other {K.V.word()}.csv"; open(p, "w").write("Kind,Count\nPear,3\nFig,9\n")
        sh(f"open -a LibreOffice '{p}'"); time.sleep(3)
        for w in C._windows():
            ok = C._find(w, "AXButton", "OK")
            if C._string(w, "AXTitle").startswith("Text Import") and ok is not None: C._press(ok); time.sleep(3)
    se("set visible to true\nset frontmost to true", APP); time.sleep(0.5)
    if state == "other_app": sh("open -a Calculator"); [time.sleep(0.3) for _ in range(20) if front_app() == APP]
    time.sleep(0.5)
def clean(state):
    return not any(C._string(w, "AXTitle") in ("Sort", "Save", "Error", "Export Text File") or C._string(w, "AXTitle").startswith("Text Import") for w in C._windows()) if C._running() else True
K = vkit.Kit("libre", C, APP, group, seed, C.CalcError, start, clean)
n = {"i": 0}
def fold(x): return "".join(c for c in unicodedata.normalize("NFD", x) if not unicodedata.combining(c)).casefold()
def read(p):
    with open(p, encoding="utf-8-sig", newline="") as h: return list(csv.reader(h))
def table(kind):
    """A made-up CSV: names (some with accents, quotes, commas), a number column, a city column."""
    n["i"] += 1; i = n["i"]
    firsts = [K.V.special() if j % 2 else K.V.word(1) for j in range(6)]
    rows = [["Name", "Points", "City, Region"]] + [[f, str(K.V.rng.randint(1, 400)), f"{K.V.word(1)}, {K.V.rng.choice(['Nord', 'Süd', 'Ost'])}"] for f in firsts]
    d = f"{K.DATA}/t{i}"; os.makedirs(f"{d}/out")
    p = f"{d}/{(K.V.special() if i % 2 else K.V.word()).replace('/', '-')}.csv"
    with open(p, "w", newline="", encoding="utf-8") as h: csv.writer(h).writerows(rows)
    return {"p": p, "rows": rows, "to": f"{d}/out/{K.V.word()} sorted.csv"}
def expected(rows, col, desc):
    i = rows[0].index(col); body = rows[1:]
    key = (lambda r: float(r[i])) if col == "Points" else (lambda r: fold(r[i]))
    return [r[i] for r in sorted(body, key=key, reverse=desc)]
def checks(c, col, desc, r, e, b, a):
    out = read(c["to"]) if os.path.isfile(c["to"]) else []
    i = c["rows"][0].index(col)
    return {"no_error": e is None, "header_same": out[:1] == c["rows"][:1], "same_rows": sorted(map(tuple, out[1:])) == sorted(map(tuple, c["rows"][1:])),
            "sorted": [x[i] for x in out[1:]] == expected(c["rows"], col, desc), "source_same": read(c["p"]) == c["rows"],
            "return": bool(r) and r["path"] == c["to"] and r["rows"] == len(c["rows"]) - 1 and r["descending"] == desc}
def state_cases(state):
    m = "ui"
    for kind, col, desc in (("text_asc", "Name", False), ("number_desc", "Points", True), ("comma_header_asc", "City, Region", False)):
        K.case("csv_sort", m, state, kind, lambda kind=kind: table(kind), lambda c, col=col, desc=desc: C.csv_sort(path=c["p"], column=col, to=c["to"], descending=desc),
               lambda c, b, a, r, e, col=col, desc=desc: checks(c, col, desc, r, e, b, a), lambda c: {vkit.nfc(c["to"])})
def errors():
    m, st = "ui", "open"
    K.case("csv_sort", m, st, "no_column", lambda: table("x"), lambda c: C.csv_sort(path=c["p"], column="Nope", to=c["to"]), lambda c, b, a, r, e: {"raised": isinstance(e, C.NotFound), "nothing_written": not os.path.exists(c["to"])})
    K.case("csv_sort", m, st, "not_found", lambda: {}, lambda c: C.csv_sort(path=f"{K.DATA}/none.csv", column="Name", to=f"{K.DATA}/n.csv"), lambda c, b, a, r, e: {"raised": isinstance(e, C.NotFound)})
    def taken():
        c = table("x"); open(c["to"], "w").write("keep\n"); return c
    K.case("csv_sort", m, st, "exists", taken, lambda c: C.csv_sort(path=c["p"], column="Name", to=c["to"]), lambda c, b, a, r, e: {"raised": isinstance(e, C.AlreadyExists), "kept": open(c["to"]).read() == "keep\n"})
    K.case("csv_sort", m, st, "bad_suffix", lambda: table("x"), lambda c: C.csv_sort(path=c["p"], column="Name", to=c["to"][:-4] + ".txt"), lambda c, b, a, r, e: {"raised": isinstance(e, ValueError)})
    K.case("csv_sort", m, st, "guard", lambda: table("x"), lambda c: C.csv_sort(path=c["p"], column="Name", to="/tmp/outside sorted.csv"), lambda c, b, a, r, e: {"raised_Outside": isinstance(e, C.OutsideAllowedRoot), "nothing_outside": not os.path.exists("/tmp/outside sorted.csv")})
    K.case("csv_sort", "background", st, "not_supported", lambda: table("x"), lambda c: C.csv_sort(path=c["p"], column="Name", to=c["to"], mode="background"), lambda c, b, a, r, e: {"raised": isinstance(e, C.NotSupported)})
def large_clipboard():
    K.case("csv_sort", "ui", "open", "large_clipboard", lambda: table("big"), lambda c: C.csv_sort(path=c["p"], column="Name", to=c["to"]),
           lambda c, b, a, r, e: checks(c, "Name", False, r, e, b, a), lambda c: {vkit.nfc(c["to"])}, big=True)
# Convert (overnight): the saved .xlsx/.ods is read back here with its own small reader (zip + XML), separately from the library.
import zipfile, xml.dom.minidom as MD
def cells_of(p):
    z = zipfile.ZipFile(p)
    if p.endswith(".xlsx"):
        sst = [ "".join(t.firstChild.data if t.firstChild else "" for t in si.getElementsByTagName("t")) for si in MD.parseString(z.read("xl/sharedStrings.xml")).getElementsByTagName("si")] if "xl/sharedStrings.xml" in z.namelist() else []
        out = []
        for r in MD.parseString(z.read("xl/worksheets/sheet1.xml")).getElementsByTagName("row"):
            row = []
            for c in r.getElementsByTagName("c"):
                v = c.getElementsByTagName("v"); val = v[0].firstChild.data if v and v[0].firstChild else ""
                row.append(sst[int(val)] if c.getAttribute("t") == "s" else val)
            out.append(row)
        return out
    out = []
    for r in MD.parseString(z.read("content.xml")).getElementsByTagName("table:table-row"):
        row = []
        for c in r.getElementsByTagName("table:table-cell"):
            text = "\n".join("".join(n.data for n in p_.childNodes if n.nodeType == n.TEXT_NODE) for p_ in c.getElementsByTagName("text:p"))
            row += [text] * int(c.getAttribute("table:number-columns-repeated") or 1)
        while row and row[-1] == "": row.pop()
        if row: out.append(row)
    return out
def converted(c, b, a, r, e):
    try: got = cells_of(c["to"])
    except Exception: got = None
    return {"no_error": e is None, "cells_match": got == c["rows"], "source_same": read(c["p"]) == c["rows"],
            "no_lock": not any(n.startswith(".~lock") for n in os.listdir(os.path.dirname(c["to"]))),
            "return": bool(r) and r["path"] == c["to"] and r["format"] == c["to"].rsplit(".", 1)[1] and r["rows"] == len(c["rows"])}
def conv_table(suffix):
    c = table("conv"); c["to"] = c["to"].replace(" sorted.csv", f" sheet{suffix}"); return c
def convert_cases(state):
    for suffix in (".xlsx", ".ods"):
        K.case("csv_convert", "ui", state, suffix[1:], lambda suffix=suffix: conv_table(suffix), lambda c: C.csv_convert(path=c["p"], to=c["to"]), converted, lambda c: {vkit.nfc(c["to"])})
def convert_group():
    for st in ("closed", "open", "other_app", "other_doc"): convert_cases(st)
    m, st = "ui", "open"
    K.case("csv_convert", m, st, "bad_suffix", lambda: table("x"), lambda c: C.csv_convert(path=c["p"], to=c["to"][:-4] + ".numbers"), lambda c, b, a, r, e: {"raised": isinstance(e, ValueError)})
    def taken():
        c = conv_table(".xlsx"); open(c["to"], "w").write("keep"); return c
    K.case("csv_convert", m, st, "exists", taken, lambda c: C.csv_convert(path=c["p"], to=c["to"]), lambda c, b, a, r, e: {"raised": isinstance(e, C.AlreadyExists), "kept": open(c["to"]).read() == "keep"})
    K.case("csv_convert", m, st, "not_found", lambda: {}, lambda c: C.csv_convert(path=f"{K.DATA}/none.csv", to=f"{K.DATA}/n.xlsx"), lambda c, b, a, r, e: {"raised": isinstance(e, C.NotFound)})
    K.case("csv_convert", m, st, "guard", lambda: table("x"), lambda c: C.csv_convert(path=c["p"], to="/tmp/outside.xlsx"), lambda c, b, a, r, e: {"raised_Outside": isinstance(e, C.OutsideAllowedRoot), "nothing_outside": not os.path.exists("/tmp/outside.xlsx")})
    K.case("csv_convert", "background", st, "not_supported", lambda: conv_table(".ods"), lambda c: C.csv_convert(path=c["p"], to=c["to"], mode="background"), lambda c, b, a, r, e: {"raised": isinstance(e, C.NotSupported)})
    K.case("csv_convert", m, st, "large_clipboard", lambda: conv_table(".xlsx"), lambda c: C.csv_convert(path=c["p"], to=c["to"]), converted, lambda c: {vkit.nfc(c["to"])}, big=True)
# Spreadsheet to CSV (overnight): each case makes an .xlsx or .ods from a made-up CSV with csv_convert (verified on its own), then
# converts it back; the new CSV is read back here and must equal the original rows.
def sheet_setup(suffix):
    c = table("tocsv"); c["sheet"] = c["to"].replace(" sorted.csv", f" book{suffix}"); C.csv_convert(path=c["p"], to=c["sheet"])
    lo_close.close_all(); c["out"] = c["to"].replace(" sorted.csv", " back.csv"); return c
def back(c, b, a, r, e):
    got = [x for x in read(c["out"]) if x] if os.path.isfile(c["out"]) else None
    return {"no_error": e is None, "rows_match": got == c["rows"], "no_lock": not any(n.startswith(".~lock") for n in os.listdir(os.path.dirname(c["out"]))),
            "return": bool(r) and r["path"] == c["out"] and r["rows"] == len(c["rows"])}
def tocsv_cases(state):
    for suffix in (".xlsx", ".ods"):
        K.case("spreadsheet_to_csv", "ui", state, suffix[1:], lambda suffix=suffix: sheet_setup(suffix), lambda c: C.spreadsheet_to_csv(path=c["sheet"], to=c["out"]), back, lambda c: {vkit.nfc(c["out"])})
def tocsv_group():
    for st in ("closed", "open", "other_app", "other_doc"): tocsv_cases(st)
    m, st = "ui", "open"
    K.case("spreadsheet_to_csv", m, st, "not_sheet", lambda: table("x"), lambda c: C.spreadsheet_to_csv(path=c["p"], to=c["to"]), lambda c, b, a, r, e: {"raised": isinstance(e, ValueError)})
    K.case("spreadsheet_to_csv", m, st, "bad_target", lambda: sheet_setup(".ods"), lambda c: C.spreadsheet_to_csv(path=c["sheet"], to=c["out"][:-4] + ".txt"), lambda c, b, a, r, e: {"raised": isinstance(e, ValueError)})
    def taken():
        c = sheet_setup(".xlsx"); open(c["out"], "w").write("keep"); return c
    K.case("spreadsheet_to_csv", m, st, "exists", taken, lambda c: C.spreadsheet_to_csv(path=c["sheet"], to=c["out"]), lambda c, b, a, r, e: {"raised": isinstance(e, C.AlreadyExists), "kept": open(c["out"]).read() == "keep"})
    K.case("spreadsheet_to_csv", m, st, "not_found", lambda: {}, lambda c: C.spreadsheet_to_csv(path=f"{K.DATA}/none.xlsx", to=f"{K.DATA}/n.csv"), lambda c, b, a, r, e: {"raised": isinstance(e, C.NotFound)})
    def fake():
        p = f"{K.DATA}/fake {K.V.word()}.xlsx"; open(p, "w").write("not a zip"); return {"p": p}
    K.case("spreadsheet_to_csv", m, st, "not_a_spreadsheet", fake, lambda c: C.spreadsheet_to_csv(path=c["p"], to=f"{K.DATA}/f.csv"), lambda c, b, a, r, e: {"raised": isinstance(e, ValueError)})
    K.case("spreadsheet_to_csv", m, st, "guard", lambda: sheet_setup(".ods"), lambda c: C.spreadsheet_to_csv(path=c["sheet"], to="/tmp/outside.csv"), lambda c, b, a, r, e: {"raised_Outside": isinstance(e, C.OutsideAllowedRoot), "nothing_outside": not os.path.exists("/tmp/outside.csv")})
    K.case("spreadsheet_to_csv", "background", st, "not_supported", lambda: sheet_setup(".ods"), lambda c: C.spreadsheet_to_csv(path=c["sheet"], to=c["out"], mode="background"), lambda c, b, a, r, e: {"raised": isinstance(e, C.NotSupported)})
    K.case("spreadsheet_to_csv", m, st, "large_clipboard", lambda: sheet_setup(".xlsx"), lambda c: C.spreadsheet_to_csv(path=c["sheet"], to=c["out"]), back, lambda c: {vkit.nfc(c["out"])}, big=True)
groups = [(s, (lambda s=s: state_cases(s))) for s in ("closed", "open", "other_app", "other_doc")] + [("errors", errors), ("large_clipboard", large_clipboard), ("convert", convert_group), ("tocsv", tocsv_group)]
K.run(states, groups)
lo_close.close_all()
