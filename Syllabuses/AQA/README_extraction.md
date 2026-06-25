# AQA Syllabus Extractor

`extract_syllabus.py` extracts the **Subject content** (the syllabus — topics,
subtopics, sub-subtopics and their content text) from every AQA specification
PDF in this folder into structured JSON, regardless of the subject's numbering
style.

---

## `extract_syllabus_pdf.py` — syllabus carved into authentic PDFs

Where the JSON tool re-encodes the text, **`extract_syllabus_pdf.py` keeps the
original page** (embedded fonts, colours, table styling, two-column layout) and
simply crops each page to the syllabus content — the running header, footer,
page numbers, decorative rules and legacy side-tabs are removed. Each cropped
region is then placed, at its natural scale, onto a **uniform A4 sheet** so every
output page is the same size. The result is visually identical to the source
spec, just header/footer-free and page-size-consistent.

```bash
python extract_syllabus_pdf.py                       # -> ./extracted_syllabus_pdf/ (A4, per sub-topic)
python extract_syllabus_pdf.py --no-a4               # keep each page at its tight cropped size
python extract_syllabus_pdf.py --mode section        # one PDF per spec instead
python extract_syllabus_pdf.py path/to/one.pdf       # a single spec
```

Default **subsection** mode writes one PDF per teachable sub-topic, mirroring the
source tree, into `extracted_syllabus_pdf/<qual>/<subject>/<spec-code>/` (files
go directly in the spec-code folder to keep Windows paths short; a code folder
holding two spec versions gets `pub2015/` `pub2023/` sub-folders):

```
001_3.1.1_Atomic_structure.pdf
002_3.1.2_Amount_of_substance.pdf      # the topic heading (3.1) leads its first sub-topic
...
_subsections.json                      # manifest: code, title, page count per file
```

How a subsection is chosen: one file per level-2 sub-topic carrying its deeper
content tables (Chemistry `3.1.2`); a level-1 topic whose only sub-headings are
codeless labels stays whole (Art & Design `3.1`); legacy table-cell codes
(`3.5.1`) are recovered so they split too. Each page is cropped to the **real
rendered ink** (not the text bounding box, which several legacy fonts
under-report) between the detected header/footer, so text is never clipped and
chrome never leaks. 103 AQA specs → 2,336 A4 subsection PDFs (0 errors, 0 blank
pages, all paths < 260 chars); audited for header/footer leaks and edge-clipping.

## Usage

```bash
python extract_syllabus.py                 # scan current folder for *.pdf -> ./extracted_syllabus/
python extract_syllabus.py --root . --out extracted_syllabus
python extract_syllabus.py path/to/one.pdf [more.pdf ...]   # specific files
```

Requires Python 3 with **PyMuPDF** (`pip install pymupdf`).

## Output

One JSON per PDF under `extracted_syllabus/`, mirroring the input folder tree,
plus three summary files:

| File | What it is |
|---|---|
| `<…>/<spec>.json` | full extraction for one PDF (metadata + nested syllabus) |
| `_index.json` | every doc's metadata + a content-free outline (handy table of contents) |
| `_extraction_report.json` | per-PDF stats (node counts, depth, warnings) |
| `_REPORT.md` | human-readable coverage table |

### Per-PDF JSON shape

```jsonc
{
  "source_pdf": "A_Level/Biology/.../AQA_ALEVEL_Biology_7402_..._CURRENT.pdf",
  "qualification": "A_Level",
  "subject": "Biology",
  "spec_code": "7402",
  "extraction_method": "toc",        // or "font-fallback"
  "n_sections": 1,
  "warnings": [],
  "sections": [
    {
      "section_code": "3",
      "section_title": "Subject content",
      "topics": [
        {
          "code": "3.1",
          "title": "Biological molecules",
          "level": 1,                 // 1=topic 2=subtopic 3=sub-subtopic 4=…
          "content": "All life on Earth shares a common chemistry…",
          "children": [
            { "code": "3.1.1", "title": "Monomers and polymers", "level": 2,
              "content": "…", "children": [] }
          ]
        }
      ]
    }
  ]
}
```

`sections` is a list because some specs carry **two** subject-content
sections ("Subject content – AS" and "– A-level", e.g. Computer Science,
Economics, Psychology, English). A node with `children` is a container; its own
`content` holds any preamble text that appears before its first child.

## How it handles the different numbering styles

The hierarchy is recovered from two signals, merged:

1. **Bookmark outline (TOC)** — correct titles/codes/pages, but its *level*
   field is sometimes corrupted and it can omit the deepest sub-topics.
2. **Font-aware text scan** — finds code-prefixed heading lines the TOC misses.

A heading's level comes from its **code's dot-count** (`3.1.1` → 3 levels deep),
which is immune to the corrupted TOC nesting. Headings are de-duplicated by
physical page position (codes are reused across a document, so de-duping by code
would collide). Body content is sliced from the page geometry between one
heading and the next, with running headers/footers removed by font size.

When a PDF's bookmark outline is too corrupt to use (e.g. the Level-2 Further
Maths certificate), a pure font-geometry fallback kicks in
(`extraction_method: "font-fallback"`).

## Coverage

63 of 64 PDFs extract cleanly (≈3,750 topic nodes, hierarchy up to 5 levels
deep). The one empty result —
`A_Level/Physics/2450_2005_to_2016/..._LEGACY.pdf` — is actually a 2014 exam
**mark scheme**, not a specification, and is flagged as such in its `warnings`.

Validation: a deterministic audit (0 issues across all 63) plus an independent
20-agent fidelity review against the source PDFs (each checked that headings are
present, correctly nested, and that body content is faithfully attributed with
no header/footer leakage).

## Table-based specs

A few specs hold their syllabus in dense multi-column tables that linear text
extraction can't reconstruct. For these (opt-in by spec code in `TABLE_SPECS`)
the parser uses PyMuPDF's table detector to recover the sub-topics row-by-row:

- **`Further Mathematics 8365`** (Level-2 cert) — Ref | Content | Notes tables →
  56 sub-topics (1.1–6.10) nested under their 6 topics.
- **`Computer Science 2520`** (legacy ICT) — Topic | Key Concepts | Amplification
  tables → 37 sub-topics nested under the 4 units, read row-by-row (un-garbled).

## Known limitations

A couple of edge cases remain; in each the **text is present**, just not
perfectly structured:

- **`Psychology 2185`** (legacy) — its sub-topics are body-sized headings in
  single-column flowing text with **no table structure** to exploit, so the 6
  units are captured with complete content but the sub-topics stay inside the
  unit's `content` rather than as separate nodes.
- **`Geography 7037` §3.3.4** — the non-exam-assessment 5-column **mark-scheme**
  grids interleave, and one band heading mis-nests. The core subject content
  (3.1, 3.2, …) is unaffected.
- **Source-PDF mojibake** — several PDFs lack glyph-to-Unicode maps, so
  apostrophes/quotes/accents/maths symbols read as `�`. This is in the PDF's own
  text layer (any extractor reproduces it); only the unambiguous date-range dash
  is repaired.
