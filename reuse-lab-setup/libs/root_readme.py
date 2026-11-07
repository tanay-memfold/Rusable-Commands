"""Build the repo's top README: python3 root_readme.py <repo> <app>:<folder>:<import> ...

Fills ROOT_TOP.md with the app table, the list of catalog files and the verified table, read from each catalog.json."""
import json
import os
import sys

repo, apps = sys.argv[1], sys.argv[2:]
here = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(here, "ROOT_TOP.md")) as handle:
    top = handle.read()
rows, files, lists = [], [], []
for spec in apps:
    app, folder, imp = spec.split(":")
    rows.append(f"| {app} | [`{folder}/`]({folder}/) | `{imp}` |")
    files.append(f"`{folder}/catalog.json`")
    with open(os.path.join(repo, folder, "catalog.json")) as handle:
        catalog = json.load(handle)
    lines = [f"**{app}** ([README]({folder}/README.md)):", "", "| Function | Background | UI |", "|---|---|---|"]
    for command in sorted(catalog["commands"], key=lambda c: c["name"]):
        modes = command["modes"]["verified"]
        lines.append(f"| `{command['name']}` | {'verified' if 'background' in modes else '—'} | "
                     f"{'verified' if 'ui' in modes else '—'} |")
    lists.append("\n".join(lines))
joined = " and ".join([", ".join(files[:-1]), files[-1]]) if len(files) > 1 else files[0]
text = (top.replace("<!-- APPS -->", "\n".join(rows)).replace("<!-- CATALOG-FILES -->", joined)
        .replace("<!-- VERIFIED-LIST -->", "\n\n".join(lists)))
with open(os.path.join(repo, "README.md"), "w") as handle:
    handle.write(text)
