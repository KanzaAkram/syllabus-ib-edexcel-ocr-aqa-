#!/usr/bin/env python3
"""Step 5: verify downloads, then generate FINAL_REPORT.md (totals, tree, gaps)."""
import csv, os, sys
from collections import defaultdict, Counter

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = os.path.dirname(os.path.abspath(__file__))
SYL = os.path.join(ROOT, "Syllabuses")
CSV_PATH = os.path.join(ROOT, "Syllabus_Master_Index.csv")
SUBJECTS = ["Mathematics","Psychology","Biology","Chemistry","Further_Mathematics","History",
    "Physics","English_Literature","English_Language","Geography","Sociology","Art_and_Design",
    "Business_Studies","Economics","Computer_Science","Religious_Studies","Spanish","French",
    "Politics","Physical_Education","Music","Drama","Design_and_Technology","Statistics","Media_Studies"]
BOARDS = ["AQA","Edexcel","OCR","IB"]

# ---- integrity check: every PDF on disk is a real PDF ----
bad, total_files, total_bytes = [], 0, 0
for dp, _, files in os.walk(SYL):
    for fn in files:
        if fn.lower().endswith(".pdf"):
            total_files += 1
            fp = os.path.join(dp, fn)
            sz = os.path.getsize(fp)
            total_bytes += sz
            with open(fp, "rb") as f:
                head = f.read(5)
            if not head.startswith(b"%PDF") or sz < 5000:
                bad.append((fn, sz, head))

# ---- parse CSV ----
rows = list(csv.DictReader(open(CSV_PATH, encoding="utf-8")))
ok = [r for r in rows if r["Notes"].startswith("OK") or r["Notes"].startswith("SKIPPED")]
nf = [r for r in rows if r["Notes"].startswith("NOT_FOUND")]

# coverage matrix: subject x board -> count of OK files
cov = defaultdict(lambda: defaultdict(int))
for r in ok:
    cov[r["Subject"]][r["Board"]] += 1

by_bl = Counter((r["Board"], r["Level"]) for r in ok)

lines = []
A = lines.append
A("# Syllabus Gathering — Final Report")
A("")
A(f"_Generated: {rows[0]['Download_Date'] if rows else 'n/a'} • Working dir: `Syllabuses/`_")
A("")
A("## 1. Totals")
A("")
A(f"- **PDF files downloaded (on disk): {total_files}**")
A(f"- Total size: **{total_bytes/1_048_576:.1f} MB**")
A(f"- CSV rows logged: {len(rows)}  (success/skipped: {len(ok)} • not-found: {len(nf)})")
n_cur = sum(1 for r in ok if r["Status"].upper() == "CURRENT")
n_leg = sum(1 for r in ok if r["Status"].upper() == "LEGACY")
A(f"- By status: **{n_cur} CURRENT** • **{n_leg} LEGACY** (pre-reform 2005–2014 + superseded versions)")
yrs = sorted(int(r["Year_Version"]) for r in ok if r["Year_Version"].isdigit())
if yrs:
    A(f"- Year span: **{yrs[0]}–{yrs[-1]}**")
A(f"- Integrity: {'ALL files valid PDFs (verified %PDF header)' if not bad else str(len(bad))+' suspect files'}")
if bad:
    for fn, sz, hd in bad:
        A(f"    - {fn} ({sz} B, starts {hd})")
A("")
A("## 2. Downloads by board / level")
A("")
A("| Board | Level | Files |")
A("|-------|-------|------:|")
for (b, l), n in sorted(by_bl.items()):
    A(f"| {b} | {l} | {n} |")
A("")
A("## 3. Coverage matrix (files per subject × board)")
A("")
A("| Subject | AQA | Edexcel | OCR | IB | Issues |")
A("|---------|----:|--------:|----:|---:|--------|")
for s in SUBJECTS:
    iss = [b for b in BOARDS if cov[s][b] == 0]
    A(f"| {s} | {cov[s]['AQA']} | {cov[s]['Edexcel']} | {cov[s]['OCR']} | {cov[s]['IB']} | {', '.join(iss) if iss else '—'} |")
A("")
A("## 4. Not-found / not-offered (with reasons)")
A("")
A("| Board | Level | Subject | Reason |")
A("|-------|-------|---------|--------|")
for r in nf:
    reason = r["Notes"].replace("NOT_FOUND:", "").strip() or "no PDF found"
    A(f"| {r['Board']} | {r['Level']} | {r['Subject']} | {reason} |")
A("")
A("## 5. Missing cells summary (subjects with 0 files for a board)")
A("")
miss = defaultdict(list)
for s in SUBJECTS:
    for b in BOARDS:
        if cov[s][b] == 0:
            miss[b].append(s)
for b in BOARDS:
    A(f"- **{b}**: {', '.join(miss[b]) if miss[b] else 'complete — every subject has ≥1 file'}")
A("")
A("## 6. Folder tree (files per leaf)")
A("")
A("```")
for board in sorted(os.listdir(SYL)):
    bpath = os.path.join(SYL, board)
    if not os.path.isdir(bpath): continue
    A(board + "/")
    for level in sorted(os.listdir(bpath)):
        lpath = os.path.join(bpath, level)
        if not os.path.isdir(lpath): continue
        nfiles = sum(1 for _, _, fs in os.walk(lpath) for x in fs if x.lower().endswith(".pdf"))
        A(f"  {level}/  ({nfiles} pdf)")
A("```")

open(os.path.join(ROOT, "FINAL_REPORT.md"), "w", encoding="utf-8").write("\n".join(lines))
print("\n".join(lines))
print("\n\n>>> Wrote FINAL_REPORT.md")
