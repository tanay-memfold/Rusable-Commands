"""Read-only view of Reminders' own database, separate from the library and from scripting. Never writes."""
import datetime, glob, os, sqlite3
STORES = os.path.expanduser("~/Library/Group Containers/group.com.apple.reminders/Container_v1/Stores")
EPOCH = datetime.datetime(2001, 1, 1, tzinfo=datetime.timezone.utc)
PRIORITY = {1: "high", 5: "medium", 9: "low"}
def _due(seconds, all_day):
    if seconds is None: return None
    moment = EPOCH + datetime.timedelta(seconds=seconds)
    return moment.strftime("%Y-%m-%d") if all_day else moment.astimezone().strftime("%Y-%m-%d %H:%M")
def snapshot() -> dict:
    """{"reminders": {key: fields}, "lists": {key: name}}, leaving out rows marked for deletion."""
    out = {"reminders": {}, "lists": {}}
    for path in glob.glob(STORES + "/*.sqlite"):
        db = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5)
        tag = os.path.basename(path)[:13]
        try:
            names = {}
            for pk, name, gone, ident in db.execute("select Z_PK, ZNAME, ZMARKEDFORDELETION, ZCKIDENTIFIER from ZREMCDBASELIST"):
                names[pk] = name
                if not gone and name is not None: out["lists"][f"{tag}:{pk}"] = name
            for pk, title, notes, due, all_day, done, gone, lst, priority in db.execute(
                    "select Z_PK, ZTITLE, ZNOTES, ZDUEDATE, ZALLDAY, ZCOMPLETED, ZMARKEDFORDELETION, ZLIST, ZPRIORITY from ZREMCDREMINDER"):
                if gone: continue
                out["reminders"][f"{tag}:{pk}"] = {"title": title, "notes": notes or "", "due": _due(due, all_day), "completed": bool(done), "list": names.get(lst), "priority": PRIORITY.get(priority)}
        except sqlite3.Error:
            pass
        finally:
            db.close()
    return out
def titled(snap, title): return [r for r in snap["reminders"].values() if r["title"] == title]
def others(before, after, keys):
    """Keys other than these that changed, appeared or went."""
    a, b = before["reminders"], after["reminders"]
    return sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k) and k not in keys)
