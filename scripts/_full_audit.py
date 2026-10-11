"""
Comprehensive mapping quality audit.
Reads classified output, syllabus JSONs, and generates:
  1. reports/mapping_quality_audit.csv  (stratified sample ~100-120 records)
  2. reports/mapping_quality_audit.md   (full quality analysis)
"""
import json, sys, io
import pandas as pd
import numpy as np
from pathlib import Path
from collections import Counter, defaultdict

ROOT = Path(__file__).resolve().parent.parent
FINAL_CSV = ROOT / "output" / "classified_question_bank.csv"
SYLLABUS_DIR = ROOT / "data" / "syllabus"
AUDIT_CSV = ROOT / "reports" / "mapping_quality_audit.csv"
AUDIT_MD = ROOT / "reports" / "mapping_quality_audit.md"

# ── Load data ──
df = pd.read_csv(FINAL_CSV, dtype=str)
df["confidence"] = pd.to_numeric(df["confidence"], errors="coerce").fillna(0.0)
canonical = df.drop_duplicates(subset=["canonical_question_id"]).copy()

# ── Load all valid taxonomy IDs from syllabus JSONs ──
valid_ids = set()
syllabus_chapters = {}  # id -> name
for f in SYLLABUS_DIR.glob("*.json"):
    with open(f, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    def walk(nodes):
        for n in nodes:
            nid = n.get("id", "")
            if nid:
                valid_ids.add(nid)
                syllabus_chapters[nid] = n.get("name", "")
            walk(n.get("children", []) or [])
    walk(data.get("curriculum", []))

# ── Score distribution ──
bins = [0.0, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50, 0.60, 0.70, 1.01]
bin_labels = ["0.00-0.05","0.05-0.10","0.10-0.15","0.15-0.20","0.20-0.25",
              "0.25-0.30","0.30-0.35","0.35-0.40","0.40-0.45","0.45-0.50",
              "0.50-0.60","0.60-0.70",">0.70"]
canonical["score_bin"] = pd.cut(canonical["confidence"], bins=bins, labels=bin_labels, include_lowest=True)
dist = canonical["score_bin"].value_counts().sort_index()

# ── Per-subject/class stats ──
subj_stats = canonical.groupby(["class", "subject"]).agg(
    count=("canonical_question_id", "count"),
    mean_conf=("confidence", "mean"),
    median_conf=("confidence", "median"),
    auto_verified=("classification_status", lambda x: (x == "auto_verified").sum()),
    chapter_only=("classification_status", lambda x: (x == "chapter_only").sum()),
    review_req=("classification_status", lambda x: (x == "review_required").sum()),
    unclassifiable=("classification_status", lambda x: (x == "unclassifiable").sum()),
    out_of_syl=("classification_status", lambda x: (x == "out_of_syllabus").sum()),
).reset_index()

# ── Detect suspicious mappings ──
suspicious = []

for _, row in canonical.iterrows():
    cqid = row["canonical_question_id"]
    text = str(row.get("question_text", ""))
    ch_id = str(row.get("chapter_id", ""))
    topic_id = str(row.get("topic_id", ""))
    conf = row["confidence"]
    status = str(row.get("classification_status", ""))
    elig = str(row.get("syllabus_eligibility", ""))
    subj = str(row.get("subject", "")).lower()
    cls = str(row.get("class", ""))
    
    concerns = []
    
    # 1. Invalid taxonomy IDs
    if ch_id not in valid_ids and ch_id not in ("UNCLASSIFIABLE", "nan", "None", ""):
        concerns.append(f"INVENTED_CHAPTER_ID: {ch_id}")
    if topic_id not in valid_ids and topic_id not in ("nan", "None", "", "null"):
        concerns.append(f"INVENTED_TOPIC_ID: {topic_id}")
    
    # 2. Very short text mapped confidently
    word_count = len(text.split())
    if word_count < 5 and status in ("auto_verified", "chapter_only"):
        concerns.append(f"SHORT_TEXT_MAPPED ({word_count} words)")
    
    # 3. Visual context needed
    visual_words = ["figure", "diagram", "graph", "table", "draw", "sketch", "shown above",
                    "given below", "following figure", "refer to", "shown in"]
    if any(w in text.lower() for w in visual_words) and status in ("auto_verified", "chapter_only"):
        concerns.append("VISUAL_CONTEXT_LIKELY_NEEDED")
    
    # 4. Hitler/Nazism mapped to current syllabus (known legacy)
    legacy_kw = ["hitler", "nazism", "nazi", "weimar", "mussolini", "fascism"]
    if any(w in text.lower() for w in legacy_kw) and elig == "CURRENT_SYLLABUS":
        concerns.append("LEGACY_TOPIC_MAPPED_TO_CURRENT")
    
    # 5. Administrative/boilerplate text mapped
    boiler_kw = ["all questions are compulsory", "section a", "section b", "section c",
                 "general instructions", "time allowed", "maximum marks",
                 "internal choice", "attempt any"]
    if any(w in text.lower() for w in boiler_kw) and status in ("auto_verified", "chapter_only"):
        concerns.append("POSSIBLE_BOILERPLATE_MAPPED")
    
    # 6. Generic math terms causing false match
    generic_math = ["find", "solve", "calculate", "prove", "show that", "evaluate"]
    if subj in ("maths", "mathematics") and word_count < 8:
        if any(w in text.lower() for w in generic_math) and status == "auto_verified":
            concerns.append("GENERIC_MATH_VERB_SHORT_TEXT")
    
    # 7. Topic-level mapping where evidence is just a chapter keyword
    if topic_id not in ("nan", "None", "", "null") and conf < 0.35:
        concerns.append(f"TOPIC_MAPPED_LOW_CONF ({conf:.3f})")
    
    # 8. Chapter-only but should be review_required (very low conf)
    if status == "chapter_only" and conf < 0.26:
        concerns.append(f"CHAPTER_ONLY_VERY_LOW_CONF ({conf:.3f})")
    
    if concerns:
        suspicious.append({
            "canonical_question_id": cqid,
            "class": cls,
            "subject": subj,
            "confidence": conf,
            "status": status,
            "eligibility": elig,
            "chapter_id": ch_id,
            "chapter_name": syllabus_chapters.get(ch_id, "?"),
            "topic_id": topic_id,
            "concerns": "; ".join(concerns),
            "text_preview": text[:150].replace("\n", " ")
        })

susp_df = pd.DataFrame(suspicious)

# ── Concern type aggregation ──
concern_types = Counter()
for s in suspicious:
    for c in s["concerns"].split("; "):
        tag = c.split("(")[0].split(":")[0].strip()
        concern_types[tag] += 1

# ── Stratified audit sample ──
sample_parts = []
# From each subject/class, take from each score band
coarse_bins = [0.0, 0.25, 0.45, 1.01]
coarse_labels = ["low", "mid", "high"]
canonical["coarse_bin"] = pd.cut(canonical["confidence"], bins=coarse_bins, labels=coarse_labels, include_lowest=True)

for (subj, cls), grp in canonical.groupby(["subject", "class"]):
    for bn in coarse_labels:
        bg = grp[grp["coarse_bin"] == bn]
        if not bg.empty:
            sample_parts.append(bg.sample(n=min(3, len(bg)), random_state=42))
    # Also from suspicious
    if not susp_df.empty:
        sg = susp_df[(susp_df["subject"] == subj) & (susp_df["class"] == cls)]
        if not sg.empty:
            ids = sg["canonical_question_id"].head(2).tolist()
            sample_parts.append(canonical[canonical["canonical_question_id"].isin(ids)])

# Ensure some of each status
for stat in ["out_of_syllabus", "unclassifiable", "boilerplate", "review_required"]:
    sg = canonical[canonical["classification_status"] == stat]
    if not sg.empty:
        sample_parts.append(sg.sample(n=min(4, len(sg)), random_state=42))

audit_sample = pd.concat(sample_parts).drop_duplicates(subset=["canonical_question_id"]).head(120)

# Add chapter name and concern info
audit_sample = audit_sample.copy()
audit_sample["chapter_name"] = audit_sample["chapter_id"].map(lambda x: syllabus_chapters.get(str(x), ""))
audit_sample["reason_for_concern"] = ""
susp_lookup = {s["canonical_question_id"]: s["concerns"] for s in suspicious}
audit_sample["reason_for_concern"] = audit_sample["canonical_question_id"].map(lambda x: susp_lookup.get(x, ""))

audit_cols = [
    "canonical_question_id", "question_text", "class", "subject",
    "chapter_id", "chapter_name", "topic_id", "confidence",
    "classification_status", "syllabus_eligibility", "reason_for_concern"
]
existing_cols = [c for c in audit_cols if c in audit_sample.columns]
audit_sample[existing_cols].to_csv(AUDIT_CSV, index=False, encoding="utf-8")

# ── Spot-check: inspect 5 records per subject in key ranges ──
spot_checks = {}
for (subj, cls), grp in canonical.groupby(["subject", "class"]):
    key = f"{cls}_{subj}"
    checks = {}
    
    # High confidence auto_verified
    hc = grp[(grp["classification_status"] == "auto_verified") & (grp["confidence"] > 0.45)]
    if not hc.empty:
        r = hc.iloc[0]
        checks["high_conf_example"] = {
            "text": str(r["question_text"])[:200],
            "chapter": str(r["chapter_id"]),
            "chapter_name": syllabus_chapters.get(str(r["chapter_id"]), "?"),
            "topic": str(r.get("topic_id", "")),
            "confidence": float(r["confidence"])
        }
    
    # Borderline auto_verified (0.45-0.50)
    border = grp[(grp["classification_status"] == "auto_verified") & (grp["confidence"] >= 0.45) & (grp["confidence"] < 0.55)]
    if not border.empty:
        r = border.iloc[0]
        checks["borderline_auto"] = {
            "text": str(r["question_text"])[:200],
            "chapter": str(r["chapter_id"]),
            "chapter_name": syllabus_chapters.get(str(r["chapter_id"]), "?"),
            "confidence": float(r["confidence"])
        }
    
    # Borderline chapter_only (0.25-0.30)
    bc = grp[(grp["classification_status"] == "chapter_only") & (grp["confidence"] >= 0.25) & (grp["confidence"] < 0.32)]
    if not bc.empty:
        r = bc.iloc[0]
        checks["borderline_chapter"] = {
            "text": str(r["question_text"])[:200],
            "chapter": str(r["chapter_id"]),
            "chapter_name": syllabus_chapters.get(str(r["chapter_id"]), "?"),
            "confidence": float(r["confidence"])
        }
    
    # Unclassifiable
    uc = grp[grp["classification_status"] == "unclassifiable"]
    if not uc.empty:
        r = uc.iloc[0]
        checks["unclassifiable_example"] = {
            "text": str(r["question_text"])[:200],
            "confidence": float(r["confidence"])
        }
    
    spot_checks[key] = checks

# ── Write the audit MD report ──
with open(AUDIT_MD, "w", encoding="utf-8") as md:
    md.write("# Mapping Quality Audit Report\n\n")
    md.write("## 1. Confidence Score Distribution\n\n")
    md.write("| Score Range | Count | Cumulative % |\n")
    md.write("|---|---|---|\n")
    total = len(canonical)
    cum = 0
    for label in bin_labels:
        cnt = int(dist.get(label, 0))
        cum += cnt
        md.write(f"| {label} | {cnt} | {cum/total*100:.1f}% |\n")
    
    md.write(f"\n**Total canonical questions:** {total}\n\n")
    
    md.write("## 2. Per-Subject/Class Breakdown\n\n")
    md.write("| Class | Subject | Count | Mean Conf | Median Conf | Auto | Chap-Only | Review | Unclass | OOS |\n")
    md.write("|---|---|---|---|---|---|---|---|---|---|\n")
    for _, r in subj_stats.iterrows():
        md.write(f"| {r['class']} | {r['subject']} | {int(r['count'])} | {r['mean_conf']:.3f} | {r['median_conf']:.3f} | {int(r['auto_verified'])} | {int(r['chapter_only'])} | {int(r['review_req'])} | {int(r['unclassifiable'])} | {int(r['out_of_syl'])} |\n")

    md.write("\n## 3. Suspicious Mapping Detection\n\n")
    md.write(f"**Total suspicious records flagged:** {len(suspicious)}\n\n")
    md.write("### Concern Type Breakdown\n\n")
    md.write("| Concern | Count |\n")
    md.write("|---|---|\n")
    for ct, cnt in concern_types.most_common():
        md.write(f"| {ct} | {cnt} |\n")
    
    md.write("\n### Suspicious by Subject\n\n")
    if not susp_df.empty:
        susp_by_subj = susp_df.groupby(["class", "subject"]).size().reset_index(name="count")
        md.write("| Class | Subject | Suspicious Count |\n")
        md.write("|---|---|---|\n")
        for _, r in susp_by_subj.iterrows():
            md.write(f"| {r['class']} | {r['subject']} | {r['count']} |\n")
    
    md.write("\n## 4. Spot-Check Examples by Subject\n\n")
    for key, checks in sorted(spot_checks.items()):
        md.write(f"### {key}\n\n")
        for check_type, info in checks.items():
            md.write(f"**{check_type}:**\n")
            for k, v in info.items():
                val = str(v).replace("\n", " ").replace("|", "/")
                if len(val) > 200:
                    val = val[:200] + "..."
                md.write(f"- {k}: {val}\n")
            md.write("\n")

    md.write("\n## 5. Threshold Analysis\n\n")
    
    # Questions at threshold boundaries
    at_045 = canonical[(canonical["confidence"] >= 0.43) & (canonical["confidence"] <= 0.47)]
    at_025 = canonical[(canonical["confidence"] >= 0.23) & (canonical["confidence"] <= 0.27)]
    
    md.write(f"### Around AUTO_VERIFY threshold (0.45)\n")
    md.write(f"Questions with confidence 0.43-0.47: {len(at_045)}\n\n")
    for _, r in at_045.head(5).iterrows():
        txt = str(r["question_text"]).replace("\n", " ")[:150]
        md.write(f"- [{r['confidence']:.3f}] `{r['chapter_id']}` -> {txt}\n")
    
    md.write(f"\n### Around CHAPTER_ONLY threshold (0.25)\n")
    md.write(f"Questions with confidence 0.23-0.27: {len(at_025)}\n\n")
    for _, r in at_025.head(5).iterrows():
        txt = str(r["question_text"]).replace("\n", " ")[:150]
        md.write(f"- [{r['confidence']:.3f}] `{r['chapter_id']}` -> {txt}\n")
    
    md.write("\n## 6. Invented ID Check\n\n")
    invented_ch = []
    invented_top = []
    for _, r in canonical.iterrows():
        ch = str(r.get("chapter_id", ""))
        top = str(r.get("topic_id", ""))
        if ch not in valid_ids and ch not in ("UNCLASSIFIABLE", "nan", "None", ""):
            invented_ch.append(ch)
        if top not in valid_ids and top not in ("nan", "None", "", "null"):
            invented_top.append(top)
    
    md.write(f"- Invented chapter IDs found: {len(invented_ch)}\n")
    if invented_ch:
        md.write(f"  - Examples: {', '.join(set(invented_ch)[:10])}\n")
    md.write(f"- Invented topic IDs found: {len(invented_top)}\n")
    if invented_top:
        md.write(f"  - Examples: {', '.join(set(invented_top)[:10])}\n")
    
    md.write("\n## 7. Recommendations\n\n")
    md.write("*(To be filled after reviewing spot-checks and suspicious mappings above.)*\n")

print(f"Audit complete.")
print(f"  Audit CSV: {AUDIT_CSV} ({len(audit_sample)} records)")
print(f"  Audit MD:  {AUDIT_MD}")
print(f"  Suspicious flags: {len(suspicious)}")
print(f"  Concern types: {dict(concern_types.most_common(10))}")
