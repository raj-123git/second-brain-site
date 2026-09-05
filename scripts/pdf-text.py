#!/usr/bin/env python
"""pdf-text.py <in.pdf> <out.txt> — extract the text of a PDF for the leak-check gate. Exit 1 if unreadable."""
import sys
try:
    import pypdf
    r = pypdf.PdfReader(sys.argv[1])
    text = "\n".join((p.extract_text() or "") for p in r.pages)
    open(sys.argv[2], "w", encoding="utf-8").write(text)
    if not text.strip():
        sys.exit(1)   # an empty text layer (scanned/rasterised PDF) cannot be checked -> treat as unreadable
except Exception:
    sys.exit(1)
