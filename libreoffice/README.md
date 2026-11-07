# LibreOffice Calc commands

`calc.py`: plain Python functions for LibreOffice Calc: sort a CSV file by one of its columns and save the result as a new CSV file,
save a CSV file as an Excel (.xlsx) or OpenDocument (.ods) spreadsheet, and save a spreadsheet's first sheet as a CSV.
Python 3.9+, standard library only. Put this folder on `sys.path` (or copy the file next to your program) and `import calc`.

```python
import calc

calc.csv_sort(path="~/Downloads/staff.csv", column="Last Name", to="~/Documents/staff by last name.csv")
calc.csv_sort(path="~/Downloads/staff.csv", column="Points", to="~/Documents/top points.csv", descending=True)
```

**Verified on macOS 15.6.1 with LibreOffice 26.8.1.1 only. This doesn't cover macOS 26 or any other version.** On another version,
results gain `"unverified_version": true` and both versions.

## How it works

UI mode only (LibreOffice has no AppleScript or command-line sort). Windows, menu items, dialogs, buttons, checkboxes and the Name
Box are found by name or identifier through the macOS Accessibility API. It depends on English names.

1. The CSV opens in LibreOffice. In the Text Import dialog, Comma is ticked, then OK. LibreOffice's first-run "Welcome to LibreOffice!"
   window is closed by its own close button. The document's window is brought forward, and nothing more happens until it has the
   keyboard.
2. The cursor goes to the column's header cell with the keyboard (⌘Home, then → once per column). Calc's Name Box must then read
   that cell (for example `C1`).
3. Data > Sort…: **Range contains column labels** is ticked, so the header row stays first, then Ascending or Descending, then OK.
   LibreOffice ignores the Accessibility "press" on that checkbox and on the order buttons. So each one's value is read first, and if
   it's unchanged, it's **clicked at the left end of the element's own frame** (its box). The value is then read again. This is the
   only clicking, and it's never at fixed screen positions.
4. File > Save As… to the new name (the folder and name are pasted, and the clipboard is restored), then **Use Text CSV Format**.
5. The written file is read back. The header must be the same, the rows the same, and the column in order: as numbers if every cell
   is one, otherwise as text ignoring case and accents. Otherwise `UIError`. Then the new document is closed (File > Close). If
   LibreOffice asks to save in its own format, the answer is Don't Save, because the CSV is already written and checked. The source
   file isn't changed.

It refuses (`StateBlocked`, nothing done) if a document with the source's or the target's name is already open, or if LibreOffice
shows its Document Recovery window. It never answers that window. Cells LibreOffice would change when importing (numbers with
leading zeros or trailing decimal zeros, dates) would change in the saved file. The read-back check catches that as `UIError`, not
silently.

## Functions

### csv_sort(path, column, to, descending=False, mode="ui") → {path, column, rows, descending}
Sorts the CSV at `path` by the column whose header (first row) is exactly `column`, and saves it as a new CSV at `to` (which must not
exist and must end in `.csv`). `rows` is the number of data rows. `NotFound` if there's no such file or column. `ValueError` if
two columns share the name or a suffix is wrong. `AlreadyExists` if `to` exists.

### csv_convert(path, to, mode="ui") → {path, format, rows}
Saves the CSV at `path` as a new spreadsheet at `to`: `.xlsx` (Excel 2010–365) or `.ods` (OpenDocument), by the suffix. The CSV is
opened as `csv_sort` opens it. Then **File > Save As…**: the file type is chosen by name in the save sheet's type menu, the folder
and name are pasted (the clipboard is restored), then Save, and LibreOffice's "Use Excel…" keep-format answer if it asks. The saved
file is read back (its XML, inside the zip), and every cell must match the CSV, or `UIError`. Then the new document is closed. The
CSV isn't changed. Added overnight in its own section of the file and tested on its own.

### spreadsheet_to_csv(path, to, mode="ui") → {path, rows}
Saves the first sheet of an `.xlsx` or `.ods` file as a new CSV at `to`. The spreadsheet is opened in LibreOffice. Then **File >
Save As…**: **Text CSV (.csv)** is chosen by name in the type menu, the folder and name are pasted (the clipboard is restored), then
Save, **Use Text CSV Format** and Export Text File's OK. The CSV is read back and must hold the first sheet's cells, or `UIError`.
Then the new document is closed. The spreadsheet isn't changed. Added overnight in its own section and tested on its own.

## How it was verified

In fresh copies of one VM, with made-up tables in each case: names with accents, quotes and emoji, a number column, and a header with
a comma in it. Runs had LibreOffice closed, open, behind another app, and with another document in front. Each sort was read back
from the saved file and compared with the order the test worked out itself. The source file was checked to be unchanged, and
nothing else in the test folder was allowed to change (LibreOffice's lock file included). Every case set a small clipboard first and
checked it came back, and one ran with a very large clipboard.

Convert (overnight): the saved .xlsx and .ods files were read back by the test with its own zip-and-XML reader, separately from
the library, and every cell compared with the CSV.

| Function | Mode | Verified | Cases | Start states |
|---|---|---|---|---|
| `csv_convert` | ui | yes | 13 | app closed, app open, another app in front, another document in front |
| `csv_sort` | ui | yes | 18 | app closed, app open, another app in front, another document in front |
| `spreadsheet_to_csv` | ui | yes | 15 | app closed, app open, another app in front, another document in front |

## Permissions

**Accessibility** and **Automation** for System Events.
