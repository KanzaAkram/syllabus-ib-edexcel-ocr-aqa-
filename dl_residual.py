#!/usr/bin/env python3
"""dl_residual.py <wf_output.json> — download the 8 residual AQA codes using
URLs discovered by the residual workflow; validate, place, append to CSV."""
import csv, json, os, sys
from datetime import date
import naming, lib_fetch

ROOT = os.path.dirname(os.path.abspath(__file__))
SYLL = os.path.join(ROOT, "Syllabuses")
CSV_PATH = os.path.join(ROOT, "Syllabus_Master_Index.csv")
TODAY = date.today().isoformat()

# code -> registry record fields (match the aqa_extra.py table)
RECS = {
    "7562": dict(subject="Dance", qual_type="ALEVEL", variant="", first_year=2017, last_year="PRESENT", status="CURRENT"),
    "7202": dict(subject="Statistics", qual_type="L2CERT", variant="", first_year=2012, last_year=2017, status="LEGACY"),
    "7203": dict(subject="Further_Mathematics", qual_type="L2CERT", variant="", first_year=2012, last_year=2019, status="LEGACY"),
    "7204": dict(subject="Further_Mathematics", qual_type="L2CERT", variant="v2", first_year=2012, last_year=2019, status="LEGACY"),
    "7205": dict(subject="Further_Mathematics", qual_type="L2CERT", variant="v3", first_year=2012, last_year=2019, status="LEGACY"),
    "7206": dict(subject="Further_Mathematics", qual_type="L2CERT", variant="v4", first_year=2012, last_year=2019, status="LEGACY"),
    "8063": dict(subject="Design_and_Technology", qual_type="GCSE", variant="Fashion_and_Textiles", first_year=2012, last_year=2017, status="LEGACY"),
    "8688": dict(subject="Persian", qual_type="GCSE", variant="", first_year=2019, last_year="PRESENT", status="CURRENT"),
}


def main():
    disc = json.load(open(sys.argv[1], encoding="utf-8"))
    res = disc.get("result", disc).get("results", disc) if isinstance(disc, dict) else disc
    if isinstance(res, dict):
        res = res.get("results", [])
    by_code = {}
    for d in res:
        by_code.setdefault(str(d.get("code")), d)

    rows = list(csv.DictReader(open(CSV_PATH, encoding="utf-8")))
    have = {r["Filename"] for r in rows if r.get("Filename")}
    new_rows, ok, fail = [], 0, 0

    for code, base in RECS.items():
        rec = dict(base, board="AQA", spec_code=code, alt_codes=[])
        folder = naming.new_folder(SYLL, rec)
        fname = naming.new_filename(rec)
        fpath = os.path.join(folder, fname)
        if os.path.exists(fpath) or fname in have:
            print(f"  SKIP {code}"); continue

        d = by_code.get(code, {})
        urls = [d.get("pdf_url")] + ([d["page_url"]] if d.get("page_url", "").endswith(".pdf") else [])
        data, src = None, ""
        for u in [u for u in urls if u]:
            data = lib_fetch.fetch_pdf(u)
            if data:
                src = u; break
        if data is None and d.get("page_url"):
            link = lib_fetch.scrape_pdf_links(d["page_url"], code)
            if link:
                data = lib_fetch.fetch_pdf(link); src = link if data else ""

        if data:
            os.makedirs(folder, exist_ok=True)
            open(fpath, "wb").write(data)
            extra = f" actual_code={d.get('actual_code')}" if d.get("actual_code") and d.get("actual_code") != code else ""
            new_rows.append(naming.csv_row(rec, fname, src, TODAY, f"OK ({len(data)//1024} KB){extra}"))
            print(f"  OK   {code} {base['subject']:24} {len(data)//1024} KB"); ok += 1
        else:
            note = d.get("notes", "no URL found")
            note = note if note.startswith(("NOT_OFFERED", "NOT_FOUND")) else "NOT_FOUND: " + note
            new_rows.append(naming.csv_row(rec, "", d.get("pdf_url", "") or d.get("page_url", ""), TODAY, note[:200]))
            print(f"  --   {code} {base['subject']:24} {note[:60]}"); fail += 1

    rows += new_rows
    tmp = CSV_PATH + ".tmp"
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=naming.CSV_HEADER); w.writeheader(); w.writerows(rows)
    os.replace(tmp, CSV_PATH)
    print(f"\nresidual: ok={ok} fail={fail} (CSV {len(rows)} rows)")


if __name__ == "__main__":
    main()
