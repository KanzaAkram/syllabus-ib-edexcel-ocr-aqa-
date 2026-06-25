#!/usr/bin/env python3
"""Hierarchy + neighbour aware QA. Distinguishes CORRECT parent-anchoring from real defects.
Real-defect classes only (high precision):
  bleed_next   : last page bottom shows the NEXT unit's heading  (definite heading-bleed)
  bleed_other  : last page bottom shows an unrelated topic heading (probable bleed)
  lead_prev    : page-1 top shows the PREVIOUS unit's heading     (prev topic bled into start)
  lead_unrel   : page-1 top shows an unrelated topic heading      (wrong start / cropping)
  lead_cut     : page-1 has no heading and starts mid-sentence    (heading cropped off top)
  blank_end    : trailing page essentially blank (<0.4% ink)
  blank_end_sliver : trailing page far lighter than the rest (likely remnant)
  blank_mid    : a near-blank page in the middle
OK-by-design (parent leads child, or file-parent's first child leads) are NOT flagged.
"""
import os, re, json, glob
import fitz
from collections import Counter

ROOT = "extracted_syllabus_pdf_edexcel"
PARENT_MARK = re.compile(r'^(?:Paper|Component|Theme|Area of study|Option|Unit|Section|Module)\b', re.I)
SECTION_HEAD = re.compile(r'(?:subject\s+content|content\s+and\s+assessment|^\d{1,2}\s+[A-Z][a-z]+\s+content\b|^\d{1,2}\s+(?:subject\s+)?content\b)', re.I)
ANYMARK = re.compile(r'^(?:Topic|Theme|Unit|Paper|Component|Section|Option|Area of study|Chapter|Module)\s+([0-9A-Z][0-9A-Za-z]?)', re.I)
DEC = re.compile(r'^(\d{1,2}(?:\.\d{1,2}){1,2})(?=\b|\s|$)')
DECNUM = re.compile(r'(\d{1,2}(?:\.\d{1,2})+)')
LET = re.compile(r'^\(([a-z])\)')
TOPNUM = re.compile(r'^(\d{1,2})\s+[A-Z]')
CHROME = re.compile(r'pearson|edexcel|©|issue\s|specification\s*[–\-:]|copyright|getty|^\s*page\b|all rights reserved', re.I)
PUREPNUM = re.compile(r'^\s*\d{1,3}\s*$')
LOWERSTART = re.compile(r'^[a-z(]')

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

def numkey(s):
    """Hierarchical numeric key, marker words stripped. 'Topic 2'->('2',) ; '2.1'->('2','1');
       '(a)'->('@a',) ; 'Paper 4, Option 4A'->('4',). None if no code."""
    if not s: return None
    s = s.strip()
    m = DEC.match(s)
    if m: return tuple(m.group(1).split('.'))
    m = ANYMARK.match(s)
    if m:
        g = m.group(1)
        mm = re.match(r'(\d+)', g)
        return (mm.group(1),) if mm else (g.upper(),)
    m = LET.match(s)
    if m: return ('@' + m.group(1),)
    m = TOPNUM.match(s)
    if m: return (m.group(1),)
    mm = DECNUM.search(s)
    if mm: return tuple(mm.group(1).split('.'))
    return None

def is_prefix(a, b):
    """a is an ancestor of (or equal to) b."""
    if not a or not b: return False
    return len(a) <= len(b) and tuple(b[:len(a)]) == tuple(a)

def heading_lines(lines, body, ymin_frac, ymax_frac, H):
    res = []
    for (y0, y1, x0, x1, sz, txt) in lines:
        if CHROME.search(txt) or PUREPNUM.match(txt): continue
        if not (ymin_frac*H <= y0 <= ymax_frac*H): continue
        k = numkey(txt)
        ishead = bool(k) or (sz >= body + 2.5 and not txt[0].islower())
        if ishead:
            res.append((y0, y1, sz, txt, k))
    return res

def body_size(doc):
    c = Counter()
    for pg in doc:
        for b in pg.get_text('dict')['blocks']:
            for l in b.get('lines', []):
                for s in l['spans']:
                    t = s['text'].strip()
                    if t: c[round(s['size'])] += len(t)
    return c.most_common(1)[0][0] if c else 10

def main():
    cache = {r['rel']: r for r in json.load(open(os.path.join(ROOT, '_qa_full.json'), encoding='utf-8'))}
    out = []
    for mf in sorted(glob.glob(os.path.join(ROOT, '**', '_subsections.json'), recursive=True)):
        base = os.path.dirname(mf)
        spec = os.path.relpath(base, ROOT).replace('\\', '/')
        try:
            units = json.load(open(mf, encoding='utf-8'))['subsections']
        except Exception:
            continue
        keys = [numkey(u.get('code', '')) or numkey(u.get('title', '')) for u in units]
        for idx, u in enumerate(units):
            path = os.path.join(base, u['file'])
            rel = os.path.relpath(path, ROOT).replace('\\', '/')
            c = cache.get(rel, {})
            inks = c.get('inks', []); med = c.get('med_ink', 0)
            flags = {}
            # blanks
            if inks:
                blanks = [i for i, v in enumerate(inks) if v < 0.004]
                if blanks:
                    if len(inks)-1 in blanks: flags['blank_end'] = round(inks[-1], 4)
                    mids = [b for b in blanks if b != len(inks)-1]
                    if mids: flags['blank_mid'] = mids
                if len(inks) >= 2 and (len(inks)-1) not in blanks and inks[-1] < 0.02 and inks[-1] < 0.30*med:
                    flags['blank_end_sliver'] = round(inks[-1], 4)
            try:
                d = fitz.open(path); n = d.page_count
                H = d[0].rect.height; body = body_size(d)
                this_k = keys[idx]; prev_k = keys[idx-1] if idx > 0 else None
                nxt_k = keys[idx+1] if idx+1 < len(keys) else None
                # ---- lead (page 1 top) ----
                tops = heading_lines(page_lines(d[0]), body, 0.0, 0.25, H)
                f0 = [r for r in page_lines(d[0]) if not (CHROME.search(r[5]) or PUREPNUM.match(r[5]))]
                if tops:
                    tk = tops[0][4]; ttxt = tops[0][3]
                    if SECTION_HEAD.search(ttxt):
                        pass  # section header legitimately leads the first unit -> OK
                    elif tk is None and PARENT_MARK.match(ttxt):
                        pass  # parent marker leads -> OK
                    elif tk is None:
                        pass  # a non-coded heading (title) -> OK
                    elif this_k and (tk == this_k or is_prefix(tk, this_k) or is_prefix(this_k, tk)):
                        pass  # self / ancestor / descendant -> OK
                    elif PARENT_MARK.match(ttxt):
                        pass  # paper/component parent -> OK
                    elif prev_k and (tk == prev_k or is_prefix(prev_k, tk)):
                        flags['lead_prev'] = {'top': ttxt[:45], 'prev_code': units[idx-1].get('code','')}
                    elif this_k:
                        flags['lead_unrel'] = {'top': ttxt[:45], 'file_code': u.get('code','')}
                else:
                    # no heading at top -> is it cut? (top line lowercase/objective & file has a code)
                    if f0 and this_k and LOWERSTART.match(f0[0][5]):
                        flags['lead_cut'] = f0[0][5][:50]
                # ---- bleed (last page bottom) ----
                last = d[n-1]
                lb = heading_lines(page_lines(last), body, 0.55, 1.0, H)
                ll = [r for r in page_lines(last) if not (CHROME.search(r[5]) or PUREPNUM.match(r[5]))]
                for (y0, y1, sz, txt, k) in lb:
                    below = sum(len(r[5]) for r in ll if r[0] > y1 + 2)
                    if below >= 200: continue
                    if k is None: continue
                    if nxt_k and (k == nxt_k or is_prefix(k, nxt_k) or is_prefix(nxt_k, k)):
                        flags.setdefault('bleed_next', []).append({'text': txt[:45], 'y': round(y0/H,2), 'below': below})
                    elif this_k and not (is_prefix(this_k, k) or is_prefix(k, this_k)):
                        flags.setdefault('bleed_other', []).append({'text': txt[:45], 'y': round(y0/H,2), 'below': below})
                d.close()
            except Exception as ex:
                flags['ERROR'] = str(ex)[:80]
            if flags:
                out.append({'rel': rel, 'spec': spec, 'idx': idx, 'code': u.get('code',''),
                            'title': u.get('title','')[:55], 'pages': u.get('pages'), 'flags': flags})
    json.dump(out, open(os.path.join(ROOT, '_qa_problems.json'), 'w', encoding='utf-8'), indent=1)
    ft = Counter(); by_spec = {}
    for r in out:
        for k in r['flags']:
            ft[k] += 1; by_spec.setdefault(r['spec'], Counter())[k] += 1
    print(f"=== {len(out)} flagged PDFs ===\nflag totals:")
    for k, v in ft.most_common(): print(f"   {v:>4}  {k}")
    print("\n=== specs by flag count ===")
    for spec, cc in sorted(by_spec.items(), key=lambda kv: -sum(kv[1].values())):
        if sum(cc.values()) >= 2:
            print(f"   {sum(cc.values()):>3}  {spec}  {dict(cc)}")

if __name__ == '__main__':
    main()
