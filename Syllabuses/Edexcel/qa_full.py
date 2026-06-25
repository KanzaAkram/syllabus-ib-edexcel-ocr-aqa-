#!/usr/bin/env python3
"""Comprehensive per-PDF QA over every extracted Edexcel sub-topic PDF.
Flags exactly the issues the user named:
  - trailing/blank pages (white page at end, or any near-blank page)
  - heading bleed (next topic's heading appearing at the bottom of the prev PDF)
  - edge cropping (text clipped at the page boundary)
  - title/code mismatch (title belongs to a different topic than the code)
  - first page missing its leading heading
Text layer is intact, so detection is text-geometry based; pixels used for blank ink ratio.
"""
import os, re, json, glob, sys
import fitz
import numpy as np
from collections import Counter

ROOT = "extracted_syllabus_pdf_edexcel"

MARK = re.compile(r'^(?:Topic|Theme|Unit|Paper|Component|Section|Option|Area of study|Chapter|Module)\s+[0-9A-Z]', re.I)
DEC  = re.compile(r'^(\d{1,2}\.\d{1,2}(?:\.\d{1,2})?)(?=\b|\s)')
LET  = re.compile(r'^\(([a-z])\)')
TOPNUM = re.compile(r'^(\d{1,2})\s+[A-Z]')
CHROME = re.compile(r'pearson|edexcel|©|©|issue\s|specification\s*[–\-]|copyright|getty|^\s*page\b', re.I)
PUREPNUM = re.compile(r'^\s*\d{1,3}\s*$')

def body_size(doc):
    c = Counter()
    for pg in doc:
        for b in pg.get_text('dict')['blocks']:
            for l in b.get('lines', []):
                for s in l['spans']:
                    t = s['text'].strip()
                    if t:
                        c[round(s['size'])] += len(t)
    return c.most_common(1)[0][0] if c else 10

def page_lines(pg):
    """Return merged lines: list of (y0, y1, x0, x1, maxsize, text)."""
    out = []
    for b in pg.get_text('dict')['blocks']:
        for l in b.get('lines', []):
            spans = [s for s in l['spans'] if s['text'].strip()]
            if not spans:
                continue
            txt = "".join(s['text'] for s in spans).strip()
            if not txt:
                continue
            x0 = min(s['bbox'][0] for s in spans); x1 = max(s['bbox'][2] for s in spans)
            y0 = min(s['bbox'][1] for s in spans); y1 = max(s['bbox'][3] for s in spans)
            sz = max(s['size'] for s in spans)
            out.append((y0, y1, x0, x1, sz, txt))
    out.sort(key=lambda r: r[0])
    return out

def ink_ratio(pg):
    pix = pg.get_pixmap(dpi=70, colorspace=fitz.csGRAY)
    a = np.frombuffer(pix.samples, dtype=np.uint8)
    return float((a < 245).mean())

def is_heading_text(txt, sz, body):
    if CHROME.search(txt) or PUREPNUM.match(txt):
        return None
    m = MARK.match(txt) or DEC.match(txt) or LET.match(txt) or TOPNUM.match(txt)
    if m and sz >= body + 0.5:
        return txt[:50]
    if sz >= body + 3 and len(txt) > 4 and not txt[0].islower():
        return txt[:50]
    return None

def code_of(txt):
    m = DEC.match(txt)
    if m: return ('dec', m.group(1))
    m = MARK.match(txt)
    if m:
        mm = re.match(r'^(\w+)\s+([0-9A-Z]+)', txt)
        if mm: return ('mark', mm.group(2).upper())
    m = TOPNUM.match(txt)
    if m: return ('num', m.group(1))
    m = LET.match(txt)
    if m: return ('let', m.group(1))
    return None

def analyze(path, code_hint=""):
    d = fitz.open(path)
    n = d.page_count
    body = body_size(d)
    W, H = d[0].rect.width, d[0].rect.height
    inks = [ink_ratio(pg) for pg in d]
    med = float(np.median(inks)) if inks else 0.0
    flags = {}

    # blank pages anywhere
    blanks = [i for i, r in enumerate(inks) if r < 0.004]
    if blanks:
        flags['blank_pages'] = blanks
    # trailing sliver: last page much lighter than rest AND small
    if n >= 2 and inks[-1] < 0.018 and inks[-1] < 0.30 * med:
        flags['trailing_sliver'] = round(inks[-1], 4)

    # heading bleed on last page (and any non-first page bottom)
    last = d[n-1]
    llines = page_lines(last)
    content = [r for r in llines if not (CHROME.search(r[5]) or PUREPNUM.match(r[5]))]
    maxy = max((r[1] for r in content), default=0)
    bleed = []
    for (y0, y1, x0, x1, sz, txt) in content:
        if y0 < 0.55 * H:
            continue
        h = is_heading_text(txt, sz, body)
        if not h:
            continue
        below = [r for r in content if r[0] > y1 + 2]
        below_chars = sum(len(r[5]) for r in below)
        # heading in bottom region with little content after it
        if below_chars < 160:
            bleed.append({'text': h, 'y_frac': round(y0/H, 2), 'size': round(sz,1),
                          'below_chars': below_chars, 'code': code_of(txt)})
    if bleed:
        # keep strongest (lowest on page)
        bleed.sort(key=lambda b: -b['y_frac'])
        flags['heading_bleed_end'] = bleed[:2]

    # edge clipping: text touching page boundary on any page
    clip = []
    for i, pg in enumerate(d):
        for (y0, y1, x0, x1, sz, txt) in page_lines(pg):
            if CHROME.search(txt):
                continue
            if x0 <= 1.5 or x1 >= W - 1.5 or y0 <= 1.0 or y1 >= H - 1.0:
                clip.append({'pg': i, 'edge': ('L' if x0<=1.5 else '')+('R' if x1>=W-1.5 else '')+('T' if y0<=1.0 else '')+('B' if y1>=H-1.0 else ''),
                             'text': txt[:40]})
    if clip:
        flags['edge_clip'] = clip[:4]

    # first page leading heading present?
    f0 = page_lines(d[0])
    fc = [r for r in f0 if not (CHROME.search(r[5]) or PUREPNUM.match(r[5]))]
    top = [r for r in fc if r[0] < 0.42 * H]
    has_head = any(is_heading_text(r[5], r[4], body) for r in top)
    if fc and not has_head:
        flags['first_page_no_heading'] = [r[5][:45] for r in top[:2]] or [fc[0][5][:45]]

    d.close()
    return {'pages': n, 'body': body, 'med_ink': round(med,4), 'inks': [round(x,4) for x in inks],
            'flags': flags}

def main():
    files = sorted(glob.glob(os.path.join(ROOT, '**', '*.pdf'), recursive=True))
    # load subsections to get code/title per file
    meta = {}
    for mf in glob.glob(os.path.join(ROOT, '**', '_subsections.json'), recursive=True):
        try:
            j = json.load(open(mf, encoding='utf-8'))
            base = os.path.dirname(mf)
            for s in j.get('subsections', []):
                fn = s.get('file') or s.get('filename')
                if fn:
                    meta[os.path.join(base, fn)] = s
        except Exception:
            pass

    results = []
    for i, f in enumerate(files):
        try:
            r = analyze(f)
        except Exception as ex:
            r = {'error': str(ex)[:120], 'flags': {'ERROR': str(ex)[:80]}}
        rel = os.path.relpath(f, ROOT).replace('\\', '/')
        parts = rel.split('/')
        spec = '/'.join(parts[:3])
        s = meta.get(f, {})
        # title/code mismatch
        title = s.get('title', '') or ''
        code = s.get('code', '') or ''
        if title and code:
            ct = code_of(title)
            cc = code_of(code) or code_of(code + ' x')
            if ct and ct[0] in ('mark','dec','num') and not title.lower().startswith(code.lower()[:3]):
                # title carries a marker/number — is it different from the file code?
                if code and ct[1] and not code.replace('.', '').startswith(str(ct[1]).replace('.', '')[:1]):
                    r.setdefault('flags', {})['title_marker'] = {'code': code, 'title': title[:50], 'title_code': ct}
        r.update({'rel': rel, 'spec': spec, 'code': code, 'title': title[:60]})
        results.append(r)
        if (i+1) % 200 == 0:
            print(f'  ...{i+1}/{len(files)}', file=sys.stderr)

    json.dump(results, open(os.path.join(ROOT, '_qa_full.json'), 'w', encoding='utf-8'), indent=1)

    # ---- summary ----
    ft = Counter()
    by_spec = {}
    for r in results:
        for k in r.get('flags', {}):
            ft[k] += 1
            by_spec.setdefault(r['spec'], Counter())[k] += 1
    print(f"\n=== QA over {len(results)} PDFs ===")
    print("flag totals:")
    for k, v in ft.most_common():
        print(f"   {v:>4}  {k}")
    print(f"\n=== specs with most flags ===")
    spec_tot = sorted(by_spec.items(), key=lambda kv: -sum(kv[1].values()))
    for spec, c in spec_tot[:40]:
        print(f"   {sum(c.values()):>3}  {spec}  {dict(c)}")

if __name__ == '__main__':
    main()
