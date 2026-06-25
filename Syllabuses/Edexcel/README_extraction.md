# Edexcel Syllabus Extractor

`extract_syllabus_pdf.py` is the **Edexcel / Pearson** counterpart of the AQA
`extract_syllabus_pdf.py`. It carves the syllabus (the *subject content*) out of
every Edexcel specification PDF and writes **one A4 PDF per teachable sub-topic**,
keeping the original page exactly (embedded fonts, colours, table styling,
two-column layout) and cropping away only the running header/footer chrome, page
numbers and decorative rules. The output format mirrors AQA's.

```bash
python extract_syllabus_pdf.py                       # -> ./extracted_syllabus_pdf_edexcel/ (A4, per sub-topic)
python extract_syllabus_pdf.py --no-a4               # keep each page at its tight cropped size
python extract_syllabus_pdf.py --mode section        # one PDF per whole syllabus section
python extract_syllabus_pdf.py path/to/one.pdf       # a single spec
python extract_syllabus_pdf.py one.pdf --proof       # also render a proof PNG of the first file
```

Requires Python 3 with **PyMuPDF** (`pip install pymupdf`) and **numpy**.

## Output

Default **subsection** mode writes one PDF per sub-topic, mirroring the source
tree, into `extracted_syllabus_pdf_edexcel/<qual>/<subject>/<spec-code>/`:

```
001_Overview.pdf                       # the section intro (Content overview / Practical skills)
002_Topic_1_Atomic_Structure_and_the_Periodic_Table.pdf
003_Topic_2_Bonding_and_Structure.pdf
...
_subsections.json                      # manifest: code, title, family, page count per file
```

Plus `_pdf_extraction_report.json` at the output root (per-PDF method, section
count, file count, warnings).

## Why Edexcel needs its own detector

Edexcel specs are laid out very differently from AQA — and differently across
the six qualifications (A_Level, GCSE, IGCSE, International_A_Level,
iLowerSecondary, iPrimary) and the 2008–2016 "legacy" vs 2017+ "current"
generations. The script copes with this without hard-coding per subject:

1. **Find the syllabus section.** Its title varies: *Knowledge, skills and
   understanding* (current sciences / English), *Subject content and assessment
   information* (humanities / languages / maths / arts), *Subject content*,
   *<Subject> content* (e.g. "Chemistry content" on IGCSE/IAL), *Detailed
   subject content* / *Content description* (new IGCSE), *Specification content*
   (legacy). Detection is **TOC-bookmark first**, **font-geometry fallback**
   (for specs with no usable outline), then **whole-document** (legacy specs
   organised directly as "Unit N" blocks with no section heading).

2. **Find the sub-topic units.** The marker word varies too — *Topic N*
   (sciences), *Theme N* (business / languages), *Component N* (English / Drama /
   Music / Art / D&T), *Paper N* / *Paper N, Option X* (maths / RS / history),
   *Area of study N* + *Option NX* (geography / RS), *Unit N* (legacy / IAL),
   *Section N* (legacy sciences), or a bare decimal *1 Principles of chemistry*
   (IGCSE, taken from the TOC). The finest consistent granularity is chosen by
   **dropping subdivided "parent" headings** (a heading split by ≥2 smaller-font
   headings before the next equal-or-larger one), so RS splits at Papers 1–3 plus
   Paper 4's options, sciences at Topic — with no per-subject rules. Where a spec
   numbers its sub-topics **N.N** (e.g. Business `1.1 … 4.4`, Physical Education,
   Geography, legacy Chemistry `1.1 … 6.7`) — including **bold body-size**
   numbering — the split happens at that decimal level and the parent
   Theme/Unit/Topic headings are dropped; a sibling that has no decimal of its own
   (e.g. a Geography Option whose own points are coded `2A.1`) is kept whole.
   Contents-list clusters (many headings on one page), running-header echoes and
   topic-restated-before-each-option duplicates are removed.

3. **Crop each page to the real rendered ink** between the detected header and
   footer, then place the crop on a uniform A4 sheet. Chrome is detected by
   **repetition across pages** (a running header recurs as the topmost element at
   a distinct font size; footers recur in the bottom margin), because current
   Edexcel specs carry colour bars behind near-top topic headings (so "wide bar
   in the top margin" would wrongly cut them) and legacy specs carry running
   headers at a *large* font (so "small font = chrome" fails).

## Notes / known limits

- A handful of short PDFs are **issue-summaries or withdrawn-spec stubs**, not
  full specifications (e.g. A_Level Economics 9EC0, Politics 9PL0, and some 3–10
  page GCSE legacy notices). They yield no sub-topics and are flagged in their
  `warnings` rather than producing output.
- Legacy specs (older 2008–2016 generation) that number their sub-topics `N.N`
  under each Unit (e.g. A-level Chemistry 8CH01 → `1.1`, `1.2`, …, `6.7`) are
  split at that **decimal sub-topic** level; the Unit headings become parents and
  are dropped. Legacy specs without decimal numbering (e.g. History) stay at
  Unit / option level. Running headers (the unit name repeated at the top of
  every page) are detected by recurrence and excluded.
- Source-PDF mojibake (some specs lack glyph-to-Unicode maps) is reproduced as in
  the original text layer; the cropped PDFs are visually identical to the source.
