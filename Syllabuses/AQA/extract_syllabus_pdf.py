#!/usr/bin/env python3
"""
extract_syllabus_pdf.py  --  Carve the AQA "Subject content" (the syllabus) out
                             of each AQA specification PDF into NEW PDFs that
                             preserve the original page exactly (fonts, colours,
                             table styling) -- only the running header and footer
                             of every page are cropped away.

Two output modes (default: subsection)
--------------------------------------
* subsection -- one PDF per teachable subsection (e.g. "3.1.2 Amount of
                substance"), each carrying its own content tables. This is the
                screenshot example. A subsection is a level-2 node of the topic
                tree; a level-1 topic that has no sub-topics (e.g. Maths
                "B: Algebra and functions") becomes its own file. The first
                subsection of each topic also carries the topic heading + any
                overview text above it, and the first subsection of the whole
                section carries the "Subject content" intro, so nothing is lost.
* section    -- one PDF per spec holding the whole Subject-content section.

Why this approach (vs. re-typesetting extracted text)
-----------------------------------------------------
The original PDF's text layer, embedded fonts, vector table fills/borders and
two-column layout are kept byte-for-byte. We never re-draw anything; we only set
each page's *crop box* to the rectangle that bounds the real syllabus content,
hiding the page chrome (the small "AQA ... exams ..." header strip, the
"Visit ... for the most up-to-date specification" footer, page numbers and the
thin decorative rules around them). The result is visually identical to the
source -- just the syllabus, page-margin-clean, with no header/footer.

How the region is found
-----------------------
1. Reuse extract_syllabus.build_heading_list (TOC + font-aware scan) to locate
   every level-1 section heading with its true page + y position. The
   "Subject content" section(s) are the syllabus; the next level-1 heading
   ("Scheme of assessment", ...) marks the end.
2. For every page in that span, compute the content band:
     top    = top of the first real body element (text size > body, or a table
              fill/border) on the page, header stripped;
     bottom = bottom of the last real body element, footer stripped.
   Chrome is excluded by font size (header/footer are ~8pt vs ~11pt body) and by
   the FOOTER_RE banner patterns; thin full-width rules in the top/bottom margin
   are treated as chrome too.
3. On the section's first page the band starts at the section heading; on the
   last page it stops just above the next section's heading. Full page width is
   kept so the original left/right margins (and table backgrounds) are intact.

Usage
-----
    python extract_syllabus_pdf.py                 # scan ./ -> ./extracted_syllabus_pdf/
    python extract_syllabus_pdf.py --root DIR --out OUTDIR
    python extract_syllabus_pdf.py path/to/one.pdf [more.pdf ...]
    python extract_syllabus_pdf.py one.pdf --proof   # also write a PNG of page 1
"""

from __future__ import annotations
import argparse
import json
import os
import re
import sys
import traceback

import fitz  # PyMuPDF
import numpy as np

# Reuse the battle-tested heading/section detection from the JSON extractor.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from extract_syllabus import (  # noqa: E402
    build_heading_list,
    build_fallback_headings,
    estimate_body_size,
    get_page_lines,
    norm_ws,
    metadata_from_path,
    looks_like_non_spec,
    SUBJECT_CONTENT_RE,
    FOOTER_RE,
)

PAD = 8.0          # points of breathing room kept around the content band
MIN_BAND = 24.0    # a cropped band thinner than this is treated as empty -> page skipped


# ----------------------------------------------------------------------------
# Section span detection
# ----------------------------------------------------------------------------

def find_subject_content_spans(doc, body_size):
    """Return (spans, headings, method) where spans is a list of
    {start_page, start_y, end_page, end_y, title} for every Subject-content
    section. end_page/end_y point at the *next* level-1 heading (the first thing
    that is NOT syllabus); end_page = doc end if the section runs to the document
    end. Falls back to font-geometry headings when the TOC path finds nothing."""
    def spans_from(headings):
        l1 = [h for h in headings if h.get("level") == 1 and h.get("y", -1) >= 0]
        l1.sort(key=lambda h: (h["page_real"], h["y"]))
        out = []
        for i, h in enumerate(l1):
            title = (h.get("title") or "") + " " + (h.get("toc_title") or "")
            if not SUBJECT_CONTENT_RE.search(title):
                continue
            if i + 1 < len(l1):
                nxt = l1[i + 1]
                end_page, end_y = nxt["page_real"], nxt["y"]
            else:
                end_page, end_y = doc.page_count - 1, 1e9
            out.append({
                "start_page": h["page_real"], "start_y": h["y"],
                "end_page": end_page, "end_y": end_y,
                "title": (h.get("title") or h.get("toc_title") or "Subject content").strip(),
            })
        return out

    headings = build_heading_list(doc, body_size)
    spans = spans_from(headings)
    if spans:
        return spans, headings, "toc"

    fb = build_fallback_headings(doc, body_size)
    spans = spans_from(fb)
    if spans:
        return spans, fb, "font-fallback"
    return [], headings, "none"


# ----------------------------------------------------------------------------
# Subsection unit detection (position-preserving topic tree)
# ----------------------------------------------------------------------------

def _pos_tree(flat):
    """Nest a flat heading list (carrying absolute `level` + page/y) into a tree,
    using the SAME level-driven algorithm as extract_syllabus.build_tree so the
    structure matches the JSON, but keeping each node's page/y position."""
    roots, stack = [], []
    for it in flat:
        node = {
            "code": it.get("code", "") or "",
            "title": (it.get("title") or it.get("toc_title") or "").strip(),
            "abs": it["level"],
            "page": it["page_real"],
            "y": it["y"],
            "children": [],
        }
        while stack and stack[-1]["abs"] >= node["abs"]:
            stack.pop()
        (stack[-1]["children"] if stack else roots).append(node)
        stack.append(node)
    return roots


def _renumber(node, depth=1):
    node["rlevel"] = depth
    for c in node["children"]:
        _renumber(c, depth + 1)


def _unit(code, title, node):
    return {"code": code or "", "title": title or "",
            "start_page": node["page"], "start_y": node["y"]}


def _collect_units(roots):
    """Cut the tree into subsection units. Each unit starts EXACTLY at its own
    heading (no parent headings bled in). For every level-1 topic:
      * if it has CODED level-2 children (e.g. Chemistry 3.1 -> 3.1.1, 3.1.2),
        emit one unit per coded child (carrying any deeper sub-topics inside),
        plus the topic's own overview prose as a separate file when present;
      * otherwise (a leaf topic, or one whose only sub-headings are codeless
        labels like Art & Design's "Areas of study" / "Skills and techniques"),
        emit the WHOLE topic as a single unit -- those labels are parts of one
        sub-topic, not separate sub-topics.
    Returns units in document order; ends are filled in by the caller."""
    for r in roots:
        _renumber(r, 1)
    units = []
    for root in roots:
        coded = [c for c in root["children"] if c["code"]]
        if not coded:                                  # leaf, or codeless-label children
            units.append(_unit(root["code"], root["title"], root))
            continue
        first = coded[0]
        has_overview = (first["page"] > root["page"]) or (first["y"] - root["y"] > 40)
        if has_overview:
            # The topic carries real overview prose -> give it its own file (which
            # holds the topic heading); each sub-topic then starts at its own heading.
            units.append(_unit(root["code"], root["title"], root))
            for ch in coded:
                units.append(_unit(ch["code"], ch["title"], ch))
        else:
            # No overview: the topic heading leads its FIRST sub-topic, so the topic
            # title shows there (and is NOT swallowed by the previous sub-topic).
            units.append({"code": coded[0]["code"], "title": coded[0]["title"],
                          "start_page": root["page"], "start_y": root["y"]})
            for ch in coded[1:]:
                units.append(_unit(ch["code"], ch["title"], ch))
    units.sort(key=lambda u: (u["start_page"], u["start_y"]))
    return units


def harvest_code_cells(doc):
    """Recover deep sub-topic codes that live as a standalone left-column table
    cell (e.g. legacy specs: a cell '3.5.1' with the bold title 'Thermodynamics'
    in the next cell). These are NOT heading-sized, so the normal scan misses
    them. We require the WHOLE line to be a decimal code of depth >= 3 in the
    left column, which never matches a modern combined 'code + title' heading."""
    out = []
    for pno in range(doc.page_count):
        pw = doc[pno].rect.width
        lines = get_page_lines(doc[pno])
        lines.sort(key=lambda l: (round(l["y0"], 1), l["x0"]))
        for ln in lines:
            t = norm_ws(ln["text"])
            if not re.fullmatch(r"\d{1,2}(?:\.\d{1,3}){2,}", t):   # standalone deep code
                continue
            if ln["x0"] > pw * 0.25:                               # must be left column
                continue
            title = ""
            for o in lines:                                        # bold title beside it
                if abs(o["y0"] - ln["y0"]) < 6 and ln["x1"] - 2 < o["x0"] < pw * 0.55:
                    cand = norm_ws(o["text"])
                    if cand and not re.fullmatch(r"[\d.]+", cand):
                        title = cand
                        break
            out.append({"code": t, "title": title, "toc_title": title,
                        "page_real": pno, "page": pno, "y": ln["y0"],
                        "y_end": ln.get("y1", ln["y0"] + ln["size"]),
                        "level": t.count(".") + 1, "source": "codecell"})
    return out


def _merge_headings(base, extra):
    """Add `extra` headings to `base`, dropping any that collide with an existing
    heading at the same physical position, and return sorted by document order."""
    seen = {(h["page_real"], round(h["y"], 0)) for h in base if h.get("y", -1) >= 0}
    merged = list(base)
    for h in extra:
        key = (h["page_real"], round(h["y"], 0))
        if key in seen:
            continue
        seen.add(key)
        merged.append(h)
    merged.sort(key=lambda h: (h["page_real"], h["y"] if h.get("y", -1) >= 0 else 1e9))
    return merged


def collect_subsections(doc, body_size):
    """All subsection units across every Subject-content section, in document
    order, with start+end positions. Falls back to font-geometry headings."""
    def units_from(headings):
        l1 = [i for i, h in enumerate(headings)
              if h.get("level") == 1 and h.get("y", -1) >= 0]
        out = []
        for k, i in enumerate(l1):
            h = headings[i]
            if not SUBJECT_CONTENT_RE.search((h.get("title") or "") + " " + (h.get("toc_title") or "")):
                continue
            nexti = l1[k + 1] if k + 1 < len(l1) else len(headings)
            if nexti < len(headings):
                end_page, end_y = headings[nexti]["page_real"], headings[nexti]["y"]
            else:
                end_page, end_y = doc.page_count - 1, 1e9
            body = [headings[j] for j in range(i + 1, nexti)
                    if headings[j].get("level", 99) >= 2 and headings[j].get("y", -1) >= 0]
            sec_units = _collect_units(_pos_tree(body))
            if not sec_units:
                continue
            # NB: we deliberately do NOT pull the section's "Subject content"
            # intro into the first subsection -- each file is its own subsection.
            for u in range(len(sec_units)):
                if u + 1 < len(sec_units):
                    sec_units[u]["end_page"] = sec_units[u + 1]["start_page"]
                    sec_units[u]["end_y"] = sec_units[u + 1]["start_y"]
                else:
                    sec_units[u]["end_page"], sec_units[u]["end_y"] = end_page, end_y
            out.extend(sec_units)
        return out

    code_cells = harvest_code_cells(doc)
    units = units_from(_merge_headings(build_heading_list(doc, body_size), code_cells))
    if units:
        return units, "toc"
    units = units_from(_merge_headings(build_fallback_headings(doc, body_size), code_cells))
    return units, ("font-fallback" if units else "none")


# ----------------------------------------------------------------------------
# Per-page content box  (position + pattern based chrome removal)
# ----------------------------------------------------------------------------
#
# The crop is computed in three steps, all robust to font size so that small
# body/table text is NEVER mistaken for chrome and footers NEVER leak:
#   1. Find the header/footer cut lines -- the bottom of the running header and
#      the top of the running footer -- by looking only in the top/bottom margin
#      zones for small text, banner phrases, page numbers and wide decorative
#      bars/rules (e.g. the lavender rule, the legacy dark-red header bar).
#   2. Take every real content element (text of any size + table fills/borders)
#      strictly between those cuts as the body, and bound it tightly -> no
#      clipping of the last table row, no trailing whitespace.
#   3. Drop far-right side tabs (legacy "unit number" markers) from the width.

# Padding around the content box. Right/bottom get a little extra "overlay" so a
# wide line or a low table border is never shaved off.
PAD_LEFT = 6.0
PAD_RIGHT = 13.0
PAD_TOP = 6.0
PAD_BOTTOM = 13.0
START_TOP = 4.0     # headroom above a subsection's OWN heading (kept small so the
                    # previous subsection's last line is never pulled in)
GAP = 2.0


def margin_cuts(page, body_size, pw, ph):
    """(header_bottom, footer_top): y below which the header chrome ends and y
    above which the footer chrome begins. Only the top 16%% / bottom 12%% margins
    are inspected, so mid-page small text is safe."""
    import re
    top_zone = ph * 0.16
    bot_zone = ph * 0.88
    small = body_size - 0.6          # header/footer are smaller than body
    header_bottom, footer_top = 0.0, ph

    for ln in get_page_lines(page):
        t = norm_ws(ln["text"])
        if not t:
            continue
        chrome = (ln["size"] <= small or FOOTER_RE.search(t)
                  or re.fullmatch(r"\d{1,4}", t))      # bare page number
        if not chrome:
            continue
        if ln["y1"] <= top_zone:
            header_bottom = max(header_bottom, ln["y1"])
        elif ln["y0"] >= bot_zone:
            footer_top = min(footer_top, ln["y0"])

    # wide decorative bars / rules (header underline, legacy colour banner)
    for d in page.get_drawings():
        r = d["rect"]
        if r.width < pw * 0.6:
            continue
        if r.y1 <= top_zone:
            header_bottom = max(header_bottom, r.y1)
        elif r.y0 >= bot_zone:
            footer_top = min(footer_top, r.y0)

    return header_bottom, footer_top


INK_DPI = 108.0          # render scale for ink detection (1.5x)
INK_THRESH = 244         # a pixel darker than this on any channel counts as ink
# horizontal window searched for ink: excludes the extreme outer margins where the
# legacy "unit number" side tabs and edge bars live, but keeps all real content
# (AQA body sits within ~9%..92% of the page width).
INK_X_LO_FRAC = 0.075
INK_X_HI_FRAC = 0.925


def _page_ink(page, cache):
    """Cached greyscale-ish ink array for a page: (np.array[H,W,3], scale, W, H)."""
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
    """Bounding box (pt) of actual rendered ink within the given window, or None.
    Measuring real pixels (not the text bbox) is essential: several legacy specs
    use fonts whose reported glyph widths are far narrower than what is drawn, so
    a bbox-based crop shaves the right-hand text. Pixels never lie.

    Ink columns are grouped into runs; an isolated run that lives entirely in the
    extreme outer margin (a legacy unit-number side tab / edge bar) is dropped."""
    arr, scale, W, H = _page_ink(page, cache)
    pw = page.rect.width
    a = max(0, int(x_lo * scale)); b = min(W, int(round(x_hi * scale)))
    c = max(0, int(y_lo * scale)); d = min(H, int(round(y_hi * scale)))
    if b <= a or d <= c:
        return None
    ink = (arr[c:d, :, :] < INK_THRESH).any(axis=2)         # (rows, full width)
    col_any = ink.any(axis=0)
    col_any[:a] = False; col_any[b:] = False                # restrict to the window
    idx = np.where(col_any)[0]
    if len(idx) == 0:
        return None

    gap = max(8, int(12 * scale))                           # >=~12pt blank splits columns
    groups, s, p = [], idx[0], idx[0]
    for i in idx[1:]:
        if i - p > gap:
            groups.append((s, p)); s = i
        p = i
    groups.append((s, p))
    out_l, out_r = 0.085 * pw * scale, 0.915 * pw * scale    # outer-margin (px)
    kept = [g for g in groups if not (g[1] < out_l or g[0] > out_r)]
    if not kept:
        kept = groups
    minx = min(g[0] for g in kept); maxx = max(g[1] for g in kept)

    row_any = ink[:, minx:maxx + 1].any(axis=1)
    ridx = np.where(row_any)[0]
    if len(ridx) == 0:
        return None
    return minx / scale, (c + ridx[0]) / scale, \
           (maxx + 1) / scale, (c + ridx[-1] + 1) / scale


def page_crop(page, body_size, is_start, is_end, start_y, end_y, cache):
    """The fitz.Rect to crop this page to, or None if the band is empty. Bounds
    come from the real rendered ink between the running header and footer, so
    nothing is ever clipped and the chrome / side tabs are excluded."""
    pw, ph = page.rect.width, page.rect.height
    header_bottom, footer_top = margin_cuts(page, body_size, pw, ph)
    head = header_bottom + 2.0                         # stay clear of the header rule
    foot = footer_top - 2.0                            # stay clear of the footer rule

    # ink is measured strictly INSIDE the chrome-free band, so the full-width
    # header/footer rules never inflate the bounds.
    y_lo = max(head, start_y) if is_start else head
    y_hi = min(foot, end_y) if is_end else foot
    if y_hi - y_lo < MIN_BAND:
        return None

    bb = ink_bbox(page, pw * INK_X_LO_FRAC, pw * INK_X_HI_FRAC, y_lo, y_hi, cache)
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
    left = max(0.0, ix0 - PAD_LEFT)
    right = min(pw, ix1 + PAD_RIGHT)
    return fitz.Rect(left, top, right, bottom)


# ----------------------------------------------------------------------------
# Emit -- compose the cropped regions into an output PDF
# ----------------------------------------------------------------------------

A4 = fitz.paper_rect("a4")          # 595.276 x 841.890 pt
A4_MARGIN_TOP = 42.0
A4_MARGIN_BOTTOM = 42.0
A4_MARGIN_SIDE = 30.0


def emit_doc(src_doc, plan, a4=True):
    """Build an output PDF from a plan of (src_page_idx, crop_rect).

    a4=True  -> every output page is a uniform A4 sheet; the cropped region is
                placed at its natural scale, centred horizontally and top-aligned
                (shrunk only if it would not otherwise fit the A4 text area), so
                every page is the same size and the text stays the same size.
    a4=False -> each page IS the crop rectangle (variable size)."""
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
            # embeds the clipped source region (vector + fonts preserved)
            page.show_pdf_page(target, src_doc, pidx, clip=rect)
        else:
            out.insert_pdf(src_doc, from_page=pidx, to_page=pidx)
            out[-1].set_cropbox(rect)
    return out


# ----------------------------------------------------------------------------
# Build the cropped PDF
# ----------------------------------------------------------------------------

def build_syllabus_pdf(src_path, out_path, proof=False, a4=True):
    doc = fitz.open(src_path)
    body_size = estimate_body_size(doc)
    spans, _headings, method = find_subject_content_spans(doc, body_size)

    info = {"method": method, "spans": len(spans), "pages_out": 0, "warnings": []}

    if not spans:
        if looks_like_non_spec(doc):
            info["warnings"].append("Not a specification (looks like a mark scheme / "
                                    "question paper); no syllabus PDF written.")
        else:
            info["warnings"].append("No 'Subject content' section located; "
                                    "no syllabus PDF written.")
        doc.close()
        return info

    # Collect, in document order, every (page_idx, crop_rect) to emit.
    pix_cache = {}
    plan = []  # list of (src_page_idx, fitz.Rect)
    for sp in spans:
        sp0, sp1 = sp["start_page"], sp["end_page"]
        for pidx in range(sp0, sp1 + 1):
            if pidx < 0 or pidx >= doc.page_count:
                continue
            rect = page_crop(
                doc[pidx], body_size,
                is_start=(pidx == sp0), is_end=(pidx == sp1),
                start_y=sp["start_y"], end_y=sp["end_y"], cache=pix_cache,
            )
            if rect is not None:
                plan.append((pidx, rect))

    if not plan:
        info["warnings"].append("Subject-content section found but produced no "
                                "content pages after trimming.")
        doc.close()
        return info

    out = emit_doc(doc, plan, a4=a4)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    out.save(out_path, garbage=4, deflate=True)
    info["pages_out"] = out.page_count

    if proof:
        png = out_path[:-4] + "_proof_p1.png"
        pix = out[0].get_pixmap(dpi=150)
        pix.save(png)
        info["proof"] = png

    out.close()
    doc.close()
    return info


# ----------------------------------------------------------------------------
# Per-subsection PDFs
# ----------------------------------------------------------------------------

def _safe_name(code, title, seq):
    """A tidy, ordered, filesystem-safe filename for one subsection."""
    import re
    title = (title or "").replace("�", "")
    title = re.sub(r"\s+", " ", title).strip()
    title = re.sub(r"[^A-Za-z0-9]+", "_", title).strip("_")[:40]   # keep paths short (Windows MAX_PATH)
    code = re.sub(r"[^A-Za-z0-9.]+", "", code or "")
    stem = "_".join(p for p in (code, title) if p) or "subsection"
    return f"{seq:03d}_{stem}.pdf"


def build_subsection_pdfs(src_path, out_dir, proof=False, a4=True):
    """Write one cropped PDF per subsection into out_dir. Returns an info dict."""
    doc = fitz.open(src_path)
    body_size = estimate_body_size(doc)
    units, method = collect_subsections(doc, body_size)
    info = {"method": method, "units": len(units), "files": 0, "warnings": [], "manifest": []}

    if not units:
        if looks_like_non_spec(doc):
            info["warnings"].append("Not a specification (looks like a mark scheme / "
                                    "question paper); nothing written.")
        else:
            info["warnings"].append("No 'Subject content' subsections located.")
        doc.close()
        return info

    os.makedirs(out_dir, exist_ok=True)
    # Clear any stale output from a previous run so re-runs are idempotent.
    import glob as _glob
    for old in _glob.glob(os.path.join(out_dir, "*.pdf")) + \
               _glob.glob(os.path.join(out_dir, "*.png")) + \
               _glob.glob(os.path.join(out_dir, "_subsections.json")):
        try:
            os.remove(old)
        except OSError:
            pass

    pix_cache = {}
    for seq, u in enumerate(units, 1):
        sp0, sp1 = u["start_page"], min(u["end_page"], doc.page_count - 1)
        plan = []
        for pidx in range(sp0, sp1 + 1):
            if pidx < 0 or pidx >= doc.page_count:
                continue
            rect = page_crop(
                doc[pidx], body_size,
                is_start=(pidx == sp0), is_end=(pidx == sp1),
                start_y=u["start_y"], end_y=u["end_y"], cache=pix_cache,
            )
            if rect is not None:
                plan.append((pidx, rect))
        if not plan:
            continue

        out = emit_doc(doc, plan, a4=a4)
        fname = _safe_name(u["code"], u["title"], seq)
        fpath = os.path.join(out_dir, fname)
        out.save(fpath, garbage=4, deflate=True)
        info["files"] += 1
        info["manifest"].append({"file": fname, "code": u["code"], "title": u["title"],
                                 "pages": out.page_count})
        if proof and seq == 1:
            out[0].get_pixmap(dpi=150).save(fpath[:-4] + "_proof.png")
        out.close()

    # a small manifest so the split is traceable
    with open(os.path.join(out_dir, "_subsections.json"), "w", encoding="utf-8") as fh:
        json.dump({"method": method, "n": info["files"], "subsections": info["manifest"]},
                  fh, ensure_ascii=False, indent=2)
    doc.close()
    return info


# ----------------------------------------------------------------------------
# Driver
# ----------------------------------------------------------------------------

def find_pdfs(root):
    skip = {"extracted_syllabus", "extracted_syllabus_pdf"}
    out = []
    for dirpath, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in skip]   # prune output trees from the walk
        for f in files:
            if f.lower().endswith(".pdf"):
                out.append(os.path.join(dirpath, f))
    return sorted(out)


def main():
    ap = argparse.ArgumentParser(description="Crop AQA syllabus (Subject content) into standalone PDFs.")
    ap.add_argument("pdfs", nargs="*", help="Specific PDF files (default: scan --root).")
    ap.add_argument("--root", default=".", help="Root folder to scan for PDFs.")
    ap.add_argument("--out", default="extracted_syllabus_pdf", help="Output folder.")
    ap.add_argument("--mode", choices=["subsection", "section"], default="subsection",
                    help="subsection: one PDF per sub-topic (default). section: one PDF per spec.")
    ap.add_argument("--proof", action="store_true", help="Also render a proof PNG of the first page.")
    ap.add_argument("--no-a4", dest="a4", action="store_false",
                    help="Keep each page at its cropped size instead of placing it on a uniform A4 sheet.")
    ap.set_defaults(a4=True)
    args = ap.parse_args()

    root = os.path.abspath(args.root)
    out_root = os.path.abspath(args.out)
    os.makedirs(out_root, exist_ok=True)

    pdfs = [os.path.abspath(p) for p in args.pdfs] if args.pdfs else find_pdfs(root)
    if not pdfs:
        print("No PDFs found.", file=sys.stderr)
        return 1

    # Output dir per spec. To keep Windows paths under MAX_PATH (260), put the
    # subsection files directly in the spec's code folder (e.g. .../7404_2016_to_PRESENT/)
    # rather than a redundant folder repeating the long spec filename. When a code
    # folder holds more than one spec PDF (e.g. ..._pub2015 / ..._pub2023), each
    # gets a short sub-folder so they don't collide.
    by_dir = {}
    for p in pdfs:
        by_dir.setdefault(os.path.dirname(p), []).append(p)

    def out_dir_for(path):
        rel_dir = os.path.relpath(os.path.dirname(path), root).replace("\\", "/")
        base = os.path.join(out_root, rel_dir)
        if len(by_dir[os.path.dirname(path)]) > 1:
            stem = os.path.splitext(os.path.basename(path))[0]
            m = re.search(r"pub\d{4}", stem)
            tag = m.group(0) if m else re.sub(r"[^A-Za-z0-9]+", "", stem)[-8:]
            base = os.path.join(base, tag)
        return base

    report = []
    for path in pdfs:
        rel = os.path.relpath(path, root).replace("\\", "/")
        try:
            if args.mode == "section":
                out_path = os.path.join(out_root, rel)
                info = build_syllabus_pdf(path, out_path, proof=args.proof, a4=args.a4)
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
                               "method": info["method"], "units": info["units"],
                               "files": info["files"], "warnings": info["warnings"]})
                print(f"[{status:5}] {rel}  method={info['method']} files={info['files']}"
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
