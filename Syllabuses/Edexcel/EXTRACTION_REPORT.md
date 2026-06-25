# Edexcel Syllabus PDF Extraction — Final Report

Output: `extracted_syllabus_pdf_edexcel/` — one cropped, header/footer-free A4 PDF per
teachable **topic / sub-topic**, mirroring the source tree, with a
`_subsections.json` manifest per spec.

## Totals

| Qualification | specs | files |
|---|--:|--:|
| A_Level | 38 | 887 |
| GCSE | 41 | 441 |
| IGCSE | 26 | 315 |
| International A_Level | 10 | 320 |
| iLowerSecondary | 4 | 91 |
| iPrimary | 4 | 49 |
| **TOTAL** | **123** | **2103** |

Status: **117 OK · 6 EMPTY · 0 ERROR · ~2580 sub-topic PDFs · ~5400 pages · 0 blank.**

Every spec is now split at its **deepest clean sub-topic level** (e.g. A-level Biology
1.1 Carbohydrates … ; Business 1.1 ; Economics 1.1.1 ; Chemistry Topic 2A/2B ; IGCSE
sciences (a)(b)(c)). A parent topic heading is carried into the first sub-topic's PDF
(not trailed on the previous one). Per-objective splitting is avoided (titles starting
with verbs like "Analyse"/"Describe" are recognised as objectives, so GCSE Physics /
Statistics stay at topic level), and deeply-nested specs (GCSE RS) are capped at a
usable level instead of exploding into hundreds of fragments. Counts are indicative;
see the live `_pdf_extraction_report.json`.

## Verification performed

- **Counts / errors / blank pages** — 0 errors, 0 blank pages, 0 zero-page files.
- **Coverage** (does every page of each section land in a sub-topic PDF?) — full
  coverage for all current specs. The only gaps are (a) deduplicated Foundation-tier
  pages in tiered Maths/Statistics (content preserved in the Higher-tier copy), and
  (b) four legacy specs with irregular layouts (8BS01, 9371, 8HI01, 8DR01).
- **Duplication** — tier duplication (Foundation+Higher) collapsed; genuine repeats
  kept (Further Maths topics across option papers, RS topics across religion papers).
- **Header-leak** — the next sub-topic's heading / a repeated table-header no longer
  bleeds onto a trailing page (Psychology, Geography, Business, …).

## How each spec splits (auto-detected, finest clean level)

1. **Maths "Topic" tables** → per Topic (A-level Maths 20, Further Maths 60).
2. **IAL Maths** → per Unit, each Unit's intro + its numbered topics (WMA11 = 98).
3. **Lettered `(a)(b)(c)`** → IGCSE Chemistry 29, Physics 28, Biology 23; GCSE Statistics.
4. **Numbered `N` topics** → IGCSE History depth+breadth (4HI1 = 22), Statistics (21),
   IGCSE Maths/FM (`2 …content` section now detected), History (1-8 + A/B options).
5. **Decimal `N.N`** → Business 1.1–4.4, PE, Geography, legacy sciences (8CH01 = 47),
   including 2-column "code | title" and bare "1.1" codes (PE 8PE01).
6. **Markers** (Theme/Unit/Paper/Component/Option) → everything else.

## Fixes applied (this round)

- **Maths "extracted twice"** — Foundation+Higher tiers collapsed (GCSE 1MA1 25→7,
  IGCSE 4MA1 13→8), gated to specs that actually have Foundation/Higher tier headings
  so RS / Further Maths repeats are NOT collapsed.
- **IGCSE Maths / Further Maths / History / Economics** — their content section
  `N <Subject> content` (e.g. "2 Economics content") is now detected directly
  instead of the "Content description" sub-heading the TOC pointed at, so they split
  per-topic (4MA1 3→8, 4PM1 4→11, 4HI1 3→22).
- **IAL Maths WMA11** — split per Unit into topics (15→98), each Unit's admin kept
  as a "Unit Px" intro and each topic clean.
- **Psychology / Geography / Business heading-leak** — trailing pages that showed
  only the next sub-topic's table-header are dropped.
- **GCSE RS 2RS01 titles** — "Section 1.1" etc now carry their 2-column titles.
- **PE 8PE01** — was a 58-page blob; now split into 1.1–4.3.
- **Economics decimals** — "1.1 – The market system" (en-dash) now matched.
- Multi-line titles captured for wrapped 2-column headings.

## Known remaining limitations

- **7 EMPTY** — genuine non-content files: A-level Economics 9EC0 (stub), Maths 8371
  (scanned, no text layer); GCSE legacy stubs with no written subject content
  (Art/D&T NA, Business 2BS01, Geography 2GE01, History 2HI01).
- **Legacy Business 8BS01** — partial coverage; its deep `3.3.1` decimals and
  letter-suffixed unit `4a` aren't split (legacy layout). All other previously-flagged
  legacy gaps are resolved or correct: **9371 now fully covered**; **8HI01 / 8DR01**
  "gaps" are Appendix exemplars / assessment-criteria pages (correctly excluded — not
  subject content).
- **Tiered Maths/Statistics** (Foundation+Higher) are deduplicated to one copy per
  topic (Higher carries the most content); the dropped Foundation duplicate shows as a
  small "gap" in a raw page-coverage check but no content is lost.
- **Skills-based specs** (Art, Music, some Languages) split into their few components;
  one component ("Performing"/"Overview") is large — these subjects have no finer
  topic structure.
- **Truncated titles** — a few specs with long wrapped headings (Geography enquiry
  questions) keep a short title; the PDF **content is complete**, only the
  filename/title is shortened.

## Fixes in the final pass

- **Politics 9PL0** re-downloaded from the Pearson archive (Brotli-decoded) — the
  local copy was a mark scheme; now a real 104-page spec that extracts.
- **Legacy Maths 9371** — running-header echoes ("Unit C1" reprinted smaller on every
  page, mirrored odd/even) were fragmenting unit spans; now dropped, full coverage.
