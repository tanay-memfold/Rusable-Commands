"""Copy one app's verified library into the repo: python3 publish.py <app> <folder> <module.py> <repo>

Reads results/<app>-verification.json (from report.py) and <folder>/catalog.json, and writes exactly three files to
<repo>/<folder>/:
  <module.py>   the library with VERIFIED filled in (unverified function+modes raise NotSupported)
  README.md     with the verification table in place of <!-- VERIFIED -->
  catalog.json  copied after checking that its commands and modes match what was verified
Verification results, recordings and example programs stay in this folder; none of them go in the repo."""
import json
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
STATE_NAMES = {"closed": "app closed", "launching": "app still launching", "open": "app open",
               "other_view": "another folder/list/view showing", "hidden": "app hidden", "minimized": "minimized",
               "other_app": "another app in front", "alert_open": "a confirmation dialog open",
               "popover_open": "a popover open", "search_text": "search field with text",
               "typed_text": "half-typed text in another item", "selected_row": "another item selected",
               "selected": "another item selected", "two_windows": "two windows open",
               "blocked": "a dialog with typed text (StateBlocked)", "not_open": "Gmail not open", "other_tab": "Gmail on another tab",
               "other_label": "another label showing", "message_open": "a message open", "popup_open": "a popup open",
               "typed_text_name": "a name being edited", "other_tab": "another tab showing", "find_open": "the find bar open", "find_bar": "the Find bar focused (StateBlocked)", "no_sidebar": "the sidebar hidden", "no_window": "no window open",
               "other_doc": "another document in front", "edited_other": "unsaved changes in another document",
               "other_sheet": "a dialog on another document", "open_panel": "an Open dialog showing", "typed_text_doc": "a dialog with typed text",
               "env_page": "the Environments page showing", "pane_open": "the same pane already showing", "no_workflow": "Automator closed (no workflow)", "project_open": "another project open",
               "compose_empty": "an empty compose window", "compose_typed": "a compose window with typed text (StateBlocked)"}


def main():
    app, folder, module, repo = sys.argv[1:5]
    with open(os.path.join(HERE, "results", f"{app}-verification.json")) as handle:
        report = json.load(handle)
    versions = report["runs"][-1]["versions"]
    date = report["runs"][-1]["started"][:10]
    verified, rows = {}, []
    for function, modes in sorted(report["functions"].items()):
        for mode, entry in sorted(modes.items()):
            states = [s for s in entry["states"] if s != "blocked"]
            if entry["passed"]:
                verified.setdefault(function, {})[mode] = versions
            rows.append(f"| `{function}` | {mode} | {'yes' if entry['passed'] else 'no'} | {entry['cases']} | "
                        f"{', '.join(STATE_NAMES.get(s, s) for s in states)} |")
    with open(os.path.join(HERE, folder, "catalog.json")) as handle:
        catalog = json.load(handle)
    listed = {c["name"]: set(c["modes"]["verified"]) for c in catalog["commands"]}
    wanted = {name: set(modes) for name, modes in verified.items()}
    if listed != wanted:
        sys.exit(f"catalog.json doesn't match what was verified: {listed} vs {wanted}")
    target = os.path.join(repo, folder)
    os.makedirs(target, exist_ok=True)
    with open(os.path.join(HERE, folder, module)) as handle:
        source = handle.read()
    source, filled = re.subn(r"^VERIFIED: dict = \{\}$", lambda _: "VERIFIED: dict = " + json.dumps(verified, indent=4,
                             ensure_ascii=False), source, count=1, flags=re.M)
    if not filled:
        sys.exit(f"{module} has no empty VERIFIED table to fill")
    with open(os.path.join(target, module), "w") as handle:
        handle.write(source)
    table = ["| Function | Mode | Verified | Cases | Start states |", "|---|---|---|---|---|", *rows]
    with open(os.path.join(HERE, folder, "README.md")) as handle:
        readme = handle.read().replace("<!-- VERIFIED -->", "\n".join(table))
    readme = readme.replace("<!-- VERSIONS -->", f"Verified on macOS {versions['macos']}, {app} {versions['app']}, "
                                                 f"{date}, in fresh VM clones.")
    with open(os.path.join(target, "README.md"), "w") as handle:
        handle.write(readme)
    shutil.copy(os.path.join(HERE, folder, "catalog.json"), os.path.join(target, "catalog.json"))
    print(f"wrote {module}, README.md and catalog.json to {target}")


main()
