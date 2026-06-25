#!/usr/bin/env python3
"""
extract_syllabus_pdf.py  (Edexcel / Pearson)  --  Carve the Edexcel "subject
content" (the syllabus) out of each Edexcel specification PDF into NEW PDFs that
preserve the original page exactly (fonts, colours, table styling, two-column
layout) -- only the running header/footer chrome of every page is cropped away.

This is the Edexcel counterpart of the AQA `extract_syllabus_pdf.py`. The output
format is identical: one A4 PDF per teachable sub-topic, mirroring the source
folder tree, plus a `_subsections.json` manifest per spec.

Why Edexcel needs its own detector
----------------------------------
Edexcel specs are laid out very differently from AQA, and differently from each
other across the six qualifications (A_Level, GCSE, IGCSE, International_A_Level,
iLowerSecondary, iPrimary) and across the 2008-2016 "legacy" vs 2017+ "current"
generations:

* The syllabus SECTION is named many ways: "Knowledge, skills and understanding"
  (current sciences/English), "Subject content and assessment information"
  (humanities / languages / maths / arts), "Subject content", "<Subject> content"
  (e.g. "Chemistry content" on IGCSE/IAL), "Detailed subject content" /
  "Content description" (new IGCSE), "Specification content" (legacy). Some legacy
  PDFs have no section heading at all -- they are organised directly as "Unit N"
  blocks.
* The teachable SUB-TOPIC unit is also named many ways: "Topic N" (sciences),
  "Theme N" (business / languages), "Component N" (English / Drama / Music / Art /
  D&T), "Paper N" / "Paper N, Option X" (maths / RS / history), "Area of study N"
  + "Option NX" (geography / RS), "Unit N" (legacy + IAL), "Section N" (legacy
  sciences), or a bare decimal "1 Principles of chemistry" (IGCSE).
* Chrome differs from AQA: current specs have NO running header, but each topic
  heading sits near the page top behind a full-width colour bar; legacy specs DO
  carry a running header but at a *large* font. So neither "wide bar in the top
  margin" nor "small font" identifies chrome reliably -- we detect chrome by
  REPETITION across pages instead.

How the region is found
-----------------------
1. Locate every syllabus SECTION span (TOC bookmark whose title matches the
   section names above; font-geometry fallback when there is no usable outline;
   whole-document fallback for the legacy "Unit N" specs).
2. Within each span, find the sub-topic unit headings (marker words above, plus
   bare-decimal headings) and pick the finest consistent granularity by font
   size, so e.g. Geography splits at Topic/Option level, History at Paper-Option
   level, sciences at Topic level.
3. Crop every page of a unit to its real rendered ink between the detected
   header/footer, exactly like the AQA tool, so nothing is clipped and no chrome
   leaks. Each crop is placed on a uniform A4 sheet.

Usage
-----
    python extract_syllabus_pdf.py                 # scan ./ -> ./extracted_syllabus_pdf_edexcel/
    python extract_syllabus_pdf.py --root DIR --out OUTDIR
    python extract_syllabus_pdf.py path/to/one.pdf [more.pdf ...]
    python extract_syllabus_pdf.py one.pdf --proof # also render a proof PNG per spec
    python extract_syllabus_pdf.py --mode section  # one PDF per whole syllabus section
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
# Small text helpers (self-contained -- no AQA imports)
# ----------------------------------------------------------------------------

def norm_ws(s: str) -> str:
    """Collapse all whitespace (incl tabs / nbsp) to single spaces, strip ends."""
    return re.sub(r"[\s ]+", " ", s or "").strip()


def get_page_lines(page) -> list[dict]:
    """Visual text lines on a page with geometry + font info.
    Each line: {text, x0, y0, x1, y1, size, bold}."""
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
            x0 = min(s["bbox"][0] for s in spans)
            y0 = min(s["bbox"][1] for s in spans)
            x1 = max(s["bbox"][2] for s in spans)
            y1 = max(s["bbox"][3] for s in spans)
            size = max(s["size"] for s in spans)
            fonts = " ".join(s["font"] for s in spans).lower()
            bold = any(k in fonts for k in ("bold", "black", "semibold", "heavy"))
            out.append({"text": text, "x0": x0, "y0": y0, "x1": x1, "y1": y1,
                        "size": size, "bold": bold})
    return out


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
    """Heuristic: a mark scheme / question paper / issue-summary, not a full spec."""
    txt = "\n".join(doc[i].get_text("text") for i in range(min(3, doc.page_count))).lower()
    return ("mark scheme" in txt or "question paper" in txt) and "specification" not in txt


def metadata_from_path(path: str, root: str) -> dict:
    rel = os.path.relpath(path, root).replace("\\", "/")
    parts = rel.split("/")
    meta = {"source_pdf": rel}
    if len(parts) >= 1:
        meta["qualification"] = parts[0]
    if len(parts) >= 2:
        meta["subject"] = parts[1].replace("_", " ")
    base = os.path.basename(path)
    m = re.search(r"_([0-9A-Z]{3,6})_\d{4}", base)
    if m:
        meta["spec_code"] = m.group(1)
    meta["pdf_name"] = base
    return meta


# ----------------------------------------------------------------------------
# Regexes
# ----------------------------------------------------------------------------

# Section titles that mark the syllabus content (case-insensitive).
SYLLABUS_SECT_RE = re.compile(
    r"knowledge,?\s*skills\s*and\s*understanding"
    r"|subject\s+content"
    r"|detailed\s+subject\s+content"
    r"|content\s+description"
    r"|specification\s+content"
    r"|^\s*\d*\.?\s*[A-Z][A-Za-z]{2,18}\s+content\s*$"     # "<Subject> content", "Chemistry content"
    r"|^\s*\d+\s+[A-Z][A-Za-z()'.,&/ -]{2,46}?\s+content\s*$",  # "2 Mathematics (Specification A) content"
    re.I,
)
# Strict section names used in the font-geometry fallback (no usable outline),
# where the loose "<x> content" rule would catch stray phrases like "expansion of
# specification content".
SECT_STRICT_RE = re.compile(
    r"knowledge,?\s*skills\s*and\s*understanding"
    r"|^\s*\d*\.?\s*subject\s+content"
    r"|^\s*\d*\.?\s*detailed\s+subject\s+content"
    r"|^\s*\d*\.?\s*specification\s+content\s*$"
    r"|^\s*\d*\.?\s*content\s+description\s*$"
    r"|^\s*\d*\.?\s*[A-Z][A-Za-z]{2,18}\s+content\s*$"     # "Physics content", "Chemistry content"
    r"|^\s*\d+\s+[A-Z][A-Za-z()'.,&/ -]{2,46}?\s+content\s*$",  # "2 Mathematics (Specification A) content"
    re.I,
)
# Section candidates that look like the syllabus by name but are NOT (appendices,
# the at-a-glance overview, mapping tables, command words).
SECT_EXCLUDE_RE = re.compile(
    r"appendix|at\s+a\s+glance|overview|mapping|command\s+words|how\s+science\s+works"
    r"|content\s+and\s+assessment\s+overview|list\s+of\s+subject\s+contents",
    re.I,
)
# Sub-headings that end the teachable content inside a section (assessment etc.).
STOP_SUBSECT_RE = re.compile(
    r"science\s+practical\s+endorsement|^\s*assessment\b|overview\s+of\s+assessment"
    r"|breakdown\s+of\s+assessment|assessment\s+objectives|administration"
    r"|^\s*appendix|non[\s-]*exam|controlled\s+assessment|unit\s+results"
    r"|scheme\s+of\s+assessment|entry\s+and\s+assessment"
    r"|how\s+science\s+works|expansion\s+of\s+specification|grade\s+descript"
    r"|mapping|^\s*appendices",
    re.I,
)

# Unit-marker families. Each captures (code, title). A code is only accepted if it
# carries a digit or is a short all-caps id (P1, FP2, A), so labels like "Unit
# description" / "Topic details" / "Area of study Instrumental" are NOT mistaken
# for units.
UNIT_PATTERNS = [
    ("Topic",         re.compile(r"^Topic\s+(\S+)\b\s*[:.–—-]?\s*(.*)$")),
    ("Option",        re.compile(r"^Option\s+(\S+?)\b\s*[:.–—-]?\s*(.*)$")),
    ("Theme",         re.compile(r"^Theme\s+(\S+)\b\s*[:.–—-]?\s*(.*)$")),
    ("Area of study", re.compile(r"^Area\s+of\s+[Ss]tudy\s+(\S+)\b\s*[:.–—-]?\s*(.*)$")),
    ("Component",     re.compile(r"^Component\s+(\S+)\b\s*[:.–—-]?\s*(.*)$")),
    ("Module",        re.compile(r"^Module\s+(\S+)\b\s*[:.–—-]?\s*(.*)$")),
    ("Section",       re.compile(r"^Section\s+(\S+)\b\s*[:.–—-]?\s*(.*)$")),
    ("Paper",         re.compile(r"^Paper\s+(\S+)\b\s*[:.,–—-]?\s*(.*)$")),
    ("Unit",          re.compile(r"^Unit\s+(\S+)\b\s*[:.–—-]?\s*(.*)$")),
]


def _valid_code(code):
    code = (code or "").strip(" .,:-–—")
    return bool(re.search(r"\d", code)) or bool(re.fullmatch(r"[A-Z]{1,3}", code))


# A bare decimal heading, e.g. IGCSE "1 Principles of chemistry", "2.3 ...",
# "1.1 - The market system" (an en-dash/colon between code and title is allowed).
NUMERIC_HEAD_RE = re.compile(r"^(\d{1,2}(?:\.\d{1,2})?)\s*[-–—:.]?\s+([A-Za-z].{2,})$")

# Footer banners (Edexcel / Pearson). Page numbers handled separately.
EDX_FOOTER_RE = re.compile(
    r"©\s*pearson|©\s*edexcel|pearson\s+education\s+limited|pearson\s+edexcel"
    r"|specification\s*[–—-]\s*issue|\bissue\s+\d"
    r"|sample\s+assessment\s+materials|\bturn\s+over\b"
    r"|\bedexcel\b.{0,40}\b(gce|gcse|igcse|international)\b"
    r"|\b(gce|gcse|igcse)\b.{0,40}\bedexcel\b",
    re.I,
)


# ----------------------------------------------------------------------------
# Document-level chrome detection (repetition based)
# ----------------------------------------------------------------------------

def build_doc_chrome(doc, body_size):
    """Detect running header/footer by REPETITION across pages.

    Returns {header_size: float|None, footer_keys: set[str]}.
    * header_size -- if a top-margin line of one distinct (non-body) font size
      recurs as the page's topmost element on >=30%% of pages, that's a running
      header (legacy specs). None means no running header (current specs), so
      content near the top is never mistaken for chrome.
    * footer_keys -- lowercased texts that recur in the bottom margin (repeated
      footer phrases that happen to be body-sized).
    """
    n = max(1, doc.page_count)
    tops = []                # (size, y0, text) of each page's topmost line
    bot_keys = Counter()
    label_pages = {}         # text -> set of pages it appears on (recurring chrome labels)
    for pno in range(doc.page_count):
        pg = doc[pno]
        ph = pg.rect.height
        lines = get_page_lines(pg)
        cands = [l for l in lines if l["y1"] < ph * 0.13]
        if cands:
            tm = min(cands, key=lambda l: l["y0"])
            tops.append((round(tm["size"]), tm["y0"], norm_ws(tm["text"]).lower()))
        for l in lines:
            if l["y0"] > ph * 0.84:
                bot_keys[norm_ws(l["text"]).lower()] += 1
            kt = norm_ws(l["text"]).lower()
            if 3 <= len(kt) <= 42:
                label_pages.setdefault(kt, set()).add(pno)

    # A running header is the page's topmost element, of a non-body font size,
    # recurring at a CONSISTENT y AND with REPEATING text across many pages
    # (legacy specs: the unit name echoed at the top of every page). The text
    # check is essential: a spec whose pages each begin with a *different*
    # sub-topic heading (e.g. iPrimary Maths 3.1, 3.2, ...) has those headings at
    # a consistent top-y too, but their text is all distinct -- not a header --
    # so they are never cropped away.
    header_size, header_y = None, None
    thr_h = max(4, int(n * 0.30))
    by_size = {}
    for sz, y, t in tops:
        by_size.setdefault(sz, []).append((y, t))
    for sz in sorted(by_size, key=lambda s: -len(by_size[s])):
        grp = by_size[sz]
        if len(grp) < thr_h or abs(sz - body_size) < 1.5:
            continue
        med = sorted(y for y, _ in grp)[len(grp) // 2]
        band = [t for y, t in grp if abs(y - med) < 12]
        if len(band) / len(grp) < 0.6:
            continue
        tc = Counter(t for t in band if t)
        if tc and tc.most_common(1)[0][1] >= 3 and len(tc) / len(band) < 0.6:
            header_size, header_y = float(sz), med
            break

    thr_f = max(4, int(n * 0.15))
    footer_keys = {t for t, c in bot_keys.items() if t and c >= thr_f}
    # Recurring table-header / column labels (e.g. "subject content", "what
    # students need to learn", "content", "guidance", "students should:") that
    # repeat across many content pages -- used to drop a trailing page whose only
    # content is such chrome (a repeated table header before the next sub-topic).
    thr_l = max(5, int(n * 0.22))
    labels = {t for t, ps in label_pages.items() if len(ps) >= thr_l}
    return {"header_size": header_size, "header_y": header_y,
            "footer_keys": footer_keys, "labels": labels}


def margin_cuts(page, body_size, pw, ph, chrome):
    """(header_bottom, footer_top): y below which header chrome ends and y above
    which footer chrome begins. Header is only cut when a running header was
    detected for the document; footers are cut by small font / banner / page
    number / repeated phrase. Only THIN full-width rules count as chrome rules."""
    bot_zone = ph * 0.84
    top_rule_zone = ph * 0.07
    hdr = chrome["header_size"]
    hdr_y = chrome.get("header_y")
    fkeys = chrome["footer_keys"]
    header_bottom, footer_top = 0.0, ph

    for ln in get_page_lines(page):
        t = norm_ws(ln["text"])
        if not t:
            continue
        # cut only lines sitting in the detected running-header band (a fixed y),
        # never a one-off heading that merely starts near the top of its page.
        if hdr is not None and abs(ln["y0"] - hdr_y) < 14 and abs(ln["size"] - hdr) < 1.2:
            header_bottom = max(header_bottom, ln["y1"])
        if ln["y0"] >= bot_zone:
            is_foot = (ln["size"] <= body_size - 0.5 or EDX_FOOTER_RE.search(t)
                       or re.fullmatch(r"\d{1,4}", t) or t.lower() in fkeys)
            if is_foot:
                footer_top = min(footer_top, ln["y0"])

    for d in page.get_drawings():
        r = d["rect"]
        if r.width < pw * 0.6 or (r.y1 - r.y0) > 3.0:    # only thin full-width rules are chrome
            continue
        if r.y1 <= top_rule_zone:
            header_bottom = max(header_bottom, r.y1)
        elif r.y0 >= bot_zone:
            footer_top = min(footer_top, r.y0)

    return header_bottom, footer_top


# ----------------------------------------------------------------------------
# Ink-based content box  (copied logic from the AQA tool -- board-agnostic)
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
INK_X_LO_FRAC = 0.06
INK_X_HI_FRAC = 0.94


def _page_ink(page, cache):
    pno = page.number
    hit = cache.get(pno)
    if hit is None:
        scale = INK_DPI / 72.0
        pm = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
        arr = np.frombuffer(pm.samples, dtype=np.uint8)
        arr = arr.reshape(pm.height, pm.stride // pm.n, pm.n)[:, :pm.width, :3]
        hit = (arr, scale, pm.width, pm.height)
        cache[pno] = hit
    return hit


def ink_bbox(page, x_lo, x_hi, y_lo, y_hi, cache):
    """Bounding box (pt) of real rendered ink in the window, or None. Measuring
    pixels (not the text bbox) avoids clipping fonts that under-report widths."""
    arr, scale, W, H = _page_ink(page, cache)
    pw = page.rect.width
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
    out_l, out_r = 0.05 * pw * scale, 0.95 * pw * scale
    kept = [g for g in groups if not (g[1] < out_l or g[0] > out_r)]
    if not kept:
        kept = groups
    minx = min(g[0] for g in kept); maxx = max(g[1] for g in kept)
    row_any = ink[:, minx:maxx + 1].any(axis=1)
    ridx = np.where(row_any)[0]
    if len(ridx) == 0:
        return None
    return minx / scale, (c + ridx[0]) / scale, (maxx + 1) / scale, (c + ridx[-1] + 1) / scale


def page_crop(page, body_size, is_start, is_end, start_y, end_y, chrome, cache):
    """fitz.Rect to crop this page to, or None if the band is empty."""
    pw, ph = page.rect.width, page.rect.height
    header_bottom, footer_top = margin_cuts(page, body_size, pw, ph, chrome)
    head = header_bottom + 2.0
    foot = footer_top - 2.0

    y_lo = max(head, start_y) if is_start else head
    y_hi = min(foot, end_y) if is_end else foot

    # Two bleeding fixes for the last page of a unit (is_end=True):
    #
    # (A) Full-width coloured/shaded heading bars: Edexcel heading bars are
    #     drawings that start ~15-25 pt ABOVE the heading text baseline.
    #     end_y = text y0 of the NEXT heading, so the bar's top half sits in
    #     [y_lo, y_hi] and bleeds in.  Clip y_hi to just before the bar.
    #
    # (B) Recurring chrome table headers: maths-style specs have a "Topic |
    #     Content | Guidance" header row at the top of every table page.  When
    #     the next topic starts on a new page, that header row appears between
    #     the last real content line and end_y.  Trim y_hi to just below the
    #     last non-chrome content (text line or non-full-width drawing).
    if is_end and end_y < 1e8:
        # (A) drawing check
        for d in page.get_drawings():
            r = d["rect"]
            if (r.width >= pw * 0.55 and (r.y1 - r.y0) >= 6
                    and r.y0 < end_y and r.y1 > end_y - 35):
                y_hi = min(y_hi, r.y0 - 1.0)

        # (B) chrome-label text trim
        if chrome.get("labels"):
            last_real_y1 = None
            for ln in get_page_lines(page):
                if ln["y0"] < y_lo or ln["y0"] >= y_hi:
                    continue
                t = norm_ws(ln["text"])
                if (t and t.lower() not in chrome["labels"]
                        and not re.fullmatch(r"[\d.,:–—-]+", t)):
                    last_real_y1 = max(last_real_y1 or 0.0, ln["y1"])
            # non-full-width drawings are real content (diagrams, formula boxes)
            for d in page.get_drawings():
                r = d["rect"]
                if r.y0 >= y_lo and r.y0 < y_hi and r.width < pw * 0.55:
                    last_real_y1 = max(last_real_y1 or 0.0, r.y1)
            if last_real_y1 is not None:
                y_hi = min(y_hi, last_real_y1 + PAD_BOTTOM + 4.0)

    if y_hi - y_lo < MIN_BAND:
        return None

    bb = ink_bbox(page, pw * INK_X_LO_FRAC, pw * INK_X_HI_FRAC, y_lo, y_hi, cache)
    if bb is None:
        return None
    ix0, iy0, ix1, iy1 = bb

    # Reject a near-blank page: only chrome survived (a legacy colour divider
    # block, a unit-number tab, and/or a full-width header rule), not real
    # content. Measured by absolute inked area, which is tiny for such pages
    # (~1-2k pt2) and far larger for any real heading+content page, so the
    # bbox shape (a full-width rule would otherwise look "wide") is irrelevant.
    arr, scale, _W, _H = _page_ink(page, cache)
    sub = arr[int(iy0 * scale):int(iy1 * scale), int(ix0 * scale):int(ix1 * scale)]
    ink_area = (sub < INK_THRESH).any(axis=2).sum() / (scale * scale) if sub.size else 0.0
    if ink_area < 2500:
        return None

    top = max(head, (start_y - START_TOP) if is_start else (iy0 - PAD_TOP))
    bottom = iy1 + PAD_BOTTOM
    if is_end:
        bottom = min(bottom, end_y - GAP)
    bottom = min(foot, bottom, ph)
    top = max(0.0, top)
    if bottom - top < MIN_BAND:
        return None

    # Drop a page whose only content WITHIN THE FINAL CROP is recurring chrome -- a
    # repeated table-header bar / column labels with no real sub-topic text (e.g.
    # the "Subject content | What students need to learn" header that tops the page
    # where the NEXT sub-topic begins, leaving the previous sub-topic a header-only
    # trailing page). Checked on [top, bottom] (not the raw ink bbox) so the next
    # sub-topic heading just below `bottom` is not mistaken for real content here.
    labels = chrome.get("labels")
    if labels:
        real = False
        for ln in get_page_lines(page):
            if top - 1 <= ln["y0"] < bottom - 1:
                t = norm_ws(ln["text"])
                if t and t.lower() not in labels and not re.fullmatch(r"[\d.,:–—-]+", t):
                    real = True
                    break
        if not real:
            return None

    # Drop a trailing page that is ENTIRELY the NEXT section's divider/intro, wrongly
    # carried in because this unit's end (= next unit's start_y) sits below that
    # divider. Two shapes, both with the divider at the very TOP of the crop (so no
    # real content of THIS unit is above it -> safe to drop the whole page):
    #   E1: a full section-divider page ("2 / Electricity / The following sub-topics
    #       are covered in this section. / (a) ...") -- IGCSE sciences.
    #   E2: a lone section/area/component/paper heading ("Area of study 4: ...",
    #       "Component 2: ...", "Paper 3 and Paper 4: ...") -- 9GE0 / 9PE0 / 9FM0.
    if is_end:
        cl = []
        for ln in get_page_lines(page):
            if top - 1 <= ln["y0"] < bottom - 1:
                t = norm_ws(ln["text"])
                if t and not EDX_FOOTER_RE.search(t) and t.lower() not in (chrome.get("labels") or set()):
                    cl.append(t)
        if cl:
            divider_top = bool(re.match(r"^(Area of study|Component|Paper|Section|Unit|Theme)\b", cl[0], re.I)
                               or re.fullmatch(r"\d{1,2}", cl[0]))
            # "The following sub-topics are covered in this section." is Edexcel's exact
            # section-divider boilerplate -- it appears ONLY on a divider/contents page.
            following = any("following" in t.lower() and "sub-topic" in t.lower() for t in cl)
            if divider_top and following:
                return None                       # E1: whole next-section divider page
            if len(cl) <= 2 and re.match(r"^(Area of study|Component|Paper|Section|Unit|Theme)\b", cl[0], re.I):
                return None                       # E2: lone next-section heading

    left = max(0.0, ix0 - PAD_LEFT)
    right = min(pw, ix1 + PAD_RIGHT)
    return fitz.Rect(left, top, right, bottom)


# ----------------------------------------------------------------------------
# Emit -- compose cropped regions onto uniform A4 sheets
# ----------------------------------------------------------------------------

A4 = fitz.paper_rect("a4")
A4_MARGIN_TOP = 42.0
A4_MARGIN_BOTTOM = 42.0
A4_MARGIN_SIDE = 30.0


def emit_doc(src_doc, plan, a4=True):
    out = fitz.open()
    for pidx, rect in plan:
        if a4:
            page = out.new_page(width=A4.width, height=A4.height)
            avail_w = A4.width - 2 * A4_MARGIN_SIDE
            avail_h = A4.height - A4_MARGIN_TOP - A4_MARGIN_BOTTOM
            scale = min(1.0, avail_w / rect.width, avail_h / rect.height)
            tw, th = rect.width * scale, rect.height * scale
            tx = (A4.width - tw) / 2.0
            target = fitz.Rect(tx, A4_MARGIN_TOP, tx + tw, A4_MARGIN_TOP + th)
            page.show_pdf_page(target, src_doc, pidx, clip=rect)
        else:
            out.insert_pdf(src_doc, from_page=pidx, to_page=pidx)
            out[-1].set_cropbox(rect)
    return out


# ----------------------------------------------------------------------------
# Section span detection
# ----------------------------------------------------------------------------

def _section_title_ok(title):
    t = norm_ws(title)
    return bool(SYLLABUS_SECT_RE.search(t)) and not SECT_EXCLUDE_RE.search(t)


def _sections_toc(doc):
    toc = doc.get_toc(simple=True)
    if not toc:
        return []
    secs = []
    for i, (lvl, title, pg) in enumerate(toc):
        if pg is None or pg < 1 or not _section_title_ok(title):
            continue
        start_page = pg - 1
        end_page, end_y = doc.page_count - 1, 1e9
        for lvl2, _t2, pg2 in toc[i + 1:]:
            if pg2 and pg2 >= 1 and lvl2 <= lvl:
                end_page = max(start_page, pg2 - 1)
                break
        secs.append({"start_page": start_page, "start_y": 0.0,
                     "end_page": end_page, "end_y": end_y,
                     "title": norm_ws(title), "whole": False, "toc_level": lvl})
    return _dedupe_sections(secs)


def _sections_whole(doc):
    return [{"start_page": 0, "start_y": 0.0, "end_page": doc.page_count - 1,
             "end_y": 1e9, "title": "Subject content", "whole": True}]


def _sections_font(doc, body_size):
    """Font-geometry fallback: a large heading whose text matches a section name."""
    big = []
    for pno in range(doc.page_count):
        pw = doc[pno].rect.width
        for ln in get_page_lines(doc[pno]):
            t = norm_ws(ln["text"])
            if (ln["size"] >= body_size + 4 and ln["x0"] < pw * 0.5
                    and len(t) < 50 and SECT_STRICT_RE.search(t)
                    and not SECT_EXCLUDE_RE.search(t)):
                big.append({"page": pno, "y": ln["y0"], "size": ln["size"],
                            "title": norm_ws(ln["text"])})
    big.sort(key=lambda h: (h["page"], h["y"]))
    if not big:
        return []
    stops = []
    for pno in range(doc.page_count):
        pw = doc[pno].rect.width
        for ln in get_page_lines(doc[pno]):
            if (ln["size"] >= body_size + 4 and ln["x0"] < pw * 0.5
                    and STOP_SUBSECT_RE.search(norm_ws(ln["text"]))):
                stops.append((pno, ln["y0"]))
    stops.sort()
    secs = []
    for k, h in enumerate(big):
        end_page, end_y = doc.page_count - 1, 1e9
        nxt = big[k + 1] if k + 1 < len(big) else None
        if nxt:
            end_page, end_y = nxt["page"], nxt["y"]
        for sp, sy in stops:
            if (sp, sy) > (h["page"], h["y"]) and (sp, sy) < (end_page, end_y):
                end_page, end_y = sp, sy
                break
        secs.append({"start_page": h["page"], "start_y": h["y"],
                     "end_page": end_page, "end_y": end_y,
                     "title": h["title"], "whole": False})
    return _dedupe_sections(secs)


_NUM_CONTENT_RE = re.compile(r"^\s*\d+\s+[A-Z][A-Za-z()'.,&/ -]{2,46}?\s+content\s*$", re.I)
_NUM_MAJOR_RE = re.compile(r"^\s*\d+\s+[A-Z]", re.I)


def _sections_numbered_content(doc, body_size):
    """IGCSE/GCSE specs head their syllabus with a big NUMBERED section
    'N <Subject> content' (e.g. '2 Economics content', '2 Mathematics
    (Specification A) content'), and put 'Content description' / 'Detailed
    content' as a SUB-heading inside it -- which the TOC often points at instead,
    missing most of the content. Detect the numbered content section directly; it
    ends at the next big numbered major heading ('3 Assessment information')."""
    majors = []   # (page, y, title) big numbered headings
    for pno in range(doc.page_count):
        pw = doc[pno].rect.width
        for ln in get_page_lines(doc[pno]):
            t = norm_ws(ln["text"])
            if ln["size"] >= body_size + 5 and ln["x0"] < pw * 0.5 and _NUM_MAJOR_RE.match(t):
                majors.append({"page": pno, "y": ln["y0"], "title": t,
                               "content": bool(_NUM_CONTENT_RE.match(t))})
    majors.sort(key=lambda m: (m["page"], m["y"]))
    out = []
    for i, m in enumerate(majors):
        if not m["content"] or SECT_EXCLUDE_RE.search(m["title"]):
            continue
        end_p, end_y = (majors[i + 1]["page"], majors[i + 1]["y"]) if i + 1 < len(majors) \
            else (doc.page_count - 1, 1e9)
        out.append({"start_page": m["page"], "start_y": m["y"],
                    "end_page": end_p, "end_y": end_y, "title": m["title"], "whole": False})
    return _dedupe_sections(out)


def find_sections(doc, body_size):
    """Return (sections, method). TOC-first, font-geometry fallback, whole-doc
    last (see collect_subsections for the units-aware retry across methods)."""
    secs = _sections_toc(doc)
    if secs:
        return secs, "toc"
    secs = _sections_font(doc, body_size)
    if secs:
        return secs, "font"
    return _sections_whole(doc), "legacy"


def _dedupe_sections(secs):
    secs.sort(key=lambda s: (s["start_page"], s["start_y"]))
    out = []
    seen = set()
    for s in secs:
        key = (s["start_page"], round(s["start_y"] / 10))
        if key in seen:
            continue
        seen.add(key)
        out.append(s)
    return out


# ----------------------------------------------------------------------------
# Unit (sub-topic) detection within a section
# ----------------------------------------------------------------------------

def _match_unit(text):
    """Return (family, code, title) for a marker-family unit heading, else None.
    Bare decimal ("Num") headings are handled separately as a fallback only."""
    t = norm_ws(text)
    for fam, pat in UNIT_PATTERNS:
        m = pat.match(t)
        if m:
            code = m.group(1).strip(" .,:-–—")
            if not _valid_code(code):
                continue
            title = norm_ws(m.group(2)) if m.lastindex and m.group(2) else ""
            return fam, code, title
    return None


def _match_numeric(text):
    """Return ('Num', code, title) for a bare-decimal heading ("1 Principles of
    chemistry"), used only as a fallback for numbered-only specs."""
    m = NUMERIC_HEAD_RE.match(norm_ws(text))
    if m:
        return "Num", m.group(1), norm_ws(m.group(2))
    return None


def _heading_lines_in_span(doc, body_size, sec, allow_bold_body=False, include_decimal=False):
    """Candidate unit-heading lines inside a section span. By default only true
    heading-sized lines (size >= body+1.3) qualify, so bold body-size sub-labels
    (e.g. A-level Chemistry 'Topic 2A') are ignored. With allow_bold_body=True a
    bold body-size line that matches a marker also qualifies (specs whose topics
    are bold body text, e.g. iLowerSecondary CS). With include_decimal=True a
    heading-sized bare-decimal sub-topic ('1.1 Formulae, equations and amounts of
    substance') also qualifies -- used for legacy specs that number their
    sub-topics N.N under each Unit. Running-header echoes (a unit/decimal heading
    that recurs on >=4 pages) are dropped."""
    sp0, sp1 = sec["start_page"], sec["end_page"]
    out = []
    for pno in range(sp0, sp1 + 1):
        if pno < 0 or pno >= doc.page_count:
            continue
        pw = doc[pno].rect.width
        lines = get_page_lines(doc[pno])
        for ln in lines:
            if pno == sp0 and ln["y0"] < sec["start_y"] - 1:
                continue
            if pno == sp1 and ln["y0"] >= sec["end_y"]:
                continue
            t = norm_ws(ln["text"])
            if not t or len(t) > 95 or ln["x0"] > pw * 0.5:
                continue
            if "continued" in t.lower():          # "Topic 4 (continued)" is not a new unit
                continue
            big = ln["size"] >= body_size + 1.3
            bold_body = ln["bold"] and ln["size"] >= body_size - 0.5
            mu = _match_unit(t)
            if mu:
                if not (big or (allow_bold_body and bold_body)):
                    continue
            elif include_decimal:
                mn = _match_numeric(t)
                if mn and "." in mn[1]:             # "1.1 Title" inline
                    if not (big or bold_body):
                        continue
                    # A real sub-topic title is capitalised ("1.2 Fractions and
                    # decimals"); a number lifted from an example/guidance column
                    # reads as a lowercase fragment ("3.5 and 7", "40.5 g and
                    # volume 15 cm3") -- skip so it doesn't become a garbage unit
                    # that also truncates the real sub-topic's content.
                    if mn[2] and mn[2][0].islower():
                        continue
                    mu = mn
                elif (big and re.fullmatch(r"\d{1,2}\.\d{1,2}", t)
                        and ln["x0"] < pw * 0.33):  # bare "1.1" code, title in next column (left column only)
                    mu = ("Num", t, "")
                else:
                    continue                        # require N.N (a sub-topic), not bare "N"
            else:
                continue
            fam, code, title = mu
            if not title:                           # code-only cell: title in next column
                title = _row_title(lines, ln, pw)
            out.append({"family": fam, "code": code, "title": title,
                        "page": pno, "y": ln["y0"], "size": round(ln["size"], 1),
                        "raw": t})
    # drop running-header echoes: a heading whose text recurs on >=4 pages
    pages_by_text = {}
    for h in out:
        pages_by_text.setdefault(re.sub(r"[^a-z0-9]", "", h["raw"].lower()), set()).add(h["page"])
    out = [h for h in out
           if len(pages_by_text[re.sub(r"[^a-z0-9]", "", h["raw"].lower())]) < 4]
    # drop smaller-font echoes of a marker that recurs as a running header (e.g.
    # legacy Maths 'Unit C1' printed big once then repeated smaller on every page,
    # mirrored odd/even so the text-recurrence rule above misses it -- which would
    # fragment the unit's page span).
    from collections import defaultdict
    szmax, cnt = defaultdict(float), defaultdict(int)
    for h in out:
        k = (h["family"], h["code"])
        szmax[k] = max(szmax[k], h["size"])
        cnt[k] += 1
    return [h for h in out
            if not (cnt[(h["family"], h["code"])] >= 3
                    and h["size"] < szmax[(h["family"], h["code"])] - 0.6)]


def _locate_y(doc, pno, title):
    """Find the y of a heading whose text starts with `title` on page pno (for
    TOC-child units whose outline gives only a page). 0.0 if not found."""
    if pno < 0 or pno >= doc.page_count:
        return 0.0
    key = re.sub(r"[^a-z0-9]", "", (title or "").lower())[:24]
    if not key:
        return 0.0
    for ln in get_page_lines(doc[pno]):
        lk = re.sub(r"[^a-z0-9]", "", norm_ws(ln["text"]).lower())
        if lk.startswith(key[:12]) and key[:12]:
            return ln["y0"]
    return 0.0


def _toc_child_units(doc, sec):
    """Units from the section's child bookmarks (IGCSE numbered topics, IAL Units)."""
    lvl = sec.get("toc_level")
    if lvl is None:
        return []
    toc = doc.get_toc(simple=True)
    if not toc:
        return []
    # find the section's own toc index
    start = None
    for i, (l, _t, pg) in enumerate(toc):
        if pg and pg - 1 == sec["start_page"] and l == lvl:
            start = i
            break
    if start is None:
        return []
    units = []
    for l, t, pg in toc[start + 1:]:
        if l <= lvl:
            break
        if l != lvl + 1 or not pg:
            continue
        pno = pg - 1
        if pno > sec["end_page"]:
            break
        title = norm_ws(t)
        if STOP_SUBSECT_RE.search(title) or SECT_EXCLUDE_RE.search(title):
            continue
        m = re.match(r"^(\d{1,2}(?:\.\d{1,2})?)\s+(.*)$", title)
        code, ttl = (m.group(1), norm_ws(m.group(2))) if m else ("", title)
        units.append({"family": "Num" if code else "Section", "code": code,
                      "title": ttl, "page": pno, "y": _locate_y(doc, pno, ttl)})
    return units


def _collapse_runheader(heads):
    """Drop a unit heading that merely repeats the previous one's (family, code)
    on an adjacent page -- i.e. a running header echoing the unit name on every
    page (legacy specs). Genuinely distinct units are never adjacent duplicates."""
    out = []
    for h in heads:
        if out and out[-1]["family"] == h["family"] and out[-1]["code"] == h["code"] \
                and h["page"] - out[-1]["page"] <= 1:
            continue
        out.append(h)
    return out


def _drop_overview_lists(heads):
    """Drop a contents / at-a-glance list: >=4 unit headings of the same family
    AND font size crammed onto a single page (e.g. a spec that lists 'Unit 1..6'
    on its first page before the real, spread-out unit headings). Real units do
    not pack four same-size siblings onto one page."""
    groups = {}
    for h in heads:
        groups.setdefault((h["family"], h["size"], h["page"]), []).append(h)
    drop = {id(h) for hs in groups.values() if len(hs) >= 4 for h in hs}
    return [h for h in heads if id(h) not in drop]


def _dedup_raw(heads):
    """Collapse headings that share the exact same text (a topic restated before
    each of its options, e.g. Geography 'Topic 2'; or a legacy/IAL spec that
    lists its units in an overview AND again as content dividers). Keep the copy
    with the LARGEST font (the real content divider, not the small overview
    entry); ties keep the earliest."""
    best = {}
    for h in heads:
        key = re.sub(r"[^a-z0-9]", "", (h.get("raw") or (h["code"] + h["title"])).lower())
        if key not in best or h["size"] > best[key]["size"] + 0.3:
            best[key] = h
    return sorted(best.values(), key=lambda h: (h["page"], h["y"]))


def _apply_decimal_split(heads):
    """When N.N decimal sub-topics are present, split at that level: drop every
    marker heading (Theme / Unit / Topic ...) that actually has a decimal under
    it, but KEEP a marker that has none (e.g. a Geography Option whose own
    sub-points are coded 2A.1, not plain decimals). Needs >=2 decimals to act."""
    nums = [h for h in heads if h["family"] == "Num"]
    if len(nums) < 2:
        return heads
    allh = sorted(heads, key=lambda h: (h["page"], h["y"]))
    keep = []
    for i, h in enumerate(allh):
        if h["family"] == "Num":
            keep.append(h)
            continue
        has_decimal = False
        for nxt in allh[i + 1:]:
            if nxt["family"] != "Num" and nxt["size"] >= h["size"] - 0.6:
                break                       # reached the next sibling/ancestor marker
            if nxt["family"] == "Num":
                has_decimal = True
                break
        if not has_decimal:
            keep.append(h)
    return keep


def _drop_parents(heads):
    """Keep only leaf unit headings: drop any heading that is subdivided by >=2
    smaller-font headings before the next heading of equal-or-larger font. This
    splits Geography at Topic/Option (not Area of study), RS at Paper-1..3 plus
    Paper-4's options, sciences at Topic, etc. -- without hard-coding families."""
    keep = []
    for i, h in enumerate(heads):
        j = i + 1
        smaller = 0
        while j < len(heads) and heads[j]["size"] < h["size"] - 0.6:
            smaller += 1
            j += 1
        if smaller >= 2:        # h is a subdivided parent -> drop it
            continue
        keep.append(h)
    return keep


def harvest_table_topics(doc, body_size, sec):
    """Maths-style specs lay the syllabus out as a 'Topic | What students need to
    learn' table whose LEFT column carries the topic NUMBER and its TITLE (the
    detailed references like 2.3 sit in the Content column). Such numbers are 9pt
    bold at the far left, so heading/decimal detection never sees them. Detect each
    topic as a unit so the split is per-topic (Topic 1 ... Topic 9). Each
    paper/unit's first topic is anchored at the paper/unit heading so its title is
    carried in. Returns [] when the span is not such a table."""
    sp0, sp1 = sec["start_page"], sec["end_page"]

    def in_span(pno, y):
        if pno == sp0 and y < sec["start_y"] - 1:
            return False
        if pno == sp1 and y >= sec["end_y"]:
            return False
        return True

    # 1) require a bold 'Topic'/'Topics' left-column header on >=2 pages
    header_pages = 0
    for pno in range(sp0, sp1 + 1):
        if pno < 0 or pno >= doc.page_count:
            continue
        pw = doc[pno].rect.width
        if any(ln["x0"] < pw * 0.28 and ln["bold"]
               and re.fullmatch(r"Topics?", norm_ws(ln["text"]))
               for ln in get_page_lines(doc[pno])):
            header_pages += 1
    if header_pages < 2:
        return []

    # 2) paper / unit headings (for context + anchoring the first topic)
    papers = []
    for pno in range(sp0, sp1 + 1):
        if pno < 0 or pno >= doc.page_count:
            continue
        pw = doc[pno].rect.width
        for ln in get_page_lines(doc[pno]):
            t = norm_ws(ln["text"])
            if (ln["size"] >= body_size + 1.5 and ln["x0"] < pw * 0.5
                    and re.match(r"(Paper|Unit)\s+\d", t)):
                papers.append({"page": pno, "y": ln["y0"], "title": t})
    papers.sort(key=lambda p: (p["page"], p["y"]))

    def paper_of(pno, y):
        cur = ""
        for p in papers:
            if (p["page"], p["y"]) <= (pno, y):
                cur = p["title"]
            else:
                break
        return cur

    # 3) topic-number cells in the left column (skip continuation pages)
    topics, seen = [], set()
    for pno in range(sp0, sp1 + 1):
        if pno < 0 or pno >= doc.page_count:
            continue
        pg = doc[pno]
        pw, ph = pg.rect.width, pg.rect.height
        lines = sorted(get_page_lines(pg), key=lambda l: (l["y0"], l["x0"]))
        for ln in lines:
            t = norm_ws(ln["text"])
            if not (ln["x0"] < pw * 0.22 and ln["bold"] and ln["y0"] < ph * 0.86
                    and in_span(pno, ln["y0"]) and re.fullmatch(r"\d{1,2}", t)):
                continue
            title_parts, cont = [], False
            for o in lines:                              # title block below the number
                if o is ln or not (o["x0"] < pw * 0.28 and ln["y0"] < o["y0"] <= ln["y0"] + 70):
                    continue
                ot = norm_ws(o["text"])
                if ot.lower() == "continued":
                    cont = True
                    break
                if re.fullmatch(r"\d{1,2}", ot):         # next topic number
                    break
                if re.fullmatch(r"Topics?", ot) or not ot:
                    continue
                title_parts.append((o["y0"], ot))
            if cont:
                continue
            pap = paper_of(pno, ln["y0"])
            key = (pap, t)
            if key in seen:
                continue
            seen.add(key)
            topics.append({"family": "Topic", "code": t,
                           "title": " ".join(x for _, x in sorted(title_parts)),
                           "page": pno, "y": ln["y0"], "size": round(ln["size"], 1),
                           "paper": pap})
    if len(topics) < 2:
        return []

    # anchor each paper/unit's first topic at the paper/unit heading (carry title)
    topics.sort(key=lambda u: (u["page"], u["y"]))
    first_done = set()
    for tp in topics:
        if tp["paper"] in first_done:
            continue
        first_done.add(tp["paper"])
        for p in papers:
            if p["title"] == tp["paper"]:
                tp["page"], tp["y"] = p["page"], p["y"]
                break
    topics.sort(key=lambda u: (u["page"], u["y"]))
    return topics


def _row_title(lines, ln, pw):
    """Title cell to the right of a code-only cell `ln`, joining wrapped
    continuation lines in the same column (so a heading that spans several lines,
    e.g. a Geography enquiry question, is captured in full, not just its first
    words). Stops at a sentence end, a blank gap, a new code, or ~90 chars."""
    row = [o for o in lines if abs(o["y0"] - ln["y0"]) < 5
           and o["x0"] > ln["x1"] and o["x0"] < pw * 0.78]
    if not row:
        return ""
    first = min(row, key=lambda o: o["x0"])
    tx = first["x0"]
    parts = [norm_ws(first["text"])]
    py = first["y1"]
    for o in sorted((o for o in lines if abs(o["x0"] - tx) < 8 and o["y0"] > first["y0"] + 1),
                    key=lambda o: o["y0"]):
        if o["y0"] - py > 16:                      # blank gap -> heading block ended
            break
        ot = norm_ws(o["text"])
        if not ot or _code_token(ot):
            break
        parts.append(ot)
        py = o["y1"]
        if parts[-1].endswith((".", ":")) or sum(len(p) for p in parts) > 90:
            break
    return " ".join(parts).strip()


# A title that STARTS with one of these is a learning objective (an instruction),
# not a named sub-topic -- used to avoid splitting a spec per-objective (e.g. GCSE
# Physics '2.10 Analyse velocity/time graphs ...', Statistics '1.1 Interpret ...').
_OBJECTIVE_RE = re.compile(
    r"^(know|knowledge|understand|recall|describe|explain|analyse|evaluate|calculate|"
    r"use|using|apply|identify|state|define|interpret|compare|justify|demonstrate|"
    r"outline|discuss|assess|determine|construct|represent|express|solve|investigate|"
    r"measure|predict|derive|deduce|show|give|list|name|select|plan|record|present|"
    r"be able|students should|candidates should)\b", re.I)


def _code_token(t):
    """(kind, code, inline_title) for a coded sub-topic heading, else None.
    kind in {'alpha' (a), 'num' (1), 'dec' (1.1), 'ldec' (P1.1)}."""
    m = re.match(r"^\(([a-z])\)\s*(.*)$", t)
    if m:
        return "alpha", m.group(1), m.group(2).strip()
    m = re.match(r"^([A-Z]{1,3}\d{0,2}\.\d{1,2})\s*(.*)$", t)        # P1.3, FP2.1
    if m:
        return "ldec", m.group(1), m.group(2).strip()
    m = re.match(r"^(\d{1,2}(?:\.\d{1,2}){1,2})\s*(.*)$", t)          # 1.1, 1.1.1
    if m:
        return "dec", m.group(1), m.group(2).strip()
    m = re.match(r"^([A-Z]\d{1,2})[:.\s]\s*([A-Z].*)$", t)           # A2 Russia..., B3 Japan...
    if m:
        return "opt", m.group(1), m.group(2).strip()
    m = re.match(r"^(\d{1,2})\.?(?:\s+(.*))?$", t)                    # 1  or  1. Title
    if m:
        return "num", m.group(1), (m.group(2) or "").strip()
    return None


def _has_consecutive_run(codes, kind):
    """True if `codes` contain 3 consecutive items (1,2,3 or a,b,c) -- evidence of
    a real coded list rather than stray numbers."""
    if kind == "alpha":
        vals = sorted({ord(c) for c in codes if len(c) == 1})
    else:
        vals = sorted({int(c) for c in codes if c.isdigit()})
    return any((v + 1 in vals and v + 2 in vals) for v in vals)


def harvest_coded_units(doc, body_size, sec):
    """Detect teachable sub-topics that are coded in the LEFT column but missed by
    marker/decimal heading detection: lettered '(a) Title' (IGCSE Chemistry),
    bare-numbered 'N Title' (IGCSE History, Statistics, IAL Maths topics). The code
    may be inline ('1 Algebra and functions') or in a left cell with the title in
    the next column ('(a)' | 'States of matter'). Returns the finest clean level
    (alpha > num) so section/unit headings above become parents; [] if none."""
    sp0, sp1 = sec["start_page"], sec["end_page"]

    def in_span(pno, y):
        if pno == sp0 and y < sec["start_y"] - 1:
            return False
        if pno == sp1 and y >= sec["end_y"]:
            return False
        return True

    buckets = {"alpha": [], "num": [], "opt": [], "dec": []}
    for pno in range(sp0, sp1 + 1):
        if pno < 0 or pno >= doc.page_count:
            continue
        pg = doc[pno]
        pw, ph = pg.rect.width, pg.rect.height
        lines = sorted(get_page_lines(pg), key=lambda l: (round(l["y0"], 1), l["x0"]))
        for ln in lines:
            if not in_span(pno, ln["y0"]) or ln["y0"] > ph * 0.9 or ln["x0"] > pw * 0.5:
                continue
            t = norm_ws(ln["text"])
            if not t or "continued" in t.lower():
                continue
            mt = _code_token(t)
            if not mt:
                continue
            kind, code, title = mt
            if kind not in buckets:
                continue
            if kind == "dec":
                # left-column decimals only (deeper x are content points); a decimal
                # sub-topic is body-size and often NOT bold (IGCSE Business 1.1,
                # Economics 1.1.1), so no bold/heading-size requirement here.
                if ln["x0"] > pw * 0.25:
                    continue
            elif not (ln["bold"] or ln["size"] >= body_size + 1.3):
                continue
            if not title:                              # left cell -> title in next column
                if kind == "dec":
                    # first right-column cell only -- the short sub-topic name; do NOT
                    # join the content row beside it (Biology '1.1 | Carbohydrates | Know...')
                    row = [o for o in lines if abs(o["y0"] - ln["y0"]) < 5
                           and o["x0"] > ln["x1"] and o["x0"] < pw * 0.7]
                    title = norm_ws(min(row, key=lambda o: o["x0"])["text"]) if row else ""
                else:
                    title = _row_title(lines, ln, pw)
            title = title.lstrip("–—-:.) ").strip()        # "1 – Business activity" -> "Business activity"
            if not title or not title[:1].isupper() or len(title) < 3:
                continue
            # never treat a section/admin heading as a sub-topic (incl. multi-word
            # "<N> <Subject> content" section titles, e.g. "Further Pure Maths content")
            if (SYLLABUS_SECT_RE.search(title) or SECT_EXCLUDE_RE.search(title)
                    or STOP_SUBSECT_RE.search(title) or re.search(r"\bcontent$", title, re.I)):
                continue
            buckets[kind].append({"code": code, "title": title, "page": pno,
                                  "y": ln["y0"], "size": round(ln["size"], 1)})

    def drop_packed(cells):
        # drop contents-list pages: >=4 codes packed tightly (small y-gaps) on one
        # page is a listing/overview, not real content (which is spread out).
        by_pg = {}
        for c in cells:
            by_pg.setdefault(c["page"], []).append(c["y"])
        packed = set()
        for pg, ys in by_pg.items():
            if len(ys) >= 4:
                ys.sort()
                gaps = sorted(b - a for a, b in zip(ys, ys[1:]))
                if gaps and gaps[len(gaps) // 2] < 70:
                    packed.add(pg)
        return sorted((c for c in cells if c["page"] not in packed),
                      key=lambda u: (u["page"], u["y"]))

    def num_ok(cells):
        # Accept bare numbers ONLY as a clean run (1,2,3,...): each code appears at
        # most twice (a code may repeat once, e.g. IGCSE Maths Foundation + Higher
        # tiers) and the order is monotonic. Rejects numbers that restart inside
        # every sub-section (IAL Maths units, History key-points) -> over-split.
        seq = [int(c["code"]) for c in cells if c["code"].isdigit()]
        cnt = Counter(seq)
        mono = sum(1 for a, b in zip(seq, seq[1:]) if b >= a)
        return bool(seq) and max(cnt.values()) <= 2 and (
            len(seq) <= 1 or mono / (len(seq) - 1) >= 0.8)

    def opt_run(codes):                                # A2,A3,A4 within a letter group
        by_l = {}
        for c in codes:
            by_l.setdefault(c[0], set()).add(int(c[1:]))
        return any(any(v + 1 in ds for v in ds) for ds in by_l.values())

    # alpha sub-points (a)(b)(c) -- the finest, used as-is (e.g. IGCSE Chemistry).
    a = drop_packed(buckets["alpha"])
    if len(a) >= 3 and _has_consecutive_run([c["code"] for c in a], "alpha"):
        for c in a:
            c["family"], c["code"] = "", f"({c['code']})"
        return a

    # left-column decimal sub-topics (IGCSE Business '1.1 Business objectives';
    # Economics '1.1.1 The economic problem'). Split at the DEEPEST level present in
    # the left column -- so Business splits at 1.1 (its 1.1.1 are far-right points,
    # already filtered out) while Economics splits at 1.1.1 (a titled near-left level).
    dec = buckets["dec"]
    if len(dec) >= 4:
        by_depth = {}
        for c in dec:
            by_depth.setdefault(c["code"].count("."), []).append(c)
        for depth in sorted(by_depth, reverse=True):
            cells = drop_packed(by_depth[depth])
            if len(cells) < 4:
                continue
            # Real nested numbering: several parents each starting at .1 (1.1, 1.2,
            # 2.1, ...). Split at this -- the deepest left-column decimal level --
            # giving the finest sub-topics (Biology 1.1, Business 1.1, Economics
            # 1.1.1). Titles are first-cell-only (see collection) so they stay tidy.
            # Skip a level whose titles are mostly learning objectives (verbs like
            # 'Analyse', 'Describe', or 'A understand ...' with a leading point letter)
            # rather than named sub-topics ('Carbohydrates') -- per-objective is too
            # granular (IGCSE Maths 4MA1, GCSE Physics).
            obj = sum(1 for c in cells
                      if _OBJECTIVE_RE.match(re.sub(r"^[A-Za-z]\s+", "", c["title"])))
            if obj / len(cells) > 0.4:
                continue
            # Skip if this level is far too granular to be a usable sub-topic split
            # (e.g. GCSE RS 1RB0 has 447 deepest-level points across all options) --
            # fall through to the coarser marker/topic level instead.
            if len(cells) > 110:
                continue
            parents = {}
            for c in cells:
                parts = c["code"].split(".")
                if parts[-1].isdigit():
                    parents.setdefault(".".join(parts[:-1]), []).append(int(parts[-1]))
            if (len(parents) >= 2 and sum(1 for v in parents.values() if 1 in v) >= 2
                    and sum(len(v) for v in parents.values()) >= 4):
                for c in cells:
                    c["family"] = "Num"
                return cells

    # HEADING-SIZED topics: bare numbers and/or letter-digit option codes (e.g.
    # IGCSE History depth studies 1..8 plus Paper-2 breadth options A2..A5, B2..B4,
    # all at 14pt). Accept when codes are near-unique (<=2x, allowing Maths tiers)
    # and form a run in either family.
    big = drop_packed([c for c in buckets["num"] + buckets["opt"]
                       if c["size"] >= body_size + 1.3])
    if len(big) >= 3:
        cnt = Counter(c["code"] for c in big)
        nums = [c["code"] for c in big if c["code"].isdigit()]
        opts = [c["code"] for c in big if not c["code"].isdigit()]
        if max(cnt.values()) <= 2 and (_has_consecutive_run(nums, "num") or opt_run(opts)):
            for c in big:
                c["family"] = "Topic"
            return big

    # body-size flat numbered list (e.g. Statistics 1..21 at body size).
    nb = drop_packed(buckets["num"])
    if len(nb) >= 3 and _has_consecutive_run([c["code"] for c in nb], "num") and num_ok(nb):
        for c in nb:
            c["family"] = "Topic"
        return nb
    return []


_ADMIN_TOPIC_RE = re.compile(
    r"unit description|assessment information|^examination|^notation|formulae$"
    r"|specimen|^content$|overview", re.I)


def harvest_unit_topics(doc, body_size, sec):
    """Specs that repeat a numbered topic list inside every Unit/Paper (e.g. IAL
    Maths: Unit P1 -> '1 Algebra and functions', '2 Coordinate geometry', ...; each
    unit restarts at 1). Detected per-unit so the Unit headings become parents and
    the split is per-topic. Admin entries (Unit description / Assessment / formulae
    lists) are excluded. Returns [] if the span is not this shape."""
    sp0, sp1 = sec["start_page"], sec["end_page"]
    markers = []
    for pno in range(sp0, sp1 + 1):
        if pno < 0 or pno >= doc.page_count:
            continue
        pw = doc[pno].rect.width
        for ln in get_page_lines(doc[pno]):
            t = norm_ws(ln["text"])
            if ln["size"] >= body_size + 1.3 and ln["x0"] < pw * 0.5 and re.match(r"Unit\s+\S", t):
                mu = _match_unit(t)
                if mu and mu[0] == "Unit":
                    markers.append({"page": pno, "y": ln["y0"], "fam": mu[0],
                                    "mcode": mu[1], "mtitle": mu[2], "size": ln["size"],
                                    "title": (mu[0] + " " + mu[1]).strip(), "raw": t})
    # keep only the real heading per unit code (largest font, earliest) -- the unit
    # name is reprinted smaller as a running header on every page (legacy IAL Maths).
    best = {}
    for mk in markers:
        k = mk["mcode"]
        if k not in best or mk["size"] > best[k]["size"] + 0.6:
            best[k] = mk
    markers = sorted(best.values(), key=lambda m: (m["page"], m["y"]))
    if len(markers) < 2:
        return []

    out = []
    for i, m in enumerate(markers):
        e_pg, e_y = (markers[i + 1]["page"], markers[i + 1]["y"]) if i + 1 < len(markers) \
            else (sp1, sec["end_y"])
        cells = []
        for pno in range(m["page"], min(e_pg, doc.page_count - 1) + 1):
            pw, ph = doc[pno].rect.width, doc[pno].rect.height
            for ln in get_page_lines(doc[pno]):
                if (pno, ln["y0"]) <= (m["page"], m["y"]) or (pno, ln["y0"]) >= (e_pg, e_y):
                    continue
                if (ln["x0"] > pw * 0.5 or ln["y0"] > ph * 0.9
                        or not (ln["bold"] or ln["size"] >= body_size + 1.5)):
                    continue
                mt = _code_token(norm_ws(ln["text"]))
                if not mt or mt[0] != "num" or not mt[2]:
                    continue
                title = mt[2].lstrip("–—-:.) ").strip()
                if not title[:1].isupper() or len(title) < 3 or _ADMIN_TOPIC_RE.search(title):
                    continue
                cells.append({"code": mt[1], "title": title, "page": pno, "y": ln["y0"]})
        # keep the longest run starting at 1 (the unit's content topics)
        cells.sort(key=lambda c: (c["page"], c["y"]))
        seq, seen = [], set()
        for c in cells:
            n = int(c["code"])
            if n in seen:
                continue
            if n == len(seq) + 1:                       # consecutive 1,2,3,...
                seq.append(c)
                seen.add(n)
        if len(seq) >= 2:
            # the unit heading + its admin (description/assessment) become the unit's
            # own intro unit; each topic then starts at its own heading (clean).
            out.append({"family": m["fam"], "code": m["mcode"], "title": m["mtitle"],
                        "page": m["page"], "y": m["y"]})
            for c in seq:
                c["family"] = "Topic"
            out.extend(seq)
    if len(out) < 4:
        return []
    # Only split per-unit when the topics are DISTINCT across units (Maths: C12 has
    # Algebra/Trig, M1 has Kinematics, ...). If the same topic titles repeat in every
    # unit (languages: each skills Unit covers the same themes), keep the unit level.
    titles = [norm_ws(u["title"]).lower() for u in out if u["family"] == "Topic" and u["title"]]
    if titles and len(set(titles)) / len(titles) < 0.6:
        return []
    return out


def _numeric_parts(code):
    """Tuple of decimal components if `code` is a pure decimal ('1.2.3'), else None."""
    m = re.match(r"^(\d{1,2}(?:\.\d{1,2})*)$", (code or "").strip())
    return tuple(m.group(1).split(".")) if m else None


# Marker containment tiers (smaller = higher/outer). A cross-family marker can only
# anchor (lead) a unit that is BELOW it: Paper/Component contain Areas/Units/Themes,
# which contain Sections, which contain Topics. Without this, 'Section 4' (a child of
# an Area of Study) was wrongly accepted as a PARENT of the next 'Area of Study 2B',
# dragging the previous area's Section 4 into it (GCSE RS 1RB0/1RA0).
_MARKER_TIER = {"paper": 0, "component": 0, "module": 0,
                "unit": 1, "area of study": 1, "theme": 1,
                "section": 2, "topic": 3}

def _marker_tier(fam):
    return _MARKER_TIER.get((fam or "").lower(), 1)


def _anchor_is_parent(cand_text, unit):
    """True only if `cand_text` is a genuine PARENT heading of `unit`, so the
    unit's start may be moved up to it. Rejects sibling and continuation
    headings: '1.1 Integers continued' is NOT a parent of '1.2', and
    'Topic 4 (continued)' is NOT a parent of 'Topic 5'. A marker heading
    (Topic/Theme/Unit/Paper/...) leads a decimal or lettered child only when its
    number is an ancestor of the child's code; a bare/decimal heading leads a
    child only as a STRICT decimal ancestor ('1' or '1.1' -> '1.1.1', never the
    sibling '1.2')."""
    if re.search(r"continued", cand_text, re.I):
        return False
    uparts = _numeric_parts(unit.get("code", ""))
    ufam = unit.get("family", "")
    is_letter_child = bool(re.fullmatch(r"\(?[a-z]\)?", (unit.get("code", "") or "").strip()))
    cand_mu = _match_unit(cand_text)
    if cand_mu:
        cparts = _numeric_parts(cand_mu[1])
        if cparts and uparts:
            return len(cparts) < len(uparts) and uparts[:len(cparts)] == cparts
        if is_letter_child:
            return True            # 'Topic 2' -> '(a)' (no numeric relation)
        if cparts is None and uparts:
            return True            # marker without a parseable number leading a decimal
        # different-family marker: a parent only if it is a HIGHER containment tier
        # (Paper -> Topic OK; Section -> Area of Study is NOT, Section is a child).
        return _marker_tier(cand_mu[0]) < _marker_tier(ufam)
    cand_mn = _match_numeric(cand_text)
    if cand_mn:
        cparts = _numeric_parts(cand_mn[1])
        if cparts and uparts:
            return len(cparts) < len(uparts) and uparts[:len(cparts)] == cparts
        return False
    return False


def collect_units_for_section(doc, body_size, sec, chrome):
    """The set of teachable sub-topic units inside one syllabus section."""
    # A non-whole section that collapses to a single page is a corrupt TOC target
    # (e.g. a bookmark pointing at the contents list). Yield nothing so that
    # collect_subsections retries with the font / whole-document method.
    if not sec.get("whole") and sec["end_page"] <= sec["start_page"]:
        return []
    # Many specs number their teachable sub-topics N.N under each Theme / Unit /
    # Topic (e.g. A-level Business 1.1, 1.2 ...; legacy Chemistry 1.1 ... 6.7).
    # Detect those decimal sub-topics so the Theme/Unit headings become parents
    # and the split happens at the finer N.N level.
    decimal = True
    from_unit_topics = False

    def build(allow_bold_body):
        hs = _heading_lines_in_span(doc, body_size, sec, allow_bold_body=allow_bold_body,
                                    include_decimal=decimal)
        hs.sort(key=lambda h: (h["page"], h["y"]))
        hs = _drop_overview_lists(hs)
        hs = _collapse_runheader(hs)
        hs = _dedup_raw(hs)
        hs = _apply_decimal_split(hs)      # split at N.N where present
        return _drop_parents(hs)

    units = build(allow_bold_body=False)
    # Also accept bold body-size markers: specs whose topics are bold body text
    # (iLowerSecondary/iPrimary CS 'Topic 1 -') AND specs with bold body-size
    # SUB-markers under heading-size topics (A-level Chemistry 'Topic 2A: Bonding'
    # under 'Topic 2'). Prefer the finer split so every spec splits at its deepest
    # sub-topic level.
    bb = build(allow_bold_body=True)
    if len(bb) > len(units):
        units = bb

    # Maths-style specs lay out their syllabus as a 'Topic' table; expand the
    # paper/unit-level units into per-topic units (Topic 1 ... Topic 9).
    table_topics = harvest_table_topics(doc, body_size, sec)
    self_anchored = False
    ut = harvest_unit_topics(doc, body_size, sec) if len(units) <= 18 else []
    if len(table_topics) >= 2 and len(table_topics) >= len(units):
        units = table_topics
        self_anchored = True
    elif len(ut) > len(units):
        # numbered topic list with DISTINCT topics inside every Unit (e.g. IAL Maths
        # Unit P1/C12 -> 1 Algebra, 2 Coordinate geometry, ...). Tried BEFORE the
        # generic coded path so Unit-based specs split cleanly per unit rather than
        # at confusing per-unit-restarting decimal refs.
        units = ut
        from_unit_topics = True
        self_anchored = True
    else:
        # Left-column coded sub-topics missed above: lettered '(a)' (IGCSE
        # Chemistry), bare-numbered 'N Title' (IGCSE History / Statistics), decimal
        # 'N.N' (Biology, Business). Use when it gives a finer split than markers.
        coded = harvest_coded_units(doc, body_size, sec)
        if len(coded) >= 2 and (len(units) < 2 or len(coded) > len(units)):
            # Don't replace a clean heading-level decimal split with a finer
            # coded one when the coarser level is already rich enough.
            # E.g. Eco 9EC0: build() finds 3.1/3.2/… (depth-1, ~20 units);
            # coded finds 3.1.1/3.1.2/… (depth-2, ~70 units). The user wants
            # the 3.1 level. Only skip coded when coded goes DEEPER and units
            # already has ≥10 properly-decimal entries.
            coded_depth = max((u.get("code", "").count(".") for u in coded), default=0)
            units_depth = max((u.get("code", "").count(".") for u in units), default=0)
            if coded_depth > units_depth >= 1 and len(units) >= 10:
                pass  # keep the coarser decimal split from build()
            elif coded_depth >= 2 and len(units) < 2:
                # No heading units at all; group coded units by parent prefix
                # (e.g. 3.1.1/3.1.2 → 3.1) so Economics stays at the 3.1 level.
                seen_parents: dict = {}
                for u in coded:
                    pcode = (u.get("code") or "").rsplit(".", 1)[0]
                    if pcode and pcode not in seen_parents:
                        seen_parents[pcode] = {**u, "code": pcode, "title": ""}
                if 2 <= len(seen_parents) < len(coded):
                    units = list(seen_parents.values())
                else:
                    units = coded
            else:
                units = coded

    # Fallbacks when in-page marker headings are absent (IGCSE numbered specs).
    if len(units) < 2:
        toc_u = _toc_child_units(doc, sec)
        if len(toc_u) >= 2:
            units = toc_u
        else:
            nums = []
            for pno in range(sec["start_page"], sec["end_page"] + 1):
                if pno < 0 or pno >= doc.page_count:
                    continue
                pw = doc[pno].rect.width
                for ln in get_page_lines(doc[pno]):
                    if pno == sec["start_page"] and ln["y0"] < sec["start_y"] - 1:
                        continue
                    if pno == sec["end_page"] and ln["y0"] >= sec["end_y"]:
                        continue
                    if ln["size"] < body_size + 2.0 or ln["x0"] > pw * 0.5:
                        continue
                    t = norm_ws(ln["text"])
                    # never treat a top-level document section as a sub-topic
                    if (SYLLABUS_SECT_RE.search(t) or STOP_SUBSECT_RE.search(t)
                            or SECT_EXCLUDE_RE.search(t) or re.match(r"^\d+\s+Introduction", t, re.I)):
                        continue
                    mn = _match_numeric(t)
                    if mn:
                        nums.append({"family": "Num", "code": mn[1], "title": mn[2],
                                     "page": pno, "y": ln["y0"], "size": round(ln["size"], 1)})
            nums = _collapse_runheader(sorted(nums, key=lambda h: (h["page"], h["y"])))
            if len(nums) >= 2:
                units = nums
    if not units:
        return []
    units.sort(key=lambda h: (h["page"], h["y"]))

    # Trim only the LAST unit's trailing content at the first STOP sub-heading
    # that appears after the last unit starts (so assessment / practical-
    # endorsement material is not pulled into the final sub-topic). STOP
    # headings BETWEEN units are ignored -- they never delete a whole unit.
    content_end_page, content_end_y = sec["end_page"], sec["end_y"]
    last = units[-1]
    for pno in range(last["page"], sec["end_page"] + 1):
        if pno < 0 or pno >= doc.page_count:
            continue
        pw = doc[pno].rect.width
        for ln in get_page_lines(doc[pno]):
            if pno == sec["end_page"] and ln["y0"] >= sec["end_y"]:
                continue
            t = norm_ws(ln["text"])
            if (ln["size"] >= body_size + 1.5 and ln["x0"] < pw * 0.5
                    and STOP_SUBSECT_RE.search(t) and not _match_unit(t)):
                if (pno, ln["y0"]) > (last["page"], last["y"] + 5):
                    content_end_page, content_end_y = pno, ln["y0"]
                    break
        else:
            continue
        break

    # Carry a parent topic/section heading into the FIRST sub-topic beneath it: if a
    # heading clearly bigger than a sub-topic sits in the gap just before it (e.g.
    # 'Topic 2 Structure and functions' above '(a) Level of organisation', or a
    # 'Theme 2' above '2.1'), move that sub-topic's start up to the parent heading --
    # so the heading leads the new topic's first PDF instead of trailing the previous
    # topic's last PDF. Skipped for table/unit-topic harvests (they self-anchor).
    if not self_anchored:
        units.sort(key=lambda u: (u["page"], u["y"]))
        # Snapshot of all sub-topic positions BEFORE anchoring so we can
        # exclude sibling units from being picked as a parent anchor.
        orig_positions = {(u["page"], round(u["y"])) for u in units}
        for i, u in enumerate(units):
            usz = u.get("size", body_size)
            prev = (units[i - 1]["page"], units[i - 1]["y"]) if i > 0 \
                else (sec["start_page"], sec["start_y"] - 1)
            cur = (u["page"], u["y"])
            anc = None
            anc_marker = False
            for pno in range(prev[0], cur[0] + 1):
                if pno < 0 or pno >= doc.page_count:
                    continue
                pw = doc[pno].rect.width
                for ln in get_page_lines(doc[pno]):
                    pos = (pno, ln["y0"])
                    if pos <= prev or pos >= cur:
                        continue
                    t = norm_ws(ln["text"])
                    if (ln["x0"] < pw * 0.5 and t and len(t) < 80
                            and not EDX_FOOTER_RE.search(t)):
                        # Skip the legacy running header ('Unit 1' echoed at the top
                        # of every page). It looks like a parent of '1.6' but sits in
                        # the header band with the previous sub-topic's tail between
                        # it and the real heading -- anchoring there drags that tail
                        # (objectives j/k of 1.5) into 1.6's first PDF.
                        if (chrome.get("header_y") is not None
                                and abs(ln["y0"] - chrome["header_y"]) < 12):
                            continue
                        # Only unit-marker headings (Topic N, Theme N, etc. or
                        # bare decimal N.N) qualify as parent anchors.  We use
                        # body_size as the minimum so same-size parent headings
                        # (e.g. "Topic 2: Data" equalling sub-topic size in GCSE
                        # specs) are accepted; the orig_positions guard already
                        # prevents sibling sub-topics from being chosen.
                        if not (_match_unit(t) or NUMERIC_HEAD_RE.match(t)):
                            continue
                        if ln["size"] < body_size:
                            continue
                        if (pno, round(ln["y0"])) in orig_positions:
                            continue
                        # The anchor must be a genuine PARENT, never the previous
                        # sub-topic's continuation header ('1.1 Integers continued')
                        # or a sibling, which would drag the previous topic's tail
                        # into this unit's first PDF.
                        if not _anchor_is_parent(t, u):
                            continue
                        if anc is None or pos > anc:
                            anc = pos
                            anc_marker = bool(_match_unit(t))
            if anc:
                apply = True
                # A real MARKER parent ('Topic 1', 'Theme 2') legitimately carries its
                # own intro text before the first child, so it may sit far above (e.g.
                # 9BI0 'Topic 1: Biological Molecules' + a 245pt intro then '1.1').
                # A BARE-NUMERIC anchor ('2 Inorganic chemistry of group 7') only
                # coincidentally prefix-matches a decimal unit ('2.8'); accept it only
                # when it sits IMMEDIATELY above the unit. If real body content lies
                # between, it's a spurious match (or the previous sub-topic's tail) --
                # reject so that content is not dragged into this unit (legacy Chem).
                if not anc_marker:
                    blockers = 0
                    for pno2 in range(anc[0], cur[0] + 1):
                        if pno2 < 0 or pno2 >= doc.page_count:
                            continue
                        for ln2 in get_page_lines(doc[pno2]):
                            pos2 = (pno2, ln2["y0"])
                            if pos2 <= anc or pos2 >= cur:
                                continue
                            t2 = norm_ws(ln2["text"])
                            if not t2 or EDX_FOOTER_RE.search(t2):
                                continue
                            if (chrome.get("header_y") is not None
                                    and abs(ln2["y0"] - chrome["header_y"]) < 12):
                                continue
                            blockers += 1
                            if blockers > 3:
                                break
                        if blockers > 3:
                            break
                    apply = blockers <= 3
                if apply:
                    u["page"], u["y"] = anc

    out = []
    # optional leading "Overview" unit for the section intro before the first unit.
    f = units[0]
    intro_gap = (f["page"] > sec["start_page"]) or (f["y"] - sec["start_y"] > 130)
    if intro_gap and not sec.get("whole"):
        out.append({"code": "", "title": "Overview", "family": "Overview",
                    "start_page": sec["start_page"], "start_y": sec["start_y"],
                    "end_page": f["page"], "end_y": f["y"]})

    for i, u in enumerate(units):
        if i + 1 < len(units):
            ep, ey = units[i + 1]["page"], units[i + 1]["y"]
        else:
            ep, ey = content_end_page, content_end_y
        code = f"{u['family']} {u['code']}".strip() if u["family"] != "Num" else u["code"]
        out.append({"code": code, "title": u["title"], "family": u["family"],
                    "start_page": u["page"], "start_y": u["y"],
                    "end_page": ep, "end_y": ey})

    # Legacy specs often list each unit twice (a one-page unit overview block,
    # then the detailed content block). Keep the larger span per unit code, and
    # carry across a title if the kept copy lacked one. Skipped when units came
    # from the per-unit topic harvester (its 'Topic N' codes repeat across units
    # by design -- collapsing by code would merge distinct topics, e.g. IAL Maths
    # legacy WMA01 where every Unit has a Topic 1).
    if sec.get("whole") and not from_unit_topics:
        best = {}
        for u in out:
            k = u["code"]
            if k not in best:
                best[k] = u
                continue
            prev = best[k]
            if not u["title"] and prev["title"]:
                u["title"] = prev["title"]
            if not prev["title"] and u["title"]:
                prev["title"] = u["title"]
            if (u["end_page"] - u["start_page"]) > (prev["end_page"] - prev["start_page"]):
                best[k] = u
        out = sorted(best.values(), key=lambda u: (u["start_page"], u["start_y"]))
    return out


def collect_subsections(doc, body_size, chrome):
    """All sub-topic units across every syllabus section, in document order.
    Tries TOC, then font-geometry, then whole-document; the first method that
    yields sub-topics wins (so a corrupt TOC whose section span collapses to one
    page does not block detection)."""
    # A tiered spec (Foundation + Higher) lists the same topics twice; detect the
    # tier headings so _dedup_units can safely collapse the repeat.
    tiered = False
    fnd = hgr = False
    for pno in range(min(doc.page_count, 60)):
        pw = doc[pno].rect.width
        for ln in get_page_lines(doc[pno]):
            t = norm_ws(ln["text"])
            if ln["size"] >= body_size + 1.3 and ln["x0"] < pw * 0.5:
                if re.fullmatch(r"Foundation\s+Tier", t, re.I):
                    fnd = True
                elif re.fullmatch(r"Higher\s+Tier", t, re.I):
                    hgr = True
    tiered = fnd and hgr

    methods = [("numbered", _sections_numbered_content(doc, body_size)),
               ("toc", _sections_toc(doc)),
               ("font", _sections_font(doc, body_size)),
               ("legacy", _sections_whole(doc))]
    for method, sections in methods:
        if not sections:
            continue
        units = []
        for sec in sections:
            units.extend(collect_units_for_section(doc, body_size, sec, chrome))
        if units:
            return _dedup_units(units, tiered=tiered), method, len(sections)
    return [], "none", 0


def _dedup_units(units, tiered=False):
    """Remove duplicate topic blocks. Two cases:
    * Tier duplication -- a Foundation + Higher tier (or two content sections)
      both number the SAME topics 1..N (GCSE/IGCSE Maths). Only when `tiered`
      (the doc actually has Foundation/Higher tier headings) and most units share
      an exact (code, title): keep one copy of each (largest span -- Higher tier
      carries the most content).
    * A contents-list echo -- a single-page listing of a topic just before its
      real multi-page block: drop the listing.
    Genuinely distinct same-titled topics in different papers (Further Maths
    'Further calculus' in FP1/FP2; RS 'Works of scholars' across religion papers)
    are NOT collapsed -- only the explicit Foundation/Higher tier case is."""
    from collections import defaultdict
    groups = defaultdict(list)
    untitled = []
    for u in units:
        key = (u.get("code", ""), norm_ws(u.get("title", "")).lower())
        (untitled if not (key[0] or key[1]) else groups[key]).append(u)

    titled = sum(len(v) for v in groups.values())
    dup = sum(len(v) for v in groups.values() if len(v) > 1)
    high = tiered and titled and dup / titled > 0.35   # Foundation/Higher tier spec

    out = []
    if high and untitled:                          # collapse repeated "Overview"s
        out.append(max(untitled, key=lambda u: u["end_page"] - u["start_page"]))
    else:
        out.extend(untitled)
    for us in groups.values():
        if high:
            out.append(max(us, key=lambda u: u["end_page"] - u["start_page"]))
            continue
        us.sort(key=lambda u: (u["end_page"] - u["start_page"]), reverse=True)
        kept = []
        for u in us:
            twin = any(abs(u["start_page"] - k["start_page"]) <= 2 for k in kept)
            if twin and u["end_page"] - u["start_page"] == 0:
                continue
            kept.append(u)
        out.extend(kept)
    return sorted(out, key=lambda u: (u["start_page"], u["start_y"]))


# ----------------------------------------------------------------------------
# Build PDFs
# ----------------------------------------------------------------------------

def _safe_name(code, title, seq):
    title = re.sub(r"\s+", " ", (title or "").replace("�", "")).strip()
    title = re.sub(r"[^A-Za-z0-9]+", "_", title).strip("_")[:42]
    code = re.sub(r"[^A-Za-z0-9]+", "_", code or "").strip("_")
    stem = "_".join(p for p in (code, title) if p) or "subsection"
    return f"{seq:03d}_{stem}.pdf"


def _plan_for_unit(doc, body_size, u, chrome, cache):
    sp0 = u["start_page"]
    sp1 = min(u["end_page"], doc.page_count - 1)
    plan = []
    for pidx in range(sp0, sp1 + 1):
        if pidx < 0 or pidx >= doc.page_count:
            continue
        rect = page_crop(doc[pidx], body_size,
                         is_start=(pidx == sp0), is_end=(pidx == sp1),
                         start_y=u["start_y"], end_y=u["end_y"], chrome=chrome, cache=cache)
        if rect is not None:
            plan.append((pidx, rect))
    return plan


def build_subsection_pdfs(src_path, out_dir, proof=False, a4=True):
    doc = fitz.open(src_path)
    body_size = estimate_body_size(doc)
    chrome = build_doc_chrome(doc, body_size)
    units, method, n_sec = collect_subsections(doc, body_size, chrome)
    info = {"method": method, "sections": n_sec, "units": len(units),
            "files": 0, "warnings": [], "manifest": []}

    if not units:
        if looks_like_non_spec(doc):
            info["warnings"].append("Looks like a mark scheme / issue summary, not a "
                                    "full specification; nothing written.")
        else:
            info["warnings"].append("No syllabus sub-topics located.")
        doc.close()
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
        plan = _plan_for_unit(doc, body_size, u, chrome, cache)
        if not plan:
            continue
        seq += 1
        out = emit_doc(doc, plan, a4=a4)
        fname = _safe_name(u["code"], u["title"], seq)
        fpath = os.path.join(out_dir, fname)
        out.save(fpath, garbage=4, deflate=True)
        info["files"] += 1
        info["manifest"].append({"file": fname, "code": u["code"], "title": u["title"],
                                 "family": u.get("family", ""), "pages": out.page_count})
        if proof and seq == 1:
            out[0].get_pixmap(dpi=150).save(fpath[:-4] + "_proof.png")
        out.close()

    if info["files"] == 0:
        info["warnings"].append("Sub-topics found but produced no content pages after trimming.")

    with open(os.path.join(out_dir, "_subsections.json"), "w", encoding="utf-8") as fh:
        json.dump({"method": method, "sections": n_sec, "n": info["files"],
                   "subsections": info["manifest"]}, fh, ensure_ascii=False, indent=2)
    doc.close()
    return info


def build_section_pdf(src_path, out_path, proof=False, a4=True):
    """--mode section: one PDF per whole syllabus section."""
    doc = fitz.open(src_path)
    body_size = estimate_body_size(doc)
    chrome = build_doc_chrome(doc, body_size)
    sections, method = find_sections(doc, body_size)
    info = {"method": method, "spans": len(sections), "pages_out": 0, "warnings": []}
    if not sections:
        info["warnings"].append("No syllabus section located.")
        doc.close()
        return info
    cache = {}
    plan = []
    for sec in sections:
        sp0, sp1 = sec["start_page"], min(sec["end_page"], doc.page_count - 1)
        for pidx in range(sp0, sp1 + 1):
            rect = page_crop(doc[pidx], body_size,
                             is_start=(pidx == sp0), is_end=(pidx == sp1),
                             start_y=sec["start_y"], end_y=sec["end_y"], chrome=chrome, cache=cache)
            if rect is not None:
                plan.append((pidx, rect))
    if not plan:
        info["warnings"].append("Section found but produced no content pages.")
        doc.close()
        return info
    out = emit_doc(doc, plan, a4=a4)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    out.save(out_path, garbage=4, deflate=True)
    info["pages_out"] = out.page_count
    if proof:
        out[0].get_pixmap(dpi=150).save(out_path[:-4] + "_proof_p1.png")
    out.close()
    doc.close()
    return info


# ----------------------------------------------------------------------------
# Driver
# ----------------------------------------------------------------------------

def find_pdfs(root):
    skip = {"extracted_syllabus", "extracted_syllabus_pdf",
            "extracted_syllabus_pdf_edexcel", "extracted_syllabus_pdf_aqa"}
    out = []
    for dirpath, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in skip]
        for f in files:
            if f.lower().endswith(".pdf"):
                out.append(os.path.join(dirpath, f))
    return sorted(out)


def main():
    ap = argparse.ArgumentParser(description="Crop Edexcel syllabus content into per-sub-topic PDFs.")
    ap.add_argument("pdfs", nargs="*", help="Specific PDF files (default: scan --root).")
    ap.add_argument("--root", default=".", help="Root folder to scan for PDFs.")
    ap.add_argument("--out", default="extracted_syllabus_pdf_edexcel", help="Output folder.")
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
