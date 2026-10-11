"""
Repair tools for CBSE 2026-27 Syllabus JSONs.

1. Re-extracts Class 10 Maths and Computer Applications using LLM over raw PDF text.
2. Cleans structural artifacts (roman numerals, letters, boilerplate) across all 7 syllabuses.
"""
import os
import json
import re
import pdfplumber
from pathlib import Path
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()
ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
SYL_DIR = ROOT / "data" / "syllabus"

def parse_with_gemini(pdf_filename, prompt):
    print(f"Extracting raw text from {pdf_filename}...")
    pdf_path = RAW_DIR / pdf_filename
    text = ""
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text += page.extract_text() + "\n"
    
    print(f"Calling Gemini to parse {pdf_filename}...")
    client = genai.Client()
    resp = client.models.generate_content(
        model="gemini-3.1-flash-lite",
        contents=f"{prompt}\nReturn ONLY valid JSON wrapped in ```json ... ``` blocks without markdown text before or after.\n\nTEXT TO PARSE:\n{text}",
        config=types.GenerateContentConfig(
            temperature=0.0
        )
    )
    
    out = resp.text.strip()
    if out.startswith("```json"):
        out = out[7:]
    if out.endswith("```"):
        out = out[:-3]
    parsed = json.loads(out.strip())
    
    if isinstance(parsed, dict):
        # Find the first list value, usually 'curriculum' or 'units' or whatever Gemini called it
        for k, v in parsed.items():
            if isinstance(v, list):
                return v
        return [parsed]
    return parsed

def clean_artifacts(nodes):
    cleaned = []
    if not isinstance(nodes, list):
        return cleaned
        
    artifacts = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", 
                 "a)", "b)", "c)", "d)", "I.", "II.", "III.", "IV.",
                 "Section:", "Chapter No.", "Chapter name", "allocation in", 
                 "instructional", "hours)", "(N Hours)"]
    for n in nodes:
        if not isinstance(n, dict):
            continue
        name_strip = str(n.get("name","")).strip()
        # Check explicit exact matches or starts with artifacts
        is_bad = False
        if name_strip in artifacts:
            is_bad = True
        elif name_strip.startswith("Section:") or name_strip.startswith("(N Hours)"):
            is_bad = True
        elif name_strip == "Name of the Chapter":
            is_bad = True
        elif name_strip == "Units" or name_strip == "Unit Name":
            is_bad = True
            
        # Recursive cleaning
        kids = clean_artifacts(n.get("children", []))
        
        if is_bad:
            # hoist children up
            cleaned.extend(kids)
        else:
            # Keep it
            n["children"] = kids
            cleaned.append(n)
            
    return cleaned

def count_nodes(nodes):
    count = 0
    if not isinstance(nodes, list):
        return 0
    for n in nodes:
        if isinstance(n, dict):
            count += 1
            count += count_nodes(n.get("children", []))
    return count

def get_counts(nodes, counts):
    if not isinstance(nodes, list):
        return
    for n in nodes:
        if isinstance(n, dict):
            t = n.get("type", "")
            counts[t] = counts.get(t, 0) + 1
            get_counts(n.get("children", []), counts)

def assign_ids(hierarchy, prefix):
    type_abbr = {"unit": "UNT", "chapter": "CHA", "topic": "TOP", "subtopic": "SUB"}
    if not isinstance(hierarchy, list): return
    for i, node in enumerate(hierarchy, 1):
        if not isinstance(node, dict): continue
        node["id"] = f"{prefix}_{i:02d}"
        for j, child in enumerate(node.get("children", []), 1):
            if not isinstance(child, dict): continue
            ab = type_abbr.get(child.get("type", "TOP"), child.get("type", "TOP")[:3].upper())
            child["id"] = f"{node['id']}_{ab}{j:02d}"
            for k, gc in enumerate(child.get("children", []), 1):
                if not isinstance(gc, dict): continue
                ab2 = type_abbr.get(gc.get("type", "TOP"), gc.get("type", "TOP")[:3].upper())
                gc["id"] = f"{child['id']}_{ab2}{k:02d}"
                for ll, ggc in enumerate(gc.get("children", []), 1):
                    if not isinstance(ggc, dict): continue
                    ab3 = type_abbr.get(ggc.get("type", "TOP"), ggc.get("type", "TOP")[:3].upper())
                    ggc["id"] = f"{gc['id']}_{ab3}{ll:02d}"

def main():
    report_lines = ["# Syllabus Taxonomy Repair Report\n"]
    
    maths_prompt = """Extract the exact CBSE Class 10 Mathematics syllabus hierarchy.
Return an array of unit objects, where each unit has children (chapters), and each chapter has children (topics/subtopics) from the key concepts.
Ensure all names represent true academic concepts exactly as written in the text. Output valid JSON array.
"""
    ca_prompt = """Extract the exact CBSE Class 10 Computer Applications syllabus hierarchy.
Return an array of unit objects, where each unit has children (chapters/topics). Look for 'Unit Designation' or similar structural headings, and the learning content beneath.
Output valid JSON array.
"""

    reextracted = {
        "cbse_class10_maths_2026_27.json": maths_prompt,
        "cbse_class10_computer_application_2026_27.json": ca_prompt
    }

    for json_file in sorted(SYL_DIR.glob("*.json")):
        print(f"Processing {json_file.name}")
        with open(json_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        old_count = count_nodes(data.get("curriculum", []))
        
        # 1. Re-extract if in list
        if json_file.name in reextracted:
            raw_pdf = json_file.name.replace(".json", ".pdf")
            data["curriculum"] = parse_with_gemini(raw_pdf, reextracted[json_file.name])
            data["extraction_method"] = "gemini_repaired"
            
        # 2. Clean artifacts
        pre_clean_count = count_nodes(data.get("curriculum", []))
        cleaned_curr = clean_artifacts(data.get("curriculum", []))
            
        # 3. Re-assign IDs
        prefix = f"CBSE{data['class']}_{data['subject'][:4].upper()}"
        if data['subject'] == "home_science": prefix = f"CBSE{data['class']}_HS"
        if data['subject'] == "social_science": prefix = f"CBSE{data['class']}_SST"
        if data['subject'] == "computer_application": prefix = f"CBSE{data['class']}_CA"
        
        assign_ids(cleaned_curr, prefix)
        data["curriculum"] = cleaned_curr
        
        # 4. Gather counts
        new_count = count_nodes(cleaned_curr)
        counts = {}
        get_counts(cleaned_curr, counts)
        
        # Write back
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            
        report_lines.append(f"## {json_file.name}")
        report_lines.append(f"- **Repaired:** {'Yes' if json_file.name in reextracted else 'Artifact clean only'}")
        report_lines.append(f"- **Previous node count:** {old_count}")
        report_lines.append(f"- **New node count:** {new_count}")
        report_lines.append(f"- **Units:** {counts.get('unit', 0)}")
        report_lines.append(f"- **Chapters/Themes:** {counts.get('chapter', 0)}")
        report_lines.append(f"- **Topics/Subtopics:** {counts.get('topic', 0) + counts.get('subtopic', 0)}")
        report_lines.append(f"- **Artifacts removed (net):** {pre_clean_count - new_count}")
        report_lines.append("")

    with open(ROOT / "reports" / "syllabus_repair_report.md", "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines))

if __name__ == "__main__":
    main()
