"""
retry_failed_classifications.py
================================
Resume classification for only those canonical questions whose previous
classification ended in an API error (status == "error").

Valid outcomes (auto_verified, review_required, unclassifiable) are NEVER
touched.  Only error records are retried.

Conservative settings
---------------------
  * batch_size = 5 (can be overridden with --batch-size)
  * inter_request_delay = 8 s (can be overridden with --delay)
  * exponential backoff: 30 s base, up to 240 s cap, 8 retries

Usage
-----
  python scripts/retry_failed_classifications.py            # full retry
  python scripts/retry_failed_classifications.py --dry-run  # inspect only
  python scripts/retry_failed_classifications.py --limit 50 # retry up to N
"""

import io, sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
else:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import json
import os
import re
import time
import argparse
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any
from collections import Counter

import pandas as pd
from pydantic import BaseModel, Field, ValidationError
from dotenv import load_dotenv
from google import genai
from google.genai import types as genai_types

load_dotenv()

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT            = Path(__file__).resolve().parent.parent
DATA_SYLLABUS   = ROOT / "data" / "syllabus"
DATA_PROCESSED  = ROOT / "data" / "processed"
OUTPUT_DIR      = ROOT / "output"
REPORTS_DIR     = ROOT / "reports"
CONFIG_FILE     = ROOT / "config" / "classification_config.json"

QBANK_CSV        = ROOT / "clean_question_bank.csv"
CHECKPOINT_FILE  = DATA_PROCESSED / "classification_results.jsonl"
FINAL_CSV        = OUTPUT_DIR / "classified_question_bank.csv"
REVIEW_CSV       = OUTPUT_DIR / "review_queue.csv"
SUMMARY_JSON     = REPORTS_DIR / "question_mapping_summary.json"
SUMMARY_MD       = REPORTS_DIR / "question_mapping_summary.md"

for d in [DATA_PROCESSED, OUTPUT_DIR, REPORTS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Statuses that must NEVER be retried (valid outcomes)
# ---------------------------------------------------------------------------
VALID_STATUSES = {"auto_verified", "review_required", "unclassifiable"}

# ---------------------------------------------------------------------------
# Pydantic schema
# ---------------------------------------------------------------------------
class ClassificationResult(BaseModel):
    unit_id:               Optional[str]  = Field(None)
    chapter_id:            str            = Field(...)
    topic_id:              Optional[str]  = Field(None)
    subtopic_id:           Optional[str]  = Field(None)
    learning_outcome_id:   Optional[str]  = Field(None)
    difficulty:            str            = Field(...)
    confidence:            float          = Field(..., ge=0.0, le=1.0)
    classification_reason: str            = Field(...)
    alternative_candidates: List[str]     = Field(default_factory=list)
    requires_visual_context: bool         = Field(False)
    syllabus_eligibility:  str            = Field(...)


# ---------------------------------------------------------------------------
# Helpers re-used from classify_questions.py
# ---------------------------------------------------------------------------
def normalise_class(raw: str) -> str:
    return re.sub(r"\D", "", str(raw))

def normalise_subject(raw: str) -> str:
    return str(raw).lower().strip()

def load_syllabuses() -> Dict:
    syllabuses: Dict = {}
    for f in DATA_SYLLABUS.glob("*.json"):
        try:
            with open(f, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            key = (normalise_class(data["class"]), normalise_subject(data["subject"]))
            syllabuses[key] = data
            log.info(f"Loaded syllabus: {key}")
        except Exception as e:
            log.warning(f"Could not load {f}: {e}")
    return syllabuses

def collect_valid_ids(syllabus: dict) -> set:
    valid: set = set()
    def walk(nodes):
        for n in nodes:
            if n.get("id"):
                valid.add(n["id"])
            walk(n.get("children", []) or [])
    walk(syllabus.get("curriculum", []))
    return valid

def format_taxonomy_for_prompt(syllabus: dict) -> str:
    lines: List[str] = []
    def walk(nodes, depth=0):
        indent = "  " * depth
        for node in nodes:
            node_type = node.get("type", "node").upper()
            name      = node.get("name", "")
            node_id   = node.get("id", "")
            lines.append(f"{indent}- [{node_type}] {name}  (ID: {node_id})")
            walk(node.get("children", []) or [], depth + 1)
    walk(syllabus.get("curriculum", []))
    return "\n".join(lines)

PROMPT_TEMPLATE = """\
You are an expert CBSE curriculum classifier for academic year 2026-27.
Your ONLY task is to assign the provided question to the most appropriate node
in the official CBSE syllabus taxonomy shown below. You must NEVER generate,
rewrite, paraphrase, or invent any question text or syllabus node.

=== QUESTION ===
ID         : {question_id}
Class      : {cls}
Subject    : {subject}
Type       : {qtype}
Marks      : {marks}
Text       :
{question_text}

=== AUTHORITATIVE CBSE 2026-27 TAXONOMY FOR {cls} {subject} ===
(Select IDs ONLY from the list below. Inventing IDs is forbidden.)

{taxonomy_text}

=== CLASSIFICATION RULES ===
1. Return ONLY valid IDs from the taxonomy above. Never invent IDs.
2. Map to the deepest node you can confidently assign.
   If only chapter-level is certain, set topic_id = null.
3. confidence: float 0.0-1.0 representing your certainty of the mapping.
4. classification_reason: 1-2 factual sentences explaining why this node applies.
5. alternative_candidates: up to 3 other valid taxonomy IDs (any level) if uncertain.
6. requires_visual_context: true only if the question explicitly refers to a
   diagram/figure that is unavailable and is necessary to identify the concept.
7. difficulty: one of easy / medium / hard / unknown.
8. syllabus_eligibility:
   - "CURRENT_SYLLABUS": Question maps to the provided 2026-27 taxonomy.
   - "OUT_OF_CURRENT_SYLLABUS": Subject matter belongs to the subject but is clearly removed/absent from the 2026-27 taxonomy.
   - "UNCLASSIFIABLE": Nonsense question, entirely unparseable, or wrong subject.
   - "INCOMPLETE": Question missing crucial text to know what it is asking.
   - "BOILERPLATE": Administrative text, non-question instructional text.
9. If syllabus_eligibility is NOT "CURRENT_SYLLABUS", set chapter_id = "UNCLASSIFIABLE".

Return a single JSON object conforming exactly to this schema -- no extra keys:
{{
  "unit_id": null or "<valid_unit_id>",
  "chapter_id": "<valid_chapter_id>",
  "topic_id": null or "<valid_topic_id>",
  "subtopic_id": null or "<valid_subtopic_id>",
  "learning_outcome_id": null or "<valid_learning_outcome_id>",
  "difficulty": "easy|medium|hard|unknown",
  "confidence": 0.0-1.0,
  "classification_reason": "Short reason.",
  "alternative_candidates": [],
  "requires_visual_context": false,
  "syllabus_eligibility": "CURRENT_SYLLABUS|OUT_OF_CURRENT_SYLLABUS|UNCLASSIFIABLE|INCOMPLETE|BOILERPLATE"
}}
"""

def build_prompt(row: pd.Series, taxonomy_text: str) -> str:
    return PROMPT_TEMPLATE.format(
        question_id=row.get("question_id", "?"),
        cls=row["class"],
        subject=row["subject"],
        qtype=row.get("question_type", "unknown"),
        marks=row.get("marks", "?"),
        question_text=str(row["question_text"]).strip(),
        taxonomy_text=taxonomy_text,
    )

def call_gemini_with_backoff(
    client: genai.Client,
    model: str,
    prompt: str,
    max_retries: int = 8,
    base_delay: float = 30.0,
) -> str:
    delay = base_delay
    for attempt in range(1, max_retries + 1):
        try:
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=genai_types.GenerateContentConfig(
                    temperature=0.0,
                    response_mime_type="application/json",
                ),
            )
            return response.text
        except Exception as e:
            err_str = str(e)
            is_rate_limit = "429" in err_str or "quota" in err_str.lower() or "rate" in err_str.lower()
            is_transient  = "503" in err_str or "unavailable" in err_str.lower() or "overload" in err_str.lower()

            if is_rate_limit or is_transient:
                m = re.search(r"retry.*?(\d+)", err_str, re.IGNORECASE)
                suggested = int(m.group(1)) + 5 if m else 0
                wait = max(delay, suggested)
                reason = "Rate limited" if is_rate_limit else "Service unavailable"
                log.warning(f"{reason} (attempt {attempt}/{max_retries}). Waiting {wait:.0f}s ...")
                time.sleep(wait)
                delay = min(delay * 2, 240)
            else:
                raise
    raise RuntimeError(f"Gemini call failed after {max_retries} retries.")

def validate_ids(result: ClassificationResult, valid_ids: set) -> List[str]:
    warnings: List[str] = []
    for field, val in {
        "unit_id": result.unit_id,
        "chapter_id": result.chapter_id,
        "topic_id": result.topic_id,
        "subtopic_id": result.subtopic_id,
        "learning_outcome_id": result.learning_outcome_id,
    }.items():
        if val is None or val in ("UNCLASSIFIABLE", "ERROR"):
            continue
        if val not in valid_ids:
            warnings.append(f"INVENTED_ID: {field}={val!r}")
    for alt in result.alternative_candidates:
        if alt and alt not in valid_ids:
            warnings.append(f"INVENTED_ALT: {alt!r}")
    return warnings

def determine_status(confidence: float, auto_threshold: float, chapter_id: str) -> str:
    if chapter_id in ("UNCLASSIFIABLE", "ERROR", "PARSE_ERROR"):
        return "unclassifiable"
    if confidence >= auto_threshold:
        return "auto_verified"
    return "review_required"

def build_canonical_map(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["question_id"] = [f"Q_{i:04d}" for i in range(len(df))]
    df["_norm_text"] = (
        df["question_text"]
        .fillna("")
        .str.lower()
        .str.replace(r"\s+", " ", regex=True)
        .str.strip()
    )
    first_occ = df.groupby("_norm_text")["question_id"].first().to_dict()
    df["canonical_question_id"] = (
        df["_norm_text"]
        .map(first_occ)
        .str.replace("Q_", "CQ_", regex=False)
    )
    df.drop(columns=["_norm_text"], inplace=True)
    return df

# ---------------------------------------------------------------------------
# Load existing checkpoint, keeping only valid (non-error) records
# ---------------------------------------------------------------------------
def load_valid_checkpoints() -> Dict[str, dict]:
    """Load checkpoint file, returning only records with a valid (non-error) status."""
    checkpoints: Dict[str, dict] = {}
    if not CHECKPOINT_FILE.exists():
        return checkpoints
    with open(CHECKPOINT_FILE, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                cqid = rec.get("canonical_question_id")
                status = rec.get("classification_status", "")
                if cqid and status in VALID_STATUSES:
                    checkpoints[cqid] = rec  # last valid wins
            except json.JSONDecodeError:
                pass
    return checkpoints

# ---------------------------------------------------------------------------
# Write merged outputs
# ---------------------------------------------------------------------------
def write_outputs(df: pd.DataFrame, results: List[dict], auto_threshold: float) -> None:
    clf_lookup: Dict[str, dict] = {r["canonical_question_id"]: r for r in results}

    clf_cols = [
        "unit_id", "chapter_id", "topic_id", "subtopic_id", "learning_outcome_id",
        "difficulty", "confidence", "classification_status", "classification_reason",
        "requires_visual_context", "syllabus_eligibility",
    ]
    for col in clf_cols:
        df[col] = df["canonical_question_id"].map(
            lambda cqid, c=col: clf_lookup.get(cqid, {}).get(c)
        )

    df["syllabus_version"] = "CBSE_2026_27"
    df.to_csv(FINAL_CSV, index=False, encoding="utf-8")
    log.info(f"Wrote {len(df)} rows to {FINAL_CSV}")

    # Review queue
    review_mask = (
        df["classification_status"].isin(["review_required", "error", "unclassifiable"]) |
        df["syllabus_eligibility"].isin(["OUT_OF_CURRENT_SYLLABUS", "INCOMPLETE", "BOILERPLATE", "UNCLASSIFIABLE"])
    )
    review_df = df[review_mask][[
        "question_id", "canonical_question_id", "question_text", "class", "subject",
        "chapter_id", "topic_id", "confidence", "syllabus_eligibility",
        "classification_reason", "classification_status"
    ]].copy()
    review_df["review_status"] = "pending"
    review_df.to_csv(REVIEW_CSV, index=False, encoding="utf-8")
    log.info(f"Wrote {len(review_df)} rows to {REVIEW_CSV}")

    # Summary
    total_q   = len(df)
    canonical = len(df["canonical_question_id"].dropna().unique())
    by_status = df["classification_status"].value_counts().to_dict()
    by_elig   = df["syllabus_eligibility"].value_counts().to_dict()

    cur_syl_mask = df["syllabus_eligibility"] == "CURRENT_SYLLABUS"
    successfully_mapped   = int(cur_syl_mask.sum())
    chapter_only_mappings = int((cur_syl_mask & (df["topic_id"].isna() | (df["topic_id"] == ""))).sum())
    topic_level_mappings  = int((cur_syl_mask & df["topic_id"].notna() & (df["topic_id"] != "")).sum())

    still_error = int(df["classification_status"].eq("error").sum())

    conf_vals = pd.to_numeric(df["confidence"], errors="coerce").dropna()
    avg_conf  = float(conf_vals.mean()) if len(conf_vals) else 0.0

    summary = {
        "total_original_records":        total_q,
        "total_canonical_questions":     canonical,
        "successfully_mapped_questions": successfully_mapped,
        "chapter_only_mappings":         chapter_only_mappings,
        "topic_level_mappings":          topic_level_mappings,
        "review_required":               by_status.get("review_required", 0),
        "auto_verified":                 by_status.get("auto_verified", 0),
        "out_of_current_syllabus":       by_elig.get("OUT_OF_CURRENT_SYLLABUS", 0),
        "boilerplate_records":           by_elig.get("BOILERPLATE", 0),
        "unclassifiable_records":        by_elig.get("UNCLASSIFIABLE", 0) + by_elig.get("INCOMPLETE", 0),
        "still_unresolved_api_errors":   still_error,
        "average_confidence":            round(avg_conf, 4),
        "requires_visual_context":       int(df["requires_visual_context"].astype(str).str.lower().eq("true").sum()),
        "mapping_counts_by_class":       df["class"].value_counts().to_dict(),
        "mapping_counts_by_subject":     df["subject"].value_counts().to_dict(),
        "mapping_counts_by_chapter":     df["chapter_id"].dropna().value_counts().to_dict(),
        "mapping_counts_by_topic":       df["topic_id"].dropna().value_counts().to_dict(),
    }

    with open(SUMMARY_JSON, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2)

    with open(SUMMARY_MD, "w", encoding="utf-8") as md:
        md.write("# Question Mapping Summary\n\n")
        md.write("## Overview\n")
        md.write(f"- **Total original questions:** {total_q}\n")
        md.write(f"- **Total unique/canonical questions:** {canonical}\n")
        md.write(f"- **Successfully mapped (CURRENT_SYLLABUS):** {successfully_mapped}\n")
        md.write(f"  - Chapter-only mappings: {chapter_only_mappings}\n")
        md.write(f"  - Topic-level mappings: {topic_level_mappings}\n")
        md.write(f"- **Auto-verified (conf ≥ {auto_threshold}):** {summary['auto_verified']}\n")
        md.write(f"- **Review-required:** {summary['review_required']}\n")
        md.write(f"- **OUT_OF_CURRENT_SYLLABUS:** {summary['out_of_current_syllabus']}\n")
        md.write(f"- **BOILERPLATE:** {summary['boilerplate_records']}\n")
        md.write(f"- **Genuine UNCLASSIFIABLE/INCOMPLETE:** {summary['unclassifiable_records']}\n")
        md.write(f"- **Still unresolved (API errors):** {still_error}\n")
        md.write(f"- **Requires visual context:** {summary['requires_visual_context']}\n")
        md.write(f"- **Average classification confidence:** {summary['average_confidence']:.4f}\n")

        md.write("\n## Mapping Counts by Class\n")
        for k, v in summary["mapping_counts_by_class"].items():
            md.write(f"- **{k}:** {v}\n")

        md.write("\n## Mapping Counts by Subject\n")
        for k, v in summary["mapping_counts_by_subject"].items():
            md.write(f"- **{k}:** {v}\n")

        md.write("\n## Top 20 Chapter Mappings\n")
        for k, v in list(summary["mapping_counts_by_chapter"].items())[:20]:
            md.write(f"- **{k}:** {v}\n")

        md.write("\n## Top 20 Topic Mappings\n")
        for k, v in list(summary["mapping_counts_by_topic"].items())[:20]:
            md.write(f"- **{k}:** {v}\n")

    log.info(f"Wrote summary to {SUMMARY_MD} and {SUMMARY_JSON}")

    # Print final stats
    print("\n=== FINAL MAPPING STATISTICS ===")
    print(f"  {'Total canonical questions':<40}: {canonical}")
    print(f"  {'Successfully mapped (CURRENT_SYLLABUS)':<40}: {successfully_mapped}")
    print(f"    {'Chapter-only':<38}: {chapter_only_mappings}")
    print(f"    {'Topic-level':<38}: {topic_level_mappings}")
    print(f"  {'Auto-verified':<40}: {summary['auto_verified']}")
    print(f"  {'Review-required':<40}: {summary['review_required']}")
    print(f"  {'OUT_OF_CURRENT_SYLLABUS':<40}: {summary['out_of_current_syllabus']}")
    print(f"  {'BOILERPLATE':<40}: {summary['boilerplate_records']}")
    print(f"  {'Genuine UNCLASSIFIABLE':<40}: {summary['unclassifiable_records']}")
    print(f"  {'Still unresolved (API errors)':<40}: {still_error}")
    print(f"  {'Average confidence':<40}: {summary['average_confidence']:.4f}")
    print("\nFiles updated:")
    print(f"  {FINAL_CSV}")
    print(f"  {REVIEW_CSV}")
    print(f"  {SUMMARY_MD}")
    print(f"  {SUMMARY_JSON}")


# ---------------------------------------------------------------------------
# Integrity check
# ---------------------------------------------------------------------------
def run_integrity_check(df: pd.DataFrame, results: List[dict]) -> None:
    print("\n=== INTEGRITY CHECK ===")
    
    # 1. Row count
    ok = len(df) == 1795
    print(f"  [{'OK' if ok else 'FAIL'}] Total original records: {len(df)} (expected 1795)")

    # 2. Canonical count
    n_canonical = len(df["canonical_question_id"].dropna().unique())
    ok2 = n_canonical == 1726
    print(f"  [{'OK' if ok2 else 'WARN'}] Canonical questions: {n_canonical} (expected 1726)")

    # 3. No invented IDs -- check against the in-memory result set
    invented = [
        r["canonical_question_id"]
        for r in results
        if r.get("validation_warnings") and any("INVENTED" in w for w in r["validation_warnings"])
    ]
    print(f"  [{'OK' if not invented else 'WARN'}] Invented taxonomy IDs: {len(invented)}")

    # 4. Duplicate consistency
    dup_inconsistent = 0
    for cqid, grp in df.groupby("canonical_question_id"):
        statuses = grp["classification_status"].dropna().unique()
        if len(statuses) > 1:
            dup_inconsistent += 1
    print(f"  [{'OK' if dup_inconsistent == 0 else 'WARN'}] Duplicate groups with inconsistent status: {dup_inconsistent}")

    # 5. Error vs genuine
    error_count = int(df["classification_status"].eq("error").sum())
    genuine_unclass = int(df["classification_status"].eq("unclassifiable").sum())
    print(f"  [INFO] Still unresolved API errors: {error_count}")
    print(f"  [INFO] Genuine unclassifiable: {genuine_unclass}")
    print("=== END INTEGRITY CHECK ===\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description="Retry failed CBSE classifications")
    parser.add_argument("--dry-run",    action="store_true", help="Show what would be retried, no API calls.")
    parser.add_argument("--limit",      type=int, default=None, help="Retry at most N failed questions.")
    parser.add_argument("--batch-size", type=int, default=5,    help="Questions per batch (default: 5).")
    parser.add_argument("--delay",      type=float, default=8.0, help="Inter-request delay in seconds (default: 8).")
    args = parser.parse_args()

    # ---- API key ----
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key and not args.dry_run:
        log.error("GEMINI_API_KEY is not set. Aborting.")
        sys.exit(1)

    # ---- Config ----
    with open(CONFIG_FILE, "r", encoding="utf-8") as fh:
        config = json.load(fh)
    model_name      = config["model"]
    auto_threshold  = config["auto_verify_threshold"]
    log.info(f"Model: {model_name} | batch: {args.batch_size} | delay: {args.delay}s | auto_verify: {auto_threshold}")

    # ---- Load syllabuses ----
    syllabuses = load_syllabuses()
    if not syllabuses:
        log.error("No syllabus JSON files found. Aborting.")
        sys.exit(1)

    # ---- Load question bank ----
    df = pd.read_csv(QBANK_CSV, dtype=str)
    df = build_canonical_map(df)
    canonical_df = df.drop_duplicates(subset=["canonical_question_id"]).copy()
    log.info(f"Total rows: {len(df)} | Canonical: {len(canonical_df)}")

    # ---- Load valid checkpoints (excludes errors) ----
    valid_checkpoints = load_valid_checkpoints()
    log.info(f"Valid (non-error) checkpoints loaded: {len(valid_checkpoints)}")

    # ---- Find canonical questions needing retry ----
    to_retry = canonical_df[
        ~canonical_df["canonical_question_id"].isin(valid_checkpoints)
    ].copy()
    log.info(f"Canonical questions requiring retry: {len(to_retry)}")

    if args.limit:
        to_retry = to_retry.head(args.limit)
        log.info(f"Limiting to {args.limit} questions.")

    if args.dry_run:
        print(f"\n=== DRY RUN ===")
        print(f"Valid checkpoints (will NOT retry): {len(valid_checkpoints)}")
        print(f"Questions to retry: {len(to_retry)}")
        by_class = to_retry["class"].value_counts().to_dict()
        by_subj  = to_retry["subject"].value_counts().to_dict()
        print(f"By class: {by_class}")
        print(f"By subject: {by_subj}")
        print("No API calls made.")
        return

    # ---- Gemini client ----
    client = genai.Client(api_key=api_key)

    # ---- Build full results from valid checkpoints ----
    results: List[dict] = list(valid_checkpoints.values())
    failed_cqids: List[str] = []
    total = len(to_retry)

    # ---- Open checkpoint for appending NEW results ----
    checkpoint_fh = open(CHECKPOINT_FILE, "a", encoding="utf-8")

    try:
        for batch_start in range(0, total, args.batch_size):
            batch = to_retry.iloc[batch_start: batch_start + args.batch_size]

            for i, (_, row) in enumerate(batch.iterrows(), start=batch_start + 1):
                cq_id    = row["canonical_question_id"]
                cls_raw  = row["class"]
                subj     = row["subject"]
                cls_num  = normalise_class(cls_raw)
                subj_key = normalise_subject(subj)

                # ---- Look up syllabus ----
                syllabus = syllabuses.get((cls_num, subj_key))
                if not syllabus:
                    log.warning(f"[{i}/{total}] {cq_id} -- no syllabus (class={cls_num}, subj={subj_key})")
                    rec = {
                        "canonical_question_id": cq_id,
                        "question_id":           row["question_id"],
                        "class": cls_raw, "subject": subj,
                        "chapter_id": "UNCLASSIFIABLE", "unit_id": None,
                        "topic_id": None, "subtopic_id": None,
                        "learning_outcome_id": None, "difficulty": "unknown",
                        "confidence": 0.0, "classification_status": "unclassifiable",
                        "classification_reason": f"No syllabus for class={cls_num} subj={subj_key}.",
                        "alternative_candidates": [], "requires_visual_context": False,
                        "syllabus_eligibility": "UNCLASSIFIABLE",
                        "pydantic_valid": True, "validation_warnings": [],
                    }
                    results.append(rec)
                    checkpoint_fh.write(json.dumps(rec) + "\n")
                    checkpoint_fh.flush()
                    print(f"[{i}/{total}] {cq_id} -- UNCLASSIFIABLE (no syllabus)")
                    continue

                valid_ids    = collect_valid_ids(syllabus)
                taxonomy_txt = format_taxonomy_for_prompt(syllabus)
                prompt       = build_prompt(row, taxonomy_txt)

                # ---- Call Gemini ----
                try:
                    raw_json = call_gemini_with_backoff(client, model_name, prompt,
                                                        max_retries=8, base_delay=30.0)
                except Exception as e:
                    log.error(f"[{i}/{total}] {cq_id} -- API call failed: {e}")
                    failed_cqids.append(cq_id)
                    rec = {
                        "canonical_question_id": cq_id,
                        "question_id":           row["question_id"],
                        "class": cls_raw, "subject": subj,
                        "chapter_id": "ERROR", "classification_status": "error",
                        "classification_reason": f"API error: {str(e)[:200]}",
                        "confidence": 0.0, "pydantic_valid": False,
                        "syllabus_eligibility": "UNCLASSIFIABLE",
                        "validation_warnings": [],
                    }
                    results.append(rec)
                    checkpoint_fh.write(json.dumps(rec) + "\n")
                    checkpoint_fh.flush()
                    print(f"[{i}/{total}] {cq_id} -- API ERROR")
                    time.sleep(args.delay)
                    continue

                # ---- Pydantic validation ----
                pydantic_valid = True
                validation_warnings: List[str] = []
                try:
                    validated = ClassificationResult.model_validate_json(raw_json)
                except ValidationError as ve:
                    log.warning(f"[{i}/{total}] {cq_id} -- Pydantic FAILED: {ve}")
                    pydantic_valid = False
                    validation_warnings.append(f"Pydantic: {ve}")
                    try:
                        raw_dict  = json.loads(raw_json)
                        validated = ClassificationResult.model_construct(**raw_dict)
                    except Exception:
                        failed_cqids.append(cq_id)
                        rec = {
                            "canonical_question_id": cq_id, "question_id": row["question_id"],
                            "class": cls_raw, "subject": subj,
                            "chapter_id": "PARSE_ERROR", "classification_status": "error",
                            "classification_reason": "Pydantic + JSON parse failed.",
                            "confidence": 0.0, "pydantic_valid": False,
                            "syllabus_eligibility": "UNCLASSIFIABLE",
                            "validation_warnings": validation_warnings,
                        }
                        results.append(rec)
                        checkpoint_fh.write(json.dumps(rec) + "\n")
                        checkpoint_fh.flush()
                        print(f"[{i}/{total}] {cq_id} -- PARSE ERROR")
                        time.sleep(args.delay)
                        continue

                # ---- ID validation ----
                id_warnings = validate_ids(validated, valid_ids)
                if id_warnings:
                    log.warning(f"[{i}/{total}] {cq_id} -- ID issues: {id_warnings}")
                    validation_warnings.extend(id_warnings)

                # ---- Status ----
                status = determine_status(validated.confidence, auto_threshold, validated.chapter_id)

                rec = {
                    "canonical_question_id":   cq_id,
                    "question_id":             row["question_id"],
                    "class":                   cls_raw,
                    "subject":                 subj,
                    "unit_id":                 validated.unit_id,
                    "chapter_id":              validated.chapter_id,
                    "topic_id":                validated.topic_id,
                    "subtopic_id":             validated.subtopic_id,
                    "learning_outcome_id":     validated.learning_outcome_id,
                    "difficulty":              validated.difficulty,
                    "confidence":              validated.confidence,
                    "classification_status":   status,
                    "classification_reason":   validated.classification_reason,
                    "alternative_candidates":  validated.alternative_candidates,
                    "requires_visual_context": validated.requires_visual_context,
                    "syllabus_eligibility":    validated.syllabus_eligibility,
                    "pydantic_valid":          pydantic_valid,
                    "validation_warnings":     validation_warnings,
                }
                results.append(rec)
                checkpoint_fh.write(json.dumps(rec) + "\n")
                checkpoint_fh.flush()
                print(f"[{i}/{total}] {cq_id} -- {status} (conf={validated.confidence:.2f}, elig={validated.syllabus_eligibility})")

                # Inter-request delay
                time.sleep(args.delay)

            # End-of-batch log
            done = min(batch_start + args.batch_size, total)
            log.info(f"Batch complete: {done}/{total} processed so far | errors so far: {len(failed_cqids)}")

    finally:
        checkpoint_fh.close()

    # ---- Write final outputs ----
    log.info("Writing final outputs ...")
    write_outputs(df, results, auto_threshold)

    # ---- Integrity check ----
    run_integrity_check(df, results)

    if failed_cqids:
        log.warning(f"Still unresolved after retry: {len(failed_cqids)} questions. Re-run to retry them.")


if __name__ == "__main__":
    main()
