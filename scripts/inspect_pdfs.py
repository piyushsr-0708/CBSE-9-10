import pdfplumber
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_RAW = ROOT / "data" / "raw"

TARGETS = [
    "cbse_class10_maths_2026_27.pdf",
    "cbse_class10_social_science_2026_27.pdf",
    "cbse_class9_science_2026_27.pdf"
]

def main():
    out_dir = ROOT / "scratch"
    out_dir.mkdir(exist_ok=True)
    
    for filename in TARGETS:
        pdf_path = DATA_RAW / filename
        if not pdf_path.exists():
            print(f"File not found: {pdf_path}")
            continue
            
        out_file = out_dir / f"{filename}.txt"
        print(f"Extracting {filename} to {out_file}...")
        
        with pdfplumber.open(pdf_path) as pdf:
            with open(out_file, "w", encoding="utf-8") as f:
                # Extract first 15 pages which usually contain the syllabus structure
                for i, page in enumerate(pdf.pages[:15]):
                    f.write(f"--- PAGE {i+1} ---\n")
                    text = page.extract_text()
                    if text:
                        f.write(text)
                        f.write("\n\n")

if __name__ == "__main__":
    main()
