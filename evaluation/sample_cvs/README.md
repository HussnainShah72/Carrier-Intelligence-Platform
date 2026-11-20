# Synthetic test CVs

**Every file in this folder is synthetic.** The people, employers, dates and
achievements are fictional and were written for testing this project. No real
candidate's CV is included anywhere in this repository.

Each document carries the marker line:

> `SYNTHETIC TEST CV - FICTIONAL PERSON - CREATED FOR NLP COURSE PROJECT TESTING`

## Realistic profiles (used for the evaluation)

| File | Profile | Used to evaluate |
|---|---|---|
| `synthetic_software_engineer.*` | Mid-level backend engineer, 4 years | Software Engineer role |
| `synthetic_data_analyst.*` | Early-career analyst, 2 years | Data Analyst role |
| `synthetic_cybersecurity_analyst.*` | SOC analyst, 3 years | Cybersecurity Analyst role |

Each is generated as `.txt`, `.pdf` (with a real text layer) and `.docx`.

## Edge-case fixtures (used for the parser tests)

| File | What it tests |
|---|---|
| `synthetic_minimal.txt` | A CV with almost no content |
| `synthetic_messy.*` | Odd headings, pipe-separated contacts, inconsistent dates, duplicate skill spellings |
| `synthetic_empty.pdf` | A zero-byte upload |
| `synthetic_not_really_a_pdf.pdf` | A non-PDF file with a `.pdf` extension (magic-byte check) |
| `synthetic_image_only.pdf` | A valid PDF with no text layer (the 'scanned CV' path) |

Regenerate everything with:

```bash
python scripts/make_sample_cvs.py
```
