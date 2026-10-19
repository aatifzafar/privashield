# Synthetic samples

These files are generated locally by `scripts/generate_samples.py` and contain deliberately fake values that are not assigned to real people:

- `fake-pan-card.png` — a fake PAN-style card.
- `fake-aadhaar-style-card.png` — a fake Aadhaar-style card with an invalid-for-real-use demo number.
- `fake-bank-statement.pdf` — a text-based synthetic bank statement.

Regenerate them with:

```bash
python scripts/generate_samples.py
```

The generator uses Pillow and PyMuPDF, which are already backend runtime dependencies. Do not replace these with real identity documents.
