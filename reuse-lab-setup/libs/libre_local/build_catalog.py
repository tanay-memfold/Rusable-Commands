"""Writes libreoffice/catalog.json. Local only."""
import json, sys
VER = sys.argv[1]
M = f"Verified on macOS 15.6.1 with LibreOffice {VER} only, so it isn't known to work on macOS 26 or any other version."
EN = "It depends on English names and was tested only in English."
UIM = {"name": "mode", "type": "str", "required": False, "default": "ui", "meaning": "Must be \"ui\": LibreOffice has no scripting for this."}
PRE = "The program has Accessibility, and Automation for System Events."
CLICK = "LibreOffice ignores the Accessibility press on the Sort dialog's labels checkbox and order buttons, so each is clicked at the left end of its own frame if its value didn't change, then read again; never fixed screen positions."
CHANGE = "Cells LibreOffice changes on import (leading zeros, trailing decimal zeros, dates) would change in the saved file; the read-back check reports that as UIError."
cmds = [{
    "name": "csv_sort", "description": "Opens a CSV in Calc, sorts its rows by one column (the header row stays first), saves the result as a new CSV, checks it by reading it back, and closes it.",
    "args": [{"name": "path", "type": "str", "required": True, "default": None, "meaning": "The CSV file to sort; not changed."},
             {"name": "column", "type": "str", "required": True, "default": None, "meaning": "The exact header of the column to sort by."},
             {"name": "to", "type": "str", "required": True, "default": None, "meaning": "The new CSV file; must not exist and must end in .csv."},
             {"name": "descending", "type": "bool", "required": False, "default": False, "meaning": "Sort Z to A / largest first."}, UIM],
    "modes": {"verified": ["ui"], "default": "ui"},
    "example_requests": ["Sort employee_list.csv by last name and save it as a new file", "Order this CSV by the Points column, highest first", "Sort the spreadsheet by city in LibreOffice"],
    "effects": "non_idempotent", "destructive": False, "precondition": PRE, "postcondition": "A new CSV at to holds the same header and rows, sorted by the column; the source is unchanged and no LibreOffice window for it is left open.",
    "returns": {"type": "object", "fields": ["path", "column", "rows", "descending"]},
    "errors": [{"name": "ValueError", "when": "a suffix is wrong, two columns share the name, or mode isn't \"ui\" or \"background\""},
               {"name": "NotFound", "when": "no such file, or no such column in the first row"},
               {"name": "AlreadyExists", "when": "to already exists; nothing is overwritten"},
               {"name": "OutsideAllowedRoot", "when": "CALC_ALLOWED_ROOT is set and a path is outside it"},
               {"name": "StateBlocked", "when": "a document with the source's or target's name is already open, LibreOffice shows Document Recovery, or another app came to the front"},
               {"name": "UIError", "when": "a named element never appeared, or the saved file wasn't sorted with the same rows"},
               {"name": "NotSupported", "when": "mode is \"background\""}],
    "known_gaps": [M, EN, CLICK, CHANGE]},
   {"name": "csv_convert", "description": "Saves a CSV file as a new Excel .xlsx or OpenDocument .ods spreadsheet with File > Save As…, checking every cell by reading the file back.",
    "args": [{"name": "path", "type": "str", "required": True, "default": None, "meaning": "The CSV file; not changed."},
             {"name": "to", "type": "str", "required": True, "default": None, "meaning": "The new file, ending in .xlsx or .ods; it must not exist."}, UIM],
    "modes": {"verified": ["ui"], "default": "ui"},
    "example_requests": ["Convert this CSV to an Excel file", "Save employee_list.csv as an .xlsx", "Turn the CSV into an OpenDocument spreadsheet"],
    "effects": "non_idempotent", "destructive": False, "precondition": PRE, "postcondition": "A new spreadsheet at to holds the CSV's cells; the CSV is unchanged and no LibreOffice window for it is left open.",
    "returns": {"type": "object", "fields": ["path", "format", "rows"]},
    "errors": [{"name": "ValueError", "when": "path isn't a .csv, to doesn't end in .xlsx or .ods, the CSV is empty, or mode isn't \"ui\" or \"background\""},
               {"name": "NotFound", "when": "no file at path"}, {"name": "AlreadyExists", "when": "to already exists; nothing is overwritten"},
               {"name": "OutsideAllowedRoot", "when": "CALC_ALLOWED_ROOT is set and a path is outside it"},
               {"name": "StateBlocked", "when": "a document with the source's or target's name is already open, LibreOffice shows Document Recovery, or another app came to the front"},
               {"name": "UIError", "when": "a named element never appeared, or the saved file's cells don't match the CSV"},
               {"name": "NotSupported", "when": "mode is \"background\""}],
    "known_gaps": [M, EN, CHANGE, "Added overnight in its own section and tested on its own."]},
   {"name": "spreadsheet_to_csv", "description": "Saves the first sheet of an .xlsx or .ods spreadsheet as a new CSV file with File > Save As…, checking it by reading it back.",
    "args": [{"name": "path", "type": "str", "required": True, "default": None, "meaning": "The .xlsx or .ods file; not changed."},
             {"name": "to", "type": "str", "required": True, "default": None, "meaning": "The new CSV file; it must not exist."}, UIM],
    "modes": {"verified": ["ui"], "default": "ui"},
    "example_requests": ["Export this Excel file as CSV", "Save the spreadsheet as a .csv", "Turn budget.ods into a CSV"],
    "effects": "non_idempotent", "destructive": False, "precondition": PRE, "postcondition": "A new CSV at to holds the first sheet's cells; the spreadsheet is unchanged and no LibreOffice window for it is left open.",
    "returns": {"type": "object", "fields": ["path", "rows"]},
    "errors": [{"name": "ValueError", "when": "path isn't an .xlsx or .ods that can be read, to doesn't end in .csv, or mode isn't \"ui\" or \"background\""},
               {"name": "NotFound", "when": "no file at path"}, {"name": "AlreadyExists", "when": "to already exists; nothing is overwritten"},
               {"name": "OutsideAllowedRoot", "when": "CALC_ALLOWED_ROOT is set and a path is outside it"},
               {"name": "StateBlocked", "when": "a document with the source's or target's name is already open, LibreOffice shows Document Recovery, or another app came to the front"},
               {"name": "UIError", "when": "a named element never appeared, or the CSV's cells don't match the first sheet"},
               {"name": "NotSupported", "when": "mode is \"background\""}],
    "known_gaps": [M, EN, "Only the first sheet is saved; only spreadsheets of plain text and whole numbers were tested.", "Added overnight in its own section and tested on its own."]}]
json.dump({"app": "LibreOffice Calc", "import": "import calc", "macos_version": "15.6.1 (24G90)", "app_version": f"{VER} ({VER})", "commands": cmds}, open("../libreoffice/catalog.json", "w"), indent=2, ensure_ascii=False); open("../libreoffice/catalog.json", "a").write("\n"); print(len(cmds))
