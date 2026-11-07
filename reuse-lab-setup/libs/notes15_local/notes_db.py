"""Read-only view of NoteStore.sqlite: every note's full text (from its protobuf), checklist lines, folder, pinned
and trash state, and every folder. Never writes."""
import gzip
import os
import sqlite3

PATH = os.path.expanduser("~/Library/Group Containers/group.com.apple.notes/NoteStore.sqlite")


def _varint(buf: bytes, i: int):
    shift = value = 0
    while True:
        byte = buf[i]
        value |= (byte & 0x7F) << shift
        i += 1
        if byte < 0x80:
            return value, i
        shift += 7


def _message(buf: bytes) -> dict:
    out, i = {}, 0
    while i < len(buf):
        key, i = _varint(buf, i)
        field, wire = key >> 3, key & 7
        if wire == 0:
            value, i = _varint(buf, i)
        elif wire == 2:
            length, i = _varint(buf, i)
            value, i = buf[i:i + length], i + length
        elif wire == 5:
            value, i = buf[i:i + 4], i + 4
        elif wire == 1:
            value, i = buf[i:i + 8], i + 8
        else:
            raise ValueError(f"wire type {wire}")
        out.setdefault(field, []).append(value)
    return out


def _note(data: bytes):
    """The note's text, its checklist lines and whether each is checked."""
    note = _message(_message(_message(gzip.decompress(data))[2][0])[3][0])
    text = note[2][0].decode("utf-8")
    styles = []
    for run in note.get(5, []):
        fields = _message(run)
        style = _message(fields[2][0]) if 2 in fields else {}
        done = _message(style[5][0]).get(2, [0])[0] if 5 in style else 0
        styles += [(style.get(1, [None])[0], done)] * fields[1][0]
    checklist, checked, offset = [], [], 0
    for line in text.split("\n"):
        style, done = styles[offset] if offset < len(styles) else (None, 0)
        if style == 103 and line:
            checklist.append(line)
            checked.append(bool(done))
        offset += len(line.encode("utf-16-le")) // 2 + 1
    return text, checklist, checked


def snapshot() -> dict:
    db = sqlite3.connect(f"file:{PATH}?mode=ro", uri=True)
    try:
        folders = {pk: {"name": name, "marked": bool(marked), "trash": kind == 1}
                   for pk, name, marked, kind in db.execute(
                       "select Z_PK, ZTITLE2, ZMARKEDFORDELETION, ZFOLDERTYPE from ZICCLOUDSYNCINGOBJECT "
                       "where ZTITLE2 is not null")}
        notes = {}
        for pk, title, folder, pinned, marked, data in db.execute(
                "select o.Z_PK, o.ZTITLE1, o.ZFOLDER, o.ZISPINNED, o.ZMARKEDFORDELETION, d.ZDATA "
                "from ZICCLOUDSYNCINGOBJECT o left join ZICNOTEDATA d on d.Z_PK = o.ZNOTEDATA "
                "where o.ZTITLE1 is not null"):
            text, checklist, done = _note(data) if data else ("", [], [])
            where = folders.get(folder, {})
            notes[pk] = {"title": title, "text": text, "body": text.split("\n", 1)[1] if "\n" in text else "",
                         "folder": where.get("name"),
                         "trashed": bool(where.get("trash")) or bool(where.get("marked")) or bool(marked),
                         "pinned": bool(pinned), "checklist": checklist, "checked": done}
        return {"notes": notes, "folders": folders}
    finally:
        db.close()


def live(snap: dict) -> dict:
    return {pk: n for pk, n in snap["notes"].items() if not n["trashed"]}


def titled(snap: dict, title: str) -> list:
    return [n for n in live(snap).values() if n["title"] == title]


def folder_names(snap: dict) -> list:
    return sorted(f["name"] for f in snap["folders"].values() if not f["marked"] and not f["trash"])
