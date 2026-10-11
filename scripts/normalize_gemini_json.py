import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent.parent
SYL_DIR = ROOT / "data" / "syllabus"

def normalize_node(n, default_type='topic'):
    out = {}
    
    # Extract name
    name = n.get('name') or n.get('unit_name') or n.get('chapter_name') or n.get('chapter') or n.get('topic') or n.get('topic_name') or n.get('unit') or n.get('theme')
    
    if not name and 'unit_number' in n:
        name = f"Unit {n['unit_number']}"
        
    out['name'] = str(name) if name else ""
    
    # Extract type
    t = n.get('type')
    if not t:
        if 'unit_name' in n or 'unit_number' in n or 'unit' in n: t = 'unit'
        elif 'chapter_name' in n or 'chapter' in n or 'theme' in n: t = 'chapter'
        else: t = default_type
    out['type'] = t
    out['children'] = []
    
    # Handle children embedded as lists of dicts or lists of strings
    kids = n.get('children') or n.get('chapters') or n.get('topics') or n.get('subtopics')
    if kids and isinstance(kids, list):
        for k in kids:
            if isinstance(k, str):
                 out['children'].append({'type':'topic', 'name':k, 'children':[]})
            elif isinstance(k, dict):
                 out['children'].append(normalize_node(k, 'chapter' if t == 'unit' else 'topic'))
    else:
        # Check other keys that might be lists
        for k, v in n.items():
            if k not in ['name', 'type', 'unit_number', 'unit_name', 'chapter', 'topic', 'unit'] and isinstance(v, list):
                for item in v:
                    if isinstance(item, str):
                        out['children'].append({'type':'topic', 'name':item, 'children':[]})
                    elif isinstance(item, dict):
                        out['children'].append(normalize_node(item, 'chapter' if t == 'unit' else 'topic'))
                break
                
    return out

def reassign_ids(hierarchy, prefix):
    type_abbr = {"unit": "UNT", "chapter": "CHA", "topic": "TOP", "subtopic": "SUB"}
    for i, node in enumerate(hierarchy, 1):
        node["id"] = f"{prefix}_{i:02d}"
        for j, child in enumerate(node.get("children", []), 1):
            ab = type_abbr.get(child.get("type", "TOP"), child.get("type", "TOP")[:3].upper())
            child["id"] = f"{node['id']}_{ab}{j:02d}"
            for k, gc in enumerate(child.get("children", []), 1):
                ab2 = type_abbr.get(gc.get("type", "TOP"), gc.get("type", "TOP")[:3].upper())
                gc["id"] = f"{child['id']}_{ab2}{k:02d}"
                for ll, ggc in enumerate(gc.get("children", []), 1):
                    ab3 = type_abbr.get(ggc.get("type", "TOP"), ggc.get("type", "TOP")[:3].upper())
                    ggc["id"] = f"{gc['id']}_{ab3}{ll:02d}"

if __name__ == "__main__":
    files = [
        ('cbse_class10_computer_application_2026_27.json', 'CBSE10_CA'),
        ('cbse_class10_maths_2026_27.json', 'CBSE10_MATH')
    ]
    
    for fname, prefix in files:
        f = SYL_DIR / fname
        if not f.exists():
            continue
            
        with open(f, 'r', encoding='utf-8') as fh:
            data = json.load(fh)
            
        curr = data.get('curriculum', [])
        new_curr = [normalize_node(n, 'unit') for n in curr if isinstance(n, dict)]
        
        # If nodes have empty names but have children, we might need to purge them or keep them if they represent units
        reassign_ids(new_curr, prefix)
        data['curriculum'] = new_curr
        
        with open(f, 'w', encoding='utf-8') as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
            
    print("Normalization complete.")
