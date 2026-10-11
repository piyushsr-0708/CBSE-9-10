import json, sys

with open('data/syllabus/cbse_class9_maths_2026_27.json', encoding='utf-8') as f:
    data = json.load(f)

lines = []
for unit in data['curriculum']:
    lines.append(f"[{unit['id']}] {unit['name']} (pages {unit['source_pages']})")
    for ch in unit.get('children', []):
        topics = ch.get('children', [])
        lines.append(f"  [{ch['id']}] {ch['name']} -> {len(topics)} topics")
        for t in topics[:3]:
            lines.append(f"    - {t['name'][:80]}")
        if len(topics) > 3:
            lines.append(f"    ... +{len(topics)-3} more")
    if not unit.get('children'):
        lines.append('  (no children)')

output = '\n'.join(lines)
with open('scratch/maths_hier.txt', 'w', encoding='utf-8') as f:
    f.write(output)
print("Written to scratch/maths_hier.txt")
print(output)
