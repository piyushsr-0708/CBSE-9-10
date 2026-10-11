"""
classify_questions.py
=====================
Classifies CBSE questions into the official 2026-27 syllabus taxonomy using Gemini.
"""

# Force UTF-8 output on Windows to handle special characters in question text
import io, sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
else:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

"""

Usage:
    python scripts/classify_questions.py --dry-run          # Test 10 questions, no output saved
    python scripts/classify_questions.py --limit 50         # Classify 50 canonical questions
    python scripts/classify_questions.py --force            # Reclassify even already-checkpointed items
    python scripts/classify_questions.py                    # Full run (all 1,726 canonical questions)

Safety constraints:
    - The LLM NEVER generates or rewrites questions.
    - Only IDs from the supplied taxonomy may be returned.
    - All 1,795 original records are preserved in final output.
"""

import json
import os
import re
import sys
import time
import argparse
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any

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
ROOT         = Path(__file__).resolve().parent.parent
DATA_SYLLABUS  = ROOT / "data" / "syllabus"
DATA_PROCESSED = ROOT / "data" / "processed"
OUTPUT_DIR     = ROOT / "output"
REPORTS_DIR    = ROOT / "reports"
CONFIG_FILE    = ROOT / "config" / "classification_config.json"

QBANK_CSV        = ROOT / "clean_question_bank.csv"
CHECKPOINT_FILE  = DATA_PROCESSED / "classification_results.jsonl"
FINAL_CSV        = OUTPUT_DIR / "classified_question_bank.csv"
REVIEW_CSV       = OUTPUT_DIR / "review_queue.csv"
SUMMARY_JSON     = REPORTS_DIR / "question_mapping_summary.json"
SUMMARY_MD       = REPORTS_DIR / "question_mapping_summary.md"

# Ensure output directories exist
for d in [DATA_PROCESSED, OUTPUT_DIR, REPORTS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Pydantic schema -- strict output contract for LLM
# ---------------------------------------------------------------------------
class ClassificationResult(BaseModel):
    unit_id:              Optional[str]  = Field(None,  description="Valid unit ID from taxonomy, if applicable")
    chapter_id:           str            = Field(...,    description="Valid chapter ID from taxonomy -- REQUIRED")
    topic_id:             Optional[str]  = Field(None,  description="Valid topic ID from taxonomy, if applicable")
    subtopic_id:          Optional[str]  = Field(None,  description="Valid subtopic ID from taxonomy, if applicable")
    learning_outcome_id:  Optional[str]  = Field(None,  description="Valid learning-outcome ID, if applicable")
    difficulty:           str            = Field(...,    description="One of: easy | medium | hard | unknown")
    confidence:           float          = Field(...,    ge=0.0, le=1.0, description="Model confidence 0.0-1.0")
    classification_reason: str           = Field(...,    description="Short factual reason (1-2 sentences)")
    alternative_candidates: List[str]    = Field(default_factory=list, description="Up to 3 alternative valid IDs")
    requires_visual_context: bool        = Field(False,  description="True if a missing diagram is required")
    syllabus_eligibility: str            = Field(...,    description="One of: CURRENT_SYLLABUS | OUT_OF_CURRENT_SYLLABUS | UNCLASSIFIABLE | INCOMPLETE | BOILERPLATE")


# ---------------------------------------------------------------------------
# Syllabus loading and key normalisation
# ---------------------------------------------------------------------------
def normalise_class(raw: str) -> str:
    """'class10' -> '10', 'Class 9' -> '9', '9' -> '9'."""
    return re.sub(r"\D", "", str(raw))

def normalise_subject(raw: str) -> str:
    return str(raw).lower().strip()

def load_syllabuses() -> Dict:
    """Load all syllabus JSON files keyed by (class_number, subject)."""
    syllabuses: Dict = {}
    for f in DATA_SYLLABUS.glob("*.json"):
        try:
            with open(f, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            key = (normalise_class(data["class"]), normalise_subject(data["subject"]))
            syllabuses[key] = data
            log.info(f"Loaded syllabus: {key} from {f.name}")
        except Exception as e:
            log.warning(f"Could not load syllabus {f}: {e}")
    return syllabuses


# ---------------------------------------------------------------------------
# Taxonomy formatting for prompt
# ---------------------------------------------------------------------------
def format_taxonomy_for_prompt(syllabus: dict) -> str:
    """
    Recursively walk the curriculum tree and produce a concise, indented list
    of node type, name, and ID for inclusion in the prompt.
    """
    lines: List[str] = []

    def walk(nodes: list, depth: int = 0) -> None:
        indent = "  " * depth
        for node in nodes:
            node_type = node.get("type", "node").upper()
            name      = node.get("name", "")
            node_id   = node.get("id", "")
            lines.append(f"{indent}- [{node_type}] {name}  (ID: {node_id})")
            children = node.get("children", []) or []
            if children:
                walk(children, depth + 1)

    walk(syllabus.get("curriculum", []))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------
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
7. difficulty: one of easy / medium / hard / unknown -- estimate from question complexity.
8. syllabus_eligibility:
   - "CURRENT_SYLLABUS": Question maps to the provided 2026-27 taxonomy.
   - "OUT_OF_CURRENT_SYLLABUS": Subject matter belongs to the subject but is clearly removed/absent from the 2026-27 taxonomy (e.g., Nazism/Hitler in 2026 History).
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


# ---------------------------------------------------------------------------
# Gemini API call with exponential back-off
# ---------------------------------------------------------------------------
def call_gemini_with_backoff(
    client: genai.Client,
    model: str,
    prompt: str,
    max_retries: int = 6,
    base_delay: float = 15.0,
) -> str:
    """
    Call Gemini with exponential backoff on transient errors:
      - 429 / quota exceeded
      - 503 / service unavailable (model overloaded)
    Non-transient errors (404, 400, auth failures) are raised immediately.
    """
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
                # Try to parse suggested retry delay from error body
                import re as _re
                m = _re.search(r"retry.*?(\d+)", err_str, _re.IGNORECASE)
                suggested = int(m.group(1)) + 5 if m else 0
                wait = max(delay, suggested)
                reason = "Rate limited" if is_rate_limit else "Service unavailable"
                log.warning(f"{reason} (attempt {attempt}/{max_retries}). Waiting {wait}s ...")
                time.sleep(wait)
                delay = min(delay * 2, 120)
            else:
                raise  # Non-transient error (404, 400, auth) -- propagate immediately

    raise RuntimeError(f"Gemini call failed after {max_retries} retries (rate limited).")


# ---------------------------------------------------------------------------
# Taxonomy ID validation
# ---------------------------------------------------------------------------
def collect_valid_ids(syllabus: dict) -> set:
    """Return all valid node IDs from the taxonomy tree."""
    valid: set = set()

    def walk(nodes: list) -> None:
        for n in nodes:
            if n.get("id"):
                valid.add(n["id"])
            walk(n.get("children", []) or [])

    walk(syllabus.get("curriculum", []))
    return valid


def validate_ids(
    result: ClassificationResult,
    valid_ids: set,
    strict: bool = True,
) -> List[str]:
    """
    Return a list of validation warnings.
    If strict=True, invented IDs are flagged as errors.
    """
    warnings: List[str] = []
    ids_to_check = {
        "unit_id":             result.unit_id,
        "chapter_id":          result.chapter_id,
        "topic_id":            result.topic_id,
        "subtopic_id":         result.subtopic_id,
        "learning_outcome_id": result.learning_outcome_id,
    }
    for field, val in ids_to_check.items():
        if val is None or val == "UNCLASSIFIABLE":
            continue
        if val not in valid_ids:
            warnings.append(f"INVENTED_ID: {field}={val!r} not found in taxonomy")

    for alt in result.alternative_candidates:
        if alt and alt not in valid_ids:
            warnings.append(f"INVENTED_ALT: {alt!r} not found in taxonomy")

    return warnings


# ---------------------------------------------------------------------------
# Determine classification status
# ---------------------------------------------------------------------------
def determine_status(confidence: float, config: dict, chapter_id: str) -> str:
    if chapter_id == "UNCLASSIFIABLE":
        return "unclassifiable"
    if confidence >= config["auto_verify_threshold"]:
        return "auto_verified"
    return "review_required"


# ---------------------------------------------------------------------------
# Canonical question ID generation
# ---------------------------------------------------------------------------
def build_canonical_map(df: pd.DataFrame) -> pd.DataFrame:
    """
    Assign row-level question IDs and derive canonical IDs by deduplicating
    on normalised question text (first occurrence wins).
    """
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
# Dry-run question sampling
# ---------------------------------------------------------------------------
TARGET_SUBJECTS = [
    ("class9",  "maths"),
    ("class9",  "science"),
    ("class9",  "social_science"),
    ("class10", "maths"),
    ("class10", "social_science"),
    ("class10", "computer_application"),
    ("class10", "home_science"),
]

def sample_stratified(canonical_df: pd.DataFrame, target_count: int) -> pd.DataFrame:
    """
    Guarantee exactly one question per target subject (all 7 must be covered).
    After the mandatory 7, fill remaining slots (up to target_count) with more
    questions from subjects that have enough data, prioritising subjects in order.
    """
    # Phase 1: mandatory -- one question per subject
    mandatory: List[pd.DataFrame] = []
    available: Dict[tuple, pd.DataFrame] = {}
    for cls, subj in TARGET_SUBJECTS:
        subset = canonical_df[
            (canonical_df["class"].str.lower() == cls) &
            (canonical_df["subject"].str.lower() == subj)
        ].copy()
        if not subset.empty:
            mandatory.append(subset.head(1))
            # Keep the remainder for phase 2 (skip row 0 already taken)
            if len(subset) > 1:
                available[(cls, subj)] = subset.iloc[1:]
        else:
            log.warning(f"SAMPLING: No canonical questions found for {cls} {subj}")

    if not mandatory:
        return canonical_df.head(target_count)

    mandatory_df = pd.concat(mandatory).drop_duplicates(subset=["canonical_question_id"])

    # Phase 2: fill extras from subjects that have remaining rows
    extras: List[pd.DataFrame] = []
    slots_left = target_count - len(mandatory_df)
    
    # We round-robin across available subjects to fill the remaining slots
    while slots_left > 0:
        added_in_round = 0
        for cls, subj in TARGET_SUBJECTS:
            if slots_left <= 0:
                break
            remainder = available.get((cls, subj))
            if remainder is not None and not remainder.empty:
                extras.append(remainder.head(1))
                available[(cls, subj)] = remainder.iloc[1:] # shift
                slots_left -= 1
                added_in_round += 1
        if added_in_round == 0:
            break # ran out of all questions

    if extras:
        result = pd.concat([mandatory_df] + extras).drop_duplicates(subset=["canonical_question_id"])
    else:
        result = mandatory_df

    return result.head(target_count)



# ---------------------------------------------------------------------------
# Checkpoint helpers
# ---------------------------------------------------------------------------
def load_checkpoints() -> Dict[str, dict]:
    checkpoints: Dict[str, dict] = {}
    if CHECKPOINT_FILE.exists():
        with open(CHECKPOINT_FILE, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    try:
                        rec = json.loads(line)
                        cqid = rec.get("canonical_question_id")
                        status = rec.get("classification_status")
                        if cqid and status != "error":
                            checkpoints[cqid] = rec
                    except json.JSONDecodeError:
                        pass
    return checkpoints


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description="CBSE Question Classifier")
    parser.add_argument("--dry-run",  action="store_true",
                        help="Classify 10 representative questions; do NOT save output.")
    parser.add_argument("--limit",    type=int, default=None,
                        help="Classify at most N canonical questions (overrides --dry-run sampling).")
    parser.add_argument("--force",    action="store_true",
                        help="Ignore checkpoint; reclassify everything.")
    args = parser.parse_args()

    # ---- Validate environment ----
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        log.error("GEMINI_API_KEY is not set. Aborting.")
        sys.exit(1)
    # Never print the key -- only confirm it is present
    log.info("GEMINI_API_KEY detected (value hidden).")

    # ---- Load config ----
    with open(CONFIG_FILE, "r", encoding="utf-8") as fh:
        config = json.load(fh)
    model_name = config["model"]
    log.info(f"Model: {model_name} | batch_size: {config['batch_size']} | "
             f"auto_verify: {config['auto_verify_threshold']} | review: {config['review_threshold']}")

    # ---- Load syllabuses ----
    syllabuses = load_syllabuses()
    if not syllabuses:
        log.error("No syllabus JSON files found in data/syllabus/. Aborting.")
        sys.exit(1)

    # ---- Load and prepare question bank ----
    df = pd.read_csv(QBANK_CSV, dtype=str)
    df = build_canonical_map(df)
    canonical_df = df.drop_duplicates(subset=["canonical_question_id"]).copy()
    log.info(f"Total rows: {len(df)} | Canonical unique questions: {len(canonical_df)}")

    # ---- Select questions to process ----
    if args.dry_run:
        to_classify = sample_stratified(canonical_df, 10)
        log.info(f"DRY RUN -- {len(to_classify)} representative questions selected.")
        print("\n" + "=" * 60)
        print("  DRY RUN MODE -- No output will be saved")
        print("=" * 60)
    elif args.limit:
        to_classify = sample_stratified(canonical_df, args.limit)
        log.info(f"Limit mode -- processing {len(to_classify)} stratified canonical questions.")
    else:
        to_classify = canonical_df
        log.info(f"Full run -- processing all {len(to_classify)} canonical questions.")

    # ---- Load existing checkpoint (skip already-done items unless --force) ----
    checkpoints = {}
    if not args.force and not args.dry_run:
        checkpoints = load_checkpoints()
        log.info(f"Loaded {len(checkpoints)} previously classified questions from checkpoint.")

    # ---- Build Gemini client ----
    client = genai.Client(api_key=api_key)

    # ---- Classification loop ----
    results: List[dict] = []
    failed_ids: List[str] = []
    skipped_ids: List[str] = []

    checkpoint_fh = None
    if not args.dry_run:
        checkpoint_fh = open(CHECKPOINT_FILE, "a", encoding="utf-8")

    total = len(to_classify)

    for i, (_, row) in enumerate(to_classify.iterrows(), start=1):
        cq_id   = row["canonical_question_id"]
        cls_raw = row["class"]
        subj    = row["subject"]

        cls_num = normalise_class(cls_raw)
        subj_key = normalise_subject(subj)

        # ---- Skip if checkpointed ----
        if cq_id in checkpoints and not args.force and not args.dry_run:
            results.append(checkpoints[cq_id])
            skipped_ids.append(cq_id)
            continue

        # ---- Look up syllabus ----
        syllabus = syllabuses.get((cls_num, subj_key))
        if not syllabus:
            log.warning(f"[{i}/{total}] No syllabus for class={cls_num} subject={subj_key} -- marking unclassifiable.")
            rec = {
                "canonical_question_id": cq_id,
                "question_id": row["question_id"],
                "class": cls_raw,
                "subject": subj,
                "chapter_id": "UNCLASSIFIABLE",
                "unit_id": None,
                "topic_id": None,
                "subtopic_id": None,
                "learning_outcome_id": None,
                "difficulty": "unknown",
                "confidence": 0.0,
                "classification_status": "unclassifiable",
                "classification_reason": f"No syllabus available for class={cls_num} subject={subj_key}.",
                "alternative_candidates": [],
                "requires_visual_context": False,
                "syllabus_eligibility": "UNCLASSIFIABLE",
                "validation_warnings": [],
                "pydantic_valid": True,
            }
            results.append(rec)
            if checkpoint_fh:
                checkpoint_fh.write(json.dumps(rec) + "\n")
                checkpoint_fh.flush()
            print(f"[{i}/{total}] {cq_id} -- UNCLASSIFIABLE (no syllabus)")
            continue

        # ---- Prepare taxonomy context ----
        valid_ids    = collect_valid_ids(syllabus)
        taxonomy_txt = format_taxonomy_for_prompt(syllabus)
        prompt       = build_prompt(row, taxonomy_txt)

        # ---- Print dry-run preview ----
        if args.dry_run:
            safe_text = str(row['question_text'])[:120].encode('ascii', errors='replace').decode('ascii')
            print(f"\n{'-'*60}")
            print(f"Q {i}/{total}  |  {cq_id}  |  {cls_raw} {subj}")
            print(f"Text (first 120 chars): {safe_text}...")
            print(f"Type: {row.get('question_type','?')}  Marks: {row.get('marks','?')}")
            print(f"\n[Taxonomy sent to model -- {len(taxonomy_txt.splitlines())} lines / "
                  f"{len(taxonomy_txt)} chars / {len(valid_ids)} valid IDs]")

        # ---- Call Gemini ----
        try:
            raw_json = call_gemini_with_backoff(client, model_name, prompt)
        except Exception as e:
            log.error(f"[{i}/{total}] {cq_id} -- API call failed: {e}")
            failed_ids.append(cq_id)
            rec = {
                "canonical_question_id": cq_id,
                "question_id": row["question_id"],
                "class": cls_raw,
                "subject": subj,
                "chapter_id": "ERROR",
                "classification_status": "error",
                "classification_reason": f"API error: {str(e)[:200]}",
                "confidence": 0.0,
                "pydantic_valid": False,
                "syllabus_eligibility": "UNCLASSIFIABLE",
                "validation_warnings": [],
            }
            results.append(rec)
            if checkpoint_fh:
                checkpoint_fh.write(json.dumps(rec) + "\n")
                checkpoint_fh.flush()
            print(f"[{i}/{total}] {cq_id} -- ERROR")
            continue

        # ---- Pydantic validation ----
        pydantic_valid = True
        validation_warnings: List[str] = []
        try:
            validated = ClassificationResult.model_validate_json(raw_json)
        except ValidationError as ve:
            log.warning(f"[{i}/{total}] {cq_id} -- Pydantic validation FAILED: {ve}")
            pydantic_valid = False
            validation_warnings.append(f"Pydantic: {ve}")
            # Attempt a best-effort parse anyway
            try:
                raw_dict = json.loads(raw_json)
                validated = ClassificationResult.model_construct(**raw_dict)
            except Exception:
                failed_ids.append(cq_id)
                rec = {
                    "canonical_question_id": cq_id,
                    "question_id": row["question_id"],
                    "class": cls_raw,
                    "subject": subj,
                    "chapter_id": "PARSE_ERROR",
                    "classification_status": "error",
                    "classification_reason": "Pydantic + JSON parse both failed.",
                    "confidence": 0.0,
                    "pydantic_valid": False,
                    "syllabus_eligibility": "UNCLASSIFIABLE",
                    "validation_warnings": validation_warnings,
                }
                results.append(rec)
                print(f"[{i}/{total}] {cq_id} -- PARSE ERROR")
                continue

        # ---- Taxonomy ID validation ----
        id_warnings = validate_ids(validated, valid_ids)
        if id_warnings:
            log.warning(f"[{i}/{total}] {cq_id} -- Taxonomy ID issues: {id_warnings}")
            validation_warnings.extend(id_warnings)

        # ---- Determine status ----
        status = determine_status(validated.confidence, config, validated.chapter_id)

        # ---- Build record ----
        rec = {
            "canonical_question_id":  cq_id,
            "question_id":            row["question_id"],
            "class":                  cls_raw,
            "subject":                subj,
            "unit_id":                validated.unit_id,
            "chapter_id":             validated.chapter_id,
            "topic_id":               validated.topic_id,
            "subtopic_id":            validated.subtopic_id,
            "learning_outcome_id":    validated.learning_outcome_id,
            "difficulty":             validated.difficulty,
            "confidence":             validated.confidence,
            "classification_status":  status,
            "classification_reason":  validated.classification_reason,
            "alternative_candidates": validated.alternative_candidates,
            "requires_visual_context": validated.requires_visual_context,
            "syllabus_eligibility":   validated.syllabus_eligibility,
            "pydantic_valid":         pydantic_valid,
            "validation_warnings":    validation_warnings,
        }
        results.append(rec)

        # ---- Print dry-run result ----
        if args.dry_run:
            print("\n[Model Output]")
            print(json.dumps({
                k: v for k, v in rec.items()
                if k not in ("question_id", "class", "subject", "canonical_question_id")
            }, indent=2, ensure_ascii=False))
            print(f"Pydantic valid: {pydantic_valid}")
            if validation_warnings:
                print(f"Warnings: {validation_warnings}")

        # ---- Write checkpoint ----
        if checkpoint_fh:
            checkpoint_fh.write(json.dumps(rec) + "\n")
            checkpoint_fh.flush()

        print(f"[{i}/{total}] {cq_id} -- {status} (conf={validated.confidence:.2f})")

    if checkpoint_fh:
        checkpoint_fh.close()

    # ---- Dry-run summary ----
    if args.dry_run:
        print("\n" + "=" * 60)
        print("  DRY RUN SUMMARY")
        print("=" * 60)
        total_q       = len(results)
        auto_v        = sum(1 for r in results if r.get("classification_status") == "auto_verified")
        review_q      = sum(1 for r in results if r.get("classification_status") == "review_required")
        unclass       = sum(1 for r in results if r.get("classification_status") == "unclassifiable")
        errors        = sum(1 for r in results if r.get("classification_status") == "error")
        invalid_ids   = sum(1 for r in results if r.get("validation_warnings"))
        visual_ctx    = sum(1 for r in results if r.get("requires_visual_context"))
        valid_pyd     = sum(1 for r in results if r.get("pydantic_valid", True))
        avg_conf      = (
            sum(r["confidence"] for r in results if isinstance(r.get("confidence"), float))
            / max(1, total_q)
        )
        print(f"  Questions tested      : {total_q}")
        print(f"  Model                 : {model_name}")
        print(f"  auto_verified         : {auto_v}")
        print(f"  review_required       : {review_q}")
        print(f"  unclassifiable        : {unclass}")
        print(f"  errors                : {errors}")
        print(f"  Pydantic valid        : {valid_pyd}/{total_q}")
        print(f"  Taxonomy ID warnings  : {invalid_ids}")
        print(f"  Require visual ctx    : {visual_ctx}")
        print(f"  Average confidence    : {avg_conf:.3f}")
        print(f"\n  API authentication    : SUCCESS")
        print(f"  Classifier readiness  : {'READY FOR FULL RUN' if errors == 0 and invalid_ids == 0 else 'NEEDS REVIEW'}")
        print("=" * 60)
        print("\nNOTE: No files were written (dry-run mode).")
        return

    # ---- Full run: merge and write output ----
    log.info("Merging classification results with original records ...")

    # Build a lookup from canonical_question_id -> classification record
    clf_lookup: Dict[str, dict] = {r["canonical_question_id"]: r for r in results}

    # Merge onto full df (all 1,795 rows)
    clf_cols = [
        "unit_id", "chapter_id", "topic_id", "subtopic_id", "learning_outcome_id",
        "difficulty", "confidence", "classification_status", "classification_reason",
        "requires_visual_context", "syllabus_eligibility"
    ]
    for col in clf_cols:
        df[col] = df["canonical_question_id"].map(
            lambda cqid, c=col: clf_lookup.get(cqid, {}).get(c)
        )

    df["syllabus_version"] = "CBSE_2026_27"

    df.to_csv(FINAL_CSV, index=False, encoding="utf-8")
    log.info(f"Wrote {len(df)} rows to {FINAL_CSV}")

    # ---- Review queue ----
    review_df = df[df["classification_status"].isin(["review_required", "error"]) | 
                   df["syllabus_eligibility"].isin(["OUT_OF_CURRENT_SYLLABUS", "INCOMPLETE", "BOILERPLATE", "UNCLASSIFIABLE"])][
        ["question_id", "canonical_question_id", "question_text", "class", "subject",
         "chapter_id", "topic_id", "confidence", "syllabus_eligibility", "classification_reason",
         "classification_status"]
    ].copy()
    review_df["review_status"] = "pending"
    review_df.to_csv(REVIEW_CSV, index=False, encoding="utf-8")
    log.info(f"Wrote {len(review_df)} rows to review queue: {REVIEW_CSV}")

    # ---- Classification summary ----
    total_q   = len(df)
    canonical = len(df["canonical_question_id"].dropna().unique())
    by_status = df["classification_status"].value_counts().to_dict()
    by_eligibility = df["syllabus_eligibility"].value_counts().to_dict()
    
    # Calculate mappings
    successfully_mapped = len(df[df["syllabus_eligibility"] == "CURRENT_SYLLABUS"])
    chapter_only_mappings = len(df[(df["syllabus_eligibility"] == "CURRENT_SYLLABUS") & (df["topic_id"].isna() | (df["topic_id"] == ""))])
    topic_level_mappings = len(df[(df["syllabus_eligibility"] == "CURRENT_SYLLABUS") & df["topic_id"].notna() & (df["topic_id"] != "")])

    summary = {
        "total_original_records":  total_q,
        "total_canonical_questions": canonical,
        "successfully_mapped_questions": successfully_mapped,
        "chapter_only_mappings": chapter_only_mappings,
        "topic_level_mappings": topic_level_mappings,
        "review_required":         by_status.get("review_required", 0),
        "out_of_current_syllabus": by_eligibility.get("OUT_OF_CURRENT_SYLLABUS", 0),
        "boilerplate_records":     by_eligibility.get("BOILERPLATE", 0),
        "unclassifiable_records":  by_eligibility.get("UNCLASSIFIABLE", 0) + by_status.get("unclassifiable", 0),
        "auto_verified":           by_status.get("auto_verified", 0),
        "errors":                  by_status.get("error", 0),
        "average_confidence":      float(df["confidence"].dropna().astype(float).mean()),
        "mapping_counts_by_class": df["class"].value_counts().to_dict(),
        "mapping_counts_by_subject": df["subject"].value_counts().to_dict(),
        "mapping_counts_by_chapter": df["chapter_id"].dropna().value_counts().to_dict(),
        "mapping_counts_by_topic": df["topic_id"].dropna().value_counts().to_dict(),
        "requires_visual_context": int(df["requires_visual_context"].astype(str).str.lower().eq("true").sum()),
        "failed_ids":              failed_ids,
        "skipped_checkpointed":    len(skipped_ids),
    }

    with open(SUMMARY_JSON, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2)
    log.info(f"Wrote summary to {SUMMARY_JSON}")

    # ---- Generate Markdown Report ----
    with open(SUMMARY_MD, "w", encoding="utf-8") as md:
        md.write("# Question Mapping Summary\n\n")
        md.write("## Overview\n")
        md.write(f"- **Total original questions:** {total_q}\n")
        md.write(f"- **Total unique/canonical questions:** {canonical}\n")
        md.write(f"- **Successfully mapped questions:** {successfully_mapped}\n")
        md.write(f"- **Chapter-only mappings:** {chapter_only_mappings}\n")
        md.write(f"- **Topic-level mappings:** {topic_level_mappings}\n")
        md.write(f"- **Review-required questions:** {summary['review_required']}\n")
        md.write(f"- **Out-of-current-syllabus questions:** {summary['out_of_current_syllabus']}\n")
        md.write(f"- **Boilerplate records:** {summary['boilerplate_records']}\n")
        md.write(f"- **Unclassifiable records:** {summary['unclassifiable_records']}\n")
        md.write(f"- **Average classification confidence:** {summary['average_confidence']:.3f}\n")

        md.write("\n## Mapping Counts by Class\n")
        for k, v in summary['mapping_counts_by_class'].items():
            md.write(f"- **Class {k}:** {v}\n")

        md.write("\n## Mapping Counts by Subject\n")
        for k, v in summary['mapping_counts_by_subject'].items():
            md.write(f"- **{k}:** {v}\n")

        md.write("\n## Top 10 Chapter Mappings\n")
        for k, v in list(summary['mapping_counts_by_chapter'].items())[:10]:
            md.write(f"- **{k}:** {v}\n")

        md.write("\n## Top 10 Topic Mappings\n")
        for k, v in list(summary['mapping_counts_by_topic'].items())[:10]:
            md.write(f"- **{k}:** {v}\n")

    log.info(f"Wrote markdown report to {SUMMARY_MD}")

    log.info("Classification complete.")
    print("\n=== CLASSIFICATION COMPLETE ===")
    for k, v in summary.items():
        if k not in ("failed_ids", "mapping_counts_by_class", "mapping_counts_by_subject", "mapping_counts_by_chapter", "mapping_counts_by_topic"):
            print(f"  {k:<35}: {v}")


if __name__ == "__main__":
    main()
