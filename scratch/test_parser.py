import pdfplumber
import re
import sys
from pathlib import Path

def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()

def parse_generic_v3(pdf_path: Path):
    hierarchy = []
    current_unit = None
    current_chapter = None
    
    # Headers to ignore
    IGNORE_LINES = {
        "Theme (time", "allocation in", "instructional", "hours)", 
        "Outline/Concepts", "Learning Outcomes and", "Competencies", 
        "Students will be able to:", "COURSE STRUCTURE CLASS – IX",
        "COURSE OUTLINE", "Units Unit Name Chapter Name Marks",
        "Chapter Name Key Concepts Releva Competencies",
        "nt CGs"
    }

    # Matches for summary tables - Roman numerals followed by subject names, ending in numbers
    # We want to skip summary tables. If we see "Total 80", we might be in summary.
    # Alternatively, just skip lines that match summary pattern.
    
    in_summary = False

    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, 1):
            text = page.extract_text()
            if not text: continue
            
            # Simple header/footer skip (first and last lines if they match certain patterns)
            lines = [line.strip() for line in text.split("\n") if line.strip()]
            
            for line in lines:
                clean_line = clean_text(line)
                
                if clean_line in IGNORE_LINES or any(clean_line.startswith(ig) for ig in IGNORE_LINES):
                    continue
                    
                if clean_line.startswith("Total 80") or clean_line.startswith("INTERNAL ASSESSMENT"):
                    continue

                # Ignore Roman numerals from summary tables like "I Number System • Number System 07"
                # If there's a two-digit number at the end, it's likely a summary table row.
                if re.match(r"^(?:I|II|III|IV|V|VI|VII|VIII)\s+.*\d{2}$", clean_line):
                    continue
                # For some isolated ones like "III Coordinate • Coordinate Geometry 04" or "Geometry"
                if re.match(r"^(?:I|II|III|IV|V|VI|VII|VIII)\s+([a-zA-Z\s]+)$", clean_line) and page_num < 5:
                    # Very likely summary table
                    continue
                    
                # Detect Part (e.g. "Part 1") -> Treat as Unit
                part_match = re.match(r"^Part\s+(\d+)$", clean_line, re.IGNORECASE)
                if part_match:
                    current_unit = {
                        "id": f"dummy", 
                        "name": f"Part {part_match.group(1)}",
                        "type": "unit",
                        "source_document": pdf_path.name,
                        "source_pages": [page_num],
                        "children": []
                    }
                    hierarchy.append(current_unit)
                    current_chapter = None
                    continue

                # Detect UNIT I: NUMBER SYSTEM
                unit_match = re.match(r"^UNIT\s+([A-Za-z0-9]+)\s*[:-]\s*(.+?)(?:\s*No\.\s*of\s*periods\s*:\s*\d+)?$", clean_line, re.IGNORECASE)
                if not unit_match:
                    # sometimes "Unit 1: Number System No. of periods : 12"
                    unit_match = re.match(r"^Unit\s+(\d+)\s*[:-]\s*(.+?)(?:\s*No\.\s*of\s*periods\s*:\s*\d+)?$", clean_line, re.IGNORECASE)

                if unit_match:
                    unit_name = clean_text(unit_match.group(2))
                    current_unit = {
                        "id": "dummy",
                        "name": f"Unit {unit_match.group(1)}: {unit_name}",
                        "type": "unit",
                        "source_document": pdf_path.name,
                        "source_pages": [page_num],
                        "children": []
                    }
                    hierarchy.append(current_unit)
                    current_chapter = None
                    continue

                # Detect Chapters
                # Pattern A: "1. Understanding Social Science (4 Hours)"
                ch_match = re.match(r"^(\d+)\.\s+(.+?)(?:\s*\(\d+\s*Hours\))?$", clean_line)
                
                # Pattern B: Capitalized words with no bullets/numbers, sometimes spanning multiple lines, but let's look for explicit Chapter Name in Math: 
                # e.g., "Introduction to Polynomials" but without numbers. 
                # Wait, Math chapters in the table don't have numbers! "Number System", "Introduction to Polynomials", "Coordinate Geometry"
                # BUT wait, the Maths PDF doesn't explicitly mark them with numbers.
                
                if ch_match:
                    ch_name = clean_text(ch_match.group(2))
                    # Ignore single numbers like "1." or "2." 
                    if len(ch_name) > 2:
                        ch = {
                            "id": "dummy",
                            "name": ch_name,
                            "type": "chapter",
                            "source_document": pdf_path.name,
                            "source_pages": [page_num],
                            "children": []
                        }
                        if current_unit:
                            current_unit["children"].append(ch)
                        else:
                            hierarchy.append(ch)
                        current_chapter = ch
                    continue

                # Bullet points
                bul_match = re.match(r"^[\u2022\u25cf\u25e6\u2013\u2014\-\*]\s+(.+)$", clean_line)
                if bul_match:
                    topic_name = clean_text(bul_match.group(1))
                    
                    # We might have bullet points that are actually chapters if current_chapter is none, but let's assume they are topics.
                    topic = {
                        "id": "dummy",
                        "name": topic_name,
                        "type": "topic",
                        "source_document": pdf_path.name,
                        "source_pages": [page_num]
                    }
                    
                    if current_chapter:
                        current_chapter["children"].append(topic)
                    elif current_unit:
                        # Sometimes topics are directly under Unit
                        # Let's create a dummy chapter or treat current_unit as chapter if no chapter was found
                        if current_unit["type"] == "unit" and not current_unit["children"]:
                             # auto create chapter
                             ch = {
                                "id": "dummy",
                                "name": current_unit["name"],
                                "type": "chapter",
                                "source_document": pdf_path.name,
                                "source_pages": [page_num],
                                "children": []
                             }
                             current_unit["children"].append(ch)
                             current_chapter = ch
                        if current_chapter:
                             current_chapter["children"].append(topic)
                    continue

                # Catch specific chapters in Maths that don't have numbers, but follow "UNIT ..."
                # If it's Title Cased, 2-5 words, and we just started a unit or chapter is expected:
                # Wait, looking at maths_out.txt:
                # "Introduction to" / "Polynomials"
                # "Sequences" / "and" / "Progression" / "s"
                # The text is very fractured.

                # A better approach for the text is required.
                
    return hierarchy

print(parse_generic_v3(Path(sys.argv[1])))
