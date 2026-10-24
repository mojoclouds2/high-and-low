"""Build worker/redirects.json (tile id -> destination URL) from affiliates.json.
Run this before deploying the Worker:  python make_redirects.py
Destination URLs live only here and in the Worker; the public page links to /go/<id> instead."""
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
cfg = json.loads((Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "affiliates.json").read_text(encoding="utf-8"))
table, problems = {}, []


def add(id_, url):
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", id_ or ""):
        problems.append(f"bad id {id_!r} (use lowercase letters, digits, - and _)")
    elif not str(url).startswith("https://"):
        problems.append(f"{id_}: url must start with https://")
    elif id_ in table:
        problems.append(f"duplicate id {id_}")
    else:
        table[id_] = url


for cat, c in (cfg.get("categories") or {}).items():
    for i in c.get("items", []):
        if i.get("enabled", True):
            add(i.get("id"), i.get("url", ""))
sp = cfg.get("sponsored") or {}
if sp.get("enabled") and sp.get("url"):
    add("sponsor", sp["url"])

if problems:
    sys.exit("Not written:\n  " + "\n  ".join(problems))
(HERE / "worker" / "redirects.json").write_text(json.dumps(table, indent=1), encoding="utf-8")
print(f"wrote worker/redirects.json with {len(table)} links")
