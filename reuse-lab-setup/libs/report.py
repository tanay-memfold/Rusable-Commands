"""Aggregate verifier results: python3 report.py <app> <group> [<group> ...]

A function+mode is verified when every case of it passed in the groups given (later groups replace earlier
results for the same function+mode+state+kind). Prints a summary and writes results/<app>-verification.json."""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def load(group):
    with open(os.path.join(HERE, "results", group, f"{group}.json")) as handle:
        return json.load(handle)


def main():
    app, groups = sys.argv[1], sys.argv[2:]
    cases, metas = {}, []
    for group in groups:
        data = load(group)
        clone = open(os.path.join(HERE, "results", f"{group}.clone")).read().strip() \
            if os.path.exists(os.path.join(HERE, "results", f"{group}.clone")) else None
        metas.append({"group": group, "clone": clone, **data["meta"]})
        for case in data["cases"]:
            # A refusal of an unverified mode shows the mode isn't there; it doesn't verify that mode.
            if case["kind"].endswith("not_supported"):
                continue
            cases[(case["function"], case["mode"], case["state"], case["kind"])] = {**case, "group": group}
    by = {}
    for (function, mode, state, kind), case in sorted(cases.items()):
        entry = by.setdefault(function, {}).setdefault(mode, {"passed": True, "states": [], "kinds": [],
                                                               "checks": set(), "cases": 0, "failures": []})
        entry["cases"] += 1
        entry["passed"] &= case["passed"]
        if state not in entry["states"]:
            entry["states"].append(state)
        if kind not in entry["kinds"]:
            entry["kinds"].append(kind)
        entry["checks"] |= set(case["checks"])
        if not case["passed"]:
            entry["failures"].append({"state": state, "kind": kind, "group": case["group"],
                                      "failed": [k for k, v in case["checks"].items() if not v],
                                      "detail": case["detail"]})
    out = {"app": app, "runs": metas, "functions": {}}
    for function, modes in by.items():
        for mode, entry in modes.items():
            entry["checks"] = sorted(entry["checks"])
            out["functions"].setdefault(function, {})[mode] = entry
            mark = "VERIFIED" if entry["passed"] else "FAILED  "
            print(f"{mark} {function:20} {mode:10} cases={entry['cases']:3} states={','.join(entry['states'])}")
            for failure in entry["failures"][:3]:
                print(f"           {failure['state']} {failure['kind']} {failure['failed']} "
                      f"{str(failure['detail'])[:220]}")
    with open(os.path.join(HERE, "results", f"{app}-verification.json"), "w") as handle:
        json.dump(out, handle, indent=1, ensure_ascii=False, default=str)


main()
