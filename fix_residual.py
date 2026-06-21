#!/usr/bin/env python3
"""fix_residual.py — correct the 8 mislabelled residual codes.
The user's subject labels were wrong; verified identities (filed under the
user's CODE so their code-keyed topical mapping resolves, with the real
identity noted in the CSV)."""
import csv, glob, os, shutil, time
from datetime import date
import naming, lib_fetch

ROOT = os.path.dirname(os.path.abspath(__file__))
SYLL = os.path.join(ROOT, "Syllabuses")
CSV_PATH = os.path.join(ROOT, "Syllabus_Master_Index.csv")
TODAY = date.today().isoformat()

ART = glob.glob(os.path.join(SYLL, "AQA", "A_Level", "Art_and_Design", "7201_*", "*.pdf"))
ART_SRC = ART[0] if ART else None

# code -> (subject, qual, variant, first, last, status, action, note)
# action: ("copy", path) | ("url", url) | ("probe4570",) | ("probe", slug)
FIX = {
    "7202": ("Art_and_Design", "ALEVEL", "Fine_Art", 2017, "PRESENT", "CURRENT",
             ("copy", ART_SRC), "real identity: A-level Art & Design (Fine Art); user labelled 'GCSE Statistics'; shares 7201 Art spec"),
    "7203": ("Art_and_Design", "ALEVEL", "Graphic_Communication", 2017, "PRESENT", "CURRENT",
             ("copy", ART_SRC), "real identity: A-level Art & Design (Graphic Communication); user labelled 'L2 Further Maths'; shares 7201 Art spec"),
    "7204": ("Art_and_Design", "ALEVEL", "Textile_Design", 2017, "PRESENT", "CURRENT",
             ("copy", ART_SRC), "real identity: A-level Art & Design (Textile Design); user labelled 'L2 Further Maths'; shares 7201 Art spec"),
    "7205": ("Art_and_Design", "ALEVEL", "Three_Dimensional_Design", 2017, "PRESENT", "CURRENT",
             ("copy", ART_SRC), "real identity: A-level Art & Design (3D Design); user labelled 'L2 Further Maths'; shares 7201 Art spec"),
    "7206": ("Art_and_Design", "ALEVEL", "Photography", 2017, "PRESENT", "CURRENT",
             ("copy", ART_SRC), "real identity: A-level Art & Design (Photography); user labelled 'L2 Further Maths'; shares 7201 Art spec"),
    "7562": ("Design_and_Technology", "ALEVEL", "Fashion_and_Textiles", 2017, "PRESENT", "CURRENT",
             ("url", "https://filestore.aqa.org.uk/resources/design-and-technology/specifications/AQA-7562-SP-2017.PDF"),
             "real identity: A-level D&T Fashion & Textiles; user labelled 'A-level Dance' (real Dance=7237)"),
    "8063": ("Design_and_Technology", "GCSE", "Textiles_Technology", 2009, 2016, "LEGACY",
             ("probe4570",), "user labelled 'GCSE D&T Fashion/Textiles (legacy)'; content = legacy D&T Textiles Technology spec 4570"),
    "8688": ("Polish", "GCSE", "", 2018, "PRESENT", "CURRENT",
             ("url", "https://filestore.aqa.org.uk/resources/polish/specifications/AQA-8688-SP-2017.PDF"),
             "real identity: AQA GCSE Polish; user labelled 'Persian' (AQA offers no Persian; Edexcel 1PN0 does)"),
}

FIXCODES = set(FIX)


def get_pdf(action):
    kind = action[0]
    if kind == "copy":
        return (open(action[1], "rb").read(), "copied from " + os.path.basename(action[1])) if action[1] else (None, "")
    if kind == "url":
        return lib_fetch.fetch_pdf(action[1]), action[1]
    if kind == "probe4570":
        base = "https://filestore.aqa.org.uk/resources/design-and-technology/specifications/AQA-4570-W-SP-{}.PDF"
        for y in list(range(16, 8, -1)):
            u = base.format(f"{y:02d}")
            if lib_fetch.head_ok(u, timeout=8):
                return lib_fetch.fetch_pdf(u), u
            time.sleep(0.05)
        for u in ["https://filestore.aqa.org.uk/resources/design-and-technology/specifications/AQA-4570-W-SP.PDF"]:
            d = lib_fetch.fetch_pdf(u)
            if d:
                return d, u
        return None, ""
    return None, ""


def main():
    rows = list(csv.DictReader(open(CSV_PATH, encoding="utf-8")))
    # drop stale wrong rows (NOT_FOUND rows I added earlier for these codes)
    before = len(rows)
    rows = [r for r in rows if not (r["Spec_Code"] in FIXCODES and r["Notes"].startswith("NOT_FOUND"))]
    print(f"dropped {before - len(rows)} stale NOT_FOUND rows for mislabelled codes")

    have = {r["Filename"] for r in rows if r.get("Filename")}
    new_rows, ok, fail = [], 0, 0
    for code, (subj, qt, var, fy, ly, st, action, note) in FIX.items():
        rec = {"board": "AQA", "qual_type": qt, "variant": var, "subject": subj,
               "spec_code": code, "first_year": fy, "last_year": ly, "status": st, "alt_codes": []}
        folder = naming.new_folder(SYLL, rec)
        fname = naming.new_filename(rec)
        fpath = os.path.join(folder, fname)
        if os.path.exists(fpath) or fname in have:
            print(f"  SKIP {code}"); continue
        data, src = get_pdf(action)
        if data and len(data) > 10000:
            os.makedirs(folder, exist_ok=True)
            open(fpath, "wb").write(data)
            new_rows.append(naming.csv_row(rec, fname, src, TODAY, f"OK ({len(data)//1024} KB) [{note}]"))
            print(f"  OK   {code} -> {subj}/{var or '-'} ({len(data)//1024} KB)"); ok += 1
        else:
            new_rows.append(naming.csv_row(rec, "", src, TODAY, f"NOT_FOUND: {note}"))
            print(f"  --   {code} -> {subj} NOT FOUND"); fail += 1

    rows += new_rows
    tmp = CSV_PATH + ".tmp"
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=naming.CSV_HEADER); w.writeheader(); w.writerows(rows)
    os.replace(tmp, CSV_PATH)
    print(f"\nfixed: ok={ok} fail={fail} (CSV now {len(rows)} rows)")


if __name__ == "__main__":
    main()
