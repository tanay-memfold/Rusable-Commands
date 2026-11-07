"""After fixes 1 to 3: the known-gap cases must now succeed. Results read from NoteStore.sqlite."""
import json, os, sys, time
sys.path.insert(0, os.path.expanduser("~/libs/notes")); sys.path.insert(0, os.path.expanduser("~/libs/verify"))
import notes as N, notes_db as D
from vcommon import osa, sh
OUT = os.path.expanduser("~/verify-out/fixes.json"); os.makedirs(os.path.dirname(OUT), exist_ok=True)
rows = []
PREP = r"""function run(argv){const N=Application("Notes"),a=JSON.parse(argv[0]);const acc=N.accounts.byName("On My Mac");
if(a.folder&&!acc.folders.whose({name:a.folder}).length)N.make({new:"folder",at:acc,withProperties:{name:a.folder}});
if(!a.html)return "ok";return N.make({new:"note",at:a.folder?acc.folders.byName(a.folder):acc.defaultFolder(),withProperties:{body:a.html}}).id();}"""
def prep(title=None, body="", folder=None):
    return osa(PREP, json.dumps({"html": N._html(title + ("\n" + body if body else "")) if title else None, "folder": folder}), lang="JavaScript")
def live(title): return [n for n in D.live(D.snapshot()).values() if n["title"] == title]
def anywhere(title): return [n for n in D.snapshot()["notes"].values() if n["title"] == title]
def body(n): return n["body"][:-1] if n["body"].endswith("\n") else n["body"]
def case(name, call, test):
    before = {k: v for k, v in D.snapshot()["notes"].items()}
    err, res = None, None
    try: res = call()
    except Exception as e: err = f"{type(e).__name__}: {str(e)[:200]}"
    end, ok = time.monotonic() + 60, False
    while time.monotonic() < end:
        try: ok = bool(test())
        except Exception: ok = False
        if ok and err is None: break
        time.sleep(1)
    rows.append({"name": name, "passed": ok and err is None, "error": err}); json.dump(rows, open(OUT, "w"), indent=1, ensure_ascii=False)
    print(("PASS " if ok and err is None else "FAIL ") + name, err or "", flush=True)
sh("open -b com.apple.Notes"); time.sleep(4); prep(folder="Lockers")
def title_only(t):
    N.note_create(title=t); time.sleep(2)
title_only("Tide 1"); case("title-only note_append", lambda: N.note_append(match="Tide 1", text="added ✨"), lambda: body(live("Tide 1")[0]) == "added ✨")
title_only("Tide 2"); case("title-only note_rename", lambda: N.note_rename(match="Tide 2", title="Tide 2b"), lambda: body(live("Tide 2b")[0]) == "" and not live("Tide 2"))
title_only("Tide 3"); case("title-only note_replace_body", lambda: N.note_replace_body(match="Tide 3", body="new\nbody"), lambda: body(live("Tide 3")[0]) == "new\nbody")
title_only("Tide 4"); case("title-only note_move", lambda: N.note_move(match="Tide 4", folder="Lockers"), lambda: live("Tide 4")[0]["folder"] == "Lockers")
title_only("Tide 5"); case("title-only note_delete", lambda: N.note_delete(match="Tide 5"), lambda: not live("Tide 5") and anywhere("Tide 5")[0]["folder"] == "Recently Deleted")
title_only("Tide 6"); case("title-only note_pin", lambda: N.note_pin(match="Tide 6"), lambda: live("Tide 6")[0]["pinned"])
prep("Marble Wharf", "old words\nmore"); time.sleep(2)
case("empty body on a note with a body", lambda: N.note_replace_body(match="Marble Wharf", body=""), lambda: live("Marble Wharf") and body(live("Marble Wharf")[0]) == "")
case("empty body again (now empty): title intact", lambda: N.note_replace_body(match="Marble Wharf", body=""), lambda: live("Marble Wharf")[0]["text"].rstrip("\n") == "Marble Wharf")
title_only("Ember Dock"); case("empty body on a UI title-only note: title intact", lambda: N.note_replace_body(match="Ember Dock", body=""), lambda: live("Ember Dock")[0]["text"].rstrip("\n") == "Ember Dock")
prep("Saffron Ledger", "pin me"); time.sleep(2)
case("note_pin first call", lambda: N.note_pin(match="Saffron Ledger"), lambda: live("Saffron Ledger")[0]["pinned"])
case("note_pin second call: succeeds, still pinned", lambda: N.note_pin(match="Saffron Ledger"), lambda: live("Saffron Ledger")[0]["pinned"])
prep("Cobalt Reef", "unpinned target"); time.sleep(2)
case("note_pin on an unpinned note while a pinned one was selected", lambda: N.note_pin(match="Cobalt Reef"), lambda: live("Cobalt Reef")[0]["pinned"] and live("Saffron Ledger")[0]["pinned"])
prep("Birch Quay", "stays unpinned"); time.sleep(2)
case("distractor stays unpinned", lambda: None, lambda: not live("Birch Quay")[0]["pinned"])
print("DONE", flush=True)
