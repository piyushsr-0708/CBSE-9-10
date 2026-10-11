import pdfplumber
import sys

filename = sys.argv[1]
with pdfplumber.open(filename) as pdf:
    for i in range(3, min(8, len(pdf.pages))): # pages are 0-indexed, so 3 is page 4
        page = pdf.pages[i]
        print(f"--- PAGE {i+1} ---")
        text = page.extract_text()
        print("TEXT:", text)
        print("TABLES:")
        tables = page.extract_tables()
        for t in tables:
            for row in t:
                print(" | ".join(str(cell).replace('\n', ' ') for cell in row))
