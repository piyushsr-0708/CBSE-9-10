"""
duplicate_analysis.py
=====================
Analyzes clean_question_bank.csv for duplicates.
Creates reports/duplicate_analysis.json with:
- canonical_question_id mappings
- exact duplicates
- different session/file occurrences

Run:
    python scripts/analyze_duplicates.py
"""

import csv
import json
import sys
from collections import defaultdict
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = ROOT / "clean_question_bank.csv"
REPORTS_DIR = ROOT / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)
OUT_FILE = REPORTS_DIR / "duplicate_analysis.json"

def main():
    if not CSV_PATH.exists():
        print(f"Error: {CSV_PATH} not found.")
        sys.exit(1)
        
    rows = []
    with open(CSV_PATH, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            rows.append(row)
            
    # Group by clean text
    text_groups = defaultdict(list)
    for row in rows:
        text = str(row.get("question_text_clean", "")).strip().lower()
        if not text:
            # If empty, just use the raw text if available
            text = str(row.get("question_text", "")).strip().lower()
            
        qid = row.get("question_id")
        session = row.get("session")
        source = row.get("source_file")
        options = row.get("options", "")
        q_type = row.get("question_type", "")
        
        # We group by text + options + type to be more precise about duplicates
        key = (text, str(options).strip().lower(), str(q_type).strip().lower())
        if text:
            text_groups[key].append({
                "question_id": qid,
                "session": session,
                "source_file": source
            })
            
    duplicate_groups = {k: v for k, v in text_groups.items() if len(v) > 1}
    
    analysis = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_questions": len(rows),
        "unique_underlying_questions": len(text_groups),
        "total_duplicate_groups": len(duplicate_groups),
        "duplicate_groups": []
    }
    
    # Analyze groups
    for i, (key, items) in enumerate(duplicate_groups.items(), start=1):
        text, options, q_type = key
        
        canonical_id = items[0]["question_id"]
        
        sessions_seen = set()
        sources_seen = set()
        for item in items:
            if item["session"]: sessions_seen.add(item["session"])
            if item["source_file"]: sources_seen.add(item["source_file"])
            
        group_type = "exact_duplicate"
        if len(sessions_seen) > 1:
            group_type = "different_sessions"
        elif len(sources_seen) > 1:
            group_type = "different_sources"
            
        analysis["duplicate_groups"].append({
            "group_id": f"DUP_{i:04d}",
            "canonical_question_id": canonical_id,
            "duplicate_type": group_type,
            "question_text_preview": text[:100] + ("..." if len(text) > 100 else ""),
            "occurrences": items
        })

    with open(OUT_FILE, "w", encoding="utf-8") as fh:
        json.dump(analysis, fh, indent=2)
        
    print(f"Duplicate analysis saved to {OUT_FILE}")
    print(f"Total questions: {len(rows)}")
    print(f"Unique underlying questions: {len(text_groups)}")
    print(f"Duplicate groups found: {len(duplicate_groups)}")

if __name__ == "__main__":
    main()
