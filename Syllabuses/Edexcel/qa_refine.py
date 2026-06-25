#!/usr/bin/env python3
"""Precise QA, reusing cached ink ratios from _qa_full.json (no re-render).
Produces a TRUSTWORTHY problem list for the user's concerns:
  - blank_end      : near-blank trailing page (white page at end)
  - blank_mid      : near-blank page in the middle
  - heading_bleed  : next topic's heading at the bottom of the last page
  - lead_mismatch  : page-1 top heading's code != file code (heading cropped/wrong start)
  - lead_missing   : no heading-like line at the top of page 1 (heading cut off)
  - edge_clip      : text clipped at the page boundary
  - title_marker   : title carries a different topic marker than the file code
"""
import os, re, json, glob
import fitz
from collections import Counter

ROOT = "extracted_syllabus_pdf_edexcel"

MARK = re.compile(r'^(?:Topic|Theme|Unit|Paper|Component|Section|Option|Area of study|Chapter|Module)\s+([0-9A-Z][0-9A-Za-z]?)', re.I)
DEC  = re.compile(r'^(\d{1,2}\.\d{1,2}(?:\.\d{1,2})?)(?=\b|\s|$)')
LET  = re.compile(r'^\(([a-z])\)')
TOPNUM = re.compile(r'^(\d{1,2})\s+[A-Z]')
CHROME = re.compile(r'pearson|edexcel|©|issue\s|specification\s*[–\-:]|copyright|getty|^\s*page\b|all rights reserved', re.I)
PUREPNUM = re.compile(r'^\s*\d{1,3}\s*$')
OBJ = re.compile(r'^(know|understand|recall|describe|explain|analyse|evaluate|calculate|use|apply|identify|state|define|interpret|compare|justify|demonstrate|outline|discuss|assess|determine|construct|represent|express|solve|investigate|measure|predict|derive|deduce|show|give|list|name|select|plan|record|present|be able|students should|candidates should|the |a |an |this |these |students |learners )', re.I)

def page_lines(pg):
    out = []
    for b in pg.get_text('dict')['blocks']:
        for l in b.get('lines', []):
            spans = [s for s in l['spans'] if s['text'].strip()]
            if not spans: continue
            txt = "".join(s['text'] for s in spans).strip()
            if not txt: continue
            x0 = min(s['bbox'][0] for s in spans); x1 = max(s['bbox'][2] for s in spans)
            y0 = min(s['bbox'][1] for s in spans); y1 = max(s['bbox'][3] for s in spans)
            sz = max(s['size'] for s in spans)
            out.append((y0, y1, x0, x1, sz, txt))
    out.sort(key=lambda r: (round(r[0]), r[2]))
    return out

def norm_code(s):
    if not s: return None
    s = s.strip()
    m = DEC.match(s)
    if m: return m.group(1)
    m = MARK.match(s)
    if m: return m.group(1).upper()
    m = LET.match(s)
    if m: return '(' + m.group(1) + ')'
    m = TOPNUM.match(s)
    if m: return m.group(1)
    return None

def file_code_norm(code):
    """Normalize the manifest code field to compare with a detected top-line code."""
    if not code: return None
    code = code.strip()
    # decimals
    m = re.match(r'^(\d{1,2}\.\d{1,2}(?:\.\d{1,2})?)', code)
    if m: return m.group(1)
    m = re.match(r'^\(([a-z])\)', code)
    if m: return '(' + m.group(1) + ')'
    m = MARK.match(code)
    if m: return m.group(1).upper()
    m = re.match(r'^([0-9A-Z][0-9A-Za-z]?)\b', code)
    if m: return m.group(1).upper()
    return code.upper()[:4]

def is_heading_line(txt, sz, body):
    if CHROME.search(txt) or PUREPNUM.match(txt): return False
    if norm_code(txt): return True
    if sz >= body + 2.5 and not txt[0].islower(): return True
    return False

def analyze_text(path, body, code):
    d = fitz.open(path); n = d.page_count
    W, H = d[0].rect.width, d[0].rect.height
    flags = {}
    fcode = file_code_norm(code)

    # --- leading heading on page 1 ---
    f0 = [r for r in page_lines(d[0]) if not (CHROME.search(r[5]) or PUREPNUM.match(r[5]))]
    top = [r for r in f0 if r[0] < 0.22 * H]
    if not top and f0:
        # nothing in the very top band
        flags['lead_missing'] = f0[0][5][:45]
    elif top:
        # topmost line(s): try to read a code; combine the first 2 top lines
        head_txt = top[0][5]
        tcode = norm_code(head_txt)
        if not tcode and len(top) > 1:
            tcode = norm_code(top[0][5] + ' ' + top[1][5])
        if fcode and tcode and tcode != fcode:
            flags['lead_mismatch'] = {'file_code': fcode, 'top_code': tcode, 'top_text': head_txt[:40]}
        elif fcode and not tcode:
            # heading expected (file has a code) but top line has none -> maybe cut
            if OBJ.match(head_txt) or head_txt[0].islower():
                flags['lead_missing'] = head_txt[:45]

    # --- heading bleed on the last page ---
    if n >= 1:
        last = d[n-1]
        ll = [r for r in page_lines(last) if not (CHROME.search(r[5]) or PUREPNUM.match(r[5]))]
        for (y0, y1, x0, x1, sz, txt) in ll:
            if y0 < 0.5 * H: continue
            if not is_heading_line(txt, sz, body): continue
            tcode = norm_code(txt)
            below = [r for r in ll if r[0] > y1 + 2]
            below_chars = sum(len(r[5]) for r in below)
            # must look like a NEW topic heading (has a code) and little/no content after
            if tcode and below_chars < 180:
                # and its code differs from this file's code (it's the NEXT topic)
                if not (fcode and tcode == fcode):
                    flags.setdefault('heading_bleed', []).append(
                        {'text': txt[:45], 'code': tcode, 'y_frac': round(y0/H, 2), 'below': below_chars})

    # --- edge clipping ---
    clip = []
    for i, pg in enumerate(d):
        for (y0, y1, x0, x1, sz, txt) in page_lines(pg):
            if CHROME.search(txt): continue
            e = ('L' if x0 <= 1.5 else '') + ('R' if x1 >= W-1.5 else '') + ('T' if y0 <= 1.0 else '') + ('B' if y1 >= H-1.0 else '')
            if e:
                clip.append({'pg': i, 'edge': e, 'text': txt[:35]})
    if clip:
        flags['edge_clip'] = clip[:4]

    d.close()
    return flags, n

def main():
    cache = {r['rel']: r for r in json.load(open(os.path.join(ROOT, '_qa_full.json'), encoding='utf-8'))}
    out = []
    for rel, c in cache.items():
        path = os.path.join(ROOT, rel)
        inks = c.get('inks', [])
        med = c.get('med_ink', 0)
        body = c.get('body', 10)
        code = c.get('code', '')
        flags = {}
        # blank pages from cached ink
        if inks:
            blanks = [i for i, v in enumerate(inks) if v < 0.004]
            if blanks:
                if (len(inks)-1) in blanks:
                    flags['blank_end'] = inks[-1]
                mids = [b for b in blanks if b != len(inks)-1]
                if mids: flags['blank_mid'] = mids
            # trailing sliver (light last page)
            if len(inks) >= 2 and (len(inks)-1) not in blanks and inks[-1] < 0.02 and inks[-1] < 0.30*med:
                flags['blank_end_sliver'] = round(inks[-1], 4)
        try:
            tflags, n = analyze_text(path, body, code)
            flags.update(tflags)
        except Exception as ex:
            flags['ERROR'] = str(ex)[:80]
        if flags:
            out.append({'rel': rel, 'spec': c['spec'], 'code': code, 'title': c.get('title',''),
                        'pages': c.get('pages'), 'flags': flags})

    json.dump(out, open(os.path.join(ROOT, '_qa_problems.json'), 'w', encoding='utf-8'), indent=1)

    ft = Counter(); by_spec = {}
    for r in out:
        for k in r['flags']:
            ft[k] += 1
            by_spec.setdefault(r['spec'], Counter())[k] += 1
    print(f"=== {len(out)} PDFs with >=1 flag (of {len(cache)}) ===")
    print("flag totals:")
    for k, v in ft.most_common(): print(f"   {v:>4}  {k}")
    print("\n=== specs by flag count ===")
    for spec, c in sorted(by_spec.items(), key=lambda kv: -sum(kv[1].values()))[:45]:
        print(f"   {sum(c.values()):>3}  {spec}  {dict(c)}")

if __name__ == '__main__':
    main()
