import json, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from pathlib import Path

for f in Path("data/syllabus").glob("*.json"):
    with open(f, "r", encoding="utf-8") as fh:
        d = json.load(fh)
    cls = d.get("class", "?")
    subj = d.get("subject", "?")
    nodes = []
    def walk(ns, depth=0):
        for n in ns:
            nodes.append((depth, n.get("type",""), n.get("id",""), n.get("name","")))
            walk(n.get("children", []) or [], depth+1)
    walk(d.get("curriculum", []))
    print(f"\n=== {f.name}: {cls} / {subj} | {len(nodes)} nodes ===")
    for dep, typ, nid, name in nodes[:8]:
        print(f"  {'  '*dep}[{typ}] {nid}: {name[:60]}")
    if len(nodes) > 8:
        print(f"  ... ({len(nodes)} total)")
