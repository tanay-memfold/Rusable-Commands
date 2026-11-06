# Preview commands

`preview.py`: plain Python functions for images and PDFs in Preview. Python 3.9+, standard library only. Put this folder on
`sys.path` (or copy the file next to your program) and `import preview`.

```python
import preview

preview.image_rotate(path="~/Pictures/scan.jpg", direction="right")
preview.document_export(path="~/Pictures/scan.jpg", to="~/Desktop/scan.pdf", format="pdf")
preview.document_close(path="~/Pictures/scan.jpg")
```

**Verified on macOS 15.6.1 with Preview 11.0 only. This doesn't cover macOS 26 or any other version.** On another version, results
gain `"unverified_version": true` and both versions.

## Keeping it inside one folder

Set `PREVIEW_ALLOWED_ROOT` to a folder and every path is checked to be inside it, after following links, before anything happens.
A path outside raises `OutsideAllowedRoot`. Setting it is recommended for an agent.

## How it works

Every command works on screen (UI mode only; Preview has no scripting for these). Elements are found by role and name through the
macOS Accessibility API, menu items are clicked by name, and folder and file names are pasted into dialogs through the clipboard,
which is restored afterwards. No screen coordinates. It depends on English names.

Preview can open a document as a tab of another window. A tab in the background isn't a window to Accessibility, so the command
chooses the tab by its file name.

## Start states

It works with Preview closed, open with another document in front, hidden, minimized, and with another app in front.

## Functions

### document_open(path, mode="ui") → {name, path}
Opens an image or PDF, or brings it to the front.

### document_list(mode="ui") → [{name, path}]
The documents shown in Preview's windows. A document in a background tab isn't listed.

### document_close(path, mode="ui") → {name, path, closed}
**File > Close Window**. Preview keeps changes as it closes.

### image_rotate(path, direction="right", mode="ui") → {name, path}
**Tools > Rotate Left** or **Rotate Right**, then **File > Save**. The file changes in place; JPEG is re-encoded.

### image_flip(path, axis="horizontal", mode="ui") → {name, path}
**Tools > Flip Horizontal** or **Flip Vertical**, then **File > Save**.

### document_export(path, to, format, mode="ui") → {name, path, from, format}
**File > Export…** with the Format pop-up set to PNG, JPEG, HEIC, TIFF or PDF, saving a new file at `to`. The original stays.

### pdf_delete_page(path, page, mode="ui") → {name, path, pages}
Selects the page and uses **Edit > Delete**, then saves.

### pdf_move_page(path, page, to, mode="ui") → {name, path, pages, page, to}
**Edit > Cut** the page, select the page now at `to`, **Edit > Paste** (which goes before it), then save. Moving a page to the very
end isn't supported; move the pages after it instead.

### pdf_append_file(path, add, mode="ui") → {name, path, pages, from}
Selects the last page and uses **Edit > Insert > Page from File…** with the other PDF, then saves. This combines two PDFs.

Pages are selected in the thumbnail sidebar with the arrow keys, and the selection is checked by the window title ("Page 2 of 3"),
because the thumbnails can't be selected through Accessibility. Cut and Paste go through the clipboard, which is restored afterwards.

## Left out

- **Adjust Color (exposure and the rest)** and **Adjust Size**: their sliders and fields have no accessible names or labels, so they
  can't be set by name.
- **Crop**: it needs a rectangle dragged on the image.

## How it was verified

In fresh copies of one VM, with made-up images and PDFs inside one test folder, including names with emoji, accents and quotes.
Images were made with four coloured corners, and each result was read back from the saved file with separate code (ImageIO through
AppKit, `sips` for the format, PDFKit for PDFs): a rotation or flip had to move each corner's colour to the right place and change
the size as expected. Every other test file was compared by content before and after, and the top level of the home folder by name
and modified time. Every case set a small clipboard first and checked it came back, and some ran with a very large clipboard
(about 3.5 MB, text and other data) that had to come back exactly. Which documents are open was read from Preview's windows through
Accessibility, which isn't independent of Preview.

Export needed two fixes for timing: Preview's Export dialog fills in its controls after it appears, and Go to Folder ignored the
keystroke until the dialog had focus. Earlier runs failed 1 of 25 and 3 of 36 export cases this way; every export case was rerun
on the final code and passed. Every case, including the page commands, was rerun on the final code.

| Function | Mode | Verified | Cases | Start states |
|---|---|---|---|---|
| `document_close` | ui | yes | 6 | app closed, app hidden, minimized, app open, another app in front |
| `document_export` | ui | yes | 31 | app closed, app hidden, minimized, app open, another app in front |
| `document_list` | ui | yes | 5 | app closed, app hidden, minimized, app open, another app in front |
| `document_open` | ui | yes | 8 | app closed, app hidden, minimized, app open, another app in front |
| `image_flip` | ui | yes | 22 | app closed, app hidden, minimized, app open, another app in front |
| `image_rotate` | ui | yes | 24 | app closed, app hidden, minimized, app open, another app in front |
| `pdf_append_file` | ui | yes | 8 | app closed, app hidden, minimized, app open, another app in front |
| `pdf_delete_page` | ui | yes | 18 | app closed, app hidden, minimized, app open, another app in front |
| `pdf_move_page` | ui | yes | 18 | app closed, app hidden, minimized, app open, another app in front |

Verified on macOS 15.6.1 (24G90), preview 11.0 (1069.7.1), 2026-11-06, in fresh VM clones.

## Permissions

**Accessibility** and **Automation** for System Events. Folders macOS protects may ask for access once.
