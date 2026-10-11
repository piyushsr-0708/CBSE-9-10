"""
fetch_cbse_syllabus.py
======================
Automatically discovers, downloads, and caches official CBSE 2026-27
curriculum PDF documents for subjects present in clean_question_bank.csv.

Source: https://cbseacademic.nic.in/curriculum_2027.html

Run:
    python scripts/fetch_cbse_syllabus.py

Output:
    data/raw/<filename>.pdf         — downloaded PDFs
    data/syllabus_sources.json      — provenance metadata
"""

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT        = Path(__file__).resolve().parent.parent
DATA_RAW    = ROOT / "data" / "raw"
DATA_RAW.mkdir(parents=True, exist_ok=True)
DATA_DIR    = ROOT / "data"
REPORTS_DIR = ROOT / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

SOURCES_FILE = DATA_DIR / "syllabus_sources.json"

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
ACADEMIC_YEAR    = "2026-27"
BASE_URL         = "https://cbseacademic.nic.in/"
CURRICULUM_PAGE  = f"{BASE_URL}curriculum_2027.html"

# Map CSV subject names → (CBSE_subject_name, class9_pdf_path, class10_pdf_path)
SUBJECT_PDF_MAP = {
    "maths": {
        "cbse_name": "Mathematics",
        "9": "web_material/CurriculumMain27/SecPart1/Maths_SecP1IX_2026-27.pdf",
        "10": "web_material/CurriculumMain27/SecPart1/Maths_SecP1X_2026-27.pdf",
    },
    "science": {
        "cbse_name": "Science",
        "9": "web_material/CurriculumMain27/SecPart1/ScienceSt_SecP1_2026-27.pdf",
        "10": "web_material/CurriculumMain27/SecPart1/Science_SecP1_2026-27.pdf",
    },
    "social_science": {
        "cbse_name": "Social Science",
        "9": "web_material/CurriculumMain27/SecPart1/SocialScience_SecP1IX_2026-27.pdf",
        "10": "web_material/CurriculumMain27/SecPart1/SocialScience_SecP1X_2026-27.pdf",
    },
    "computer_application": {
        "cbse_name": "Computer Applications",
        "9": "web_material/CurriculumMain27/SecPart1/Computer_Applications_SecP1IX_2026-27.pdf",
        "10": "web_material/CurriculumMain27/SecPart1/Computer_Applications_SecP1X_2026-27.pdf",
    },
    "home_science": {
        "cbse_name": "Home Science",
        "9": "web_material/CurriculumMain27/SecPart1/Home_Science_SecP1IX_2026-27.pdf",
        "10": "web_material/CurriculumMain27/SecPart1/Home_Science_SecP1X_2026-27.pdf",
    },
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}


# ---------------------------------------------------------------------------
# Helper: detect which subjects/classes are present in the CSV
# ---------------------------------------------------------------------------
def detect_required_subjects(csv_path: Path) -> dict:
    """
    Returns dict: { csv_subject: set_of_classes }
    e.g. { "maths": {"9", "10"}, "science": {"9", "10"}, ... }
    """
    import csv
    required: dict = {}
    with open(csv_path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            subj  = str(row.get("subject", "")).strip().lower()
            cls   = str(row.get("class", "")).strip().lower()
            cls_n = cls.replace("class", "").strip()   # "class9" -> "9"
            if subj and cls_n:
                required.setdefault(subj, set()).add(cls_n)
    return required


# ---------------------------------------------------------------------------
# Helper: download a file
# ---------------------------------------------------------------------------
def download_pdf(url: str, dest: Path, retries: int = 3) -> bool:
    """Download url → dest. Returns True on success."""
    if dest.exists() and dest.stat().st_size > 1024:
        print(f"  [CACHED] {dest.name}")
        return True

    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=60, stream=True)
            if resp.status_code == 200:
                with open(dest, "wb") as fh:
                    for chunk in resp.iter_content(chunk_size=8192):
                        fh.write(chunk)
                size_kb = dest.stat().st_size // 1024
                print(f"  [OK] {dest.name}  ({size_kb} KB)")
                return True
            else:
                print(f"  [HTTP {resp.status_code}] attempt {attempt}: {url}")
        except requests.RequestException as exc:
            print(f"  [ERROR] attempt {attempt}: {exc}")
        time.sleep(2 ** attempt)

    print(f"  [FAILED] {url}")
    return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    csv_path = ROOT / "clean_question_bank.csv"
    if not csv_path.exists():
        print(f"ERROR: {csv_path} not found", file=sys.stderr)
        sys.exit(1)

    print("=== Step 1: Detect required subjects from CSV ===")
    required = detect_required_subjects(csv_path)
    print(f"  CSV subjects  : {list(required.keys())}")
    for s, classes in required.items():
        print(f"    {s}: classes {sorted(classes)}")

    # Validate all CSV subjects are in our map
    unknown_subjects = [s for s in required if s not in SUBJECT_PDF_MAP]
    if unknown_subjects:
        print(f"\nWARNING: No PDF mapping for subjects: {unknown_subjects}")
        print("  These subjects will be skipped — manual intervention required.")

    print(f"\n=== Step 2: Download PDFs from {CURRICULUM_PAGE} ===")
    sources = []
    failed  = []

    for csv_subj, classes in required.items():
        if csv_subj not in SUBJECT_PDF_MAP:
            failed.append({"subject": csv_subj, "reason": "no_pdf_mapping_defined"})
            continue

        pdf_info = SUBJECT_PDF_MAP[csv_subj]

        for cls in sorted(classes):
            if cls not in pdf_info:
                failed.append({
                    "subject": csv_subj,
                    "class": cls,
                    "reason": f"no_pdf_path_for_class_{cls}",
                })
                print(f"  [MISSING] No PDF path defined for {csv_subj} class {cls}")
                continue

            rel_path    = pdf_info[cls]
            doc_url     = BASE_URL + rel_path
            filename    = f"cbse_class{cls}_{csv_subj}_2026_27.pdf"
            local_file  = DATA_RAW / filename
            retrieved   = datetime.now(timezone.utc).isoformat()

            ok = download_pdf(doc_url, local_file)

            entry = {
                "source_name": "CBSE Academic",
                "source_url": CURRICULUM_PAGE,
                "document_url": doc_url,
                "document_title": (
                    f"CBSE 2026-27 Secondary Curriculum - "
                    f"Class {cls} {pdf_info['cbse_name']}"
                ),
                "academic_year": ACADEMIC_YEAR,
                "class": cls,
                "subject_csv": csv_subj,
                "subject_cbse": pdf_info["cbse_name"],
                "retrieved_at": retrieved,
                "local_file": str(local_file),
                "download_status": "success" if ok else "failed",
            }
            sources.append(entry)

            if not ok:
                failed.append({
                    "subject": csv_subj,
                    "class": cls,
                    "document_url": doc_url,
                    "reason": "download_failed",
                })

    # -----------------------------------------------------------------------
    # Save provenance
    # -----------------------------------------------------------------------
    provenance = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "academic_year": ACADEMIC_YEAR,
        "curriculum_discovery_url": CURRICULUM_PAGE,
        "documents": sources,
        "failed": failed,
    }
    with open(SOURCES_FILE, "w", encoding="utf-8") as fh:
        json.dump(provenance, fh, indent=2, ensure_ascii=False)
    print(f"\nProvenance saved: {SOURCES_FILE}")

    # Summary
    ok_count   = sum(1 for s in sources if s["download_status"] == "success")
    fail_count = len(sources) - ok_count + len(
        [f for f in failed if "download_status" not in f]
    )
    print(f"\n=== Summary ===")
    print(f"  Documents attempted : {len(sources)}")
    print(f"  Successful          : {ok_count}")
    print(f"  Failed              : {len(failed)}")

    if failed:
        print("\n=== FAILURES (require manual intervention) ===")
        for f in failed:
            print(f"  {f}")

    if failed:
        sys.exit(2)


if __name__ == "__main__":
    main()
