"""Diagnostic: write results to a file to avoid console encoding issues."""
import json, re
import pandas as pd
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "reports" / "_diag_output.md"

lines = []

# Load syllabus keys
syl_keys = []
for f in sorted((ROOT / "data" / "syllabus").glob("*.json")):
    with open(f, "r", encoding="utf-8") as fh:
        d = json.load(fh)
    cls_num = re.sub(r"\D", "", str(d.get("class","")))
    subj_norm = d.get("subject","").lower().strip()
    syl_keys.append((cls_num, subj_norm, f.name))
    lines.append(f"Syllabus: class_num={cls_num}, subject_norm={subj_norm}, file={f.name}")

lines.append("")

# Load question bank
df = pd.read_csv(ROOT / "output" / "classified_question_bank.csv", dtype=str)
canon = df.drop_duplicates(subset=["canonical_question_id"])

for (cls, subj), grp in canon.groupby(["class", "subject"]):
    cls_num = re.sub(r"\D", "", str(cls))
    subj_norm = subj.lower().strip()
    match = any(sk[0] == cls_num and sk[1] == subj_norm for sk in syl_keys)
    statuses = grp["classification_status"].value_counts().to_dict()
    lines.append(f"QBank: class={cls} (num={cls_num}), subject={subj} (norm={subj_norm}), "
                 f"count={len(grp)}, syllabus_match={'YES' if match else 'NO'}, statuses={statuses}")

lines.append("")
lines.append("--- SAMPLE CLASS10 MATHS QUESTIONS ---")
c10m = canon[(canon["class"]=="class10") & (canon["subject"]=="maths")]
for _, r in c10m.head(5).iterrows():
    txt = str(r.get("question_text",""))[:150].replace("\n"," ")
    lines.append(f"  [{r['canonical_question_id']}] {txt}")

lines.append("")
lines.append("--- SAMPLE CLASS10 COMPUTER_APPLICATION QUESTIONS ---")
c10ca = canon[(canon["class"]=="class10") & (canon["subject"]=="computer_application")]
for _, r in c10ca.head(5).iterrows():
    txt = str(r.get("question_text",""))[:150].replace("\n"," ")
    lines.append(f"  [{r['canonical_question_id']}] {txt}")

lines.append("")

# Check syllabus class/subject normalization in hybrid script
lines.append("--- SYLLABUS KEY LOOKUP DEBUG ---")
for cls_num, subj_norm, fname in syl_keys:
    lines.append(f"  ({cls_num}, {subj_norm}) -> {fname}")

with open(OUT, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))

print(f"Written to {OUT}")
