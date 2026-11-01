# Request: delete my empty notes, but keep any note in the folder Keep.
import notes

for note in notes.note_list(limit=500, fields="title,body,folder"):
    if not note["body"].strip() and note["folder"] != "Keep":
        notes.note_delete(match=note["title"], folder=note["folder"])
