"""Full state check - show complete breakdown."""
import json, sys
from pathlib import Path
from collections import Counter

CHECKPOINT = Path("data/processed/classification_results.jsonl")
records = {}
with open(CHECKPOINT, "r", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
            cqid = rec.get("canonical_question_id")
            if cqid:
                records[cqid] = rec
        except Exception:
            pass

valid_statuses = {"auto_verified", "review_required", "unclassifiable"}
valid   = {k: v for k, v in records.items() if v.get("classification_status") in valid_statuses}
errors  = {k: v for k, v in records.items() if v.get("classification_status") == "error"}

status_counts = Counter(r.get("classification_status","?") for r in records.values())
elig_counts   = Counter(r.get("syllabus_eligibility","?") for r in valid.values())

sys.stdout.write(f"=== CHECKPOINT STATE ===\n")
sys.stdout.write(f"Total canonical IDs     : {len(records)}\n")
sys.stdout.write(f"\nStatus breakdown:\n")
for k, v in status_counts.most_common():
    sys.stdout.write(f"  {k:<22}: {v}\n")
sys.stdout.write(f"\nEligibility (valid only):\n")
for k, v in elig_counts.most_common():
    sys.stdout.write(f"  {k:<42}: {v}\n")
sys.stdout.write(f"\nValid (will NOT retry)  : {len(valid)}\n")
sys.stdout.write(f"Errors (WILL retry)     : {len(errors)}\n")
sys.stdout.flush()
