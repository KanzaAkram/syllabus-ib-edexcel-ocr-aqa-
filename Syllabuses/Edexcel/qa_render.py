#!/usr/bin/env python3
"""Render a page region of a PDF to PNG for visual QA.
Usage: python qa_render.py <pdf_path> <first|last|N> <top|bottom|full|topbottom> <out_prefix>
Writes <out_prefix>.png (or _top/_bottom). Prints what was written + page text snippet.
"""
import sys, fitz
pdf, page, region, outpre = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
d = fitz.open(pdf)
n = d.page_count
pi = 0 if page == 'first' else (n - 1 if page == 'last' else int(page))
pi = max(0, min(pi, n - 1))
pg = d[pi]; r = pg.rect
def render(reg, suffix=''):
    if reg == 'top':    clip = fitz.Rect(r.x0, r.y0, r.x1, r.y0 + r.height * 0.42)
    elif reg == 'bottom': clip = fitz.Rect(r.x0, r.y0 + r.height * 0.56, r.x1, r.y1)
    else: clip = r
    out = outpre + suffix + '.png'
    pg.get_pixmap(dpi=140, clip=clip).save(out)
    print('WROTE', out, '| page', pi, 'of', n, '| region', reg)
if region == 'topbottom':
    render('top', '_top'); render('bottom', '_bottom')
else:
    render(region)
print('--- page text (first 600 chars) ---')
print(pg.get_text()[:600])
