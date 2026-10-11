"""Check why class10 maths and class10 computer_application have 0% match."""
import sys, io, json, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import pandas as pd
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Load syllabus keys
syl_keys = []
for f in sorted((ROOT / "data" / "syllabus").glob("*.json")):
    with open(f, "r", encoding="utf-8") as fh:
        d = json.load(fh)
    cls_raw = d.get("class","")
    subj_raw = d.get("subject","")
    cls_num = re.sub(r"\D", "", str(cls_raw))
    subj_norm = subj_raw.lower().strip()
    syl_keys.append((cls_num, subj_norm, f.name))
    print(f"Syllabus: class_num={cls_num}, subject_norm={subj_norm}, file={f.name}")

print()

# Load question bank class/subject values
df = pd.read_csv(ROOT / "output" / "classified_question_bank.csv", dtype=str)
canon = df.drop_duplicates(subset=["canonical_question_id"])

for (cls, subj), grp in canon.groupby(["class", "subject"]):
    cls_num = re.sub(r"\D", "", str(cls))
    subj_norm = subj.lower().strip()
    match = any(sk[0] == cls_num and sk[1] == subj_norm for sk in syl_keys)
    
    # Status breakdown
    statuses = grp["classification_status"].value_counts().to_dict()
    print(f"QBank: class={cls} (num={cls_num}), subject={subj} (norm={subj_norm}), "
          f"count={len(grp)}, syllabus_match={'YES' if match else 'NO'}, statuses={statuses}")
