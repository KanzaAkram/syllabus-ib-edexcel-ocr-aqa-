#!/usr/bin/env python3
"""
extract_syllabus_pdf.py  (OCR)  --  Carve the OCR "subject content" (the syllabus)
out of each OCR specification PDF into NEW PDFs that preserve the original page
exactly (fonts, colours, table styling, two-column layout) -- only the running
header/footer chrome of every page is cropped away.

This is the OCR counterpart of the AQA / Edexcel `extract_syllabus_pdf.py`. The
output format is identical: one A4 PDF per teachable sub-topic, mirroring the
source folder tree, plus a `_subsections.json` manifest per spec.

Why OCR needs its own detector
------------------------------
OCR specs are laid out very differently from AQA and Edexcel. Every current OCR
specification (H/J codes, 2015+) is organised into NUMBERED top-level sections:

    1 Why choose ... | 2 The specification overview | 3 Assessment | 4 Admin | 5 Appendices

The syllabus always lives inside **section 2 ("The specification overview")**, in
one or more *lettered* sub-sections whose title begins "Content of ..." (or
"Detailed Content of ...", "Core Content of ..."). The exact letter varies by
subject:

* Sciences / Maths -- ONE big content sub-section that internally splits into
  Modules/Topics/Chapters and decimal sub-topics:
    "2c. Content of modules 1 to 6"  (Biology/Chemistry/Physics A-level)
    "2c. Content of topics B1 to B6" / "Content of chapters B1 to B8" (GCSE science)
    "2f. Detailed Content of A Level Mathematics A (H240)"
* Component / unit-group subjects (most humanities, social sciences, arts) --
  SEVERAL content sub-sections, one per exam component / unit group:
    "2c. Content of Component 1: Microeconomics (H460/01)"  (Economics)
    "2c. Content of unit group 1: British period study ..."  (History)
    "2c. Content of Philosophy of religion (H573/01)"        (Religious Studies)

A short "2b. Content of <Qualification> in <Subject> (<CODE>)" overview precedes
the real content and is deliberately skipped (unless it is the ONLY content
sub-section, e.g. GCSE Maths J560 / A-level Business H431, where it is promoted).

The page CHROME is also OCR-specific:
* a full-width brand-coloured decorative BAND across the top of every content
  page (the "running header" -- has no useful text, just colour);
* a large white section number on a brand-coloured SIDE TAB in the extreme outer
  margin (alternates left/right by page parity);
* a small footer (version string, page number, "Cambridge OCR ... GCE/GCSE ...").

How the region is found
-----------------------
1. Locate every content sub-section span from the TOC bookmarks (font-geometry
   fallback when there is no usable outline; whole-document fallback otherwise).
2. Within each content span, detect the sub-topic unit headings -- OCR headings
   are drawn in the subject's brand colour (Module/decimal codes: 2.1, 2.1.1,
   B1.1, Topic B1, ...) or in large black bold (Economics "1. ...", Maths
   "1 - Pure Mathematics"), or are codeless brand-coloured labels (Psychology).
   The finest consistent granularity is chosen, mirroring the AQA tool: a coded
   grouping (Module / Topic) becomes an overview file plus one file per child
   sub-topic, with deeper sub-sub-topics nested inside.
3. Crop every page of a unit to its real rendered ink between the detected
   header band and footer, exactly like the AQA/Edexcel tools, so nothing is
   clipped and no chrome leaks. Each crop is placed on a uniform A4 sheet
   (A4-landscape for landscape source pages, e.g. Mathematics).

Usage
-----
    python extract_syllabus_pdf.py                 # scan ./ -> ./extracted_syllabus_pdf_ocr/
    python extract_syllabus_pdf.py --root DIR --out OUTDIR
    python extract_syllabus_pdf.py path/to/one.pdf [more.pdf ...]
    python extract_syllabus_pdf.py one.pdf --proof # also render a proof PNG per spec
    python extract_syllabus_pdf.py --mode section  # one PDF per whole content section
"""

from __future__ import annotations
import argparse
import glob as _glob
import json
import os
import re
import sys
import traceback
from collections import Counter

import fitz  # PyMuPDF
import numpy as np

sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # safe printing on cp1252 consoles


# ----------------------------------------------------------------------------
# Small text helpers (self-contained)
# ----------------------------------------------------------------------------

def norm_ws(s: str) -> str:
    """Collapse all whitespace (incl tabs / nbsp) to single spaces, strip ends."""
    return re.sub(r"[\s ]+", " ", s or "").strip()


def page_dims(page):
    """VISUAL page (width, height) -- i.e. how the page is displayed. For a normal
    page this equals the mediabox; for the OCR landscape specs (GCSE sciences,
    A-level Maths) whose portrait pages carry /Rotate 90, it is the rotated size.
    The whole module works in this single VISUAL coordinate space (see
    get_page_lines / get_page_drawings), so detection, cropping and emit all agree
    and the rotation never has to be reasoned about again downstream."""
    return page.rect.width, page.rect.height


def get_page_lines(page) -> list:
    """Visual text lines on a page with geometry + font/colour info, with every
    bbox mapped into the page's VISUAL (display) coordinate space so rotated pages
    are handled transparently. Each line: {text,x0,y0,x1,y1,size,bold,color}."""
    M = page.rotation_matrix          # identity for un-rotated pages
    out = []
    for b in page.get_text("dict").get("blocks", []):
        if "lines" not in b:
            continue
        for ln in b["lines"]:
            spans = ln.get("spans", [])
            if not spans:
                continue
            text = "".join(s["text"] for s in spans)
            if not text.strip():
                continue
            r = fitz.Rect(min(s["bbox"][0] for s in spans),
                          min(s["bbox"][1] for s in spans),
                          max(s["bbox"][2] for s in spans),
                          max(s["bbox"][3] for s in spans)) * M
            r.normalize()
            size = max(s["size"] for s in spans)
            fonts = " ".join(s["font"] for s in spans).lower()
            bold = any(k in fonts for k in ("bold", "black", "semibold", "heavy"))
            big = max(spans, key=lambda s: s["size"])      # dominant-ink colour
            color = big.get("color", 0)
            out.append({"text": text, "x0": r.x0, "y0": r.y0, "x1": r.x1, "y1": r.y1,
                        "size": size, "bold": bold, "color": color})
    return out


def get_page_drawings(page):
    """Vector drawings with rects mapped into the page's VISUAL coordinate space
    (consistent with get_page_lines). Yields (rect, fill)."""
    M = page.rotation_matrix
    for d in page.get_drawings():
        r = d["rect"] * M
        r.normalize()
        yield r, d.get("fill")


def estimate_body_size(doc) -> float:
    """Most common rounded font size across the doc ~ the body text size."""
    c = Counter()
    for pno in range(doc.page_count):
        for b in doc[pno].get_text("dict").get("blocks", []):
            if "lines" not in b:
                continue
            for ln in b["lines"]:
                for s in ln["spans"]:
                    if s["text"].strip():
                        c[round(s["size"])] += 1
    return float(c.most_common(1)[0][0]) if c else 11.0


def looks_like_non_spec(doc) -> bool:
    """Heuristic: a mark scheme / question paper, not a full spec."""
    txt = "\n".join(doc[i].get_text("text") for i in range(min(3, doc.page_count))).lower()
    return ("mark scheme" in txt or "question paper" in txt) and "specification" not in txt


# colour helpers -------------------------------------------------------------

def _rgb(color: int):
    return ((color >> 16) & 255, (color >> 8) & 255, color & 255)


def _is_blackish(color: int) -> bool:
    r, g, b = _rgb(color)
    return r < 70 and g < 70 and b < 70


def _is_whiteish(color: int) -> bool:
    r, g, b = _rgb(color)
    return r > 200 and g > 200 and b > 200


def _is_grayish(color: int) -> bool:
    r, g, b = _rgb(color)
    return abs(r - g) < 18 and abs(g - b) < 18 and abs(r - b) < 18


def _color_close(a: int, b: int, tol: int = 40) -> bool:
    ra, ga, ba = _rgb(a); rb, gb, bb = _rgb(b)
    return abs(ra - rb) <= tol and abs(ga - gb) <= tol and abs(ba - bb) <= tol


# ----------------------------------------------------------------------------
# Regexes
# ----------------------------------------------------------------------------

# A content sub-section title inside section 2: "Content of X", "Detailed Content
# of X", "Core Content of X", "Subject content for X", "Content for X", "Content: X".
CONTENT_TITLE_RE = re.compile(
    r"(?:detailed\s+|core\s+)?(?:subject\s+)?content\s*(?:of|for|:)\b", re.I)

# Some specs name their content sub-sections by component without "Content of",
# e.g. D&T "2e. Design Engineering (H404/01 and H404/02)". Accept a lettered
# section-2 subsection whose title ends with a slashed component/paper code.
COMPONENT_SECT_RE = re.compile(
    r"^\s*\d{1,2}[a-z](?:\([ivx]+\))?\.\s+.+\([A-Z]?\d{2,3}/\d", re.I)

# The short overview sub-section: "Content of <Qual> in <Subject> (<CODE>)".
# It always carries the qualification phrase " in " followed by a trailing
# parenthesised spec code. The detailed sections never have that exact shape.
OVERVIEW_TITLE_RE = re.compile(
    r"content\s+of\s+(?:the\s+)?(?:ocr\s+)?"
    r"(?:a\s*level|as\s*level|gce|gcse).*\bin\b.*\([A-Z]?\d[\w./–— -]*\)\s*$",
    re.I)

# Titles that look like content but are NOT teachable syllabus content. The
# intro/overview words are anchored to the title PREFIX (after an optional "2b."
# code) so a real section such as "Content of J205/01 - Introduction to Economics"
# or "Content of ... Overview" is NOT wrongly excluded.
CONTENT_EXCLUDE_RE = re.compile(
    r"^\s*(?:\d{1,2}[a-z]?(?:\([ivx]+\))?\.?\s*)?(?:introduction\b|overview\b)"
    r"|from\s+the\s+specification\s+content"      # glossary ("Glossary of terms from ...")
    r"|glossary"
    r"|list\s+of\s+(?:subject\s+)?content"
    r"|at\s+a\s+glance"
    r"|assessment\s+interpretation"           # D&T NEA "interpretation" sections
    r"|content\s+and\s+assessment\s+overview",
    re.I)

# Top-level numbered section headings that BOUND the content (start of "3", "4", ...).
SECTION_NUM_RE = re.compile(r"^\s*(\d{1,2})\s+[A-Z]")   # "3 Assessment of ...", "2 The specification ..."
ASSESSMENT_SECT_RE = re.compile(
    r"^\s*\d*\s*assessment\b|prior\s+knowledge|^\s*\d*\s*admin\b|appendices",
    re.I)

# Sub-topic unit marker families (heading begins with one of these + a code).
UNIT_MARKERS = [
    ("Module",        re.compile(r"^Module\s+(\S+)\b\s*[:.–—-]?\s*(.*)$")),
    ("Chapter",       re.compile(r"^Chapter\s+(\S+)\b\s*[:.–—-]?\s*(.*)$")),
    ("Topic Area",    re.compile(r"^Topic\s+Area\s+(\S+)\b\s*[:.–—-]?\s*(.*)$")),
    ("Topic",         re.compile(r"^Topic\s+(\S+?)\b\s*[:.–—-]?\s*(.*)$")),
    ("Component",     re.compile(r"^Component\s+(\S+)\b\s*[:.–—-]?\s*(.*)$")),
    ("Unit group",    re.compile(r"^Unit\s+group\s+(\S+)\b\s*[:.–—-]?\s*(.*)$")),
    ("Unit",          re.compile(r"^Unit\s+(\S+)\b\s*[:.–—-]?\s*(.*)$")),
    ("Area of study", re.compile(r"^Area\s+of\s+[Ss]tudy\s+(\S+)\b\s*[:.–—-]?\s*(.*)$")),
    ("Paper",         re.compile(r"^Paper\s+(\S+)\b\s*[:.–—-]?\s*(.*)$")),
    ("Section",       re.compile(r"^Section\s+(\S+)\b\s*[:.–—-]?\s*(.*)$")),
]
# Marker families that may appear at mere body size (accepted as headings anyway
# when bold + carrying a valid code -- e.g. History "Unit Y101: ..." options).
_MARKER_KINDS = {fam for fam, _ in UNIT_MARKERS}

# Code-prefixed heading: decimal (2.1, 2.1.1, 1.01), alnum science (B1, B1.1,
# C2.3, P1.10), unit option (Y101), "N. Title" / "N - Title".
CODE_DECIMAL_RE = re.compile(r"^(\d{1,2}(?:\.\d{1,2}){1,3})\s+(.+)$")
CODE_ALNUM_RE   = re.compile(r"^([A-Z]{1,3}\d{1,2}(?:\.\d{1,2}){0,2})\b\s*[:.–—-]?\s*(.*)$")
CODE_INT_RE     = re.compile(r"^(\d{1,2})\s*[.)–—-]\s+(.+)$")

# Footer banners (OCR / Cambridge). Page numbers handled separately.
OCR_FOOTER_RE = re.compile(
    r"©\s*(?:cambridge\s+)?ocr"
    r"|cambridge\s+ocr"
    r"|\bocr\b.{0,30}\b20\d\d"
    r"|version\s+[\d.]+\s*\("
    r"|advanced\s+(?:subsidiary\s+)?gce"
    r"|level\s+[123]\b.{0,30}\bgce"
    r"|gcse\s*\(9"
    r"|\bturn\s+over\b"
    r"|www\.ocr\.org",
    re.I)


def _valid_unit_code(code: str) -> bool:
    code = (code or "").strip(" .,:-–—")
    if not code:
        return False
    return bool(re.search(r"\d", code)) or bool(re.fullmatch(r"[A-Z]{1,3}", code))


# A unit whose title is really post-content material (assessment / admin / generic
# appendix) that slipped in at a section boundary -- dropped from the output.
STOP_UNIT_RE = re.compile(
    r"^\s*(?:section\s+)?\d{0,2}[a-z]?(?:\([ivx]+\))?\.?\s*"
    r"(prior\s+knowledge|overview\s+of\s+assessment|forms?\s+of\s+assessment"
    r"|assessment\s+objectives|how\s+science\s+works|mathematical\s+requirements"
    r"|appendix|appendices|synoptic\s+assessment|use\s+of\s+technology"
    r"|the\s+large\s+data\s+set|command\s+words"
    r"|permitted\s+combinations|topics\s+available|introduction\s+to\s+the\b"
    r"|key\s+issues|entry\s+code|terminal\s+assessment|performance\s+objectives?"
    r"|externally\s+assessed|nea\s+units?|\bpo\d\b|moderat)\b",
    re.I)


def _clean_unit_title(title: str) -> str:
    """Strip a dangling section/sub-section prefix ("2e. ", "Content of ...") that
    can survive when a whole content sub-section becomes one unit."""
    t = norm_ws(title)
    t = re.sub(r"^\d{1,2}[a-z]?(?:\([ivx]+\))?\.\s*", "", t)
    t = re.sub(r"^(?:detailed\s+|core\s+)?(?:subject\s+)?content\s*(?:of|for|:)\s+",
               "", t, flags=re.I)
    return t.strip() or norm_ws(title)


# ----------------------------------------------------------------------------
# Brand colour detection
# ----------------------------------------------------------------------------

def detect_brand_color(doc, body_size):
    """The subject's heading/brand colour = the most common non-black, non-white,
    non-gray colour among bold, larger-than-body heading lines across the doc."""
    c = Counter()
    for pno in range(doc.page_count):
        for ln in get_page_lines(doc[pno]):
            if (ln["bold"] and ln["size"] >= body_size + 1.5
                    and not _is_blackish(ln["color"]) and not _is_whiteish(ln["color"])
                    and not _is_grayish(ln["color"])):
                c[ln["color"]] += 1
    return c.most_common(1)[0][0] if c else None


# ----------------------------------------------------------------------------
# Content-section span detection (TOC first)
# ----------------------------------------------------------------------------

def _is_content_title(title: str) -> bool:
    t = norm_ws(title)
    if not (CONTENT_TITLE_RE.search(t) or COMPONENT_SECT_RE.search(t)):
        return False
    if CONTENT_EXCLUDE_RE.search(t):
        return False
    return True


def _toc_entries(doc):
    """TOC as [(level, title, page0)], page0 = 0-based page index, sorted."""
    out = []
    for lvl, title, pg in doc.get_toc(simple=True):
        if pg and pg >= 1:
            out.append((lvl, norm_ws(title), pg - 1))
    return out


def find_content_sections(doc, body_size):
    """Return (sections, method). Each section dict:
    {start_page, start_y, end_page, end_y, title, code(letter)}.
    Detailed-content sub-sections only; the brief overview is skipped unless it
    is the only content sub-section (then promoted)."""
    toc = _toc_entries(doc)
    if toc:
        secs = _sections_from_toc(doc, toc)
        if secs:
            return secs, "toc"

    # Font-geometry fallback: large brand/bold headings whose text says "Content of".
    secs = _sections_from_font(doc, body_size)
    if secs:
        return secs, "font"

    # Whole-document fallback (legacy specs with no usable structure).
    return [{"start_page": 0, "start_y": 0.0, "end_page": doc.page_count - 1,
             "end_y": 1e9, "title": "Subject content", "code": ""}], "legacy"


def _sections_from_toc(doc, toc):
    cand = []   # (idx, title, page, is_overview)
    for i, (lvl, title, pg) in enumerate(toc):
        if not _is_content_title(title):
            continue
        cand.append({"i": i, "lvl": lvl, "title": title, "page": pg,
                     "overview": bool(OVERVIEW_TITLE_RE.search(title))})
    if not cand:
        return []

    # End of each candidate = the next TOC entry at level <= its own level.
    def end_of(i, lvl):
        for lvl2, _t2, pg2 in toc[i + 1:]:
            if lvl2 <= lvl:
                return pg2
        return doc.page_count
    for c in cand:
        c["end"] = end_of(c["i"], c["lvl"])
        c["span"] = max(0, c["end"] - c["page"])

    detailed = [c for c in cand if not c["overview"]]
    if not detailed:
        # Promote: the spec stores its whole syllabus under a "Content of <Qual>
        # in <Subject> (CODE)" heading (e.g. GCSE Maths J560, A-level Business).
        # Keep the substantial overview block(s).
        biggest = max(c["span"] for c in cand)
        detailed = [c for c in cand if c["span"] >= max(4, biggest - 1)]
    if not detailed:
        detailed = cand

    # Drop stray duplicate bookmarks for the same section (some specs, e.g. the
    # 2015 Biology print, repeat a content title at page 1); keep the occurrence
    # with the largest page span. Distinct titles (History unit groups 1/2/3,
    # RS religions, ...) are preserved.
    best = {}
    for c in detailed:
        key = re.sub(r"[^a-z0-9]", "", c["title"].lower())
        if key not in best or c["span"] > best[key]["span"]:
            best[key] = c
    detailed = sorted(best.values(), key=lambda c: c["page"])

    secs = []
    for c in detailed:
        start_page = c["page"]
        end_page = max(start_page, c["end"] - 1)
        sy = _locate_title_y(doc, start_page, c["title"])
        secs.append({"start_page": start_page, "start_y": sy,
                     "end_page": end_page, "end_y": 1e9,
                     "title": c["title"], "code": _letter_code(c["title"])})
    secs.sort(key=lambda s: (s["start_page"], s["start_y"]))
    # The end of one content section is the start of the next when they are
    # contiguous (component subjects); otherwise the TOC end already applies.
    for k in range(len(secs) - 1):
        nxt = secs[k + 1]
        if nxt["start_page"] <= secs[k]["end_page"]:
            secs[k]["end_page"] = nxt["start_page"]
            secs[k]["end_y"] = nxt["start_y"]
    return secs


def _sections_from_font(doc, body_size):
    big = []
    for pno in range(doc.page_count):
        pw = page_dims(doc[pno])[0]
        for ln in get_page_lines(doc[pno]):
            t = norm_ws(ln["text"])
            if (ln["size"] >= body_size + 3 and ln["x0"] < pw * 0.5 and len(t) < 80
                    and _is_content_title(t) and not OVERVIEW_TITLE_RE.search(t)):
                big.append({"page": pno, "y": ln["y0"], "title": t})
    big.sort(key=lambda h: (h["page"], h["y"]))
    if not big:
        return []
    secs = []
    for k, h in enumerate(big):
        if k + 1 < len(big):
            ep, ey = big[k + 1]["page"], big[k + 1]["y"]
        else:
            ep, ey = _find_assessment_stop(doc, h["page"], body_size)
        secs.append({"start_page": h["page"], "start_y": h["y"],
                     "end_page": ep, "end_y": ey, "title": h["title"],
                     "code": _letter_code(h["title"])})
    return secs


def _find_assessment_stop(doc, start_page, body_size):
    """First 'Assessment'/'Prior knowledge' heading after start_page -> content end."""
    for pno in range(start_page + 1, doc.page_count):
        pw = page_dims(doc[pno])[0]
        for ln in get_page_lines(doc[pno]):
            if (ln["size"] >= body_size + 3 and ln["x0"] < pw * 0.5
                    and ASSESSMENT_SECT_RE.search(norm_ws(ln["text"]))):
                return pno, ln["y0"]
    return doc.page_count - 1, 1e9


def _letter_code(title):
    m = re.match(r"^\s*(\d{1,2}[a-z]?(?:\([ivx]+\))?)\.", norm_ws(title))
    return m.group(1) if m else ""


def _locate_title_y(doc, pno, title):
    """y of the heading line that matches `title` on page pno (0 if not found)."""
    if pno < 0 or pno >= doc.page_count:
        return 0.0
    key = re.sub(r"[^a-z0-9]", "", title.lower())[:26]
    if not key:
        return 0.0
    best = None
    for ln in get_page_lines(doc[pno]):
        lk = re.sub(r"[^a-z0-9]", "", norm_ws(ln["text"]).lower())
        if lk and (lk.startswith(key[:16]) or key[:16] in lk):
            if best is None or ln["y0"] < best:
                best = ln["y0"]
    return best if best is not None else 0.0


# ----------------------------------------------------------------------------
# Sub-topic unit detection within a content section
# ----------------------------------------------------------------------------

def _classify_heading(text):
    """Return (kind, code, title, level) for a heading line, or None.
    level = code depth (Module/marker=1, 2.1=2, 2.1.1=3, B1=1, B1.1=2, '1.'=1)."""
    t = norm_ws(text)
    # marker families (Module / Topic / Component / Unit group / ...)
    for fam, pat in UNIT_MARKERS:
        m = pat.match(t)
        if m:
            code = m.group(1).strip(" .,:-–—")
            if not _valid_unit_code(code):
                continue
            title = norm_ws(m.group(2)) if m.lastindex >= 2 and m.group(2) else ""
            level = 1 + code.count(".")
            return fam, f"{fam} {code}".strip(), title, level
    # decimal code (2.1 / 2.1.1 / 1.01)
    m = CODE_DECIMAL_RE.match(t)
    if m:
        code = m.group(1)
        return "decimal", code, norm_ws(m.group(2)), 1 + code.count(".")
    # alnum science / option code (B1, B1.1, C2.3, P1.10, Y101)
    m = CODE_ALNUM_RE.match(t)
    if m and re.search(r"\d", m.group(1)):
        code = m.group(1)
        title = norm_ws(m.group(2))
        return "alnum", code, title, 1 + code.count(".")
    # "N. Title" / "N - Title" (Economics / Maths black topic headings)
    m = CODE_INT_RE.match(t)
    if m and len(norm_ws(m.group(2))) >= 3:
        return "int", m.group(1), norm_ws(m.group(2)), 1
    return None


def _heading_candidates(doc, sec, body_size, brand):
    """Heading-like lines inside a content section span, with classification.
    A heading is brand-coloured (any size >= body) OR large black bold."""
    sp0, sp1 = sec["start_page"], sec["end_page"]
    out = []
    for pno in range(sp0, sp1 + 1):
        if pno < 0 or pno >= doc.page_count:
            continue
        pw = page_dims(doc[pno])[0]
        for ln in get_page_lines(doc[pno]):
            if pno == sp0 and ln["y0"] < sec["start_y"] - 1:
                continue
            if pno == sp1 and ln["y0"] >= sec["end_y"]:
                continue
            t = norm_ws(ln["text"])
            if not t or len(t) > 110 or ln["x0"] > pw * 0.55:
                continue
            if _is_whiteish(ln["color"]):
                continue
            cl = _classify_heading(t)
            coded = cl is not None and cl[0] != "label"
            # A body-size line is accepted as a sub-topic heading only when it is a
            # left-column, code-prefixed line WITH a descriptive title (e.g. Physics
            # "P1.2 Changes of state", CamNat "1.1 Characteristics ..."). This keeps
            # out right-column reference codes ("PM1", "M0.1") and bare code cells.
            strong = cl is not None and (cl[0] in ("decimal", "alnum")
                                         or cl[0] in _MARKER_KINDS) and "." in (cl[1] or "")
            cell_head = (ln["bold"] and strong and ln["x0"] < pw * 0.20
                         and len(cl[2]) >= 4 and ln["size"] >= body_size - 0.3)
            brand_hit = (brand is not None and ln["bold"]
                         and _color_close(ln["color"], brand)
                         and ln["size"] >= body_size + 0.3)
            # Big black headings, OR body-size black headings carrying a code
            # (Economics/GCSE Econ "1." at body+1, which a plain bold body label
            # like "Learning outcomes" never matches).
            black_hit = (ln["bold"] and _is_blackish(ln["color"]) and (
                ln["size"] >= body_size + 2.5
                or (coded and ln["size"] >= body_size + 0.8)))
            # Marker-family headings (Unit Y101 / Component / Paper / Section ...)
            # are often only body-sized bold (e.g. OCR History options), so a valid
            # marker code is accepted at body size too.
            marker_hit = (ln["bold"] and cl is not None and cl[0] in _MARKER_KINDS
                          and ln["size"] >= body_size - 0.5 and len(t) <= 95)
            if not (brand_hit or black_hit or marker_hit or cell_head):
                continue
            out.append({"page": pno, "y": ln["y0"], "x0": ln["x0"],
                        "size": round(ln["size"], 1),
                        "color": ln["color"], "brand": brand_hit, "raw": t,
                        "kind": cl[0] if cl else "label",
                        "code": cl[1] if cl else "",
                        "title": (cl[2] if cl else t),
                        "level": cl[3] if cl else None})
    out.sort(key=lambda h: (h["page"], h["y"]))
    return _merge_wrapped_headings(out)


def _merge_wrapped_headings(heads):
    """Merge a heading line with the line(s) immediately below it when they form
    ONE wrapped heading (same page, same size/colour, ~one line-height apart, and
    the lower line carries no new code -- e.g. "… Programming project (Component 03"
    + "or 04)", or History "… (Units Y101 to" + "Y113)"). Without this a wrapped
    title is mistaken for two separate sub-topic units."""
    out = []
    for h in heads:
        if out:
            p = out[-1]
            gap = h["y"] - p["y"]
            if (h["page"] == p["page"] and 0 <= gap <= max(h["size"], p["size"]) * 1.6
                    and abs(h["size"] - p["size"]) < 0.8 and h["brand"] == p["brand"]
                    and not h["code"]):
                p["raw"] = norm_ws(p["raw"] + " " + h["raw"])
                if not p["title"] or p["title"] == p["raw"]:
                    p["title"] = p["raw"]
                else:
                    p["title"] = norm_ws(p["title"] + " " + (h["title"] or h["raw"]))
                p["y_end_merged"] = True
                continue
        out.append(h)
    return out


def _dedupe_headings(heads):
    """Drop a heading that repeats the previous one's code/text on an adjacent
    page (a running header echoing the unit name), and exact-text duplicates."""
    out, seen = [], set()
    for h in heads:
        key = re.sub(r"[^a-z0-9]", "", (h["code"] + h["title"]).lower()) or \
              re.sub(r"[^a-z0-9]", "", h["raw"].lower())
        if out and out[-1]["code"] and out[-1]["code"] == h["code"] \
                and h["page"] - out[-1]["page"] <= 1 and h["kind"] != "label":
            continue
        if key and key in seen:
            continue
        seen.add(key)
        out.append(h)
    return out


def _assign_levels(heads):
    """Give every heading a concrete level. Coded headings already carry one;
    codeless brand labels get a level from their font-size rank (largest=1)."""
    coded = [h for h in heads if h["level"] is not None]
    if coded:
        # Re-base coded levels so the shallowest present becomes 1.
        base = min(h["level"] for h in coded)
        for h in coded:
            h["level"] = h["level"] - base + 1
    sizes = sorted({h["size"] for h in heads if h["level"] is None}, reverse=True)
    rank = {s: i + 1 for i, s in enumerate(sizes)}
    deepest_coded = max((h["level"] for h in coded), default=0)
    for h in heads:
        if h["level"] is None:
            # codeless labels sit below any coded grouping of the same size band
            h["level"] = deepest_coded + rank.get(h["size"], 1)
    return heads


def _build_tree(heads):
    roots, stack = [], []
    for h in heads:
        node = {"h": h, "level": h["level"], "children": []}
        while stack and stack[-1]["level"] >= node["level"]:
            stack.pop()
        (stack[-1]["children"] if stack else roots).append(node)
        stack.append(node)
    return roots


OVERVIEW_PROSE_GAP = 38.0    # a child this far below its parent => parent has its own prose


def _gap_has_real_prose(doc, pno, y_start, y_end, body_size):
    """True if there is at least one non-table-header, non-chrome text line
    strictly between y_start and y_end on page pno. Used to decide whether a
    section-divider heading (e.g. Economics '2. The role of markets') has real
    teachable prose before its first child, or only a table column-header row
    like 'Topic | Students should be able to:' which must not trigger a
    standalone PDF for the parent heading."""
    if pno < 0 or pno >= doc.page_count:
        return False
    for ln in get_page_lines(doc[pno]):
        if ln["y0"] <= y_start + 1 or ln["y0"] >= y_end - 1:
            continue
        t = norm_ws(ln["text"])
        if not t:
            continue
        # White text on a coloured table-header bar (e.g. "Teaching content |
        # Breadth and depth" on a teal bar in Cambridge Nationals specs).
        if _is_whiteish(ln["color"]):
            continue
        if _COL_HEADER_RE.match(t):
            continue
        if OCR_FOOTER_RE.search(t) or re.fullmatch(r"\d{1,4}", t):
            continue
        if ln["size"] < body_size - 1.5:
            continue
        return True
    return False


def _collect_units_from_tree(roots, sec, doc=None, body_size=None):
    """Cut the heading tree into sub-topic units, mirroring the AQA tool: a coded
    grouping with children becomes an overview file (when it carries its own
    prose) plus one file per child sub-topic, recursing to the deepest level;
    where a grouping has no prose its heading leads its first child's file."""
    units = []

    def start_of(node):
        return node["h"]["page"], node["h"]["y"]

    def walk(node, lead):
        # `lead` = (page, y) the file should begin at (parent heading folded in).
        children = node["children"]
        if not children:
            units.append({"node": node, "start": lead})
            return
        # Always fold the parent heading (and any intro prose or column headers
        # between it and the first child) into the first child's file. This
        # ensures section-divider headings such as "1 – Pure Mathematics" or
        # "2. The role of markets" appear at the top of the first subtopic file
        # rather than in a separate standalone PDF.
        for k, c in enumerate(children):
            cl = lead if k == 0 else start_of(c)
            walk(c, cl)

    for r in roots:
        walk(r, start_of(r))

    units.sort(key=lambda u: (u["start"][0], u["start"][1]))
    # Fill in end positions (next unit start; last -> section end).
    out = []
    for i, u in enumerate(units):
        node = u["node"]["h"]
        sp, sy = u["start"]
        if i + 1 < len(units):
            ep, ey = units[i + 1]["start"]
        else:
            ep, ey = sec["end_page"], sec["end_y"]
        out.append({"code": node["code"], "title": _clean_unit_title(node["title"] or node["raw"]),
                    "kind": node["kind"], "start_page": sp, "start_y": sy,
                    "end_page": ep, "end_y": ey})
    return out


def _harvest_code_cells(doc, sec, body_size):
    """Recover deep sub-topics whose code lives as a STANDALONE left-column table
    cell at body size (e.g. Economics '1.1' / '2.1' with the title on the line
    below). These are not heading-sized so the normal scan misses them; we require
    the whole line to be a pure decimal code (>=1 dot) in the left column."""
    sp0, sp1 = sec["start_page"], min(sec["end_page"], doc.page_count - 1)
    out = []
    for pno in range(max(0, sp0), sp1 + 1):
        pw = page_dims(doc[pno])[0]
        lines = sorted(get_page_lines(doc[pno]), key=lambda l: (round(l["y0"], 1), l["x0"]))
        for ln in lines:
            if pno == sp0 and ln["y0"] < sec["start_y"] - 1:
                continue
            if pno == sp1 and ln["y0"] >= sec["end_y"]:
                continue
            t = norm_ws(ln["text"])
            if not re.fullmatch(r"\d{1,2}(?:\.\d{1,3}){1,2}", t):
                continue
            if ln["x0"] > pw * 0.20 or not ln["bold"]:
                continue
            title = ""                       # the row label, on the line(s) below at ~same x
            for o in lines:
                if abs(o["x0"] - ln["x0"]) < 60 and 0 <= o["y0"] - ln["y0"] < 42:
                    ot = norm_ws(o["text"])
                    if (ot and ot != t and not re.fullmatch(r"[\d.]+", ot)
                            and not re.match(r"(?:explain|evaluate|analyse|describe|"
                                             r"calculate|state|define|identify)\b", ot, re.I)):
                        title = ot
                        break
            out.append({"page": pno, "y": ln["y0"], "x0": ln["x0"],
                        "size": round(ln["size"], 1),
                        "color": ln["color"], "brand": False, "raw": t, "kind": "decimal",
                        "code": t, "title": title, "level": 1 + t.count(".")})
    return out


_COL_HEADER_RE = re.compile(
    r"^(area\s+of\s+study|content|topic|learners?\s+should|students?\s+should"
    r"|reference|key\s+knowledge|key\s+concepts|amplification|guidance|sub.?topic"
    r"|additional\s+guidance|specification|detail|notes?|opportunities|maths"
    r"|working\s+scientifically|practical|to\s+include|statement"
    r"|teaching|breadth|objectives?|assessment\s+criteria|skills?\s+and"
    r"|knowledge\s+and|understanding)\b", re.I)


def _harvest_row_labels(doc, sec, body_size):
    """Last-resort split for code-LESS table specs (e.g. A-level Business 'Area of
    Study' rows): treat each bold multi-line cell in the leftmost column as a
    sub-topic. Column-header cells are skipped. Used only when no coded/heading
    structure was found, so it can't disturb specs that split normally."""
    sp0, sp1 = sec["start_page"], min(sec["end_page"], doc.page_count - 1)
    out = []
    for pno in range(max(0, sp0), sp1 + 1):
        pw = page_dims(doc[pno])[0]
        lines = sorted(get_page_lines(doc[pno]), key=lambda l: (round(l["y0"], 1), l["x0"]))
        col = [ln for ln in lines
               if ln["x0"] < pw * 0.13 and ln["bold"] and abs(ln["size"] - body_size) < 1.6
               and not _is_whiteish(ln["color"])
               and not (pno == sp0 and ln["y0"] < sec["start_y"] - 1)
               and not (pno == sp1 and ln["y0"] >= sec["end_y"])]
        groups = []
        for ln in col:
            if (groups and ln["y0"] - groups[-1][-1]["y1"] < 16
                    and abs(ln["x0"] - groups[-1][0]["x0"]) < 8):
                groups[-1].append(ln)
            else:
                groups.append([ln])
        for g in groups:
            title = norm_ws(" ".join(x["text"] for x in g))
            if not title or len(title) < 3 or len(title) > 60:
                continue
            # Skip column headers and prose that merged into the cell, and any
            # label that swallowed a header phrase (e.g. 'Practices Area of study').
            if _COL_HEADER_RE.match(title) or title.endswith(":"):
                continue
            # drop a label that swallowed a column header / prose anywhere in it
            if re.search(r"area\s+of\s+study|should\s+be\s+able|\bable\s+to\b"
                         r"|learners?\b|students?\b|study\s+of|\bthrough\b|key\s+knowledge",
                         title, re.I):
                continue
            out.append({"page": pno, "y": g[0]["y0"], "x0": g[0]["x0"],
                        "size": round(g[0]["size"], 1),
                        "color": g[0]["color"], "brand": False, "raw": title,
                        "kind": "rowlabel", "code": "", "title": title, "level": 1})
    return out


def _merge_by_pos(base, extra):
    """Add `extra` headings to `base`, skipping any at a position already taken."""
    seen = {(h["page"], round(h["y"], 0)) for h in base}
    out = list(base)
    for h in extra:
        key = (h["page"], round(h["y"], 0))
        if key in seen:
            continue
        seen.add(key)
        out.append(h)
    out.sort(key=lambda h: (h["page"], h["y"]))
    return out


def _sort_column_aware(heads, doc):
    """Re-sort headings for two-column layout specs (e.g. OCR Further Maths).
    When a single page has headings in both a left column (x < ~45% of page
    width) and a right column (x >= ~45%), a naive y-sort produces wrong order:
    the right-column top (small y) appears before the left-column bottom (large
    y), causing the last left-column topic to absorb everything to the right.
    Fix: on two-column pages, sort left-column headings before right-column
    ones regardless of y, preserving top-to-bottom order within each column."""
    by_page: dict = {}
    for h in heads:
        by_page.setdefault(h["page"], []).append(h)

    two_col: set = set()
    for pno, phs in by_page.items():
        if pno < 0 or pno >= doc.page_count:
            continue
        pw = page_dims(doc[pno])[0]
        split = pw * 0.44
        has_left = any(h["x0"] < split for h in phs)
        has_right = any(h["x0"] >= split + pw * 0.04 for h in phs)
        if has_left and has_right:
            two_col.add(pno)

    if not two_col:
        return heads  # already sorted correctly

    def _col_key(h):
        if h["page"] not in two_col:
            return (h["page"], 0, h["y"])
        pw = page_dims(doc[h["page"]])[0]
        col = 1 if h["x0"] >= pw * 0.44 else 0
        return (h["page"], col, h["y"])

    return sorted(heads, key=_col_key)


def _prefer_landscape_headings(heads, doc):
    """For specs that have a portrait overview page (e.g. OCR Further Maths):
    when the same topic code (e.g. '4.05') appears on both a portrait page
    (rotation=0) and a landscape content page (rotation=90/270), drop the
    portrait instances and keep the landscape ones.  The landscape pages carry
    the actual content so their positions give the correct crop boundaries.
    If all pages share the same rotation the function is a no-op."""
    from collections import defaultdict
    code_rots: dict = defaultdict(set)
    for h in heads:
        code = h.get("code", "")
        if code and 0 <= h["page"] < doc.page_count:
            code_rots[code].add(doc[h["page"]].rotation)

    # Codes that appear on BOTH portrait (0°) and landscape (90°/270°) pages
    mixed = {code for code, rots in code_rots.items()
             if 0 in rots and rots - {0}}
    if not mixed:
        return heads

    return [h for h in heads
            if not (h.get("code") in mixed
                    and 0 <= h["page"] < doc.page_count
                    and doc[h["page"]].rotation == 0)]


def collect_units_for_section(doc, sec, body_size, brand):
    """Sub-topic units inside one content section. Falls back to a single
    whole-section unit when no consistent internal heading structure exists."""
    heads = _heading_candidates(doc, sec, body_size, brand)
    # Pull in deep sub-topic codes that live as standalone left-column table cells
    # (Economics 1.1/2.1, etc.) so the split reaches the finest numbered level.
    cells = _harvest_code_cells(doc, sec, body_size)
    if len(cells) >= 2:
        heads = _merge_by_pos(heads, cells)
    heads = _prefer_landscape_headings(heads, doc)
    heads = _sort_column_aware(heads, doc)
    heads = _dedupe_headings(heads)
    # Keep only real classified headings for the tree; drop stray labels unless
    # they are the only structure we have (codeless brand labels = Psychology).
    coded = [h for h in heads if h["kind"] != "label"]
    structured = coded if len(coded) >= 2 else [h for h in heads if h["brand"]]
    structured = [h for h in structured if h["title"] or h["code"]]

    if len(structured) < 2:
        # Code-less table spec: fall back to leftmost-column row labels.
        rows = _harvest_row_labels(doc, sec, body_size)
        rows = [r for r in rows if not STOP_UNIT_RE.search(r["title"])]
        if len(rows) >= 2:
            structured = rows

    if len(structured) < 2:
        # No internal split -> the whole content section is one unit.
        title = re.sub(r"^\s*\d{1,2}[a-z]?(?:\([ivx]+\))?\.?\s*", "", sec["title"])
        title = re.sub(r"^(?:detailed\s+|core\s+)?(?:subject\s+)?content\s*(?:of|for|:)\s*",
                       "", title, flags=re.I).strip()
        return [{"code": sec["code"], "title": title or sec["title"], "kind": "section",
                 "start_page": sec["start_page"], "start_y": sec["start_y"],
                 "end_page": sec["end_page"], "end_y": sec["end_y"]}]

    _assign_levels(structured)
    tree = _build_tree(structured)
    units = _collect_units_from_tree(tree, sec, doc=doc, body_size=body_size)

    # If the section starts before the first detected subtopic heading (intro prose
    # or a section title above the first heading), pull the first subtopic's start
    # back to include that content rather than creating a separate overview file.
    f = units[0]
    if (f["start_page"] > sec["start_page"]) or (f["start_y"] - sec["start_y"] > 2):
        units[0]["start_page"] = sec["start_page"]
        units[0]["start_y"] = sec["start_y"]
    return units


def collect_subsections(doc, body_size, brand):
    """All sub-topic units across every content section, in document order."""
    sections, method = find_content_sections(doc, body_size)
    units = []
    for sec in sections:
        units.extend(collect_units_for_section(doc, sec, body_size, brand))
    # Final ordering + drop empties.
    units = [u for u in units if u["end_page"] > u["start_page"]
             or (u["end_page"] == u["start_page"] and u["end_y"] > u["start_y"] + 4)]
    # Drop post-content material (assessment / prior knowledge / appendix) that can
    # slip in at a section boundary; never drop the only unit of a section.
    units = [u for u in units if not STOP_UNIT_RE.search(u.get("title", ""))]
    units.sort(key=lambda u: (u["start_page"], u["start_y"]))
    return units, method, len(sections)


# ----------------------------------------------------------------------------
# Per-page chrome detection
# ----------------------------------------------------------------------------

def _fill_not_white(fill):
    return fill is not None and not (fill[0] > 0.95 and fill[1] > 0.95 and fill[2] > 0.95)


def page_content_box(page, body_size=11.0):
    """(x0, x1) of the page's content column in VISUAL coords. From the top
    decorative brand band's width when present, else default OCR margins, then
    trimmed to just inside any brand-coloured SIDE TAB hugging an outer edge.
    On rotated (landscape) pages the running footer/version line lands in a side
    margin (not the bottom), so footer-like text in the outer x-margins is trimmed
    too. Mid-edge landscape side tabs are also dropped in ink_bbox."""
    pw, ph = page_dims(page)
    left, right = pw * 0.05, pw * 0.95
    band = None
    for r, fill in get_page_drawings(page):
        if (r.y1 <= ph * 0.18 and r.width > pw * 0.55 and r.width < pw * 0.985
                and (r.y1 - r.y0) > 6 and _fill_not_white(fill)):
            if band is None or r.width > band.width:
                band = r
    if band is not None:
        left, right = band.x0, band.x1
    for r, fill in get_page_drawings(page):
        if not _fill_not_white(fill):
            continue
        w, h = r.width, (r.y1 - r.y0)
        if not (12 < w < 110 and 14 < h < 200):
            continue
        # a side tab hugs an outer edge at (almost) any vertical position
        if r.x0 < pw * 0.10:            # left side tab
            left = max(left, r.x1 + 2)
        elif r.x1 > pw * 0.90:          # right side tab
            right = min(right, r.x0 - 2)
    if page.rotation in (90, 270):
        for ln in get_page_lines(page):
            t = norm_ws(ln["text"])
            if not t:
                continue
            chrome = (ln["size"] <= body_size - 0.5 or OCR_FOOTER_RE.search(t)
                      or re.fullmatch(r"\d{1,4}", t))
            if not chrome:
                continue
            if ln["x1"] < pw * 0.13:
                left = max(left, ln["x1"] + 2)
            elif ln["x0"] > pw * 0.87:
                right = min(right, ln["x0"] - 2)
    if right - left < pw * 0.3:         # detection went wrong -> safe default
        return pw * 0.05, pw * 0.95
    return left, right


def margin_cuts(page, body_size, pw, ph):
    """(header_bottom, footer_top): y below which the top brand band/header ends
    and y above which the footer begins (VISUAL coords)."""
    top_zone = ph * 0.18
    bot_zone = ph * 0.86
    header_bottom, footer_top = 0.0, ph

    # Top brand band (a wide, tall, coloured fill in the top margin) is chrome,
    # but a full-bleed background (covers ~whole width) is not.
    for r, fill in get_page_drawings(page):
        if r.width < pw * 0.5:
            continue
        if (r.y1 <= top_zone and r.width < pw * 0.985 and (r.y1 - r.y0) > 6
                and _fill_not_white(fill)):
            header_bottom = max(header_bottom, r.y1)
        elif r.y0 >= bot_zone and (r.y1 - r.y0) <= 3.0:   # thin footer rule only
            footer_top = min(footer_top, r.y0)

    for ln in get_page_lines(page):
        t = norm_ws(ln["text"])
        if not t:
            continue
        if ln["y0"] >= bot_zone:
            is_foot = (ln["size"] <= body_size - 0.5 or OCR_FOOTER_RE.search(t)
                       or re.fullmatch(r"\d{1,4}", t))
            if is_foot:
                footer_top = min(footer_top, ln["y0"])
    return header_bottom, footer_top


# ----------------------------------------------------------------------------
# Ink-based content box (board-agnostic, from the AQA/Edexcel tools)
# ----------------------------------------------------------------------------

PAD_LEFT = 6.0
PAD_RIGHT = 13.0
PAD_TOP = 6.0
PAD_BOTTOM = 13.0
START_TOP = 6.0
GAP = 2.0
MIN_BAND = 24.0

INK_DPI = 108.0
INK_THRESH = 244


def _page_ink(page, cache):
    pno = page.number
    hit = cache.get(pno)
    if hit is None:
        scale = INK_DPI / 72.0
        # Native render == the VISUAL page (rotation applied), matching the visual
        # coords used everywhere else.
        pm = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
        arr = np.frombuffer(pm.samples, dtype=np.uint8)
        arr = arr.reshape(pm.height, pm.stride // pm.n, pm.n)[:, :pm.width, :3]
        hit = (arr, scale, pm.width, pm.height)
        cache[pno] = hit
    return hit


def ink_bbox(page, x_lo, x_hi, y_lo, y_hi, cache):
    """Bounding box (pt) of real rendered ink in the window, or None. Measuring
    pixels (not the text bbox) avoids clipping fonts that under-report widths.
    Isolated ink runs in the extreme outer margin (side tabs) are dropped."""
    arr, scale, W, H = _page_ink(page, cache)
    a = max(0, int(x_lo * scale)); b = min(W, int(round(x_hi * scale)))
    c = max(0, int(y_lo * scale)); d = min(H, int(round(y_hi * scale)))
    if b <= a or d <= c:
        return None
    ink = (arr[c:d, :, :] < INK_THRESH).any(axis=2)
    col_any = ink.any(axis=0)
    col_any[:a] = False; col_any[b:] = False
    idx = np.where(col_any)[0]
    if len(idx) == 0:
        return None
    gap = max(8, int(12 * scale))
    groups, s, p = [], idx[0], idx[0]
    for i in idx[1:]:
        if i - p > gap:
            groups.append((s, p)); s = i
        p = i
    groups.append((s, p))
    out_l, out_r = x_lo * scale, x_hi * scale
    kept = [g for g in groups if not (g[1] < out_l or g[0] > out_r)]
    if not kept:
        kept = groups
    # Drop a side TAB: a narrow ink run sitting in the outer margin, separated
    # from the body by a clear gap (the white section number on its colour tab --
    # on baked landscape pages it lands ~85-90% across, beyond the table). A real
    # text column is wider and/or not gap-isolated, so it is never dropped.
    pw = page_dims(page)[0]
    narrow = 0.12 * pw * scale
    big_gap = 0.035 * pw * scale
    out_margin = 0.20 * pw * scale
    while len(kept) >= 2:
        g = kept[-1]                                   # rightmost
        if (g[1] - g[0]) < narrow and (g[0] - kept[-2][1]) > big_gap \
                and g[0] > (W - out_margin):
            kept.pop(); continue
        g = kept[0]                                    # leftmost
        if (g[1] - g[0]) < narrow and (kept[1][0] - g[1]) > big_gap \
                and g[1] < out_margin:
            kept.pop(0); continue
        break
    minx = min(g[0] for g in kept); maxx = max(g[1] for g in kept)
    row_any = ink[:, minx:maxx + 1].any(axis=1)
    ridx = np.where(row_any)[0]
    if len(ridx) == 0:
        return None
    return minx / scale, (c + ridx[0]) / scale, (maxx + 1) / scale, (c + ridx[-1] + 1) / scale


def page_crop(page, body_size, is_start, is_end, start_y, end_y, cache):
    """fitz.Rect to crop this page to (VISUAL coords), or None if empty."""
    pw, ph = page_dims(page)
    header_bottom, footer_top = margin_cuts(page, body_size, pw, ph)
    cx0, cx1 = page_content_box(page, body_size)
    head = header_bottom + 2.0
    foot = footer_top - 2.0

    y_lo = max(head, start_y) if is_start else head
    y_hi = min(foot, end_y) if is_end else foot

    # Bleeding fix: when this is the last page of a unit, a full-width colored
    # heading bar for the NEXT unit may start just above end_y (bar top < end_y
    # but bar bottom > end_y - 35) and bleed into this unit's crop.  Clip y_hi
    # to just before the bar top.  Height gated to 5-35 pt to exclude tall
    # table-background fills; width gated to 45% of content column width.
    if is_end and end_y < 1e9:
        cw = cx1 - cx0
        for r, fill in get_page_drawings(page):
            h = r.y1 - r.y0
            if (fill is not None and _fill_not_white(fill)
                    and r.width >= cw * 0.45
                    and 5.0 <= h <= 35.0
                    and r.y0 < end_y and r.y1 > end_y - 35):
                y_hi = min(y_hi, r.y0 - 1.0)

    if y_hi - y_lo < MIN_BAND:
        return None

    bb = ink_bbox(page, cx0, cx1, y_lo, y_hi, cache)
    if bb is None:
        return None
    ix0, iy0, ix1, iy1 = bb

    top = max(head, (start_y - START_TOP) if is_start else (iy0 - PAD_TOP))
    bottom = iy1 + PAD_BOTTOM
    if is_end:
        bottom = min(bottom, end_y - GAP)
    bottom = min(foot, bottom, ph)
    top = max(0.0, top)
    if bottom - top < MIN_BAND:
        return None
    # Clamp to the content box so PAD never pushes the crop back over an excluded
    # side tab (the section-number tab sits just outside [cx0, cx1]).
    left = max(cx0, ix0 - PAD_LEFT)
    right = min(cx1, ix1 + PAD_RIGHT)
    if right - left < MIN_BAND:
        return None
    return fitz.Rect(left, top, right, bottom)


# ----------------------------------------------------------------------------
# Emit -- compose cropped regions onto uniform A4 sheets
# ----------------------------------------------------------------------------

A4 = fitz.paper_rect("a4")
A4_MARGIN_TOP = 42.0
A4_MARGIN_BOTTOM = 42.0
A4_MARGIN_SIDE = 30.0
RASTER_DPI = 220.0      # render DPI for /Rotate landscape pages (see emit_doc)


def side_tab_rects(page):
    """Brand-coloured section-number SIDE TAB rectangles (VISUAL coords). On
    landscape (/Rotate) pages the tab sits mid-edge -- overlapping content columns
    in x AND y -- so it can't be removed by a margin crop; emit_doc paints it out
    of the rasterised image instead. A tab is a small coloured fill that hugs a
    page edge (its bbox runs off the edge)."""
    pw, ph = page_dims(page)
    out = []
    for r, fill in get_page_drawings(page):
        if not _fill_not_white(fill):
            continue
        w, h = r.width, (r.y1 - r.y0)
        if not (10 < w < 120 and 12 < h < 220):
            continue
        if (r.x0 < pw * 0.03 or r.x1 > pw * 0.97
                or r.y0 < ph * 0.03 or r.y1 > ph * 0.97):
            out.append(r)
    return out


def emit_doc(src_doc, plan, a4=True):
    """Build the output PDF. Each crop is placed at natural scale on a uniform A4
    sheet (landscape A4 when the source crop is landscape), centred & top-aligned,
    shrunk only if it would otherwise overflow.

    Crop rects are in VISUAL coords. An upright page embeds straight into the
    output as vectors (fonts/colours preserved). A /Rotate 90|270 page (OCR's
    landscape GCSE-science / Maths specs) can't be vector-clipped (show_pdf_page
    validates the clip against the rotated rect yet renders with an unrotated one),
    so it is rendered upright to a high-DPI image of exactly the crop region and
    inserted -- crisp and correctly oriented."""
    out = fitz.open()
    for pidx, rect in plan:
        sp = src_doc[pidx]
        rotated = sp.rotation in (90, 270)
        ppw, pph = page_dims(sp)
        vw, vh = rect.width, rect.height          # rect is already visual
        if not a4:
            out.insert_pdf(src_doc, from_page=pidx, to_page=pidx)
            if not rotated:
                out[-1].set_cropbox(rect)
            continue
        # Sheet orientation follows the SOURCE page, not the crop aspect, so a
        # portrait spec never lands on a landscape sheet (and vice-versa).
        landscape = ppw > pph
        pw = A4.height if landscape else A4.width
        ph = A4.width if landscape else A4.height
        page = out.new_page(width=pw, height=ph)
        avail_w = pw - 2 * A4_MARGIN_SIDE
        avail_h = ph - A4_MARGIN_TOP - A4_MARGIN_BOTTOM
        scale = min(1.0, avail_w / vw, avail_h / vh)
        tw, th = vw * scale, vh * scale
        tx = (pw - tw) / 2.0
        target = fitz.Rect(tx, A4_MARGIN_TOP, tx + tw, A4_MARGIN_TOP + th)
        if rotated:
            s = RASTER_DPI / 72.0
            pix = sp.get_pixmap(matrix=fitz.Matrix(s, s), clip=rect)
            page.insert_image(target, pixmap=pix)
            # Overlay white over any section-number tab inside the crop (it sits
            # mid-edge, overlapping the table, so it can't be cropped away). Map
            # its visual rect into the placed target rectangle and paint it out.
            sx = target.width / rect.width
            sy = target.height / rect.height
            for tr in side_tab_rects(sp):
                ax0 = max(tr.x0, rect.x0); ay0 = max(tr.y0, rect.y0)
                ax1 = min(tr.x1, rect.x1); ay1 = min(tr.y1, rect.y1)
                if ax1 <= ax0 or ay1 <= ay0:
                    continue
                wr = fitz.Rect(target.x0 + (ax0 - rect.x0) * sx - 1,
                               target.y0 + (ay0 - rect.y0) * sy - 1,
                               target.x0 + (ax1 - rect.x0) * sx + 1,
                               target.y0 + (ay1 - rect.y0) * sy + 1)
                page.draw_rect(wr, color=(1, 1, 1), fill=(1, 1, 1))
        else:
            page.show_pdf_page(target, src_doc, pidx, clip=rect)
    return out


# ----------------------------------------------------------------------------
# Build PDFs
# ----------------------------------------------------------------------------

def _safe_name(code, title, seq):
    title = re.sub(r"\s+", " ", (title or "").replace("�", "")).strip()
    title = re.sub(r"[^A-Za-z0-9]+", "_", title).strip("_")[:42]
    code = re.sub(r"[^A-Za-z0-9]+", "_", code or "").strip("_")
    stem = "_".join(p for p in (code, title) if p) or "subsection"
    return f"{seq:03d}_{stem}.pdf"


def _plan_for_unit(doc, body_size, u, cache):
    sp0 = u["start_page"]
    sp1 = min(u["end_page"], doc.page_count - 1)
    plan = []
    for pidx in range(sp0, sp1 + 1):
        if pidx < 0 or pidx >= doc.page_count:
            continue
        rect = page_crop(doc[pidx], body_size,
                         is_start=(pidx == sp0), is_end=(pidx == sp1),
                         start_y=u["start_y"], end_y=u["end_y"], cache=cache)
        if rect is not None:
            plan.append((pidx, rect))
    return plan


def build_subsection_pdfs(src_path, out_dir, proof=False, a4=True):
    doc = fitz.open(src_path)
    body_size = estimate_body_size(doc)
    brand = detect_brand_color(doc, body_size)
    units, method, n_sec = collect_subsections(doc, body_size, brand)
    info = {"method": method, "sections": n_sec, "units": len(units),
            "files": 0, "warnings": [], "manifest": []}

    def _cleanup():
        doc.close()

    if not units:
        if looks_like_non_spec(doc):
            info["warnings"].append("Looks like a mark scheme / question paper, not a "
                                    "full specification; nothing written.")
        else:
            info["warnings"].append("No syllabus content sub-topics located.")
        _cleanup()
        return info

    os.makedirs(out_dir, exist_ok=True)
    for old in (_glob.glob(os.path.join(out_dir, "*.pdf"))
                + _glob.glob(os.path.join(out_dir, "*.png"))
                + _glob.glob(os.path.join(out_dir, "_subsections.json"))):
        try:
            os.remove(old)
        except OSError:
            pass

    cache = {}
    seq = 0
    for u in units:
        plan = _plan_for_unit(doc, body_size, u, cache)
        if not plan:
            continue
        seq += 1
        out = emit_doc(doc, plan, a4=a4)
        fname = _safe_name(u["code"], u["title"], seq)
        fpath = os.path.join(out_dir, fname)
        out.save(fpath, garbage=4, deflate=True)
        info["files"] += 1
        info["manifest"].append({"file": fname, "code": u["code"], "title": u["title"],
                                 "kind": u.get("kind", ""), "pages": out.page_count})
        if proof and seq == 1:
            out[0].get_pixmap(dpi=150).save(fpath[:-4] + "_proof.png")
        out.close()

    if info["files"] == 0:
        info["warnings"].append("Sub-topics found but produced no content pages after trimming.")

    with open(os.path.join(out_dir, "_subsections.json"), "w", encoding="utf-8") as fh:
        json.dump({"method": method, "sections": n_sec, "n": info["files"],
                   "subsections": info["manifest"]}, fh, ensure_ascii=False, indent=2)
    _cleanup()
    return info


def build_section_pdf(src_path, out_path, proof=False, a4=True):
    """--mode section: one PDF per whole content section."""
    doc = fitz.open(src_path)
    body_size = estimate_body_size(doc)
    brand = detect_brand_color(doc, body_size)
    sections, method = find_content_sections(doc, body_size)
    info = {"method": method, "spans": len(sections), "pages_out": 0, "warnings": []}

    def _cleanup():
        doc.close()

    if not sections:
        info["warnings"].append("No content section located.")
        _cleanup()
        return info
    cache = {}
    plan = []
    for sec in sections:
        sp0, sp1 = sec["start_page"], min(sec["end_page"], doc.page_count - 1)
        for pidx in range(sp0, sp1 + 1):
            rect = page_crop(doc[pidx], body_size,
                             is_start=(pidx == sp0), is_end=(pidx == sp1),
                             start_y=sec["start_y"], end_y=sec["end_y"], cache=cache)
            if rect is not None:
                plan.append((pidx, rect))
    if not plan:
        info["warnings"].append("Section found but produced no content pages.")
        _cleanup()
        return info
    out = emit_doc(doc, plan, a4=a4)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    out.save(out_path, garbage=4, deflate=True)
    info["pages_out"] = out.page_count
    if proof:
        out[0].get_pixmap(dpi=150).save(out_path[:-4] + "_proof_p1.png")
    out.close()
    _cleanup()
    return info


# ----------------------------------------------------------------------------
# Driver
# ----------------------------------------------------------------------------

def find_pdfs(root):
    skip = {"extracted_syllabus", "extracted_syllabus_pdf",
            "extracted_syllabus_pdf_edexcel", "extracted_syllabus_pdf_aqa",
            "extracted_syllabus_pdf_ocr", "__pycache__"}
    out = []
    for dirpath, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in skip]
        for f in files:
            if f.lower().endswith(".pdf"):
                out.append(os.path.join(dirpath, f))
    return sorted(out)


def main():
    ap = argparse.ArgumentParser(description="Crop OCR syllabus content into per-sub-topic PDFs.")
    ap.add_argument("pdfs", nargs="*", help="Specific PDF files (default: scan --root).")
    ap.add_argument("--root", default=".", help="Root folder to scan for PDFs.")
    ap.add_argument("--out", default="extracted_syllabus_pdf_ocr", help="Output folder.")
    ap.add_argument("--mode", choices=["subsection", "section"], default="subsection")
    ap.add_argument("--proof", action="store_true", help="Render a proof PNG of the first file/page.")
    ap.add_argument("--no-a4", dest="a4", action="store_false",
                    help="Keep each page at its cropped size instead of a uniform A4 sheet.")
    ap.set_defaults(a4=True)
    args = ap.parse_args()

    root = os.path.abspath(args.root)
    out_root = os.path.abspath(args.out)
    os.makedirs(out_root, exist_ok=True)

    pdfs = [os.path.abspath(p) for p in args.pdfs] if args.pdfs else find_pdfs(root)
    if not pdfs:
        print("No PDFs found.", file=sys.stderr)
        return 1

    by_dir = {}
    for p in pdfs:
        by_dir.setdefault(os.path.dirname(p), []).append(p)

    def out_dir_for(path):
        rel_dir = os.path.relpath(os.path.dirname(path), root).replace("\\", "/")
        base = os.path.join(out_root, rel_dir)
        if len(by_dir[os.path.dirname(path)]) > 1:
            stem = os.path.splitext(os.path.basename(path))[0]
            m = re.search(r"(pub\d{4}|\d{4}_to_\w+)", stem)
            tag = m.group(0) if m else re.sub(r"[^A-Za-z0-9]+", "", stem)[-8:]
            base = os.path.join(base, tag)
        return base

    report = []
    for path in pdfs:
        rel = os.path.relpath(path, root).replace("\\", "/")
        try:
            if args.mode == "section":
                out_path = os.path.join(out_root, rel)
                info = build_section_pdf(path, out_path, proof=args.proof, a4=args.a4)
                status = "OK" if info["pages_out"] else "EMPTY"
                report.append({"pdf": rel, "status": status, "mode": "section", **info})
                print(f"[{status:5}] {rel}  method={info['method']} spans={info['spans']} "
                      f"pages={info['pages_out']}"
                      + (f"  !{info['warnings'][0]}" if info["warnings"] else ""))
            else:
                out_dir = out_dir_for(path)
                info = build_subsection_pdfs(path, out_dir, proof=args.proof, a4=args.a4)
                status = "OK" if info["files"] else "EMPTY"
                report.append({"pdf": rel, "status": status, "mode": "subsection",
                               "method": info["method"], "sections": info["sections"],
                               "units": info["units"], "files": info["files"],
                               "warnings": info["warnings"]})
                print(f"[{status:5}] {rel}  method={info['method']} sec={info['sections']} "
                      f"files={info['files']}"
                      + (f"  !{info['warnings'][0]}" if info["warnings"] else ""))
        except Exception as e:  # noqa
            report.append({"pdf": rel, "status": "ERROR", "error": repr(e),
                           "trace": traceback.format_exc()})
            print(f"[ERROR] {rel}: {e!r}", file=sys.stderr)

    with open(os.path.join(out_root, "_pdf_extraction_report.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)

    ok = sum(1 for r in report if r["status"] == "OK")
    empty = sum(1 for r in report if r["status"] == "EMPTY")
    err = sum(1 for r in report if r["status"] == "ERROR")
    print(f"\n=== DONE: {len(report)} PDFs | OK={ok} EMPTY={empty} ERROR={err} ===")
    print(f"Syllabus PDFs written under: {out_root}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
