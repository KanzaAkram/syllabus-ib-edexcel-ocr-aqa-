#!/usr/bin/env python3
"""recover_8063.py — recover the legacy AQA D&T Textiles spec (code 4570, the
content behind the user's code 8063) from the Internet Archive (Wayback)."""
import csv, json, os, time
from datetime import date
import requests
import naming, lib_fetch

ROOT = os.path.dirname(os.path.abspath(__file__))
SYLL = os.path.join(ROOT, "Syllabuses")
CSV_PATH = os.path.join(ROOT, "Syllabus_Master_Index.csv")
TODAY = date.today().isoformat()
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0"}

CDX = "https://web.archive.org/cdx/search/cdx"
QUERIES = [
    {"url": "filestore.aqa.org.uk/subjects/AQA-4570*", "matchType": "prefix"},
    {"url": "aqa.org.uk", "matchType": "domain", "filter": ["urlkey:.*4570.*", "mimetype:application/pdf"]},
]


def cdx_candidates():
    seen, out = set(), []
    for q in QUERIES:
        params = dict(q, output="json", collapse="digest", limit="200")
        try:
            r = requests.get(CDX, params=params, headers=UA, timeout=40)
            rows = r.json()
        except Exception as e:
            print("  cdx err", q["url"], str(e)[:60]); continue
        for row in rows[1:] if rows and rows[0][0] == "urlkey" else []:
            # columns: urlkey timestamp original mimetype statuscode digest length
            ts, orig, mime, status = row[1], row[2], row[3], row[4]
            low = orig.lower()
            if "4570" not in low or ".pdf" not in low:
                continue
            if status not in ("200", "-"):
                continue
            # prefer the actual specification PDF, skip papers/mark schemes/other docs
            if any(b in low for b in ("-qp-", "-ms-", "question", "mark-scheme", "-w-ms",
                                      "-w-qp", "-mag-", "-trb-", "case-study", "-wre-",
                                      "-pm-", "-pef-", "-rep-", "-w-trb")):
                continue
            key = orig.lower()
            if key in seen:
                continue
            seen.add(key)
            raw = f"https://web.archive.org/web/{ts}id_/{orig}"
            score = (("-w-sp" in low or "-sp" in low or "specification" in low) * 5)
            out.append((score, raw, orig, ts))
    out.sort(key=lambda x: -x[0])
    return out


def main():
    cands = cdx_candidates()
    print(f"Wayback candidates for 4570: {len(cands)}")
    for sc, raw, orig, ts in cands[:12]:
        print(f"  [{sc}] {ts}  {orig[:90]}")

    rec = {"board": "AQA", "qual_type": "GCSE", "variant": "Textiles_Technology",
           "subject": "Design_and_Technology", "spec_code": "8063",
           "first_year": 2009, "last_year": 2016, "status": "LEGACY", "alt_codes": []}
    folder = naming.new_folder(SYLL, rec)
    fname = naming.new_filename(rec)
    fpath = os.path.join(folder, fname)

    data, src = None, ""
    for sc, raw, orig, ts in cands:
        d = lib_fetch.fetch_pdf(raw)
        if d and len(d) > 10000:
            data, src = d, raw; break
        time.sleep(0.5)

    rows = list(csv.DictReader(open(CSV_PATH, encoding="utf-8")))
    rows = [r for r in rows if not (r["Spec_Code"] == "8063" and r["Notes"].startswith("NOT_FOUND"))]
    note_id = "actual spec=4570 legacy D&T Textiles Technology; user code 8063"
    if data:
        os.makedirs(folder, exist_ok=True)
        open(fpath, "wb").write(data)
        rows.append(naming.csv_row(rec, fname, src, TODAY, f"OK ({len(data)//1024} KB) [Wayback; {note_id}]"))
        print(f"\nRECOVERED 8063 -> {len(data)//1024} KB from {src[:80]}")
    else:
        rows.append(naming.csv_row(rec, "", "", TODAY, f"NOT_FOUND: no Wayback PDF located; {note_id}"))
        print("\n8063 still not recoverable via Wayback")

    tmp = CSV_PATH + ".tmp"
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=naming.CSV_HEADER); w.writeheader(); w.writerows(rows)
    os.replace(tmp, CSV_PATH)
    print("CSV rows now:", len(rows))


if __name__ == "__main__":
    main()
