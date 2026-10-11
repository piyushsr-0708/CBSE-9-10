"""Inspect node text representations for class10 maths and computer_application."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

for fname in ["cbse_class10_maths_2026_27.json", "cbse_class10_computer_application_2026_27.json"]:
    fp = ROOT / "data" / "syllabus" / fname
    with open(fp, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    nodes = []
    def walk(ns, path="", depth=0):
        for n in ns:
            ntype = n.get("type","")
            nid = n.get("id","")
            name = n.get("name","")
            desc = n.get("description","")
            text = f"{path} {name} {desc}".strip()
            nodes.append({
                "depth": depth, "type": ntype, "id": nid,
                "name": name[:80], "desc": desc[:80],
                "full_text": text[:120]
            })
            walk(n.get("children",[]) or [], text, depth+1)
    walk(data.get("curriculum",[]))
    
    out = ROOT / "reports" / f"_nodes_{fname.replace('.json','')}.md"
    with open(out, "w", encoding="utf-8") as f:
        f.write(f"# Nodes for {fname}\n\n")
        f.write(f"Total: {len(nodes)}\n\n")
        for n in nodes:
            indent = "  " * n["depth"]
            f.write(f"{indent}[{n['type']}] {n['id']}: {n['name']}\n")
            if n['desc']:
                f.write(f"{indent}  desc: {n['desc']}\n")
    print(f"Written {len(nodes)} nodes to {out}")
