"""Throwaway: compare the catalogs with the code, statically (nothing is imported or run)."""
import ast
import json
import os
import sys

REPO = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
KEYS = {"name", "description", "args", "modes", "example_requests", "effects", "destructive", "precondition",
        "postcondition", "returns", "errors"}
OPTIONAL = {"confirm", "known_gaps", "verified_on"}
DESTRUCTIVE = {"event_delete", "calendar_delete", "folder_delete", "note_replace_body", "message_send", "message_reply", "message_trash", "reminder_delete", "list_delete", "file_trash", "contact_delete", "group_delete", "environment_remove", "shortcut_delete"}
LEFT_OUT = {"message_get", "shortcut_create"}  # in the code, refuses with NotSupported because it was not verified
ARG_KEYS = {"name", "type", "required", "default", "meaning"}
EFFECTS = {"read_only", "idempotent", "non_idempotent"}
total = 0


def check(problems, ok, message):
    global total
    total += 1
    if not ok:
        problems.append(message)


def signature(fn, consts=None):
    """A default that names a module-level constant (e.g. RUN_TIMEOUT) is read as that constant's literal value."""
    consts = consts or {}
    def value(d):
        if isinstance(d, ast.Name) and d.id in consts:
            return consts[d.id]
        return ast.literal_eval(d)
    args = fn.args.args
    defaults = [None] * (len(args) - len(fn.args.defaults)) + list(fn.args.defaults)
    out = []
    for a, d in zip(args, defaults):
        out.append({"name": a.arg, "type": ast.unparse(a.annotation) if a.annotation else None, "required": d is None,
                    "default": value(d) if d is not None else None})
    return out


def run(folder, module):
    problems = []
    path = f"{REPO}/{folder}/{module}"
    tree = ast.parse(open(path).read())
    functions = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef) and not n.name.startswith("_") and n.name not in LEFT_OUT}
    classes = {n.name for n in tree.body if isinstance(n, ast.ClassDef)}
    values = {}
    for n in tree.body:
        if isinstance(n, ast.AnnAssign) and n.target.id == "VERIFIED":
            values["VERIFIED"] = ast.literal_eval(n.value)
        if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", None) in ("FIELDS", "DEFAULT_FIELDS"):
            values[n.targets[0].id] = ast.literal_eval(n.value)
        if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", None) in ("ROW_FIELDS", "ROW_DEFAULT"):
            values[{"ROW_FIELDS": "FIELDS", "ROW_DEFAULT": "DEFAULT_FIELDS"}[n.targets[0].id]] = ast.literal_eval(n.value)
    verified = values["VERIFIED"]
    catalog = json.load(open(f"{REPO}/{folder}/catalog.json"))
    check(problems, True, "parses")
    later = {c["name"]: c["verified_on"] for c in catalog["commands"] if "verified_on" in c}
    versions = {(m["macos"], m["app"]) for name, f in verified.items() if name not in later for m in f.values()}
    check(problems, versions == {(catalog["macos_version"], catalog["app_version"])}, f"versions {versions}")
    for name, macos in later.items():
        check(problems, all(m["macos"].startswith(macos + " ") for m in verified.get(name, {}).values()), f"{name}: verified_on {macos}")
    check(problems, set(catalog) == {"app", "import", "macos_version", "app_version", "commands"}, "top-level keys")
    names = [c["name"] for c in catalog["commands"]]
    check(problems, len(names) == len(set(names)), "duplicate command")
    check(problems, set(names) == set(verified), f"catalog vs VERIFIED: {set(names) ^ set(verified)}")
    check(problems, set(names) == set(functions), f"catalog vs public functions: {set(names) ^ set(functions)}")
    for c in catalog["commands"]:
        name = c["name"]
        check(problems, KEYS <= set(c) <= KEYS | OPTIONAL, f"{name}: keys {set(c) ^ KEYS}")
        destructive = c.get("destructive")
        check(problems, type(destructive) is bool, f"{name}: destructive is not true/false")
        check(problems, destructive == (name in DESTRUCTIVE), f"{name}: destructive {destructive}")
        check(problems, ("confirm" in c) == (destructive is True), f"{name}: confirm vs destructive")
        if "confirm" in c:
            question = c["confirm"]
            check(problems, question.endswith("?") and "<" in question and ">" in question, f"{name}: confirm wording")
            roles = {a["name"] for a in c["args"]} | {"title"}
            used = {part.split(">")[0] for part in question.split("<")[1:]}
            check(problems, used <= roles, f"{name}: confirm roles {used}")
        gaps = c.get("known_gaps", [])
        check(problems, isinstance(gaps, list) and ("known_gaps" not in c or gaps), f"{name}: known_gaps empty")
        for gap in gaps:
            check(problems, gap.strip() and gap.endswith(".") and gap.count(". ") == 0, f"{name}: gap wording {gap}")
        fn = functions.get(name)
        check(problems, fn is not None, f"{name}: not in code")
        if fn is None:
            continue
        consts = {n.targets[0].id: ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign) and len(n.targets) == 1
                  and isinstance(n.targets[0], ast.Name) and n.targets[0].id.isupper() and isinstance(n.value, ast.Constant)}
        real = signature(fn, consts)
        check(problems, [a["name"] for a in c["args"]] == [a["name"] for a in real], f"{name}: arg names/order")
        for mine, code in zip(c["args"], real):
            where = f"{name}.{code['name']}"
            check(problems, set(mine) == ARG_KEYS, f"{where}: keys")
            check(problems, mine["required"] == code["required"], f"{where}: required")
            check(problems, mine["default"] == code["default"] and type(mine["default"]) is type(code["default"]),
                  f"{where}: default {mine['default']!r} vs {code['default']!r}")
            if code["type"] is not None:
                check(problems, mine["type"] == code["type"], f"{where}: type {mine['type']} vs {code['type']}")
            else:
                check(problems, (code["name"] == "fields" and mine["type"] == "str | list | None") or (code["name"] == "to" and mine["type"] == "str | list"), f"{where}: untyped")
            check(problems, bool(mine["meaning"].strip()), f"{where}: meaning")
        modes = c["modes"]
        check(problems, set(modes) == {"verified", "default"}, f"{name}: modes keys")
        check(problems, set(modes["verified"]) == set(verified[name]), f"{name}: modes {modes['verified']}")
        default = next(a["default"] for a in real if a["name"] == "mode")
        check(problems, modes["default"] == default, f"{name}: default mode {modes['default']} vs {default}")
        check(problems, default in verified[name], f"{name}: default mode {default} is not verified")
        check(problems, 3 <= len(c["example_requests"]) <= 5, f"{name}: example_requests")
        check(problems, c["effects"] in EFFECTS, f"{name}: effects")
        check(problems, bool(c["description"].strip()) and c["description"].count(". ") == 0, f"{name}: description")
        check(problems, c["precondition"].strip() and c["postcondition"].strip(), f"{name}: conditions")
        text = ast.unparse(fn)
        builtin = {"ValueError"}
        for e in c["errors"]:
            check(problems, e["name"] in classes | builtin and e["when"].strip(), f"{name}: error {e['name']}")
        listed = {e["name"] for e in c["errors"]}
        check(problems, "UIError" in listed and "ValueError" in listed, f"{name}: UIError/ValueError missing")
        check(problems, ("StateBlocked" not in listed or "ui" in verified[name]) and ("StateBlocked" in listed or "ui" not in verified[name] or c["effects"] == "read_only"), f"{name}: StateBlocked vs ui mode")
        check(problems, ("NotSupported" in listed) == (set(verified[name]) != {"ui", "background"} or "NotSupported" in text or "_script_open(" in text),
              f"{name}: NotSupported vs modes")
        check(problems, ("AlreadyExists" in listed) == ("AlreadyExists" in text or "_free(" in text or "_new_path(" in text or "_new_pdf(" in text), f"{name}: AlreadyExists vs code")
        # Returns: fields= commands use the module's defaults; others are read from the source of the function.
        r = c["returns"]
        has_fields = any(a["name"] == "fields" for a in real)
        check(problems, r["type"] == ("list" if fn.returns and ast.unparse(fn.returns) == "list" else "object"), f"{name}: returns type")
        if has_fields:
            check(problems, r["fields"] == values["DEFAULT_FIELDS"].split(","), f"{name}: default fields")
            check(problems, set(r["fields"]) | set(r["optional_fields"]) == set(values["FIELDS"]), f"{name}: optional fields")
        elif "DEFAULT_FIELDS" in text:
            extra = set(r["fields"]) - set(values["DEFAULT_FIELDS"].split(",")) - {"id", "uid"}
            for key in extra:
                check(problems, repr(key) in text, f"{name}: returned key {key} not in code")
            key = "id" if folder in ("notes", "reminders", "contacts") else "uid"
            check(problems, key in r["fields"], f"{name}: {key}")
    return names, problems


failed = 0
for folder, module in [("notes", "notes.py"), ("calendar", "calendar_app.py"), ("gmail", "gmail.py"), ("reminders", "reminders.py"), ("finder", "finder.py"), ("contacts", "contacts.py"), ("safari", "safari.py"), ("chrome", "chrome.py"), ("textedit", "textedit.py"), ("preview", "preview.py"), ("keka", "keka.py"), ("obsidian", "obsidian.py"), ("automator", "automator.py"), ("vscode", "vscode.py"), ("xcode", "xcode.py"), ("obs", "obs.py"), ("anaconda", "anaconda.py"), ("libreoffice", "calc.py"), ("settings", "system_settings.py"), ("shortcuts", "shortcuts.py")]:
    names, problems = run(folder, module)
    print(f"{folder}: {len(names)} commands, {'OK' if not problems else 'PROBLEMS'}")
    for p in problems:
        print("  -", p)
    failed += len(problems)
print(f"{total} checks, {failed} problems")
sys.exit(1 if failed else 0)
