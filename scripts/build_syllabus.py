"""
build_syllabus.py (v4 - table-aware hierarchical parser)
=========================================================
Architecture
------------
CBSE 2026-27 curriculum PDFs are structured as multi-column tables:

  Maths:
    Col 0: Chapter Name  (may contain merged UNIT header rows)
    Col 1: Key Concepts  (bullet points for topics)
    Col 2: Relevant CGs
    Col 3: Competencies

  Social Science:
    Col 0: S. No.
    Col 1: Theme (Chapter) + time allocation
    Col 2: Outline/Concepts
    Col 3: Learning Outcomes

Parser strategy
---------------
1. extract_tables() from pdfplumber gives us clean column-separated rows.
2. Identify UNIT/PART boundary rows (single value spanning all cols, matching
   a known regex).
3. Ignore table header rows (S. No., allocation in, Theme, Chapter Name …).
4. Map chapter name -> key concepts as the primary hierarchy.
5. Fall back to text-line parsing only for subjects without clear tables.

Run:
    python scripts/build_syllabus.py              # only Class 9 Maths + SST
    python scripts/build_syllabus.py --all         # all subjects
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import pdfplumber

ROOT = Path(__file__).resolve().parent.parent
DATA_RAW = ROOT / "data" / "raw"
DATA_SYLLABUS = ROOT / "data" / "syllabus"
DATA_SYLLABUS.mkdir(parents=True, exist_ok=True)
BACKUP_DIR = DATA_SYLLABUS / "backup"
BACKUP_DIR.mkdir(parents=True, exist_ok=True)
REPORTS_DIR = ROOT / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

SOURCES_FILE = ROOT / "data" / "syllabus_sources.json"
AUDIT_FILE = REPORTS_DIR / "syllabus_taxonomy_validation.md"

ACADEMIC_YEAR = "2026-27"
BOARD = "CBSE"

SUBJECT_CODE = {
    "maths": "MATH",
    "science": "SCI",
    "social_science": "SST",
    "computer_application": "CA",
    "home_science": "HS",
}

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def clean_text(text: str) -> str:
    """Collapse whitespace and strip."""
    if not text:
        return ""
    return re.sub(r"\s+", " ", str(text)).strip()


def is_unit_header(text: str) -> re.Match | None:
    """
    Detect strings like:
      "UNIT II: ALGEBRA No. of periods : 66"
      "Unit 1: Number System No. of periods : 12"
    Returns a match object with groups (numeral, name) or None.
    """
    return re.match(
        r"^(?:UNIT|Unit)\s+([IVXivx0-9]+)\s*[:\-]\s*(.+?)(?:\s*No\.\s*of\s*[Pp]eriods\s*:?\s*\d+)?$",
        clean_text(text),
        flags=re.IGNORECASE
    )


def is_part_header(text: str) -> re.Match | None:
    """Detect 'Part 1', 'Part 2', 'PART I' etc."""
    return re.match(r"^(?:Part|PART)\s+([0-9IVXivx]+)(?:\s*[:\-]\s*(.+))?$",
                    clean_text(text))


# Table header cell patterns to skip
_TABLE_HEADER_PATTERNS = [
    r"^S\.\s*No\.?$",
    r"^Theme\b",
    r"^allocation",
    r"^instructional",
    r"^hours?\)",
    r"^Outline[/\\]?Concepts",
    r"^Learning\s+Out",
    r"^Competencies",
    r"^Students\s+will\s+be",
    r"^Chapter\s+Name",
    r"^Key\s+Concepts",
    r"^Releva",
    r"^nt\s+CGs?$",
    r"^Relevant\s+CGs?",
    r"^Units?\s+Unit\s+Name",
    r"^Unit\s+Name",
    r"^Units?$",
    r"^\(approx\.\)",
    r"^None$",
    r"^Total\s*\d*$",
    r"^TOTAL",
    r"^Marks$",
    r"^Description$",
    r"^Weightage",
]

# Internal Assessment / administrative node names that are NOT academic content
_INTERNAL_ASSESSMENT_PATTERNS = [
    r"Pen\s*Paper\s*Test",
    r"Multiple\s*Assessment",
    r"Portfolio",
    r"Lab\s*Practical",
    r"Lab\s*activities",
    r"Project\s*work",
    r"Interdisciplinary\s*project",
    r"Quiz.*debate",
    r"debate.*role\s*play",
    r"self.?assessment",
    r"peer\s*assessment",
    r"Map\s*Work",
    r"internal\s*assessment",
    r"NCERT$",
    r"Social\s*Science.Part\s*[12]",
    r"^Marks$",
    r"^allocation$",
    r"Classroom.*work\s*done",
    r"Heritage\s*India\s*quiz",
    r"activities.*assignments\)\s*reflections",
]

_IA_RE = re.compile("|".join(_INTERNAL_ASSESSMENT_PATTERNS), re.IGNORECASE)


def is_internal_assessment_node(text: str) -> bool:
    """Return True if the text represents administrative/IA content, not academic."""
    return bool(_IA_RE.search(clean_text(text or "")))

_TABLE_HEADER_RE = re.compile(
    "|".join(_TABLE_HEADER_PATTERNS), re.IGNORECASE
)


def is_table_header_cell(text: str) -> bool:
    return bool(_TABLE_HEADER_RE.match(clean_text(text or "")))


# Summary table row: Roman numeral + chapter names + marks (two-digit number)
_SUMMARY_ROW_RE = re.compile(
    r"^(?:I{1,3}|IV|V|VI|VII|VIII|IX|X)\s+.+\d{1,2}$"
)

def is_summary_row(text: str) -> bool:
    return bool(_SUMMARY_ROW_RE.match(clean_text(text or "")))


def is_noise_text(text: str) -> bool:
    """Lines that should never become nodes."""
    t = clean_text(text or "")
    if not t:
        return True
    if t.isdigit():                    # page numbers
        return True
    if re.match(r"^\d+$", t):
        return True
    # Standalone structural markers that are table metadata, not syllabus nodes
    if t in {"Units", "Unit Name", "Chapter Name", "S. No.", "Marks", "Total",
             "None", "Geometry", "Probability", "Algebra", "Mensuration",
             "Number System", "Statistics"}:
        # Only skip bare standalone column-header words when they appear
        # isolated (these are legitimate chapter names ONLY when inside a unit)
        # handled by context check below at parse time
        pass
    for pat in [
        r"^COURSE\s+(STRUCTURE|OUTLINE)",
        r"^CLASS\s*[–\-]\s*IX",
        r"^CLASS\s*[–\-]\s*X\b",
        r"^INTERNAL\s+ASSESSMENT",
        r"^QUESTION\s+PAPER\s+DESIGN",
        r"^Subject\s+Code",
        r"^Part\s+[12]$",           # standalone "Part 1" / "Part 2"
        r"^Units?$",                # bare 'Units' from summary table header
        r"^Unit\s+Name$",
    ]:
        if re.search(pat, t, re.IGNORECASE):
            return True
    return False


def normalise_chapter_name(name: str) -> str:
    """Remove line-wrap artefacts from chapter names.

    pdfplumber may insert an erroneous space inside a word when a table cell
    wraps across rows:
      'Understandin g'  → 'Understanding'
      'Quadrilater als' → 'Quadrilaterals'
      'Authorit y'      → 'Authority'
      'Progression s'   → 'Progressions'

    Strategy: merge only when the right fragment is 1–3 lowercase chars AND
    is NOT a valid standalone English word (on, of, in, to, …).
    We do NOT attempt to split merged words — that causes regressions.
    """
    _STANDALONE = {
        "a", "an", "as", "at", "be", "by", "do", "go", "he", "if", "in",
        "is", "it", "me", "my", "no", "of", "on", "or", "so", "to", "up",
        "us", "we", "and", "are", "but", "can", "did", "for", "get", "had",
        "has", "him", "his", "how", "its", "let", "may", "not", "now", "our",
        "out", "put", "say", "see", "she", "the", "too", "two", "use", "was",
        "way", "who", "why", "yet", "you",
    }

    def _maybe_merge(m: re.Match) -> str:
        left, right = m.group(1), m.group(2)
        if right.lower() in _STANDALONE:
            return m.group(0)   # keep the space — valid word boundary
        return left + right

    # Pattern: ≥3 lowercase chars, a space, then 1–3 lowercase chars at word boundary
    fixed = re.sub(r"([a-z]{3,}) ([a-z]{1,3})\b", _maybe_merge, name)

    return clean_text(fixed)



def extract_bullet_texts(cell_text: str) -> list[str]:
    """
    Given a concatenated cell string like
      ' Introduction to polynomials  Degree of a polynomial  ...'
    split on bullet characters and return individual, clean topic strings.
    """
    if not cell_text:
        return []
    # Split on bullets U+2022, U+25CF, U+25E6, U+2023, or literal •
    parts = re.split(r"[\u2022\u25cf\u25e6\u2023•]", cell_text)
    results = []
    for p in parts:
        p = clean_text(p)
        # Skip very short fragments and known noise
        if not p or len(p) < 4:
            continue
        # Skip CG references like 'CG-1, C-1.1, CG-9'
        if re.match(r"^(?:CG|C)-[\d\.]+", p):
            continue
        # Skip 'The student will be able to:' and similar lead-ins
        if re.search(r"student\s+will\s+be\s+able", p, re.IGNORECASE):
            continue
        # Skip Bloom's taxonomy level labels that appear in assessment columns
        if re.match(r"^(?:Remembering|Understanding|Applying|Analysing|Evaluating|Creating):", p):
            continue
        results.append(p)
    return results


# ---------------------------------------------------------------------------
# Table-aware parser (primary)
# ---------------------------------------------------------------------------

def parse_via_tables(pdf_path: Path, subject_type: str = "maths") -> tuple[list, str]:
    """
    Parse a CBSE PDF using pdfplumber's table extraction.

    Returns (hierarchy, extraction_method_string).

    hierarchy is a list of unit nodes:
      {id, name, type:'unit', source_document, source_pages, children:[
        {id, name, type:'chapter', source_document, source_pages, children:[
          {id, name, type:'topic', source_document, source_pages}
        ]}
      ]}
    """
    hierarchy: list[dict] = []
    current_unit: dict | None = None
    current_chapter: dict | None = None

    def new_unit(name: str, page: int) -> dict:
        return {
            "id": "dummy",
            "name": name,
            "type": "unit",
            "source_document": pdf_path.name,
            "source_pages": [page],
            "children": [],
        }

    def new_chapter(name: str, page: int) -> dict:
        return {
            "id": "dummy",
            "name": name,
            "type": "chapter",
            "source_document": pdf_path.name,
            "source_pages": [page],
            "children": [],
        }

    def new_topic(name: str, page: int) -> dict:
        return {
            "id": "dummy",
            "name": name,
            "type": "topic",
            "source_document": pdf_path.name,
            "source_pages": [page],
        }

    def add_chapter(ch: dict) -> None:
        nonlocal current_chapter
        if current_unit is not None:
            # Deduplicate adjacent identical names (wrapped text artefact)
            if not current_unit["children"] or current_unit["children"][-1]["name"] != ch["name"]:
                current_unit["children"].append(ch)
                current_chapter = ch
        else:
            if not hierarchy or hierarchy[-1].get("type") != "chapter" or hierarchy[-1]["name"] != ch["name"]:
                hierarchy.append(ch)
                current_chapter = ch

    def set_unit(name: str, page: int) -> None:
        nonlocal current_unit, current_chapter
        # Update source_pages if unit already exists (continuation across pages)
        for u in hierarchy:
            if u["type"] == "unit" and u["name"] == name:
                if page not in u["source_pages"]:
                    u["source_pages"].append(page)
                current_unit = u
                current_chapter = None
                return
        u = new_unit(name, page)
        hierarchy.append(u)
        current_unit = u
        current_chapter = None

    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, 1):
            tables = page.extract_tables()
            if not tables:
                continue

            for table in tables:
                for row in table:
                    if not row:
                        continue

                    # Flatten None → ""
                    cells = [clean_text(c or "") for c in row]

                    # Skip fully-empty rows
                    if not any(cells):
                        continue

                    # The first non-empty cell drives classification
                    first_cell = cells[0] if cells else ""
                    all_text = " ".join(c for c in cells if c)

                    # ---- 1. Detect UNIT boundary ----
                    # Unit headers appear as a single meaningful cell that spans
                    # the table width (other cells are empty/None).
                    # They look like: "UNIT II: ALGEBRA No. of periods : 66"
                    # Check ALL cells for a unit match (some PDFs put it anywhere)
                    unit_found = False
                    for cell in cells:
                        m = is_unit_header(cell)
                        if m:
                            unit_name = f"Unit {m.group(1).upper()}: {clean_text(m.group(2))}"
                            set_unit(unit_name, page_num)
                            unit_found = True
                            break
                    if unit_found:
                        continue

                    # ---- 2. Detect PART boundary ----
                    for cell in cells:
                        m = is_part_header(cell)
                        if m:
                            pname = f"Part {m.group(1)}"
                            if m.group(2):
                                pname += f": {clean_text(m.group(2))}"
                            set_unit(pname, page_num)
                            break

                    # ---- 3. Skip table header rows ----
                    if is_table_header_cell(first_cell):
                        continue
                    # Skip summary table rows (Roman numeral + marks)
                    if is_summary_row(all_text):
                        continue
                    if is_noise_text(first_cell) and all(is_noise_text(c) or is_table_header_cell(c) for c in cells[1:]):
                        continue
                    # For SST: also check the chapter column cell (col 1) directly,
                    # since col 0 is the S.No. and may be empty even on header rows.
                    # This catches 'allocation in', 'instructional', 'hours)' fragments.
                    _ch_col_preview = cells[1] if len(cells) > 1 else ""
                    if is_table_header_cell(_ch_col_preview) or is_table_header_cell(normalise_chapter_name(_ch_col_preview)):
                        continue

                    # ---- 4. Determine chapter column ----
                    # For MATHS: col 0 = Chapter name, col 1 = Key Concepts
                    # For SST:   col 0 = S.No., col 1 = Theme/Chapter name, col 2 = Outline

                    chapter_col: int
                    concepts_col: int

                    if subject_type == "social_science":
                        chapter_col = 1
                        concepts_col = 2
                    else:
                        # Maths and generic
                        chapter_col = 0
                        concepts_col = 1

                    # Safe access
                    ch_raw = cells[chapter_col] if chapter_col < len(cells) else ""
                    concepts_raw = cells[concepts_col] if concepts_col < len(cells) else ""

                    # ---- 5. Clean chapter name ----
                    # For SST, chapter name includes "(N Hours)"; strip it.
                    ch_name = re.sub(r"\s*\(\d+\s*Hours?\)", "", ch_raw, flags=re.IGNORECASE)
                    ch_name = normalise_chapter_name(ch_name)

                    # Skip if chapter name looks like a header or noise
                    if not ch_name or is_table_header_cell(ch_name) or is_noise_text(ch_name):
                        # Still try to attach concepts to current chapter if available
                        if current_chapter and concepts_raw:
                            for t in extract_bullet_texts(concepts_raw):
                                if not any(c["name"] == t for c in current_chapter["children"]):
                                    current_chapter["children"].append(new_topic(t, page_num))
                        continue

                    # Skip if chapter name is just a number (SST S.No. column leak)
                    if re.match(r"^\d+\.?$", ch_name):
                        continue

                    # Skip Internal Assessment administrative nodes
                    if is_internal_assessment_node(ch_name):
                        continue

                    # ---- 6. Create or update chapter ----
                    # If current_chapter already has this name (multi-row continuation),
                    # just append topics.
                    if current_chapter and current_chapter["name"] == ch_name:
                        ch = current_chapter
                    else:
                        ch = new_chapter(ch_name, page_num)
                        add_chapter(ch)

                    # ---- 7. Extract topics from concepts column ----
                    # Each bullet point becomes its own topic node.
                    for t in extract_bullet_texts(concepts_raw):
                        if not any(c["name"] == t for c in ch["children"]):
                            ch["children"].append(new_topic(t, page_num))

    # --------------------------------------------------------------------
    # Post-processing: remove obviously malformed fragment nodes
    # --------------------------------------------------------------------
    def _clean_children(nodes: list[dict]) -> list[dict]:
        kept = []
        for n in nodes:
            name = n.get("name", "")
            ntype = n.get("type", "")
            # Keep any node with children (even if name is short, it's structural)
            if n.get("children"):
                n["children"] = _clean_children(n["children"])
                kept.append(n)
            # Keep topics unconditionally if name is meaningful
            elif ntype == "topic" and len(name) > 3:
                kept.append(n)
            # Keep chapters/units with a meaningful name
            elif ntype in ("chapter", "unit") and len(name) > 4:
                kept.append(n)
        return kept

    hierarchy = _clean_children(hierarchy)

    return hierarchy, "table_aware_parser_v4"


# ---------------------------------------------------------------------------
# Science parser (text-line based, separate structure)
# ---------------------------------------------------------------------------

def parse_class9_science(pdf_path: Path) -> tuple[list, str]:
    """Chapter-level parser for Class 9 Science (no-table structure)."""
    hierarchy: list[dict] = []
    current_chapter: dict | None = None

    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, 1):
            text = page.extract_text()
            if not text:
                continue
            for line in text.split("\n"):
                line = line.strip()
                ch_match = re.match(
                    r"^(.+?)\s+No\.?\s*of\s*Periods?:?\s*\d+$", line, re.IGNORECASE
                )
                if ch_match:
                    ch_name = clean_text(ch_match.group(1))
                    current_chapter = {
                        "id": "dummy",
                        "name": ch_name,
                        "type": "chapter",
                        "source_document": pdf_path.name,
                        "source_pages": [page_num],
                        "children": [],
                    }
                    hierarchy.append(current_chapter)
                    continue
                bul = re.match(r"^[\u2022\u25cf]\s*(.+)$", line)
                if bul and current_chapter:
                    topic_name = clean_text(bul.group(1))
                    current_chapter["children"].append({
                        "id": "dummy",
                        "name": topic_name,
                        "type": "topic",
                        "source_document": pdf_path.name,
                        "source_pages": [page_num],
                    })

    return hierarchy, "text_line_parser_science"


# ---------------------------------------------------------------------------
# ID assignment
# ---------------------------------------------------------------------------

def assign_ids(hierarchy: list[dict], prefix: str) -> None:
    """Assign stable hierarchical IDs to all nodes in-place."""
    type_abbr = {"unit": "UNT", "chapter": "CHA", "topic": "TOP",
                 "subtopic": "SUB", "learning_outcome": "LO"}

    for i, node in enumerate(hierarchy, 1):
        node["id"] = f"{prefix}_{i:02d}"
        for j, child in enumerate(node.get("children", []), 1):
            ab = type_abbr.get(child["type"], child["type"][:3].upper())
            child["id"] = f"{node['id']}_{ab}{j:02d}"
            for k, gc in enumerate(child.get("children", []), 1):
                ab2 = type_abbr.get(gc["type"], gc["type"][:3].upper())
                gc["id"] = f"{child['id']}_{ab2}{k:02d}"
                # Level 4 (rare)
                for ll, ggc in enumerate(gc.get("children", []), 1):
                    ab3 = type_abbr.get(ggc["type"], ggc["type"][:3].upper())
                    ggc["id"] = f"{gc['id']}_{ab3}{ll:02d}"


# ---------------------------------------------------------------------------
# Validation report
# ---------------------------------------------------------------------------

def _count_nodes(nodes: list[dict]) -> dict:
    counts = {"unit": 0, "chapter": 0, "topic": 0, "subtopic": 0,
              "learning_outcome": 0, "empty_parents": 0}
    for n in nodes:
        ntype = n["type"]
        counts[ntype] = counts.get(ntype, 0) + 1
        if ntype in ("unit", "chapter") and not n.get("children"):
            counts["empty_parents"] += 1
        child_counts = _count_nodes(n.get("children", []))
        for k, v in child_counts.items():
            counts[k] = counts.get(k, 0) + v
    return counts


def build_validation_entry(cls: str, csv_subj: str, pdf_name: str,
                            method: str, hierarchy: list[dict]) -> list[str]:
    c = _count_nodes(hierarchy)
    total_chapters = c["chapter"]
    total_units = c["unit"]
    total_topics = c["topic"] + c.get("learning_outcome", 0)
    empty = c["empty_parents"]

    status = "PASS"
    warnings: list[str] = []
    if total_units == 0 and total_chapters == 0:
        status = "FAIL"
        warnings.append("No structural nodes extracted.")
    elif total_topics == 0:
        status = "WARN"
        warnings.append("No topics/key-concepts extracted.")
    if empty > 0:
        warnings.append(f"{empty} unit(s)/chapter(s) have no children.")

    lines = [
        f"## Class {cls} — {csv_subj.upper()}",
        f"- **Source PDF:** {pdf_name}",
        f"- **Academic Year:** {ACADEMIC_YEAR}",
        f"- **Extraction Method:** `{method}`",
        f"- **Units:** {total_units}",
        f"- **Chapters/Themes:** {total_chapters}",
        f"- **Topics/Key Concepts:** {total_topics}",
        f"- **Empty parent nodes:** {empty}",
        f"- **Status:** **{status}**",
    ]
    if warnings:
        lines.append("- **Warnings:**")
        for w in warnings:
            lines.append(f"  - {w}")
    lines.append("")
    return lines


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(args: argparse.Namespace) -> None:
    if not SOURCES_FILE.exists():
        print(f"ERROR: {SOURCES_FILE} not found.", file=sys.stderr)
        sys.exit(1)

    with open(SOURCES_FILE, encoding="utf-8") as fh:
        sources = json.load(fh)

    all_docs = [d for d in sources.get("documents", [])
                if d.get("download_status") == "success"]

    if args.all:
        docs = all_docs
    else:
        # Default: only rebuild affected Class 9 Maths + SST
        docs = [d for d in all_docs
                if d["class"] == "9" and d["subject_csv"] in ("maths", "social_science")]

    validation_md: list[str] = ["# Syllabus Taxonomy Validation Report\n"]

    for doc in docs:
        cls = doc["class"]
        csv_subj = doc["subject_csv"]
        local_pdf = Path(doc["local_file"])
        source_url = doc["document_url"]

        out_name = f"cbse_class{cls}_{csv_subj}_2026_27.json"
        out_path = DATA_SYLLABUS / out_name
        backup_path = BACKUP_DIR / out_name

        print(f"Processing {local_pdf.name} ...")

        if not local_pdf.exists():
            print(f"  WARNING: PDF not found at {local_pdf}", file=sys.stderr)
            continue

        # Backup existing file (never overwrite backup)
        if out_path.exists() and not backup_path.exists():
            import shutil
            shutil.copy2(out_path, backup_path)
            print(f"  Backed up existing JSON to {backup_path}")

        prefix = f"CBSE{cls}_{SUBJECT_CODE.get(csv_subj, csv_subj[:4].upper())}"

        # Choose parser
        if cls == "9" and csv_subj == "science":
            hierarchy, method = parse_class9_science(local_pdf)
        elif csv_subj == "social_science":
            hierarchy, method = parse_via_tables(local_pdf, subject_type="social_science")
        else:
            # Maths and all other subjects with table-based PDFs
            hierarchy, method = parse_via_tables(local_pdf, subject_type="maths")

        assign_ids(hierarchy, prefix)

        syllabus = {
            "board": BOARD,
            "academic_year": ACADEMIC_YEAR,
            "class": cls,
            "subject": csv_subj,
            "source_url": source_url,
            "source_pdf": local_pdf.name,
            "extracted_at": datetime.now(timezone.utc).isoformat(),
            "extraction_method": method,
            "curriculum": hierarchy,
        }

        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(syllabus, fh, indent=2, ensure_ascii=False)

        print(f"  Saved → {out_path}")

        validation_md.extend(
            build_validation_entry(cls, csv_subj, local_pdf.name, method, hierarchy)
        )

    with open(AUDIT_FILE, "w", encoding="utf-8") as fh:
        fh.write("\n".join(validation_md))

    print(f"\nValidation report saved → {AUDIT_FILE}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build CBSE syllabus JSON files.")
    parser.add_argument(
        "--all", action="store_true",
        help="Rebuild all subjects (default: only Class 9 Maths + Social Science)"
    )
    main(parser.parse_args())
