import re

with open("scripts/build_syllabus.py", "r", encoding="utf-8") as f:
    code = f.read()

new_generic = """
def parse_generic(pdf_path: Path):
    \"\"\"Robust generic parser supporting Units, Parts, and complex tables.\"\"\"
    hierarchy = []
    current_unit = None
    current_chapter = None
    
    IGNORE_LINES = {
        "Theme (time", "allocation in", "instructional", "hours)", 
        "Outline/Concepts", "Learning Outcomes and", "Competencies", 
        "Students will be able to:", "COURSE STRUCTURE", "CLASS - IX", "CLASS - X",
        "Units Unit Name Chapter Name Marks",
        "Chapter Name Key Concepts Releva Competencies",
        "nt CGs", "(approx.)", "S. No.", "Theme", "Chapter Name", 
        "Key Concepts", "Relevant CGs", "Part 1", "Part 2", "Total", "TOTAL"
    }
    
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, 1):
            text = page.extract_text()
            if not text: continue
            
            lines = [line.strip() for line in text.split("\\n") if line.strip()]
            for i, line in enumerate(lines):
                clean_line = clean_text(line)
                
                if not clean_line: continue
                
                # Ignore noisy headers
                if clean_line in IGNORE_LINES or any(clean_line.startswith(ig) for ig in IGNORE_LINES):
                    continue
                if "INTERNAL ASSESSMENT" in clean_line.upper():
                    continue
                    
                # Skip numeric-only or short strings like "I", "II" in summary tables
                if re.match(r"^(?:I|II|III|IV|V|VI|VII|VIII|IX|X)\\s+.*\\d{2}$", clean_line):
                    continue
                if re.match(r"^(?:I|II|III|IV|V|VI|VII|VIII|IX|X)\\s+([a-zA-Z\\s]+)$", clean_line) and page_num < 5:
                    continue

                # Detect Part boundary
                part_match = re.match(r"^Part\\s+(\\d+)(?:\\s*[:-]\\s*(.+))?$", clean_line, re.IGNORECASE)
                if part_match:
                    name = part_match.group(2) if part_match.group(2) else f"Part {part_match.group(1)}"
                    current_unit = {
                        "id": "dummy", 
                        "name": clean_text(name),
                        "type": "unit",
                        "source_document": pdf_path.name,
                        "source_pages": [page_num],
                        "children": []
                    }
                    hierarchy.append(current_unit)
                    current_chapter = None
                    continue

                # Detect Unit boundary
                unit_match = re.match(r"^(?:UNIT|Unit)\\s+([A-Za-z0-9]+)\\s*[:-]\\s*(.+?)(?:\\s*No\\.\\s*of\\s*periods\\s*:\\s*\\d+)?$", clean_line, re.IGNORECASE)
                if unit_match:
                    unit_name = clean_text(unit_match.group(2))
                    current_unit = {
                        "id": "dummy",
                        "name": f"Unit {unit_match.group(1).upper()}: {unit_name}",
                        "type": "unit",
                        "source_document": pdf_path.name,
                        "source_pages": [page_num],
                        "children": []
                    }
                    hierarchy.append(current_unit)
                    current_chapter = None
                    continue

                # Detect Chapter boundary
                # Pattern A: "1. Understanding Social Science (4 Hours)"
                ch_match = re.match(r"^(\\d+)\\.\\s+(.+?)(?:\\s*\\(\\d+\\s*(?:Hours|Periods)\\))?$", clean_line, re.IGNORECASE)
                
                # Check if it looks like a chapter from Maths (Title case, no bullet, no number)
                # This is risky, so we rely on context. Math chapters are in the "Chapter Name" column
                # or they are standalone lines with NO bullets, that don't match sentences.
                ch_name = None
                if ch_match:
                    ch_name = clean_text(ch_match.group(2))
                    # Prevent matching "1. This is a point."
                    if len(ch_name.split()) > 10:
                        ch_name = None
                        
                # Math Chapter specific workaround: if line doesn't start with bullet, isn't a long sentence, 
                # and follows a unit closely, it might be a chapter.
                is_bullet = re.match(r"^[\\u2022\\u25cf\\u25e6\\u2013\\u2014\\-\\*]\\s*", clean_line)
                
                is_potential_chapter = False
                if not ch_name and not is_bullet and 2 < len(clean_line) < 60 and not clean_line.endswith("."):
                    # Check if it's mostly Title Case or just a short phrase
                    if current_unit and not re.search(r"\\d$", clean_line) and clean_line != clean_line.upper():
                        is_potential_chapter = True
                        ch_name = clean_text(clean_line)
                
                if ch_name and (ch_match or is_potential_chapter):
                    # We might have fragment chapters if wrapped, but we will accept for now.
                    # Ignore single numbers
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
                            # Avoid duplicate/fragment chapters - very rough heuristic
                            if not current_unit["children"] or current_unit["children"][-1]["name"] != ch_name:
                                current_unit["children"].append(ch)
                                current_chapter = ch
                        else:
                            if not hierarchy or hierarchy[-1]["name"] != ch_name:
                                hierarchy.append(ch)
                                current_chapter = ch
                    
                    if not is_potential_chapter:  # Real numbered chapters are definitively handled
                        continue

                # Bullet points
                if is_bullet:
                    topic_name = clean_text(is_bullet.sub(\"\", clean_line))
                    
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
                        if not current_unit["children"]:
                             ch = {
                                "id": "dummy",
                                "name": current_unit["name"] + " (Topics)",
                                "type": "chapter",
                                "source_document": pdf_path.name,
                                "source_pages": [page_num],
                                "children": []
                             }
                             current_unit["children"].append(ch)
                             current_chapter = ch
                        current_chapter["children"].append(topic)
                    else:
                        # Top level topic -> treat as chapter
                        ch = {
                            "id": "dummy",
                            "name": topic_name,
                            "type": "chapter",
                            "source_document": pdf_path.name,
                            "source_pages": [page_num],
                            "children": []
                        }
                        hierarchy.append(ch)
                        current_chapter = ch
                    continue

                if is_potential_chapter and current_chapter:
                    # If it wasn't a bullet, but we appended it as a chapter, that's fine.
                    continue
                    
    # Only return units/chapters that have children/topics, to clean up empty fragment chapters, EXCEPT if it's intentionally empty (like a top level theme)
    # Wait, the instruction said: "Do not remove legitimate official chapters/themes merely because they are empty."
    # So we don't prune empty chapters unless they are obvious garbage (e.g., 3 letters long).
    
    cleaned_hierarchy = []
    for node in hierarchy:
        if node["type"] == "unit":
            cleaned_children = [c for c in node["children"] if len(c["name"]) > 3 or c.get("children")]
            node["children"] = cleaned_children
            if node["children"] or len(node["name"]) > 5:
                cleaned_hierarchy.append(node)
        else:
            if len(node["name"]) > 3 or node.get("children"):
                cleaned_hierarchy.append(node)

    return cleaned_hierarchy, "generic_parser_v3"
"""

code = re.sub(
    r"def parse_generic\(pdf_path: Path\):.*?return hierarchy, \"generic_parser\"", 
    new_generic.strip(), 
    code,
    flags=re.DOTALL
)

main_replacement = """
        if cls == "9" and csv_subj == "science":
            hierarchy, method = parse_class9_science(local_pdf)
        else:
            hierarchy, method = parse_generic(local_pdf)
"""

code = re.sub(
    r"        if cls == \"10\" and csv_subj == \"maths\":.*?        else:.*?hierarchy, method = parse_generic\(local_pdf\)",
    main_replacement.strip(),
    code,
    flags=re.DOTALL
)

with open("scripts/build_syllabus.py", "w", encoding="utf-8") as f:
    f.write(code)
