#!/usr/bin/env python3
"""
report.py — generate final_report.txt from Syllabus_Master_Index.csv + the tree.
Sections: totals by board/qual/year-range; year-coverage gaps per subject;
failed-download list with URLs; folder tree with file counts; NOT_OFFERED list.
"""
import csv, os, collections
from datetime import date

ROOT = os.path.dirname(os.path.abspath(__file__))
SYLL = os.path.join(ROOT, "Syllabuses")
CSV_PATH = os.path.join(ROOT, "Syllabus_Master_Index.csv")
OUT = os.path.join(ROOT, "final_report.txt")
YEARS = list(range(2005, 2027))


def lastnum(s):
    return 2026 if str(s).upper() == "PRESENT" else (int(s) if str(s).isdigit() else 2026)


def main():
    rows = list(csv.DictReader(open(CSV_PATH, encoding="utf-8")))
    have = [r for r in rows if r.get("Filename") and not r["Notes"].startswith(("NOT_FOUND", "NOT_OFFERED"))]
    fail = [r for r in rows if r["Notes"].startswith("NOT_FOUND")]
    noff = [r for r in rows if r["Notes"].startswith("NOT_OFFERED")]

    # actual files on disk
    ondisk = []
    for dp, dn, fn in os.walk(SYLL):
        for f in fn:
            if f.lower().endswith(".pdf"):
                ondisk.append(os.path.join(dp, f))

    L = []
    w = L.append
    w("=" * 78)
    w("SYLLABUS GATHERING — FINAL REPORT (year-range convention)")
    w(f"Generated: {date.today().isoformat()}")
    w("=" * 78)

    w("\n1. TOTALS")
    w(f"   PDF files on disk          : {len(ondisk)}")
    total_bytes = sum(os.path.getsize(p) for p in ondisk)
    w(f"   Total size                 : {total_bytes/1048576:.1f} MB")
    w(f"   CSV rows                   : {len(rows)}  (downloaded/migrated {len(have)} | NOT_FOUND {len(fail)} | NOT_OFFERED {len(noff)})")
    st = collections.Counter(r["Status"] for r in have)
    w(f"   By status                  : CURRENT {st.get('CURRENT',0)} | LEGACY {st.get('LEGACY',0)}")

    w("\n2. FILES BY BOARD x QUALIFICATION TYPE")
    bq = collections.Counter((r["Board"], r["Qualification_Type"]) for r in have)
    w(f"   {'Board':10} {'Qual':12} Files")
    for k in sorted(bq):
        w(f"   {k[0]:10} {k[1]:12} {bq[k]}")
    w("   " + "-" * 30)
    bb = collections.Counter(r["Board"] for r in have)
    for b in sorted(bb):
        w(f"   {b:10} {'TOTAL':12} {bb[b]}")

    w("\n3. FILES BY FIRST-ASSESSMENT-YEAR")
    fy = collections.Counter(r["First_Assessment_Year"] for r in have)
    for y in sorted(fy, key=lambda x: str(x)):
        w(f"   {y}: {fy[y]}")

    w("\n4. YEAR-COVERAGE GAPS PER SUBJECT (years 2005-2026 with NO spec on disk, any board)")
    subj_year = collections.defaultdict(set)
    for r in have:
        try:
            f0 = int(r["First_Assessment_Year"])
        except ValueError:
            continue
        f1 = lastnum(r["Last_Assessment_Year"])
        for y in range(f0, min(f1, 2026) + 1):
            subj_year[r["Subject"]].add(y)
    for s in sorted(subj_year):
        gaps = [y for y in YEARS if y not in subj_year[s]]
        if gaps:
            # compress to ranges
            rng, start = [], None
            for y in YEARS:
                if y in gaps and start is None:
                    start = y
                elif y not in gaps and start is not None:
                    rng.append(f"{start}-{y-1}" if y-1 > start else f"{start}"); start = None
            if start is not None:
                rng.append(f"{start}-2026" if 2026 > start else f"{start}")
            w(f"   {s:24} gaps: {', '.join(rng)}")
        else:
            w(f"   {s:24} FULL 2005-2026 coverage")

    w("\n5. NOT_OFFERED (per board)")
    if noff:
        for r in sorted(noff, key=lambda x: (x["Board"], x["Subject"])):
            w(f"   {r['Board']:10} {r['Qualification_Type']:10} {r['Subject']:22} {r['Spec_Code']:8} {r['Notes'][:70]}")
    else:
        w("   (none)")

    w("\n6. FAILED DOWNLOADS — for manual retry (URL in CSV Source_URL)")
    if fail:
        for r in sorted(fail, key=lambda x: (x["Board"], x["Subject"])):
            w(f"   {r['Board']:10} {r['Qualification_Type']:10} {r['Subject']:22} {r['Spec_Code']:8} {r['Source_URL'][:60]}")
    else:
        w("   (none)")

    w("\n7. FOLDER TREE — file counts per board/qual")
    counts = collections.Counter()
    for p in ondisk:
        rel = os.path.relpath(p, SYLL).split(os.sep)
        if len(rel) >= 2:
            counts[(rel[0], rel[1])] += 1
    cur_board = None
    for (b, q) in sorted(counts):
        if b != cur_board:
            w(f"   {b}/"); cur_board = b
        w(f"     {q}/  ({counts[(b,q)]} pdf)")

    open(OUT, "w", encoding="utf-8").write("\n".join(L) + "\n")
    print(f"wrote {OUT} ({len(L)} lines)")
    print("\n".join(L[:40]))


if __name__ == "__main__":
    main()
