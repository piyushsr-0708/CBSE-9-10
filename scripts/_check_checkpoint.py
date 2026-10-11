import json
from pathlib import Path
from collections import Counter

checkpoint = Path('data/processed/classification_results.jsonl')
records = {}
with open(checkpoint, 'r', encoding='utf-8') as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
            cqid = rec.get('canonical_question_id')
            status = rec.get('classification_status', '')
            if cqid:
                records[cqid] = status  # last wins
        except Exception:
            pass

status_counts = Counter(records.values())
valid_statuses = {'auto_verified', 'review_required', 'unclassifiable'}
valid = {cqid: s for cqid, s in records.items() if s in valid_statuses}
errors = {cqid: s for cqid, s in records.items() if s == 'error'}
other = {cqid: s for cqid, s in records.items() if s not in valid_statuses and s != 'error'}

print(f'Total checkpoint records (unique): {len(records)}')
print('Status breakdown:')
for k, v in status_counts.most_common():
    print(f'  {k}: {v}')
print(f'\nValid (will NOT retry): {len(valid)}')
print(f'Error/API-failed (WILL retry): {len(errors)}')
print(f'Other: {len(other)} -> {Counter(other.values()).most_common()}')
