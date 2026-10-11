"""
audit_dataset.py
================
Inspects clean_question_bank.csv and produces:
  reports/dataset_audit.json
  reports/dataset_audit.md

Run:
    python scripts/audit_dataset.py
"""

import csv
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = ROOT / "clean_question_bank.csv"
REPORTS_DIR = ROOT / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

JSON_REPORT = REPORTS_DIR / "dataset_audit.json"
MD_REPORT   = REPORTS_DIR / "dataset_audit.md"


def load_csv(path: Path):
    """Load CSV with DictReader; return (headers, rows)."""
    rows = []
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        headers = reader.fieldnames or []
        for row in reader:
            rows.append(row)
    return headers, rows


def audit(path: Path) -> dict:
    headers, rows = load_csv(path)

    total_records = len(rows)
    num_columns   = len(headers)

    # -----------------------------------------------------------------------
    # Missing-value counts (empty string = missing)
    # -----------------------------------------------------------------------
    missing_counts = {col: 0 for col in headers}
    for row in rows:
        for col in headers:
            val = row.get(col, "")
            if val is None or str(val).strip() == "":
                missing_counts[col] += 1

    # -----------------------------------------------------------------------
    # Unique values for key categorical columns
    # -----------------------------------------------------------------------
    def unique_non_empty(col):
        vals = set()
        for row in rows:
            v = str(row.get(col, "")).strip()
            if v:
                vals.add(v)
        return sorted(vals)

    unique_classes        = unique_non_empty("class")
    unique_subjects       = unique_non_empty("subject")
    unique_sessions       = unique_non_empty("session")
    unique_question_types = unique_non_empty("question_type")

    # -----------------------------------------------------------------------
    # Marks distribution
    # -----------------------------------------------------------------------
    marks_counter: Counter = Counter()
    for row in rows:
        m = str(row.get("marks", "")).strip()
        marks_counter[m if m else "missing"] += 1

    # -----------------------------------------------------------------------
    # Duplicate detection (based on question_text_clean)
    # -----------------------------------------------------------------------
    text_seen: dict = defaultdict(list)
    for i, row in enumerate(rows, start=2):   # 2 = first data row
        key = str(row.get("question_text_clean", "")).strip().lower()
        if key:
            text_seen[key].append(row.get("question_id", f"row_{i}"))

    duplicate_groups = {k: v for k, v in text_seen.items() if len(v) > 1}
    duplicate_question_count = sum(len(v) - 1 for v in duplicate_groups.values())

    # -----------------------------------------------------------------------
    # Empty question text
    # -----------------------------------------------------------------------
    empty_qtext = [
        row.get("question_id", f"row_{i+2}")
        for i, row in enumerate(rows)
        if not str(row.get("question_text", "")).strip()
           and not str(row.get("question_text_clean", "")).strip()
    ]

    # -----------------------------------------------------------------------
    # Questions with missing important metadata
    # -----------------------------------------------------------------------
    important_cols = ["class", "subject", "session", "question_type", "question_text_clean"]
    missing_meta: list = []
    for i, row in enumerate(rows):
        qid = row.get("question_id", f"row_{i+2}")
        missing_fields = [c for c in important_cols if not str(row.get(c, "")).strip()]
        if missing_fields:
            missing_meta.append({"question_id": qid, "missing_fields": missing_fields})

    # -----------------------------------------------------------------------
    # Data types (inferred)
    # -----------------------------------------------------------------------
    inferred_types = {}
    for col in headers:
        values = [str(r.get(col, "")).strip() for r in rows if str(r.get(col, "")).strip()]
        if not values:
            inferred_types[col] = "empty"
        else:
            try:
                [int(v) for v in values]
                inferred_types[col] = "integer"
            except ValueError:
                try:
                    [float(v) for v in values]
                    inferred_types[col] = "float"
                except ValueError:
                    inferred_types[col] = "string"

    # -----------------------------------------------------------------------
    # Per subject-class breakdown
    # -----------------------------------------------------------------------
    breakdown: dict = defaultdict(lambda: defaultdict(int))
    for row in rows:
        cls  = str(row.get("class", "")).strip()
        subj = str(row.get("subject", "")).strip()
        if cls and subj:
            breakdown[cls][subj] += 1

    breakdown_plain = {cls: dict(subjects) for cls, subjects in breakdown.items()}

    # -----------------------------------------------------------------------
    # Assemble report
    # -----------------------------------------------------------------------
    report = {
        "generated_at": datetime.now().isoformat(),
        "source_file": str(path),
        "total_records": total_records,
        "num_columns": num_columns,
        "column_names": headers,
        "inferred_data_types": inferred_types,
        "missing_value_counts": missing_counts,
        "unique_classes": unique_classes,
        "unique_subjects": unique_subjects,
        "unique_sessions": unique_sessions,
        "unique_question_types": unique_question_types,
        "marks_distribution": dict(marks_counter),
        "duplicate_question_count": duplicate_question_count,
        "duplicate_groups_sample": {
            k: v for k, v in list(duplicate_groups.items())[:10]
        },
        "empty_question_text_count": len(empty_qtext),
        "empty_question_text_ids": empty_qtext[:20],
        "questions_with_missing_metadata_count": len(missing_meta),
        "questions_with_missing_metadata_sample": missing_meta[:20],
        "class_subject_breakdown": breakdown_plain,
    }
    return report


def to_markdown(report: dict) -> str:
    lines = [
        "# Dataset Audit Report",
        f"\n**Generated at:** {report['generated_at']}",
        f"**Source file:** `{report['source_file']}`\n",
        "---",
        "## Summary",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Total records | {report['total_records']} |",
        f"| Columns | {report['num_columns']} |",
        f"| Duplicate questions | {report['duplicate_question_count']} |",
        f"| Empty question text | {report['empty_question_text_count']} |",
        f"| Questions missing metadata | {report['questions_with_missing_metadata_count']} |",
        "",
        "## Column Names & Inferred Types",
        "| # | Column | Inferred Type | Missing Count |",
        "|---|--------|---------------|---------------|",
    ]
    for i, col in enumerate(report["column_names"], 1):
        dtype   = report["inferred_data_types"].get(col, "?")
        missing = report["missing_value_counts"].get(col, 0)
        lines.append(f"| {i} | `{col}` | {dtype} | {missing} |")

    lines += [
        "",
        "## Unique Classes",
        ", ".join(f"`{c}`" for c in report["unique_classes"]),
        "",
        "## Unique Subjects",
        ", ".join(f"`{s}`" for s in report["unique_subjects"]),
        "",
        "## Unique Sessions",
        ", ".join(f"`{s}`" for s in report["unique_sessions"]),
        "",
        "## Unique Question Types",
        ", ".join(f"`{qt}`" for qt in report["unique_question_types"]),
        "",
        "## Marks Distribution",
        "| Marks | Count |",
        "|-------|-------|",
    ]
    for marks_val, cnt in sorted(report["marks_distribution"].items()):
        lines.append(f"| {marks_val} | {cnt} |")

    lines += [
        "",
        "## Class x Subject Breakdown",
        "| Class | Subject | Count |",
        "|-------|---------|-------|",
    ]
    for cls, subj_dict in sorted(report["class_subject_breakdown"].items()):
        for subj, cnt in sorted(subj_dict.items()):
            lines.append(f"| {cls} | {subj} | {cnt} |")

    if report["questions_with_missing_metadata_sample"]:
        lines += [
            "",
            "## Sample - Questions Missing Important Metadata (first 20)",
            "| question_id | missing_fields |",
            "|-------------|----------------|",
        ]
        for item in report["questions_with_missing_metadata_sample"]:
            lines.append(f"| {item['question_id']} | {', '.join(item['missing_fields'])} |")

    if report.get("duplicate_groups_sample"):
        lines += [
            "",
            "## Sample Duplicate Groups (first 10 groups)",
        ]
        for text, ids in list(report["duplicate_groups_sample"].items())[:5]:
            snippet = text[:80].replace("\n", " ")
            lines.append(f"- IDs {ids}: \"{snippet}...\"")

    return "\n".join(lines)


def main():
    if not CSV_PATH.exists():
        print(f"ERROR: CSV not found at {CSV_PATH}", file=sys.stderr)
        sys.exit(1)

    print(f"Auditing: {CSV_PATH}")
    report = audit(CSV_PATH)

    with open(JSON_REPORT, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, ensure_ascii=False)
    print(f"JSON report saved: {JSON_REPORT}")

    md = to_markdown(report)
    with open(MD_REPORT, "w", encoding="utf-8") as fh:
        fh.write(md)
    print(f"Markdown report saved: {MD_REPORT}")

    print("\n=== QUICK SUMMARY ===")
    print(f"  Records         : {report['total_records']}")
    print(f"  Columns         : {report['num_columns']}")
    print(f"  Classes         : {report['unique_classes']}")
    print(f"  Subjects        : {report['unique_subjects']}")
    print(f"  Sessions        : {report['unique_sessions']}")
    print(f"  Question types  : {report['unique_question_types']}")
    print(f"  Duplicates      : {report['duplicate_question_count']}")
    print(f"  Empty text      : {report['empty_question_text_count']}")
    print(f"  Missing meta    : {report['questions_with_missing_metadata_count']}")


if __name__ == "__main__":
    main()
