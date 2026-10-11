import pandas as pd
import numpy as np
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FINAL_CSV = ROOT / "output" / "classified_question_bank.csv"
AUDIT_CSV = ROOT / "reports" / "mapping_quality_audit.csv"
AUDIT_MD = ROOT / "reports" / "mapping_quality_audit.md"

df = pd.read_csv(FINAL_CSV, dtype=str)
canonical_df = df.drop_duplicates(subset=["canonical_question_id"]).copy()

canonical_df["confidence"] = pd.to_numeric(canonical_df["confidence"], errors="coerce").fillna(0.0)

# Create bins
bins = [0.0, 0.20, 0.25, 0.35, 0.45, 0.60, 1.0]
labels = ["<0.20", "0.20-0.25", "0.25-0.35", "0.35-0.45", "0.45-0.60", ">0.60"]
canonical_df["score_bin"] = pd.cut(canonical_df["confidence"], bins=bins, labels=labels, include_lowest=True)

# Select stratified sample (~100 records)
samples = []
for (subject, class_lvl), group in canonical_df.groupby(["subject", "class"]):
    for score_bin, bin_group in group.groupby("score_bin"):
        if not bin_group.empty:
            # take up to 2 random from each bin/subject/class combo
            sampled = bin_group.sample(n=min(3, len(bin_group)), random_state=42)
            samples.append(sampled)
            
# Also ensure some statuses are captured
for stat in ["review_required", "out_of_syllabus", "unclassifiable", "boilerplate"]:
    grp = canonical_df[canonical_df["classification_status"] == stat]
    if not grp.empty:
        samples.append(grp.sample(n=min(5, len(grp)), random_state=42))

sample_df = pd.concat(samples).drop_duplicates(subset=["canonical_question_id"]).head(150)

# Basic heuristic to identify "reason for concern"
def find_concern(row):
    conf = float(row["confidence"])
    stat = str(row["classification_status"])
    text = str(row["question_text"]).lower()
    ch_id = str(row["chapter_id"])
    
    concerns = []
    if "auto_verified" in stat and conf < 0.5:
        concerns.append("Auto-verified but confidence is low")
    if "chapter_only" in stat and conf < 0.3:
        concerns.append("Chapter-only but confidence is very low (<0.3)")
    if len(text.split()) < 4 and stat in ["auto_verified", "chapter_only"]:
        concerns.append("Very short text mapped confidently")
    if "UNCLASSIFIABLE" not in ch_id and len(text.split()) > 40 and conf > 0.4:
        concerns.append("Long text, possible TF-IDF illusion")
    # visual
    if any(w in text for w in ["figure", "diagram", "graph", "table"]) and row.get("requires_visual_context", "False") != "True":
        concerns.append("Visual context missed")
        
    return "; ".join(concerns) if concerns else "None obvious"

sample_df["reason_for_concern"] = sample_df.apply(find_concern, axis=1)

output_cols = [
    "canonical_question_id", "question_text", "class", "subject", 
    "chapter_id", "topic_id", "confidence", "classification_status", 
    "syllabus_eligibility", "reason_for_concern"
]
sample_df[output_cols].to_csv(AUDIT_CSV, index=False)

# Compute Distribution
dist = canonical_df["score_bin"].value_counts().sort_index()

with open(ROOT / "reports" / "dist_temp.json", "w") as f:
    json.dump(dist.to_dict(), f, indent=2)

print(f"Sampled {len(sample_df)} questions for audit.")
print(dist)
