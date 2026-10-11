"""
hybrid_classify_questions.py
============================
Hybrid local-first syllabus mapping pipeline for CBSE questions.

Stage 1: Local candidate generation using TF-IDF and keyword matching.
Stage 2: Automatic high-confidence classification.
Stage 3: Gemini for ambiguous cases only (if needed).
"""
import io, sys, os, json, re, time, argparse, logging
from pathlib import Path
from collections import defaultdict, Counter
from typing import Optional, List, Dict, Any, Tuple

import pandas as pd
from pydantic import BaseModel, Field, ValidationError
from dotenv import load_dotenv
from google import genai
from google.genai import types as genai_types

# Set UTF-8
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
else:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

load_dotenv()
log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")

# ---------------------------------------------------------------------------
# Setup & Config
# ---------------------------------------------------------------------------
ROOT            = Path(__file__).resolve().parent.parent
DATA_SYLLABUS   = ROOT / "data" / "syllabus"
DATA_PROCESSED  = ROOT / "data" / "processed"
OUTPUT_DIR      = ROOT / "output"
REPORTS_DIR     = ROOT / "reports"
QBANK_CSV       = ROOT / "clean_question_bank.csv"
CHECKPOINT_FILE = DATA_PROCESSED / "hybrid_classification_results.jsonl"
FINAL_CSV       = OUTPUT_DIR / "classified_question_bank.csv"
REVIEW_CSV      = OUTPUT_DIR / "review_queue.csv"
SUMMARY_MD      = REPORTS_DIR / "question_mapping_summary.md"
SUMMARY_JSON    = REPORTS_DIR / "question_mapping_summary.json"
EVAL_MD         = REPORTS_DIR / "local_mapping_evaluation.md"

for d in [DATA_PROCESSED, OUTPUT_DIR, REPORTS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# Try to load local TF-IDF matcher
try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False
    log.warning("scikit-learn is not installed. Local matching will fall back to simple keyword intersection.")

AUTO_VERIFY_THRESHOLD  = 0.45  # Confident topic-level
CHAPTER_ONLY_THRESHOLD = 0.25  # Confident chapter-level
REVIEW_THRESHOLD       = 0.05  # Below this, completely unclassifiable

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
class ClassificationResult(BaseModel):
    unit_id:               Optional[str]  = Field(None)
    chapter_id:            str            = Field(...)
    topic_id:              Optional[str]  = Field(None)
    subtopic_id:           Optional[str]  = Field(None)
    learning_outcome_id:   Optional[str]  = Field(None)
    difficulty:            str            = Field("unknown")
    confidence:            float          = Field(0.0)
    classification_reason: str            = Field("")
    alternative_candidates: List[str]     = Field(default_factory=list)
    requires_visual_context: bool         = Field(False)
    syllabus_eligibility:  str            = Field("CURRENT_SYLLABUS")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def normalise_class(raw: str) -> str:
    return re.sub(r"\D", "", str(raw))

def normalise_subject(raw: str) -> str:
    return str(raw).lower().strip()

def normalize_text(text: str) -> str:
    if not isinstance(text, str):
        return ""
    text = text.lower()
    text = re.sub(r"[^\w\s\.]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text

def build_canonical_map(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["question_id"] = [f"Q_{i:04d}" for i in range(len(df))]
    df["_norm_text"] = df["question_text"].fillna("").str.lower().str.replace(r"\s+", " ", regex=True).str.strip()
    first_occ = df.groupby("_norm_text")["question_id"].first().to_dict()
    df["canonical_question_id"] = df["_norm_text"].map(first_occ).str.replace("Q_", "CQ_", regex=False)
    df.drop(columns=["_norm_text"], inplace=True)
    return df

def load_syllabuses() -> Dict:
    syllabuses = {}
    for f in DATA_SYLLABUS.glob("*.json"):
        if f.is_file():
            try:
                with open(f, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                key = (normalise_class(data["class"]), normalise_subject(data["subject"]))
                syllabuses[key] = data
            except Exception as e:
                log.warning(f"Could not load {f}: {e}")
    return syllabuses

def load_checkpoints() -> Dict[str, dict]:
    checkpoints = {}
    if CHECKPOINT_FILE.exists():
        with open(CHECKPOINT_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        rec = json.loads(line)
                        cqid = rec.get("canonical_question_id")
                        if cqid:
                            checkpoints[cqid] = rec
                    except: pass
    return checkpoints

# ---------------------------------------------------------------------------
# Stage 1: Local Matcher
# ---------------------------------------------------------------------------
class LocalMatcher:
    def __init__(self, syllabuses: Dict):
        self.syllabuses = syllabuses
        self.corpora = {}        # (class, subj) -> list of texts
        self.node_maps = {}      # (class, subj) -> list of node info
        self.vectorizers = {}
        self.tfidf_matrices = {}
        self.build_search_index()

    def build_search_index(self):
        log.info("Building local syllabus representations...")
        for key, syllabus in self.syllabuses.items():
            corpus = []
            nodes = []
            
            # Recursive extraction
            def walk(level_nodes, path_text="", unit_id=None, chapter_id=None, topic_id=None, subtopic_id=None):
                for n in level_nodes:
                    n_type = n.get("type", "").lower()
                    n_id = n.get("id", "")
                    n_name = n.get("name", "")
                    n_desc = n.get("description", "")
                    
                    cur_unit = n_id if n_type == "unit" else unit_id
                    cur_chap = n_id if n_type in ("chapter", "theme") else chapter_id
                    cur_top  = n_id if n_type == "topic" else topic_id
                    cur_sub  = n_id if n_type == "subtopic" else subtopic_id
                    
                    text_repr = f"{path_text} {n_name} {n_desc}".strip()
                    
                    if n_id and n_type in ("chapter", "theme", "topic", "subtopic", "learning_outcome"):
                        norm_text = normalize_text(text_repr)
                        corpus.append(norm_text)
                        nodes.append({
                            "type": n_type,
                            "id": n_id,
                            "name": n_name,
                            "unit_id": cur_unit,
                            "chapter_id": cur_chap,
                            "topic_id": cur_top,
                            "subtopic_id": cur_sub,
                            "learning_outcome_id": n_id if n_type == "learning_outcome" else None,
                            "text": norm_text
                        })
                    
                    walk(n.get("children", []) or [], text_repr, cur_unit, cur_chap, cur_top, cur_sub)

            walk(syllabus.get("curriculum", []))
            
            self.corpora[key] = corpus
            self.node_maps[key] = nodes
            
            if SKLEARN_AVAILABLE and corpus:
                vec = TfidfVectorizer(stop_words='english', ngram_range=(1, 2))
                try:
                    mat = vec.fit_transform(corpus)
                    self.vectorizers[key] = vec
                    self.tfidf_matrices[key] = mat
                except Exception as e:
                    log.warning(f"TFIDF failing for {key}: {e}")

    def search(self, cls: str, subj: str, query: str, top_k: int = 5) -> List[Tuple[float, dict]]:
        key = (normalise_class(cls), normalise_subject(subj))
        if key not in self.node_maps or not query.strip():
            return []
            
        q_norm = normalize_text(query)
        
        if SKLEARN_AVAILABLE and key in self.vectorizers:
            vec = self.vectorizers[key]
            mat = self.tfidf_matrices[key]
            q_vec = vec.transform([q_norm])
            sim = cosine_similarity(q_vec, mat).flatten()
            
            results = []
            for idx in sim.argsort()[::-1][:top_k]:
                score = sim[idx]
                if score > 0.01:
                    results.append((float(score), self.node_maps[key][idx]))
            return results
        else:
            # Fallback simple keyword match
            q_tokens = set(q_norm.split())
            if not q_tokens: return []
            scores = []
            for n in self.node_maps[key]:
                n_tokens = set(n["text"].split())
                inter = len(q_tokens.intersection(n_tokens))
                union = len(q_tokens.union(n_tokens))
                jaccard = inter / union if union else 0.0
                scores.append((jaccard, n))
            scores.sort(key=lambda x: x[0], reverse=True)
            return [s for s in scores[:top_k] if s[0] > 0.01]

# ---------------------------------------------------------------------------
# Out-of-syllabus hardcoding (Hitler/Nazism in Class 9 SST)
# ---------------------------------------------------------------------------
def check_out_of_syllabus_heuristics(cls_raw: str, subj_raw: str, text: str) -> bool:
    """Returns True if question is known out-of-syllabus."""
    cls_num = normalise_class(cls_raw)
    subj = normalise_subject(subj_raw)
    t = text.lower()
    
    if cls_num == "9" and subj in ("social_science", "social science", "sst"):
        # Hitler, Nazism, Weimar Republic
        if any(w in t for w in ["hitler", "nazism", "nazi", "weimar"]):
            return True
    return False

# ---------------------------------------------------------------------------
# API Ambiguous Resolution (Gemini)
# ---------------------------------------------------------------------------
PROMPT_TEMPLATE = """\
You are an expert CBSE 2026-27 classifier.
Select the BEST syllabus mapping for this question from the provided CANDIDATES ONLY.

=== QUESTION ===
Class: {cls}
Subject: {subject}
Text:
{text}

=== LOCAL CANDIDATES ===
{candidates}

=== RULES ===
1. Return purely JSON conforming to the schema.
2. Only use IDs from the candidates list.
3. If no candidate fits, but it's a valid question, mark "REVIEW_REQUIRED".
4. If it's an old syllabus topic (e.g. absent from current CBSE), mark syllabus_eligibility="OUT_OF_CURRENT_SYLLABUS".
5. If text is junk/boilerplate, syllabus_eligibility="BOILERPLATE".
6. If chapter_id is unknown, output "UNCLASSIFIABLE".

Return JSON:
{{
  "chapter_id": "<valid_chapter_id_or_UNCLASSIFIABLE>",
  "topic_id": null,
  "confidence": 0.0-1.0,
  "classification_reason": "...",
  "syllabus_eligibility": "CURRENT_SYLLABUS|OUT_OF_CURRENT_SYLLABUS|BOILERPLATE|UNCLASSIFIABLE|INCOMPLETE"
}}
"""

API_AVAILABLE = True
CONSECUTIVE_API_ERRORS = 0

def call_gemini_for_ambiguous(client: genai.Client, model_name: str, row: pd.Series, candidates: List[tuple]) -> dict:
    global API_AVAILABLE, CONSECUTIVE_API_ERRORS
    if not API_AVAILABLE:
        return {}
    cand_strs = []
    valid_ids = set(["UNCLASSIFIABLE"])
    for sc, cand in candidates:
        valid_ids.add(cand.get("chapter_id"))
        valid_ids.add(cand.get("topic_id"))
        cand_strs.append(f"- Score {sc:.2f}: Chapter [{cand.get('chapter_id')}], Topic [{cand.get('topic_id')}], Name: {cand.get('name')}")
    
    prompt = PROMPT_TEMPLATE.format(
        cls=row["class"],
        subject=row["subject"],
        text=str(row["question_text"]).strip(),
        candidates="\n".join(cand_strs)
    )
    
    delay = 2.0
    for attempt in range(4):
        try:
            resp = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=genai_types.GenerateContentConfig(temperature=0.0, response_mime_type="application/json")
            )
            data = json.loads(resp.text)
            
            cid = data.get("chapter_id", "UNCLASSIFIABLE")
            if cid not in valid_ids and cid != "UNCLASSIFIABLE":
                cid = "UNCLASSIFIABLE"
                
            return {
                "chapter_id": cid,
                "topic_id": data.get("topic_id"),
                "confidence": min(float(data.get("confidence", 0.5)), 0.85), # max out at review if from gemini ambiguous
                "classification_reason": data.get("classification_reason", "Gemini resolved"),
                "syllabus_eligibility": data.get("syllabus_eligibility", "CURRENT_SYLLABUS")
            }
        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "503" in err_str or "quota" in err_str.lower():
                CONSECUTIVE_API_ERRORS += 1
                if CONSECUTIVE_API_ERRORS >= 3:
                    log.error("API quota exhausted or unavailable. Disabling Gemini calls.")
                    API_AVAILABLE = False
                    return {}
                time.sleep(delay)
                delay *= 2
            else:
                return {}
    return {}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    api_key = os.environ.get("GEMINI_API_KEY", "")
    client = genai.Client(api_key=api_key) if api_key else None
    
    syllabuses = load_syllabuses()
    matcher = LocalMatcher(syllabuses)
    
    df = pd.read_csv(QBANK_CSV, dtype=str)
    df = build_canonical_map(df)
    canonical_df = df.drop_duplicates(subset=["canonical_question_id"]).copy()
    
    checkpoints = load_checkpoints()
    
    results = []
    checkpoint_fh = open(CHECKPOINT_FILE, "a", encoding="utf-8")
    
    stats = {
        "local_auto": 0,
        "local_chapter_only": 0,
        "sent_to_gemini": 0,
        "resolved_by_gemini": 0,
        "review_required": 0,
        "out_of_syllabus": 0,
        "unclassifiable": 0,
        "boilerplate": 0
    }
    
    for i, (_, row) in enumerate(canonical_df.iterrows(), 1):
        cqid = row["canonical_question_id"]
        if cqid in checkpoints:
            res = checkpoints[cqid]
            results.append(res)
            # tally stats based on res["classification_status"] and reason
            if res.get("syllabus_eligibility") == "OUT_OF_CURRENT_SYLLABUS":
                stats["out_of_syllabus"] += 1
            elif res.get("syllabus_eligibility") in ("BOILERPLATE", "INCOMPLETE"):
                stats["boilerplate"] += 1
            elif res.get("classification_status") == "auto_verified":
                stats["local_auto"] += 1
            elif res.get("classification_status") == "chapter_only":
                stats["local_chapter_only"] += 1
            elif res.get("classification_status") == "review_required":
                if "Gemini" in res.get("classification_reason", ""):
                    stats["resolved_by_gemini"] += 1
                else:
                    stats["review_required"] += 1
            else:
                stats["unclassifiable"] += 1
            continue

        qtext = str(row["question_text"]).strip()
        cls_raw = row["class"]
        subj = row["subject"]
        
        # 1. Heuristic out-of-syllabus
        if check_out_of_syllabus_heuristics(cls_raw, subj, qtext):
            rec = {
                "canonical_question_id": cqid,
                "chapter_id": "UNCLASSIFIABLE",
                "classification_status": "out_of_syllabus",
                "classification_reason": "Heuristic trigger (known legacy topic).",
                "syllabus_eligibility": "OUT_OF_CURRENT_SYLLABUS",
                "confidence": 1.0,
            }
            stats["out_of_syllabus"] += 1
            results.append(rec)
            checkpoint_fh.write(json.dumps(rec)+"\n")
            continue
            
        # 2. Heuristic Boilerplate
        if len(qtext.split()) < 3 or "all questions are compulsory" in qtext.lower():
            rec = {
                "canonical_question_id": cqid,
                "chapter_id": "UNCLASSIFIABLE",
                "classification_status": "boilerplate",
                "classification_reason": "Administrative instructions or too short.",
                "syllabus_eligibility": "BOILERPLATE",
                "confidence": 1.0,
            }
            stats["boilerplate"] += 1
            results.append(rec)
            checkpoint_fh.write(json.dumps(rec)+"\n")
            continue

        # 3. Local Search
        cands = matcher.search(cls_raw, subj, qtext, top_k=5)
        
        base_rec = {
            "canonical_question_id": cqid,
            "unit_id": None, "chapter_id": "UNCLASSIFIABLE", "topic_id": None, "subtopic_id": None,
            "classification_status": "unclassifiable",
            "confidence": 0.0,
            "syllabus_eligibility": "UNCLASSIFIABLE",
            "classification_reason": "No local candidates found."
        }

        if not cands:
            stats["unclassifiable"] += 1
            results.append(base_rec)
            checkpoint_fh.write(json.dumps(base_rec)+"\n")
            continue
            
        top_score, top_node = cands[0]
        
        # Hydrate base_rec with top node
        ch_id = top_node.get("chapter_id")
        if not ch_id:
            ch_id = "UNCLASSIFIABLE"
            
        base_rec.update({
            "unit_id": top_node.get("unit_id"),
            "chapter_id": ch_id,
            "topic_id": top_node.get("topic_id"),
            "subtopic_id": top_node.get("subtopic_id"),
            "syllabus_eligibility": "CURRENT_SYLLABUS",
            "confidence": top_score
        })
        
        # 4. Automatic Classification Thresholds
        if top_score >= AUTO_VERIFY_THRESHOLD:
            base_rec["classification_status"] = "auto_verified"
            base_rec["classification_reason"] = f"Local TF-IDF matched strongly (score: {top_score:.3f})"
            stats["local_auto"] += 1
        elif top_score >= CHAPTER_ONLY_THRESHOLD:
            base_rec["classification_status"] = "chapter_only"
            base_rec["topic_id"] = None # drop topic, retain chapter
            base_rec["subtopic_id"] = None
            base_rec["classification_reason"] = f"Local TF-IDF matched chapter (score: {top_score:.3f})"
            stats["local_chapter_only"] += 1
        else:
            # 5. Gemini Ambiguous Resolution
            if client and len(cands) > 0:
                stats["sent_to_gemini"] += 1
                gemini_res = call_gemini_for_ambiguous(client, "gemini-3.1-flash-lite", row, cands)
                
                if gemini_res:
                    stats["resolved_by_gemini"] += 1
                    base_rec["chapter_id"] = gemini_res.get("chapter_id", ch_id)
                    base_rec["topic_id"] = gemini_res.get("topic_id")
                    base_rec["confidence"] = gemini_res.get("confidence", top_score)
                    base_rec["classification_reason"] = f"Gemini ambiguous resolution. {gemini_res.get('classification_reason', '')}"
                    base_rec["syllabus_eligibility"] = gemini_res.get("syllabus_eligibility", "CURRENT_SYLLABUS")
                    base_rec["classification_status"] = "review_required"
                else:
                    # Gemini failed, keep local weak match as review_required
                    stats["review_required"] += 1
                    base_rec["classification_status"] = "review_required"
                    base_rec["classification_reason"] = f"Weak local match (score: {top_score:.3f}), Gemini failed."
            else:
                stats["review_required"] += 1
                base_rec["classification_status"] = "review_required"
                base_rec["classification_reason"] = f"Weak local match (score: {top_score:.3f}), Gemini bypass."
                
        results.append(base_rec)
        checkpoint_fh.write(json.dumps(base_rec)+"\n")
        checkpoint_fh.flush()

        if i % 100 == 0:
            log.info(f"Processed {i}/{len(canonical_df)}")

    checkpoint_fh.close()
    
    # ---- Merge and Save ----
    clf_lookup = {r["canonical_question_id"]: r for r in results}
    for col in ["unit_id", "chapter_id", "topic_id", "subtopic_id", "difficulty", "confidence", "classification_status", "classification_reason", "syllabus_eligibility"]:
        df[col] = df["canonical_question_id"].map(lambda c, c2=col: clf_lookup.get(c, {}).get(c2))
        
    df.to_csv(FINAL_CSV, index=False, encoding="utf-8")
    
    review_mask = df["classification_status"].isin(["review_required", "unclassifiable"]) | df["syllabus_eligibility"].isin(["OUT_OF_CURRENT_SYLLABUS", "BOILERPLATE", "UNCLASSIFIABLE"])
    df[review_mask].to_csv(REVIEW_CSV, index=False, encoding="utf-8")

    # ---- Validation ----
    log.info(f"Integrity check: Original rows: {len(df)} == 1795? {len(df) == 1795}")
    log.info(f"Integrity check: Canonical unique: {len(df['canonical_question_id'].unique())} == 1726? {len(df['canonical_question_id'].unique()) == 1726}")
    
    # ---- Eval Report ----
    with open(EVAL_MD, "w", encoding="utf-8") as f:
        f.write("# Local Mapping Evaluation\n\n")
        f.write(f"- total canonical: {len(canonical_df)}\n")
        f.write(f"- local auto_verified: {stats['local_auto']}\n")
        f.write(f"- local chapter_only: {stats['local_chapter_only']}\n")
        f.write(f"- sent to Gemini: {stats['sent_to_gemini']}\n")
        f.write(f"- resolved by Gemini (kept as review_required): {stats['resolved_by_gemini']}\n")
        f.write(f"- local review_required: {stats['review_required']}\n")
        f.write(f"- out of syllabus (heuristic + gemini): {stats['out_of_syllabus']}\n")
        f.write(f"- boilerplate: {stats['boilerplate']}\n")
        f.write(f"- genuinely unclassifiable: {stats['unclassifiable']}\n")

    # ---- Summary Markdown ----
    with open(SUMMARY_MD, "w", encoding="utf-8") as f:
        f.write("# Question Mapping Summary (Hybrid Engine)\n\n")
        f.write(f"- **Total original questions:** {len(df)}\n")
        f.write(f"- **Total canonical questions:** {len(canonical_df)}\n\n")
        
        cur_mask = df["syllabus_eligibility"] == "CURRENT_SYLLABUS"
        success = int(cur_mask.sum())
        ch_only = int((cur_mask & df["topic_id"].isna()).sum())
        top_only = int((cur_mask & df["topic_id"].notna()).sum())
        
        f.write(f"- **Successfully mapped:** {success}\n")
        f.write(f"- **Chapter-only mappings:** {ch_only}\n")
        f.write(f"- **Topic-level mappings:** {top_only}\n")
        f.write(f"- **Review-required questions:** {int((df['classification_status'] == 'review_required').sum())}\n")
        f.write(f"- **Out-of-current-syllabus:** {int((df['syllabus_eligibility'] == 'OUT_OF_CURRENT_SYLLABUS').sum())}\n")
        f.write(f"- **Boilerplate records:** {int((df['syllabus_eligibility'] == 'BOILERPLATE').sum())}\n")
        f.write(f"- **Unclassifiable records:** {int((df['classification_status'] == 'unclassifiable').sum())}\n")
        avg_cnf = pd.to_numeric(df["confidence"], errors="coerce").mean()
        f.write(f"- **Average classification confidence:** {avg_cnf:.3f}\n")
        
    with open(SUMMARY_JSON, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2)
        
    print("Hybrid Classification Completed.")
    print(f"Check {EVAL_MD} and {SUMMARY_MD} for reports.")

if __name__ == "__main__":
    main()
