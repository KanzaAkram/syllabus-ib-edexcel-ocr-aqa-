# OCR Syllabus Extractor

`extract_syllabus_pdf.py` carves the **subject content** (the syllabus — modules /
topics / components and their numbered sub-topics) out of every OCR specification
PDF in this folder into NEW PDFs that **preserve the original page** (embedded
fonts, colours, table styling, two-column layout). Only the running page chrome is
cropped away. It is the OCR counterpart of the AQA / Edexcel `extract_syllabus_pdf.py`
and writes the same output shape: one A4 PDF per teachable sub-topic, mirroring the
source folder tree, plus a `_subsections.json` manifest per spec.

```bash
python extract_syllabus_pdf.py                       # scan ./ -> ./extracted_syllabus_pdf_ocr/
python extract_syllabus_pdf.py --root DIR --out OUTDIR
python extract_syllabus_pdf.py path/to/one.pdf       # a single spec
python extract_syllabus_pdf.py --proof one.pdf       # also render a proof PNG
python extract_syllabus_pdf.py --mode section        # one PDF per whole content section
```

Requires Python 3 with **PyMuPDF** (`pip install pymupdf`) and **numpy**.

## How OCR specs are laid out (and why this needs its own detector)

Every current OCR specification (H/J codes, 2015+) is organised into numbered
top-level sections:

```
1 Why choose … | 2 The specification overview | 3 Assessment | 4 Admin | 5 Appendices
```

The syllabus always lives inside **section 2 ("The specification overview")**, in
one or more *lettered* sub-sections whose title begins "Content of …" (or
"Detailed/Core Content of …"). The letter and naming vary by subject, so the
detector recognises every variant:

| Subject family | Content section(s) | Sub-topic split |
|---|---|---|
| Sciences / Maths | one big `2c. Content of modules 1 to 6` / `Content of topics B1 to B6` / `2f. Detailed Content of …` | `Module N` → `2.1` → `2.1.1`, or `Topic B1` → `B1.1`, or `1.01`, `2.01`… |
| Component subjects (humanities, social sciences, arts) | several `2c./2d./… Content of <Component>` | per-component, then internal `1.`, `1.1`, `2.1`… |
| History (A-level & GCSE) | `2c. Content of unit group N` / period & depth studies | per teachable **option** (`Unit Y101`, `China 1950–1981 (J410/…)`) |
| D&T | `2e./2f./2g. <Endorsed title> (H40N/0N …)` (no "Content of") | `1.1`, `2.1` … per component |
| Table-only specs (A-level Business, RS themes) | one `2c. Content of …` | code-less leftmost-column row labels |

A short `2b. Content of <Qualification> in <Subject> (<CODE>)` overview precedes the
real content and is skipped (unless it is the *only* content sub-section — e.g.
GCSE Maths J560, A-level Business H431 — when it is promoted).

The page **chrome** is OCR-specific and all removed:

* a full-width brand-coloured **band** across the top of every content page;
* a large white section number on a brand-coloured **side tab** in the outer margin
  (alternates left/right by page parity, and on landscape pages sits mid-edge over
  the table — it is painted out of those rasterised pages);
* a small **footer** (version string, "Cambridge OCR … GCE/GCSE …", page number).

### Landscape specs

GCSE sciences and A-level Maths/Further Maths are portrait pages flagged `/Rotate 90`
(they display landscape). The whole tool works in a single **visual** coordinate
space so rotation is handled transparently; those pages are emitted as crisp,
upright **A4-landscape** images of exactly the cropped region (chrome removed).

## How the region is found

1. Locate the content-section span(s) from the TOC bookmarks (font-geometry
   fallback when there is no usable outline; whole-document fallback for legacy
   specs). Duplicate bookmarks and post-content material (Prior knowledge,
   Assessment, Appendices, Permitted combinations, NEA / Performance Objectives) are
   dropped.
2. Within each span, find the sub-topic units — headings drawn in the subject's
   brand colour (`Module`, `2.1`, `2.1.1`, `B1.1`, `Topic B1`, …), large black bold
   headings (`1. …`), body-size **coded** headings in the left column
   (`P1.2 Changes of state`, `1.1 Characteristics …`), **standalone decimal code
   cells** in tables (Economics `1.1`/`2.1`, GCSE Maths `1.01`), or, as a last
   resort for code-less tables, the **row labels** in the leftmost column
   (A-level Business "Area of Study"). A coded grouping becomes an overview file
   plus one file per child, recursing to the finest level — mirroring the AQA tool.
3. Crop every page to its **real rendered ink** between the detected header band
   and footer, with the side tab excluded, so nothing is clipped and no chrome
   leaks. Each crop is placed on a uniform A4 sheet.

## Output

```
extracted_syllabus_pdf_ocr/<qual>/<subject>/<spec-code>/
    001_Module_1_Development_of_practical_skills.pdf
    002_1.1_Practical_skills_assessed_in_a_written_exam.pdf
    ...
    _subsections.json                 # manifest: code, title, page count per file
_pdf_extraction_report.json           # per-spec stats + warnings
```

## Coverage

80 OCR PDFs processed, **0 errors**. The 51 *current* specs (H/J, 2015+) all split
subtopic-wise — ~1,540 sub-topic PDFs, from per-component to per-numbered-sub-topic
(e.g. Biology 39, Physics 105, Economics 62 with `2.1/2.2`, GCSE Maths 46 with
`1.01`, D&T 100 with `1.1`, History 61 options). Chrome removal (band, side tab,
footer) was audited across portrait and landscape specs for leaks and edge-clipping.

## Known limitations

* **A-level Religious Studies H573** splits per exam component (8 files) rather than
  per numbered topic — its topics are code-less and centre-column, defeating both
  the heading and the leftmost-column row-label detectors.
* **Legacy specs (F/G codes, 2008–2016) and Cambridge Nationals** have a different,
  pre-2015 structure; they are handled best-effort by the font-geometry / whole-doc
  fallback and may be split more coarsely or include some front-matter.
* Source-PDF mojibake (apostrophes / dashes shown as `�`) is reproduced as-is — it
  is in the PDF's own text layer, so any extractor shows it.
