"""Comprehensive syllabus quality check across all 7 JSON files."""
import json
from pathlib import Path
from collections import Counter

ROOT = Path(__file__).resolve().parent.parent
SYLLABUS_DIR = ROOT / "data" / "syllabus"
OUT = ROOT / "reports" / "_syllabus_quality.md"

lines = ["# Syllabus JSON Quality Check\n"]

for f in sorted(SYLLABUS_DIR.glob("*.json")):
    with open(f, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    
    cls = data.get("class","?")
    subj = data.get("subject","?")
    
    type_counts = Counter()
    depth_max = 0
    all_nodes = []
    state = {"depth_max": 0, "empty_name": 0, "empty_children_chapters": 0}
    
    def walk(ns, depth=0):
        for n in ns:
            ntype = n.get("type","unknown")
            nid = n.get("id","")
            name = n.get("name","").strip()
            children = n.get("children", []) or []
            type_counts[ntype] += 1
            if depth > state["depth_max"]:
                state["depth_max"] = depth
            if not name:
                state["empty_name"] += 1
            if ntype in ("chapter","theme","unit") and not children:
                state["empty_children_chapters"] += 1
            all_nodes.append({"type":ntype, "id":nid, "name":name[:60], "depth":depth, "n_children":len(children)})
            walk(children, depth+1)
    
    walk(data.get("curriculum", []))
    
    lines.append(f"\n## {f.name}")
    lines.append(f"- Class: {cls}, Subject: {subj}")
    lines.append(f"- Total nodes: {len(all_nodes)}")
    lines.append(f"- Max depth: {state['depth_max']}")
    lines.append(f"- Type breakdown: {dict(type_counts)}")
    lines.append(f"- Empty names: {state['empty_name']}")
    lines.append(f"- Chapters/Units with NO children: {state['empty_children_chapters']}")
    
    if len(all_nodes) <= 3:
        lines.append(f"- **WARNING: VERY FEW NODES - EXTRACTION LIKELY INCOMPLETE**")
    elif state['empty_children_chapters'] > 0 and type_counts.get("topic",0) == 0 and type_counts.get("subtopic",0) == 0:
        lines.append(f"- **WARNING: NO TOPICS/SUBTOPICS - SHALLOW EXTRACTION**")
    
    lines.append("")
    lines.append("Node listing (first 30):")
    for n in all_nodes[:30]:
        indent = "  " * n["depth"]
        lines.append(f"  {indent}[{n['type']}] {n['id']}: {n['name']} ({n['n_children']} children)")

with open(OUT, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))
print(f"Written to {OUT}")
