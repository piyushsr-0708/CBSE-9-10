import pdfplumber
import sys

filename = sys.argv[1]
outfile = sys.argv[2]
with open(outfile, 'w', encoding='utf-8') as f:
    with pdfplumber.open(filename) as pdf:
        # Check first 15 pages to be sure
        for i in range(min(15, len(pdf.pages))):
            page = pdf.pages[i]
            f.write(f"--- PAGE {i+1} ---\n")
            text = page.extract_text()
            if text:
                f.write("TEXT:\n" + text + "\n")
            f.write("TABLES:\n")
            tables = page.extract_tables()
            for t in tables:
                for row in t:
                    f.write(" | ".join(str(cell).replace('\n', ' ') for cell in row) + "\n")
