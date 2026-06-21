#!/usr/bin/env python3
"""
extract_syllabus.py  --  Extract AQA specification "Subject content" (the syllabus)
                          from every AQA spec PDF into structured JSON.

Why this works across the many different AQA numbering styles
-------------------------------------------------------------
Every AQA spec PDF is laid out the same way structurally even though the
*numbering* differs by subject:

  * Sciences / languages / most subjects use decimal codes:  3.1  -> 3.1.1 -> 3.1.1.1
  * History uses option codes:                               1A, 1B, 2A ... + "Part one/two"
  * Maths A-level uses lettered sections:                    "3.2 B: Algebra and functions"
  * Level-2 certificates use bare section numbers:           "2. Algebra"

The hierarchy is recovered from TWO independent signals which are then merged:

  1. The embedded PDF bookmark outline (TOC).  Titles/codes/pages are always
     correct, but the *level* field is sometimes corrupted (mis-nested) and the
     outline sometimes omits the deepest sub-topics.
  2. A font-aware text scan of the pages that finds every heading line carrying
     a decimal code in a heading-sized font -- this recovers the deep sub-topics
     the TOC drops.

The level of a heading is taken from the *code* whenever it is a decimal code
(`3.1.1` -> level 3), which is immune to TOC mis-nesting.  Codeless / option
headings (History "Part one", "1A ...") fall back to the (re-based) TOC level.

Body content for each heading is sliced out of the page geometry: everything
between a heading's position and the next heading's position, with running
headers/footers and repeated table-column labels removed, in left-column ->
right-column reading order.

Usage
-----
    python extract_syllabus.py                # scan ./ for *.pdf, write ./extracted_syllabus/
    python extract_syllabus.py --root DIR --out OUTDIR
    python extract_syllabus.py path/to/one.pdf [more.pdf ...]
"""

from __future__ import annotations
import argparse
import json
import os
import re
import sys
import traceback
from collections import Counter

import fitz  # PyMuPDF


# ----------------------------------------------------------------------------
# Regexes & constants
# ----------------------------------------------------------------------------

# A decimal code such as "3", "3.1", "3.1.1", "4.7.2.1" at the very start of a line.
DECIMAL_CODE_RE = re.compile(r"^\s*(\d{1,2}(?:\.\d{1,3}){0,5})(?=[\s \t]|$)")
# An "option" code such as "1A", "2B" (History) at the start of a line.
OPTION_CODE_RE = re.compile(r"^\s*(\d{1,2}[A-Z])(?=[\s \t]|$)")

# Lines that are running headers / footers / banners and must never become content.
FOOTER_RE = re.compile(
    r"(visit\s+.*for\s+the\s+most\s+up-to-date"
    r"|for\s+the\s+most\s+up-to-date\s+specification"
    r"|are\s+you\s+using\s+the\s+latest\s+version\s+of\s+this\s+specification"
    r"|^\s*version\s+\d"
    r"|for\s+(as\s+|a2\s+|gcse\s+)?exams?\s+(in\s+)?.*onwards"
    r"|for\s+certification\s+from\s+.*onwards"   # legacy footer
    r"|\(version\s+\d"                            # legacy footer "(version 1.1)"
    r"|for\s+teaching\s+from"
    r"|\baqa\.org\.uk\b"
    r"|^\s*\d{1,3}\s*$)",            # a bare page number on its own line
    re.I,
)

# Repeated table column labels that are layout noise, not syllabus content.
DROP_EXACT = {
    "content",
    "opportunities for skills development",
    "opportunities for skills",
    "development",                 # orphaned 2nd line of the column header above
    "additional information",
    "ref content",
    "notes",
    "key concepts",
    "content and amplification",
    "topic",
}

SUBJECT_CONTENT_RE = re.compile(r"subject\s+content", re.I)
STOP_SECTION_RE = re.compile(r"scheme\s+of\s+assessment|general\s+administration", re.I)

# Specs whose subject content lives in dense multi-column tables that linear text
# extraction cannot reconstruct. For these we recover the deepest sub-topics with
# PyMuPDF's table detector instead. Opt-in by spec code so all other docs are
# untouched.
#   assign="code_prefix": a row code like "2.5" nests under the topic coded "2".
#   assign="page":        a row nests under whichever topic's page span it falls in
#                         (its code restarts per topic, e.g. "1. ...", so we synth
#                          a code as <topic-code>.<n>).
TABLE_SPECS = {
    "8365": {"assign": "code_prefix", "row_code_re": r"^\d+\.\d+$"},   # Further Maths L2
    "2520": {"assign": "page",        "row_code_re": r"^\d+\.\s"},     # legacy ICT/CS
}


def clean_cell(c: str) -> str:
    return re.sub(r"\s+", " ", (c or "").replace("\n", " ")).strip()


# ----------------------------------------------------------------------------
# Small helpers
# ----------------------------------------------------------------------------

def norm_ws(s: str) -> str:
    """Collapse all whitespace (incl tabs / nbsp) to single spaces, strip ends."""
    return re.sub(r"[\s ]+", " ", s).strip()


def alnum_key(s: str) -> str:
    """Lower-cased, alphanumeric-only key used for fuzzy title matching across the
    PDF's broken bookmark encoding (where apostrophes/dashes become U+FFFD)."""
    return re.sub(r"[^a-z0-9]", "", s.lower())


def fix_text(s: str) -> str:
    """Repair the ONE unambiguous mojibake case. AQA PDFs whose font lacks a
    ToUnicode map emit U+FFFD for apostrophes/dashes/accents; PyMuPDF reproduces
    the source bytes faithfully. Only a digit-FFFD-digit run is unambiguous (a
    date range en-dash, e.g. '1840<FFFD>1895'); everything else (apostrophe vs
    accented vowel vs quote) is genuinely ambiguous, so we leave it untouched."""
    if not s or "�" not in s:
        return s
    return re.sub(r"(?<=\d)�(?=\d)", "–", s)


def code_level(code: str) -> int | None:
    """Level implied by a decimal code: '3' -> 1, '3.1' -> 2, '3.1.1' -> 3 ..."""
    if code and re.fullmatch(r"\d{1,2}(?:\.\d{1,3})*", code):
        return code.count(".") + 1
    return None


def strip_code_prefix(text: str, code: str) -> str:
    """Remove a leading code (and following separators) from a heading line."""
    t = norm_ws(text)
    if code and t.startswith(code):
        t = t[len(code):]
    return t.lstrip(" \t:.–—-").strip()


# ----------------------------------------------------------------------------
# Page line extraction
# ----------------------------------------------------------------------------

def get_page_lines(page) -> list[dict]:
    """Return visual text lines on a page with geometry + font info.

    Each line: {text, x0, y0, x1, size, font, light}
    `light` flags AQA's header/footer font (AQAChevinPro-Light, ~8pt).
    """
    out = []
    for b in page.get_text("dict").get("blocks", []):
        if "lines" not in b:
            continue
        for ln in b["lines"]:
            spans = ln["spans"]
            if not spans:
                continue
            text = "".join(s["text"] for s in spans)
            if not text.strip():
                continue
            xs0 = min(s["bbox"][0] for s in spans)
            ys0 = min(s["bbox"][1] for s in spans)
            xs1 = max(s["bbox"][2] for s in spans)
            ys1 = max(s["bbox"][3] for s in spans)
            size = max(s["size"] for s in spans)
            font = spans[0]["font"]
            light = any("Light" in s["font"] for s in spans)
            out.append(
                {"text": text, "x0": xs0, "y0": ys0, "x1": xs1, "y1": ys1,
                 "size": size, "font": font, "light": light}
            )
    return out


def estimate_body_size(doc) -> float:
    """Most common rounded font size across the doc ~ the body text size (≈11)."""
    c = Counter()
    for pno in range(doc.page_count):
        for b in doc[pno].get_text("dict").get("blocks", []):
            if "lines" not in b:
                continue
            for ln in b["lines"]:
                for s in ln["spans"]:
                    if s["text"].strip():
                        c[round(s["size"])] += 1
    if not c:
        return 11.0
    # the most common size that is small-ish (body, not heading) -- pick the mode
    return float(c.most_common(1)[0][0])


# ----------------------------------------------------------------------------
# Heading harvesting
# ----------------------------------------------------------------------------

def harvest_toc_headings(doc) -> list[dict]:
    """Headings from the bookmark outline. Level is taken from the code when the
    code is decimal (immune to TOC mis-nesting); otherwise the TOC level is
    re-based so the top numbered sections sit at level 1."""
    toc = doc.get_toc(simple=True)
    if not toc:
        return []

    # Re-base TOC levels: find the level at which the real numbered top sections
    # ("1 Introduction", "3 Subject content", ...) live, then shift so they = 1.
    base = None
    for lvl, title, _pg in toc:
        if re.match(r"^\s*\d{1,2}[\s \t]", title) and SUBJECT_CONTENT_RE.search(title) \
                or re.match(r"^\s*\d{1,2}[\s \t]+(introduction|subject)", title, re.I):
            base = lvl if base is None else min(base, lvl)
    if base is None:
        # fall back: minimum level of any "<int> Word" entry
        for lvl, title, _pg in toc:
            if re.match(r"^\s*\d{1,2}[\s \t]", title):
                base = lvl if base is None else min(base, lvl)
    if base is None:
        base = 1
    shift = base - 1

    out = []
    for lvl, title, pg in toc:
        if pg is None or pg < 1:
            continue
        title = title.replace("\t", " ")
        t = norm_ws(title)
        m = DECIMAL_CODE_RE.match(t)
        mo = OPTION_CODE_RE.match(t)
        code = m.group(1) if m else (mo.group(1) if mo else "")
        clvl = code_level(code)
        if clvl is not None:
            level = clvl
        else:
            level = max(1, lvl - shift)
        out.append({
            "code": code,
            "toc_title": t,
            "page": pg - 1,            # 0-indexed
            "level": level,
            "source": "toc",
        })
    return out


def harvest_scan_headings(doc, body_size: float) -> list[dict]:
    """Headings recovered by scanning page text: any line that starts with a
    decimal code in a heading-sized font. Recovers deep sub-topics the TOC omits."""
    thr = body_size + 1.5
    out = []
    for pno in range(doc.page_count):
        lines = get_page_lines(doc[pno])
        lines.sort(key=lambda l: (round(l["y0"], 1), l["x0"]))
        for i, ln in enumerate(lines):
            t = norm_ws(ln["text"])
            m = DECIMAL_CODE_RE.match(t)
            if not m:
                continue
            code = m.group(1)
            if "." not in code:          # bare section numbers handled via TOC
                continue
            if ln["size"] < thr:         # must look like a heading, not body text
                continue
            if FOOTER_RE.search(t):
                continue
            title = strip_code_prefix(t, code)
            # geometry-based wrap merge: a scan heading has no TOC title to guide
            # it, so absorb same-size lines immediately below in the same column.
            H = ln["size"]
            prev_y = ln["y0"]
            j = i + 1
            while j < len(lines):
                nx = lines[j]
                j += 1
                nt = norm_ws(nx["text"])
                if not nt:
                    continue
                if abs(nx["size"] - H) > 1.0 or nx["y0"] - prev_y > H * 2.2:
                    break
                if DECIMAL_CODE_RE.match(nt) or OPTION_CODE_RE.match(nt):
                    break
                # wrapped lines are often indented under the code; only exclude
                # the clearly-other-column text (which sits ~250px to the right)
                if abs(nx["x0"] - ln["x0"]) > 120 or FOOTER_RE.search(nt):
                    break
                if nt.lower() in DROP_EXACT:
                    break
                title = (title + " " + nt).strip() if title else nt
                prev_y = nx["y0"]
            out.append({
                "code": code,
                "toc_title": title,
                "page": pno,
                "level": code_level(code),
                "source": "scan",
            })
    return out


def locate_on_page(doc, page_idx: int, code: str, title: str):
    """Find a heading on/near its page and return (page_idx, y_top, y_end, title).

    AQA headings frequently WRAP across two or more visual lines (e.g. "3.3
    Organisms exchange substances with their" / "environment") and -- oddly --
    render the wrapped tail in a DIFFERENT font at the same size. So we merge by
    following the known TOC title TEXT: keep absorbing same-size lines below the
    heading while they continue building toward the full title. We report y_end
    (the bottom of the whole heading block) so the body slicer starts *below* it
    rather than leaking the wrapped tail into the content."""
    full_title = strip_code_prefix(title, code) if code else norm_ws(title)
    target = alnum_key(full_title)
    tkey = target[:40]
    for pidx in (page_idx, page_idx + 1, page_idx - 1):
        if pidx < 0 or pidx >= doc.page_count:
            continue
        lines = get_page_lines(doc[pidx])
        lines.sort(key=lambda l: (round(l["y0"], 1), l["x0"]))
        best = None
        best_i = None
        for i, ln in enumerate(lines):
            t = norm_ws(ln["text"])
            if code:
                # exact code prefix not immediately followed by another digit/dot
                if re.match(re.escape(code) + r"(?![\d.])", t):
                    if best is None or ln["size"] > best["size"]:
                        best, best_i = ln, i
            elif tkey:
                ak = alnum_key(t)
                if ak.startswith(tkey) or (tkey.startswith(ak) and len(ak) >= 8):
                    if best is None or ln["size"] > best["size"]:
                        best, best_i = ln, i
        if best is None:
            continue

        H = best["size"]
        assembled = strip_code_prefix(best["text"], code) if code else norm_ws(best["text"])
        acc = alnum_key(assembled)
        y_end = best.get("y1", best["y0"] + H)
        prev_y = best["y0"]
        j = best_i + 1
        while j < len(lines):
            if target and len(acc) >= len(target):
                break                                   # full title captured
            ln = lines[j]
            j += 1
            t = norm_ws(ln["text"])
            if not t:
                continue
            if abs(ln["size"] - H) > 1.0:               # different size -> not the heading
                break
            if ln["y0"] - prev_y > H * 2.2:             # too far below
                break
            if DECIMAL_CODE_RE.match(t) or OPTION_CODE_RE.match(t):
                break
            cand = acc + alnum_key(t)
            if target:
                if not target.startswith(cand):         # line doesn't continue the title
                    break
            elif abs(ln["x0"] - best["x0"]) > 120:      # no TOC title: fall back to geometry
                break
            assembled = (assembled + " " + t).strip()
            acc = cand
            y_end = max(y_end, ln.get("y1", ln["y0"] + H))
            prev_y = ln["y0"]
        return pidx, best["y0"], y_end, (full_title or norm_ws(assembled))
    return None


# ----------------------------------------------------------------------------
# Heading list assembly (merge TOC + scan, dedupe, locate, level, sort)
# ----------------------------------------------------------------------------

def build_heading_list(doc, body_size: float) -> list[dict]:
    # Collect every candidate from BOTH sources, then de-duplicate by physical
    # position -- NOT by code, because AQA reuses codes across the document
    # (e.g. GCSE science has both "4 Scientific vocabulary..." as a child of
    # "3 Working scientifically" and a separate section "4 Subject content").
    cands = harvest_toc_headings(doc) + harvest_scan_headings(doc, body_size)

    located = []
    for h in cands:
        loc = locate_on_page(doc, h["page"], h["code"], h["toc_title"])
        if loc is None:
            h["page_real"] = h["page"]
            h["y"] = -1.0
            h["y_end"] = -1.0
            h["title"] = h["toc_title"]
        else:
            pidx, y, y_end, pt = loc
            h["page_real"] = pidx
            h["y"] = y
            h["y_end"] = y_end
            h["title"] = pt or h["toc_title"]
        located.append(h)

    # Surgical fix for repeated code-less headings (e.g. English Literature lists
    # "Prose" / "Drama" / "Poetry" several times on one page): they all match the
    # first occurrence and collapse together. Where N code-less headings share an
    # identical title on a page AND the page has >=N occurrences of that exact
    # title, redistribute them across the successive occurrences in order. This
    # touches ONLY genuine same-title collisions; everything else is untouched.
    groups: dict = {}
    for h in located:
        if not h["code"] and h["y"] >= 0 and h["title"]:
            groups.setdefault((h["page_real"], alnum_key(h["title"])), []).append(h)
    for (pg, akey), grp in groups.items():
        if len(grp) < 2 or not akey:
            continue
        plines = get_page_lines(doc[pg])
        plines.sort(key=lambda l: (round(l["y0"], 1), l["x0"]))
        occ = [ln for ln in plines if alnum_key(norm_ws(ln["text"])) == akey]
        if len(occ) < len(grp):
            continue
        for h, ln in zip(grp, occ):           # grp is in TOC order; occ in page order
            h["y"] = ln["y0"]
            h["y_end"] = ln.get("y1", ln["y0"] + ln["size"])

    located.sort(key=lambda h: (h["page_real"], h["y"] if h["y"] >= 0 else 1e9))

    # de-dupe by physical position; a TOC entry and its scan twin land on the
    # same (page, y). Prefer the TOC source (reliable level for code-less
    # headings) and the longer/cleaner title.
    best: dict = {}
    order: list = []
    for h in located:
        if h["y"] >= 0:
            key = (h["page_real"], round(h["y"], 1))
        else:
            key = ("u", h["page_real"], h["code"], alnum_key(h["title"])[:24])
        if key not in best:
            best[key] = h
            order.append(key)
        else:
            cur = best[key]
            # prefer an entry that carries a decimal code (gives a real level)
            cur_has = code_level(cur["code"]) is not None
            new_has = code_level(h["code"]) is not None
            if (new_has and not cur_has) or \
               (new_has == cur_has and len(h.get("title", "")) > len(cur.get("title", ""))):
                # keep position/level from whichever has a code; keep longer title
                merged = dict(cur)
                merged["title"] = h["title"] if len(h.get("title", "")) > len(cur.get("title", "")) else cur["title"]
                if new_has and not cur_has:
                    merged["code"] = h["code"]
                    merged["level"] = h["level"]
                best[key] = merged

    result = [best[k] for k in order]
    # final tidy: a title should never still carry its own code prefix
    for h in result:
        if h["code"] and h["title"].strip().startswith(h["code"]):
            h["title"] = strip_code_prefix(h["title"], h["code"]) or h["title"]
    return result


def build_fallback_headings(doc, body_size: float) -> list[dict]:
    """Pure font-geometry heading detection, used only when the TOC path finds
    no subject content (e.g. AQA Level-2 Certificate in Further Maths, whose
    bookmark outline is corrupt and whose topics are bare-numbered "1. Number").

    Major sections are the largest heading tier; topics are the next tier within
    the "Subject content" section. A lone number line ("1.") is merged with the
    following heading line to recover its title.
    """
    thr = body_size + 4.0
    raw = []  # heading-style lines across the doc
    for pno in range(doc.page_count):
        lines = get_page_lines(doc[pno])
        for i, ln in enumerate(lines):
            if ln["light"] or ln["size"] < thr:
                continue
            t = norm_ws(ln["text"])
            if not t or FOOTER_RE.search(t) or "Medium" not in ln["font"] and "Arial" not in ln["font"] and "DemiB" not in ln["font"]:
                continue
            raw.append({"page": pno, "y": ln["y0"], "x0": ln["x0"],
                        "size": ln["size"], "text": t, "_idx": i, "_lines": lines})

    if not raw:
        return []
    max_sz = max(r["size"] for r in raw)
    l1_thr = max_sz - 3.0

    headings = []
    skip_until = -1
    for j, r in enumerate(raw):
        if j <= skip_until:
            continue
        t = r["text"]
        m_full = re.match(r"^(\d+(?:\.\d+)+)\b\s*(.*)$", t)      # 3.1 / 3.1.1 ...
        m_bare = re.match(r"^(\d+)\.?\s*(.*)$", t)               # "1." or "1. Number"
        code = ""
        title = t
        if m_full:
            code = m_full.group(1)
            title = m_full.group(2).strip()
        elif m_bare:
            code = m_bare.group(1)
            title = m_bare.group(2).strip()
        # a lone number: pull the title from the next heading-style line nearby
        if code and not title and j + 1 < len(raw):
            nxt = raw[j + 1]
            if nxt["page"] == r["page"] and abs(nxt["y"] - r["y"]) < 40 \
                    and not re.match(r"^\d", nxt["text"]):
                title = nxt["text"]
                skip_until = j + 1
        is_section = r["size"] >= l1_thr
        headings.append({"code": code, "toc_title": title, "title": title,
                         "page": r["page"], "page_real": r["page"], "y": r["y"],
                         "size": r["size"], "is_section": is_section, "source": "font"})

    # assign levels: largest tier = sections (1); inside subject content the rest
    # are topics, nested by their decimal depth (bare number -> a flat topic).
    for h in headings:
        if h["is_section"]:
            h["level"] = 1
        else:
            h["level"] = 2 + (h["code"].count(".") if h["code"] else 0)
    # in this geometry-only mode a non-section heading without a code is almost
    # always a stray large-font phrase from running prose -> drop it
    headings = [h for h in headings if h["is_section"] or h["code"]]
    headings.sort(key=lambda h: (h["page_real"], h["y"]))
    return headings


# ----------------------------------------------------------------------------
# Content slicing
# ----------------------------------------------------------------------------

def slice_content(doc, start, nxt, heading_positions, page_width_cache, body_size) -> str:
    """Text between heading `start` and the following heading `nxt` (any level),
    cleaned of headers/footers/column-labels, in left->right column order."""
    p0 = start["page_real"]
    y0 = start.get("y_end", start["y"])      # start below the whole (possibly wrapped) heading
    if nxt is not None:
        p1, y1 = nxt["page_real"], nxt["y"]
    else:
        p1, y1 = doc.page_count - 1, 1e9

    # running headers/footers are markedly smaller than the body font (~7-8pt vs
    # 10-11pt). Using size -- not the font *name* -- is essential: some specs
    # (e.g. legacy ones) set their body text in a "...-Light" font.
    small = max(8.5, body_size - 1.5)
    chunks = []
    for pidx in range(p0, p1 + 1):
        if pidx < 0 or pidx >= doc.page_count:
            continue
        pw = page_width_cache.get(pidx)
        if pw is None:
            pw = doc[pidx].rect.width
            page_width_cache[pidx] = pw
        lines = get_page_lines(doc[pidx])
        band = []
        for ln in lines:
            y = ln["y0"]
            if pidx == p0 and y <= y0 + 1.0:        # at/above this heading
                continue
            if pidx == p1 and y >= y1 - 0.5:        # at/below the next heading
                continue
            if ln["size"] <= small:                 # running header / footer
                continue
            t = norm_ws(ln["text"])
            if not t or FOOTER_RE.search(t):
                continue
            if t.lower() in DROP_EXACT:
                continue
            # drop any line that is itself one of the detected headings
            if (pidx, round(y, 1)) in heading_positions:
                continue
            col = 0 if ln["x0"] < pw * 0.5 else 1
            band.append((col, y, ln["x0"], t))
        band.sort(key=lambda r: (r[0], r[1], r[2]))
        chunks.extend(r[3] for r in band)

    return clean_join(chunks)


def clean_join(lines: list[str]) -> str:
    """Join content lines, attaching dangling bullets to the following text."""
    out_lines = []
    pending_bullet = False
    for ln in lines:
        s = ln.strip()
        if not s:
            continue
        if re.fullmatch(r"[•·▪◦‣●\-–—]{1,3}", s):
            pending_bullet = True
            continue
        # normalise an inline leading bullet glyph (e.g. "•• text") to "- text"
        s = re.sub(r"^[•·▪◦‣●]{1,3}\s*", "- ", s)
        if pending_bullet:
            out_lines.append("- " + s.lstrip("- ").strip())
            pending_bullet = False
        else:
            out_lines.append(s)
    text = "\n".join(out_lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ----------------------------------------------------------------------------
# Tree building
# ----------------------------------------------------------------------------

def build_tree(flat: list[dict]) -> list[dict]:
    """Build a nested tree from a flat list of nodes carrying an absolute `level`.
    `level` 1 = topic, 2 = subtopic, 3 = subsubtopic, 4 = subsubsubtopic ..."""
    roots = []
    stack = []  # list of (level, node)
    for item in flat:
        node = {
            "code": item["code"],
            "title": fix_text(item["title"]),
            "level": item["level"],
            "content": fix_text(item["content"]),
            "children": [],
        }
        lvl = item["level"]
        while stack and stack[-1][0] >= lvl:
            stack.pop()
        if stack:
            stack[-1][1]["children"].append(node)
        else:
            roots.append(node)
        stack.append((lvl, node))
    return roots


def renumber_levels(node: dict, depth: int = 1):
    node["level"] = depth
    for c in node["children"]:
        renumber_levels(c, depth + 1)


# ----------------------------------------------------------------------------
# Per-PDF extraction
# ----------------------------------------------------------------------------

def _headings_to_sections(doc, headings, warnings, body_size):
    """Attach content to every heading, then carve out the Subject-content
    section(s) and build their topic trees."""
    heading_positions = {
        (h["page_real"], round(h["y"], 1)) for h in headings if h["y"] >= 0
    }
    page_width_cache = {}
    for i, h in enumerate(headings):
        if h.get("source") == "table":      # content already filled from the table cell
            continue
        nxt = headings[i + 1] if i + 1 < len(headings) else None
        h["content"] = slice_content(doc, h, nxt, heading_positions, page_width_cache, body_size)

    sc_indices = [
        i for i, h in enumerate(headings)
        if h["level"] == 1 and SUBJECT_CONTENT_RE.search(h["title"] + " " + h.get("toc_title", ""))
    ]
    sections = []
    for idx in sc_indices:
        end = len(headings)
        for j in range(idx + 1, len(headings)):
            if headings[j]["level"] == 1:
                end = j
                break
        body = [h for h in headings[idx + 1:end] if h["level"] >= 2]
        if not body:
            warnings.append(f"Subject-content section {headings[idx]['title']!r} had no topics.")
            continue
        topics = build_tree(body)
        for t in topics:
            renumber_levels(t, 1)
        sec = headings[idx]
        sections.append({
            "section_code": sec["code"],
            "section_title": sec["title"] or sec.get("toc_title", ""),
            "topics": topics,
        })
    return sections


def _table_rows(doc, p0, p1):
    """Every table row in a page range as (page, y_top, [non-empty cells])."""
    rows = []
    for pno in range(max(0, p0), min(doc.page_count, p1 + 1)):
        try:
            finder = doc[pno].find_tables()
        except Exception:
            continue
        for tb in finder.tables:
            data = tb.extract()
            trows = tb.rows
            for ri, r in enumerate(data):
                cells = [clean_cell(c) for c in r]
                ne = [c for c in cells if c]
                if not ne:
                    continue
                y = trows[ri].bbox[1] if ri < len(trows) else 0.0
                rows.append((pno, y, ne))
    rows.sort(key=lambda r: (r[0], r[1]))
    return rows


def enrich_headings_with_tables(doc, headings, spec_code):
    """For TABLE_SPECS docs, recover deep sub-topics from the subject-content
    tables and splice them into the heading list as extra (pre-filled) headings."""
    cfg = TABLE_SPECS[spec_code]
    code_re = re.compile(cfg["row_code_re"])

    # locate the subject-content section and its topics (level-2 headings)
    sc = [i for i, h in enumerate(headings)
          if h["level"] == 1 and SUBJECT_CONTENT_RE.search(h["title"] + " " + h.get("toc_title", ""))]
    if not sc:
        return headings
    start = sc[0]
    end = len(headings)
    for j in range(start + 1, len(headings)):
        if headings[j]["level"] == 1:
            end = j
            break
    topics = [h for h in headings[start + 1:end] if h["level"] == 2 and h["y"] >= 0]
    if not topics:
        return headings
    topics.sort(key=lambda h: (h["page_real"], h["y"]))

    region_p0 = min(h["page_real"] for h in topics)
    region_p1 = headings[end]["page_real"] - 1 if end < len(headings) else doc.page_count - 1

    def parent_for(code, pno, y):
        if cfg["assign"] == "code_prefix":
            pc = code.rsplit(".", 1)[0]
            for t in topics:
                if t["code"] == pc:
                    return t
            return None
        # page mode: the topic that most recently precedes this row in document
        # order -- mirrors how build_tree nests, so synthesised codes stay
        # consistent with the actual tree parent (no boundary off-by-one).
        chosen = None
        for t in topics:
            if (t["page_real"], t["y"]) <= (pno, y):
                chosen = t
            else:
                break
        return chosen

    HEADER = {"ref", "content", "notes", "topic", "ref content", "key concepts",
              "content and amplification", "content and amplifi cation"}

    def dedup(seq):                       # drop consecutive duplicate cells
        outc = []
        for c in seq:
            if not outc or outc[-1] != c:
                outc.append(c)
        return outc

    subs = []
    current = None
    counters = {}
    for pno, y, ne0 in _table_rows(doc, region_p0, region_p1):
        ne = dedup(ne0)
        first = ne[0]
        if ne and clean_cell(first).lower() in HEADER:
            continue                      # skip repeated column-header rows
        if code_re.match(first):
            if cfg["assign"] == "code_prefix":
                code = first
                rest = ne[1:]
                while rest and rest[0] == code:    # code sometimes duplicated into the next cell
                    rest = rest[1:]
                title = rest[0] if rest else ""
                content = " ".join(rest[1:]) if len(rest) > 1 else ""
                parent = parent_for(code, pno, y)
            else:  # page mode: "N. Title" -> synth code <topic>.<n>
                m = re.match(r"^(\d+)\.\s*(.*)", first)
                parent = parent_for(first, pno, y)
                if not (m and parent):
                    current = None
                    continue
                counters[parent["code"]] = counters.get(parent["code"], 0) + 1
                code = parent["code"] + "." + str(counters[parent["code"]])
                title = m.group(2).strip()
                content = " — ".join(ne[1:]) if len(ne) > 1 else ""
            if parent is None:
                current = None
                continue
            current = {
                "code": code, "toc_title": title, "title": title,
                "content": content, "page_real": pno, "y": y, "y_end": y,
                "page": pno, "level": parent["level"] + 1, "source": "table",
            }
            subs.append(current)
        elif current is not None:
            # a wrapped continuation row (cell text spilled onto its own row):
            # fold it into the current sub-topic instead of dropping it.
            extra = (": " if cfg["assign"] == "page" else " ").join(ne)
            if extra and extra not in current["content"]:
                current["content"] = (current["content"] + " " + extra).strip()

    if not subs:
        return headings
    merged = headings + subs
    merged.sort(key=lambda h: (h["page_real"], h["y"] if h["y"] >= 0 else 1e9))
    return merged


def looks_like_non_spec(doc) -> bool:
    """Heuristic: the file is a mark scheme / question paper, not a specification."""
    txt = "\n".join(doc[i].get_text("text") for i in range(min(3, doc.page_count))).lower()
    return ("mark scheme" in txt or "question paper" in txt) and "specification" not in txt


def extract_pdf(path: str) -> dict:
    doc = fitz.open(path)
    warnings = []
    body_size = estimate_body_size(doc)
    m = re.search(r"_(\d{3,5}(?:-\d{3,5})?)_", os.path.basename(path))
    spec_code = m.group(1) if m else None
    table_mode = spec_code in TABLE_SPECS

    headings = build_heading_list(doc, body_size)
    if table_mode:
        headings = enrich_headings_with_tables(doc, headings, spec_code)
    method = "table" if table_mode else "toc"
    sections = _headings_to_sections(doc, headings, warnings, body_size)

    # Fallback: corrupt bookmark outline -> detect headings from page geometry.
    if not sections:
        fb_warnings = []
        fb_headings = build_fallback_headings(doc, body_size)
        if table_mode:
            fb_headings = enrich_headings_with_tables(doc, fb_headings, spec_code)
        fb_sections = _headings_to_sections(doc, fb_headings, fb_warnings, body_size)
        if fb_sections:
            sections = fb_sections
            warnings = fb_warnings
            method = "table+font-fallback" if table_mode else "font-fallback"
            headings = fb_headings

    if not sections:
        if looks_like_non_spec(doc):
            warnings.append("Document does not appear to be a specification "
                            "(looks like a mark scheme / question paper); nothing extracted.")
        else:
            warnings.append("No 'Subject content' section could be located.")

    doc.close()
    return {"sections": sections, "warnings": warnings, "body_size": body_size,
            "method": method, "n_headings": len(headings)}


# ----------------------------------------------------------------------------
# Metadata from path
# ----------------------------------------------------------------------------

def metadata_from_path(path: str, root: str) -> dict:
    rel = os.path.relpath(path, root).replace("\\", "/")
    parts = rel.split("/")
    meta = {"source_pdf": rel}
    if len(parts) >= 1:
        meta["qualification"] = parts[0]
    if len(parts) >= 2:
        meta["subject"] = parts[1].replace("_", " ")
    base = os.path.basename(path)
    m = re.search(r"_(\d{3,5}(?:-\d{3,5})?)_", base)
    if m:
        meta["spec_code"] = m.group(1)
    meta["pdf_name"] = base
    return meta


# ----------------------------------------------------------------------------
# Stats
# ----------------------------------------------------------------------------

def count_nodes(topics):
    n = 0
    maxd = 0
    empties = 0
    for t in topics:
        n += 1
        maxd = max(maxd, t["level"])
        if not t["content"] and not t["children"]:
            empties += 1
        cn, cd, ce = count_nodes(t["children"])
        n += cn
        maxd = max(maxd, cd)
        empties += ce
    return n, maxd, empties


# ----------------------------------------------------------------------------
# Driver
# ----------------------------------------------------------------------------

def find_pdfs(root: str) -> list[str]:
    out = []
    for dirpath, _dirs, files in os.walk(root):
        if os.path.basename(dirpath) == "extracted_syllabus":
            continue
        for f in files:
            if f.lower().endswith(".pdf"):
                out.append(os.path.join(dirpath, f))
    return sorted(out)


def main():
    ap = argparse.ArgumentParser(description="Extract AQA syllabus content to JSON.")
    ap.add_argument("pdfs", nargs="*", help="Specific PDF files (default: scan --root).")
    ap.add_argument("--root", default=".", help="Root folder to scan for PDFs.")
    ap.add_argument("--out", default="extracted_syllabus", help="Output folder.")
    args = ap.parse_args()

    root = os.path.abspath(args.root)
    out_root = os.path.abspath(args.out)
    os.makedirs(out_root, exist_ok=True)

    pdfs = [os.path.abspath(p) for p in args.pdfs] if args.pdfs else find_pdfs(root)
    if not pdfs:
        print("No PDFs found.", file=sys.stderr)
        return 1

    report = []
    docs = []
    for path in pdfs:
        rel = os.path.relpath(path, root).replace("\\", "/")
        try:
            meta = metadata_from_path(path, root)
            result = extract_pdf(path)
            doc_json = {**meta,
                        "extraction_method": result["method"],
                        "n_sections": len(result["sections"]),
                        "warnings": result["warnings"],
                        "sections": result["sections"]}
            # write JSON mirroring the input tree
            out_path = os.path.join(out_root, rel[:-4] + ".json")
            os.makedirs(os.path.dirname(out_path), exist_ok=True)
            with open(out_path, "w", encoding="utf-8") as fh:
                json.dump(doc_json, fh, ensure_ascii=False, indent=2)
            docs.append((doc_json, os.path.relpath(out_path, out_root).replace("\\", "/")))

            total_nodes = 0
            maxd = 0
            empties = 0
            for s in result["sections"]:
                n, d, e = count_nodes(s["topics"])
                total_nodes += n
                maxd = max(maxd, d)
                empties += e
            status = "OK" if result["sections"] else "EMPTY"
            report.append({
                "pdf": rel, "status": status, "sections": len(result["sections"]),
                "nodes": total_nodes, "max_depth": maxd, "empty_leaves": empties,
                "warnings": result["warnings"], "out": os.path.relpath(out_path, out_root),
            })
            print(f"[{status:5}] {rel}  sections={len(result['sections'])} "
                  f"nodes={total_nodes} depth={maxd} empty={empties}")
        except Exception as e:  # noqa
            report.append({"pdf": rel, "status": "ERROR", "error": repr(e),
                           "trace": traceback.format_exc()})
            print(f"[ERROR] {rel}: {e!r}", file=sys.stderr)

    # write reports + combined index + human-readable summary
    with open(os.path.join(out_root, "_extraction_report.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
    write_index_and_report(out_root, docs, report)

    ok = sum(1 for r in report if r.get("status") == "OK")
    empty = sum(1 for r in report if r.get("status") == "EMPTY")
    err = sum(1 for r in report if r.get("status") == "ERROR")
    print(f"\n=== DONE: {len(report)} PDFs | OK={ok} EMPTY={empty} ERROR={err} ===")
    print(f"JSON written under: {out_root}")
    print(f"Index: {os.path.join(out_root, '_index.json')}  |  Report: {os.path.join(out_root, '_REPORT.md')}")
    return 0


def write_index_and_report(out_root, docs, report):
    """Write _index.json (metadata + content-free outline of every doc) and
    _REPORT.md (a human-readable coverage table)."""
    def outline(nodes):
        return [{"code": n["code"], "title": n["title"], "level": n["level"],
                 "children": outline(n["children"])} for n in nodes]

    index = []
    for doc_json, jrel in docs:
        index.append({
            "source_pdf": doc_json.get("source_pdf"),
            "qualification": doc_json.get("qualification"),
            "subject": doc_json.get("subject"),
            "spec_code": doc_json.get("spec_code"),
            "extraction_method": doc_json.get("extraction_method"),
            "json": jrel,
            "warnings": doc_json.get("warnings"),
            "outline": [{"section_code": s["section_code"], "section_title": s["section_title"],
                         "topics": outline(s["topics"])} for s in doc_json.get("sections", [])],
        })
    with open(os.path.join(out_root, "_index.json"), "w", encoding="utf-8") as fh:
        json.dump(index, fh, ensure_ascii=False, indent=2)

    rep_by_pdf = {r["pdf"]: r for r in report}
    lines = ["# AQA Syllabus Extraction — Report", "",
             f"{len(report)} PDFs processed. One JSON per PDF under `extracted_syllabus/` mirroring the source tree.",
             "", "| Qualification | Subject | Spec | Method | Nodes | Depth | Status | Notes |",
             "|---|---|---|---|--:|--:|---|---|"]
    for doc_json, _ in sorted(docs, key=lambda d: d[0].get("source_pdf", "")):
        r = rep_by_pdf.get(doc_json.get("source_pdf"), {})
        note = "; ".join(doc_json.get("warnings", []))[:80]
        lines.append(f"| {doc_json.get('qualification','')} | {doc_json.get('subject','')} | "
                     f"{doc_json.get('spec_code','')} | {doc_json.get('extraction_method','')} | "
                     f"{r.get('nodes',0)} | {r.get('max_depth',0)} | {r.get('status','')} | {note} |")
    with open(os.path.join(out_root, "_REPORT.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    sys.exit(main())
