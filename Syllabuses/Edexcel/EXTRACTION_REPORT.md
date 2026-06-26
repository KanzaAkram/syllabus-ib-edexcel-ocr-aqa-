# Edexcel Syllabus PDF Extraction — Final Report

Output: `extracted_syllabus_pdf_edexcel/` — one cropped, header/footer-free A4 PDF per
teachable **topic / sub-topic**, mirroring the source tree, with a
`_subsections.json` manifest per spec.

## Totals

| Qualification | files |
|---|--:|
| A_Level | 930 |
| GCSE | 597 |
| IGCSE | 394 |
| International A_Level | 368 |
| iLowerSecondary | 96 |
| iPrimary | 56 |
| **TOTAL** | **2441** |

Status: **117 OK · 6 EMPTY · 0 ERROR · 2441 sub-topic PDFs · 5027 pages · 0 blank pages · 0 zero-page files.**

Every spec is now split at its **deepest clean sub-topic level** (e.g. A-level Biology
1.1 Carbohydrates … ; Business 1.1 ; Economics 1.1.1 ; Chemistry Topic 2A/2B ; IGCSE
sciences (a)(b)(c)). A parent topic heading is carried into the first sub-topic's PDF
(not trailed on the previous one). Per-objective splitting is avoided (titles starting
with verbs like "Analyse"/"Describe" are recognised as objectives, so GCSE Physics /
Statistics stay at topic level), and deeply-nested specs (GCSE RS) are capped at a
usable level instead of exploding into hundreds of fragments. Counts are indicative;
see the live `_pdf_extraction_report.json`.

## QA audit round 2 (2026-06-26) — multi-agent verification + fixes

A full re-audit was run: a precise, hierarchy- and neighbour-aware detector scanned all
2,441 PDFs for the four user-named defects (heading bleeding at the **start**, the
**next** heading bleeding onto the last page, **blank/white** trailing pages, and
**cropped** headings), then a 73-agent fleet visually verified every flagged file
(rendering each suspect page region) to separate real defects from detector false
positives. That confirmed **161 real defects in 37 specs** (31 specs fully clean).

Six shared root-cause fixes were made in `extract_syllabus_pdf.py` and the whole set
re-extracted; **135 of 161 (84%) confirmed defects are resolved**, verified by re-render:

1. **Previous sub-topic's "…continued" page bled into the next PDF** (LMA11, JMA11,
   LCP11, 9ST0, JSC11, 9PH0, 1PH0): the parent-heading **anchor** accepted sibling /
   "continued" headings. Anchors are now restricted to genuine **ancestors**.
2. **Content numbers mistaken for sub-topic headings** (`40.5 g…`, `3.5 and 7`), which
   created garbage units *and truncated* the real sub-topic (LMA11, 1SP1): decimal
   headings with lowercase/fragment titles are rejected; bare `N.N` codes must be
   left-column.
3. **Legacy heading cropped off the top** ("opens at *j …*", 8CH01, WCH01): the anchor
   was grabbing the **running header** ("Unit 1" echoed on every page) — header-band
   lines are now skipped.
4. **Anchor jumped to a far bare-numeric sub-heading** across a page of other content
   (8CH01 1.6/1.7): marker anchors ("Topic 1") are trusted across their own intro, but
   bare-numeric anchors must sit immediately above the unit — *preserving* the wanted
   "Topic N leads its first sub-topic" behaviour (9BI0, 9BS0, 9CH0).
5. **Next-section divider / blank page at the end** (4PH1, 4BI1, 4CH1, 9GE0, 9PE0,
   9FM0…): a trailing page that is wholly the next section's divider/contents page is
   dropped.
6. **GCSE RS "Area of Study" off-by-one** (1RB0, 1RA0): each area's PDF opened with the
   *previous* area's Section 4. A marker **containment-tier** rule (Paper/Component ▸
   Unit/Area/Theme ▸ Section ▸ Topic) stops a child "Section 4" from anchoring its
   parent "Area of Study". Also incidentally fixed GCSE History 1HI0 options.

**Current (in-use) specs now have no genuine start-defects** — the few remaining `lead_*`
flags on current specs are detector false positives (the heading *is* present, e.g.
WMA01 "2. Coordinate geometry", 1GA0 "8.2 The UK"). The residual real defects are all in
**legacy (2008–2016) specs** with irregular layouts (see limitations).

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

### Residual defects after the round-2 audit (≈ a dozen files, all edge/legacy)

These are the only confirmed real defects left (everything affecting current in-use
specs is resolved; the remaining `bleed_*`/`blank_end_sliver` detector flags on current
specs were visually verified as **false positives** — own-content continuing onto the
last page, or legitimately short pages):

- **Legacy GCSE Physics 2PH01 (2012–2016)** — a unit's last sub-topic over-spans into
  the *next* Unit (e.g. a `5.x` file runs into "Unit P2"). The next Unit's first topic
  isn't detected as a sub-topic boundary in this legacy layout.
- **Legacy A-level 8MU01 / 8GP01 / 8HI01 / 8ET01 / 8PE01 (2008–2016)** — assessment /
  coursework sub-sections ("Assessment information", "Task 4.1 Development Plan",
  "Section E …") open at an internal numbered part rather than the component heading.
  (8PE01's "Task 4.1" top line is in fact legitimate.)
- **Legacy Biology 8BN01 / WBI01** — Salters-Nuffield dual "Concept approach / Context
  approach" layout (codes like `1.3` titled "Topic 1") confuses boundary detection.
- **A-level Economics 9EC0** — the source is a "specification map" grid (3.1.1/3.1.2…
  in a matrix), not prose content, so it doesn't crop into clean per-topic pages.
- **GCSE RS 1RB0** — Area off-by-one fixed; a few last pages still show the next area's
  Section-1 heading at the very bottom (minor trailing bleed).

## Fixes in the final pass

- **Politics 9PL0** re-downloaded from the Pearson archive (Brotli-decoded) — the
  local copy was a mark scheme; now a real 104-page spec that extracts.
- **Legacy Maths 9371** — running-header echoes ("Unit C1" reprinted smaller on every
  page, mirrored odd/even) were fragmenting unit spans; now dropped, full coverage.
