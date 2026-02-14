from pathlib import Path
import pdfplumber

p = Path(r"C:\Users\ericm\Desktop\syllabus1.pdf")
if not p.exists():
    print("MISSING_FILE")
    raise SystemExit(0)

try:
    with pdfplumber.open(p) as pdf:
        texts = []
        for i, page in enumerate(pdf.pages, start=1):
            t = page.extract_text() or ""
            texts.append(f"--- PAGE {i} ---\n" + t)
    out = "\n\n".join(texts)
    # Print a truncated preview
    preview = out[:20000]
    print(preview)
except Exception as e:
    print("ERROR:", e)
