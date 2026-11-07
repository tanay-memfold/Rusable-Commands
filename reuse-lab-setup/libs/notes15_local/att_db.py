"""Read-only: a note's attachments in NoteStore.sqlite and the stored media files' hashes. Never writes."""
import hashlib, os, sqlite3
import notes_db
ROOT = os.path.expanduser("~/Library/Group Containers/group.com.apple.notes")
def _db(): return sqlite3.connect(f"file:{notes_db.PATH}?mode=ro", uri=True)
def note_pk(title):
    with _db() as db:
        rows = db.execute("select Z_PK from ZICCLOUDSYNCINGOBJECT where ZTITLE1 = ? and (ZMARKEDFORDELETION is null or ZMARKEDFORDELETION = 0)", (title,)).fetchall()
    return rows[0][0] if len(rows) == 1 else None
def media_hash(identifier):
    for base, dirs, files in os.walk(os.path.join(ROOT, "Accounts")):
        if os.path.basename(base) == identifier or identifier in base.split(os.sep):
            for f in files:
                return hashlib.sha256(open(os.path.join(base, f), "rb").read()).hexdigest()
    return None
def attachments(title):
    """[(uti, media file hash or None)] for the note's live attachments, or None if the note isn't found once."""
    pk = note_pk(title)
    if pk is None: return None
    with _db() as db:
        rows = db.execute("select a.ZTYPEUTI, m.ZIDENTIFIER from ZICCLOUDSYNCINGOBJECT a left join ZICCLOUDSYNCINGOBJECT m on m.Z_PK = a.ZMEDIA "
                          "where a.ZNOTE = ? and a.ZTYPEUTI is not null and (a.ZMARKEDFORDELETION is null or a.ZMARKEDFORDELETION = 0)", (pk,)).fetchall()
    return sorted((uti, media_hash(ident) if ident else None) for uti, ident in rows)
def text(title):
    found = notes_db.titled(notes_db.snapshot(), title)
    return found[0]["text"] if len(found) == 1 else None
