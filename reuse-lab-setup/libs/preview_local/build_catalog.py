"""Writes preview/catalog.json. Local only."""
import json
M = "Verified on macOS 15.6.1 with Preview 11.0 only, so it isn't known to work on macOS 26 or any other version."
ROOT = "Only touches what PREVIEW_ALLOWED_ROOT allows if it is set; if it isn't set, any image or PDF you can reach is accepted."
EN = "It depends on English names and was tested only in English."
SMALL = "Only small test images were used."
UIM = {"name": "mode", "type": "str", "required": False, "default": "ui", "meaning": "Must be \"ui\": Preview has no scripting for this."}
PATH = {"name": "path", "type": "str", "required": True, "default": None, "meaning": "An absolute path, or one starting with ~, to an image (.png, .jpg, .jpeg, .heic, .tif, .tiff, .gif, .bmp) or a PDF."}
IMG = {"name": "path", "type": "str", "required": True, "default": None, "meaning": "An absolute path, or one starting with ~, to an image (.png, .jpg, .jpeg, .heic, .tif, .tiff, .gif, .bmp)."}
V = {"name": "ValueError", "when": "an argument is invalid or mode isn't \"ui\" or \"background\""}
U = {"name": "UIError", "when": "a named element never appeared, or the change wasn't seen in time"}
S = {"name": "StateBlocked", "when": "the document has a dialog open, a dialog with typed text is showing, or another app came to the front; nothing is changed"}
NF = {"name": "NotFound", "when": "nothing is at the path; nothing is changed"}
OUT = {"name": "OutsideAllowedRoot", "when": "PREVIEW_ALLOWED_ROOT is set and a path is outside it; nothing is done"}
NS = {"name": "NotSupported", "when": "mode is \"background\": there is no background mode"}
PRE = "The program has Accessibility, and Automation for System Events."
ITEM = {"type": "object", "fields": ["name", "path"]}
def cmd(name, desc, args, req, eff, post, ret, errs, gaps):
    return {"name": name, "description": desc, "args": args, "modes": {"verified": ["ui"], "default": "ui"}, "example_requests": req, "effects": eff, "destructive": False, "precondition": PRE, "postcondition": post, "returns": ret, "errors": errs, "known_gaps": gaps}
cmds = [
 cmd("document_open", "Opens an image or PDF in Preview, or brings it to the front if it's open.", [PATH, UIM], ["Open this photo in Preview", "Show me the PDF", "Open the scan"], "idempotent", "The document is in front in Preview; the file is unchanged.", ITEM, [V, U, S, NF, OUT, NS], [M, ROOT, EN, "Preview may open it as a tab of another window; the tab is chosen by its file name."]),
 cmd("document_list", "Lists the documents shown in Preview's windows.", [UIM], ["What's open in Preview?", "List my open images", "Which PDFs are open?"], "read_only", "Nothing is changed.", {"type": "list", "fields": ["name", "path"]}, [V, U, NS], [M, EN, "A document in a background tab isn't listed, because only each window's front tab is a window to Accessibility."]),
 cmd("document_close", "Closes a document's window with File > Close Window; Preview keeps its changes.", [PATH, UIM], ["Close the photo", "Close this PDF in Preview", "I'm done with the image, close it"], "non_idempotent", "The window is gone.", {"type": "object", "fields": ["name", "path", "closed"]}, [V, U, S, {"name": "NotFound", "when": "the document isn't shown in a Preview window; nothing is changed"}, OUT, NS], [M, ROOT, EN, "A document in a background tab can't be closed, because it isn't found."]),
 cmd("image_rotate", "Rotates an image a quarter turn with Tools > Rotate Left or Rotate Right, and saves it.", [IMG, {"name": "direction", "type": "str", "required": False, "default": "right", "meaning": "\"left\" or \"right\"."}, UIM], ["Rotate this photo to the right", "Turn the image 90 degrees left", "Fix the sideways picture"], "non_idempotent", "The file is rotated and saved in place.", ITEM, [V, U, S, NF, OUT, NS], [M, ROOT, EN, SMALL, "The file is changed in place; JPEG is re-encoded."]),
 cmd("image_flip", "Flips an image with Tools > Flip Horizontal or Flip Vertical, and saves it.", [IMG, {"name": "axis", "type": "str", "required": False, "default": "horizontal", "meaning": "\"horizontal\" or \"vertical\"."}, UIM], ["Mirror this image", "Flip the photo upside down", "Flip the picture horizontally"], "non_idempotent", "The file is flipped and saved in place.", ITEM, [V, U, S, NF, OUT, NS], [M, ROOT, EN, SMALL, "The file is changed in place; JPEG is re-encoded."]),
 cmd("document_export", "Saves a copy of an image or PDF in another format with File > Export….", [PATH, {"name": "to", "type": "str", "required": True, "default": None, "meaning": "The new file's path, which must not exist, with a suffix that fits the format."}, {"name": "format", "type": "str", "required": True, "default": None, "meaning": "\"png\", \"jpeg\", \"heic\", \"tiff\" or \"pdf\"."}, UIM], ["Save this image as a JPEG", "Convert the PNG to PDF", "Export the photo as HEIC to my Desktop"], "non_idempotent", "The new file is in that format; the original is unchanged.", {"type": "object", "fields": ["name", "path", "from", "format"]}, [V, U, S, NF, {"name": "AlreadyExists", "when": "the new path is taken; nothing is overwritten"}, OUT, NS], [M, ROOT, EN, SMALL, "Format options such as JPEG quality are left as Preview sets them."]),
]
PDF = {"name": "path", "type": "str", "required": True, "default": None, "meaning": "An absolute path, or one starting with ~, to a .pdf."}
PG = lambda n, m: {"name": n, "type": "int", "required": True, "default": None, "meaning": m}
cmds += [
 cmd("pdf_delete_page", "Deletes one page of a PDF with Edit > Delete and saves it.", [PDF, PG("page", "The page to delete, counting from 1."), UIM], ["Delete page 3 of this PDF", "Remove the blank second page", "Take out the last page of the report"], "non_idempotent", "The PDF has every other page, in order.", {"type": "object", "fields": ["name", "path", "pages"]}, [V, U, S, NF, OUT, NS], [M, ROOT, EN, "The page is selected with the arrow keys in the thumbnail sidebar and checked by the window title, because the thumbnails can't be selected through Accessibility.", "Only small PDFs were tested."]),
 cmd("pdf_move_page", "Moves one page of a PDF to another position with Cut and Paste, and saves it.", [PDF, PG("page", "The page to move, counting from 1."), PG("to", "Its new position, from 1 to one less than the number of pages."), UIM], ["Move page 4 to the front", "Put the last page second", "Reorder the PDF so page 3 comes first"], "non_idempotent", "The page is at its new position and the others keep their order.", {"type": "object", "fields": ["name", "path", "pages", "page", "to"]}, [V, U, S, NF, OUT, NS], [M, ROOT, EN, "Moving a page to the very end isn't supported, because Paste goes before the selected page; move the pages after it instead.", "Only small PDFs were tested."]),
 cmd("pdf_append_file", "Adds every page of another PDF to the end of a PDF with Edit > Insert > Page from File…, and saves it.", [PDF, {"name": "add", "type": "str", "required": True, "default": None, "meaning": "The PDF whose pages are added; it stays as it is."}, UIM], ["Combine these two PDFs", "Add the appendix PDF to the end of the report", "Merge scan2.pdf into scan1.pdf"], "non_idempotent", "The PDF ends with the other PDF's pages, in order.", {"type": "object", "fields": ["name", "path", "pages", "from"]}, [V, U, S, NF, OUT, NS], [M, ROOT, EN, "Only small PDFs were tested."]),
]
FR = lambda n, m: {"name": n, "type": "float", "required": True, "default": None, "meaning": m}
DRAG = "The rectangle is dragged on screen with positions computed from the image element's own frame after Zoom to Fit, never fixed screen positions; the whole image must show in its window."
DAY4 = "Added on day 4 in its own section and tested on its own."
cmds += [
 cmd("image_crop", "Crops an image to a rectangle given as fractions of its width and height, and saves it (Tools > Rectangular Selection, a drag over the image, Tools > Crop).",
     [IMG, FR("left", "The rectangle's left edge, 0 to 1 of the width."), FR("top", "Its top edge, 0 to 1 of the height."), FR("right", "Its right edge."), FR("bottom", "Its bottom edge."), UIM],
     ["Crop the photo to its centre", "Cut off the right third of the image", "Crop this screenshot to the top half"], "non_idempotent", "The file holds only the rectangle.", ITEM,
     [V, U, S, NF, OUT, NS], [M, EN, DRAG, "The rectangle must be at least 5% of the image wide and high; sizes come out within a pixel or two.", DAY4]),
 cmd("image_adjust", "Changes an image's exposure, contrast or saturation in Tools > Adjust Color… and saves it.",
     [IMG, {"name": "exposure", "type": "float | None", "required": False, "default": None, "meaning": "-2 to 2."}, {"name": "contrast", "type": "float | None", "required": False, "default": None, "meaning": "-1 to 1."},
      {"name": "saturation", "type": "float | None", "required": False, "default": None, "meaning": "0 to 2 (1 is unchanged)."}, UIM],
     ["Brighten the photo", "Raise the exposure a bit", "Make the image black and white"], "non_idempotent", "The file is saved with the change.", ITEM,
     [V, U, S, NF, OUT, NS], [M, EN, "Each slider is found by the named icons beside it and set to the value; a value outside the slider's own range raises ValueError.", DAY4]),
 cmd("image_resize", "Resizes an image in pixels with Tools > Adjust Size… and saves it, keeping its proportions when only a width or a height is given.",
     [IMG, {"name": "width", "type": "int | None", "required": False, "default": None, "meaning": "New width in pixels, 1 to 20000."},
      {"name": "height", "type": "int | None", "required": False, "default": None, "meaning": "New height in pixels, 1 to 20000; give both to set both exactly."}, UIM],
     ["Resize the photo to 600 pixels wide", "Make this image 400 pixels tall", "Shrink the picture to 800 by 600"], "non_idempotent", "The file is saved at the new size.", {"type": "object", "fields": ["name", "path", "width", "height", "was"]},
     [V, U, S, NF, OUT, NS], [M, EN, "The dialog's size fields have no names: each is found on the row of its own label (Width:, Height:) and checked by value before typing.", "Added overnight in its own section and tested on its own."]),
 cmd("pdf_insert_blank_page", "Adds a blank page to a PDF right after a given page with Edit > Insert > Blank Page, and saves it.",
     [{"name": "path", "type": "str", "required": True, "default": None, "meaning": "The PDF."}, {"name": "after", "type": "int", "required": True, "default": None, "meaning": "The page (from 1) the blank page goes after."}, UIM],
     ["Add a blank page after page 2", "Insert an empty page at the end of this PDF", "Put a blank page after the cover"], "non_idempotent", "The PDF has one more page, blank, right after page after.", {"type": "object", "fields": ["name", "path", "pages", "blank_page"]},
     [V, U, S, NF, OUT, NS], [M, EN, "Added overnight in its own section and tested on its own."]),
 cmd("pdf_rotate_page", "Turns one page of a PDF a quarter turn with Tools > Rotate Right or Rotate Left and saves it; the other pages stay as they are.",
     [{"name": "path", "type": "str", "required": True, "default": None, "meaning": "The PDF."}, {"name": "page", "type": "int", "required": True, "default": None, "meaning": "The page to turn, from 1."},
      {"name": "direction", "type": "str", "required": False, "default": "right", "meaning": "\"right\" (clockwise) or \"left\"."}, UIM],
     ["Rotate page 3 of this PDF", "Turn the second page left", "Fix the sideways page in the scan"], "non_idempotent", "Only that page is turned a quarter turn in the saved PDF.", {"type": "object", "fields": ["name", "path", "page", "direction", "pages"]},
     [V, U, S, NF, OUT, NS], [M, EN, "The saved file's page rotations are read back and checked.", "Added overnight in its own section and tested on its own."]),
]
json.dump({"app": "Preview", "import": "import preview", "macos_version": "15.6.1 (24G90)", "app_version": "11.0 (1069.7.1)", "commands": cmds}, open("../preview/catalog.json", "w"), indent=2, ensure_ascii=False); open("../preview/catalog.json", "a").write("\n"); print(len(cmds))
