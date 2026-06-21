#!/usr/bin/env python3
"""
aqa_extra.py — download 39 additional AQA specs (AS-levels + extra subjects)
the user flagged as missing, via filestore multi-slug/year probing, validate,
place in the year-range tree, and append to Syllabus_Master_Index.csv.

AS and A-level are separate AQA qualifications with separate codes; the corpus
previously held only the A-level (A2) codes, so all AS codes were missing.
"""
import csv, os, time
from datetime import date

import naming, lib_fetch

ROOT = os.path.dirname(os.path.abspath(__file__))
SYLL = os.path.join(ROOT, "Syllabuses")
CSV_PATH = os.path.join(ROOT, "Syllabus_Master_Index.csv")
TODAY = date.today().isoformat()

# (code, subject, qual_type, variant, first, last, status, [candidate slugs])
T = [
    # ---- AS levels (separate code from the A-level) ----
    ("7036", "Geography", "AS", "", 2016, "PRESENT", "CURRENT", ["geography"]),
    ("7041", "History", "AS", "", 2016, "PRESENT", "CURRENT", ["history"]),
    ("7061", "Religious_Studies", "AS", "", 2017, "PRESENT", "CURRENT", ["rs", "religious-studies"]),
    ("7131", "Business_Studies", "AS", "", 2016, "PRESENT", "CURRENT", ["business", "business-subjects"]),
    ("7135", "Economics", "AS", "", 2016, "PRESENT", "CURRENT", ["economics"]),
    ("7181", "Psychology", "AS", "", 2016, "PRESENT", "CURRENT", ["psychology"]),
    ("7191", "Sociology", "AS", "", 2016, "PRESENT", "CURRENT", ["sociology"]),
    ("7356", "Mathematics", "AS", "", 2018, "PRESENT", "CURRENT", ["mathematics"]),
    ("7401", "Biology", "AS", "", 2016, "PRESENT", "CURRENT", ["biology", "science"]),
    ("7404", "Chemistry", "AS", "", 2016, "PRESENT", "CURRENT", ["chemistry", "science"]),
    ("7407", "Physics", "AS", "", 2016, "PRESENT", "CURRENT", ["physics", "science"]),
    ("7516", "Computer_Science", "AS", "", 2016, "PRESENT", "CURRENT", ["computer-science", "computing"]),
    ("7651", "French", "AS", "", 2017, "PRESENT", "CURRENT", ["french"]),
    ("7661", "German", "AS", "", 2017, "PRESENT", "CURRENT", ["german"]),
    ("7691", "Spanish", "AS", "", 2017, "PRESENT", "CURRENT", ["spanish"]),
    ("7701", "English_Language", "AS", "", 2016, "PRESENT", "CURRENT", ["english"]),
    ("7711", "English_Literature", "AS", "A", 2016, "PRESENT", "CURRENT", ["english"]),
    ("7716", "English_Literature", "AS", "B", 2016, "PRESENT", "CURRENT", ["english"]),
    # ---- A-levels not previously held ----
    ("7562", "Dance", "ALEVEL", "", 2017, "PRESENT", "CURRENT", ["dance", "physical-education"]),
    ("7662", "German", "ALEVEL", "", 2018, "PRESENT", "CURRENT", ["german"]),
    ("7687", "Polish", "ALEVEL", "", 2018, "PRESENT", "CURRENT", ["polish"]),
    # ---- Level 2 Certificate Further Mathematics ----
    ("7203", "Further_Mathematics", "L2CERT", "", 2012, 2019, "LEGACY", ["mathematics"]),
    ("7204", "Further_Mathematics", "L2CERT", "v2", 2012, 2019, "LEGACY", ["mathematics"]),
    ("7205", "Further_Mathematics", "L2CERT", "v3", 2012, 2019, "LEGACY", ["mathematics"]),
    ("7206", "Further_Mathematics", "L2CERT", "v4", 2012, 2019, "LEGACY", ["mathematics"]),
    # ---- GCSE / Level 2 ----
    ("7202", "Statistics", "L2CERT", "", 2012, 2017, "LEGACY", ["mathematics"]),
    ("8063", "Design_and_Technology", "GCSE", "Fashion_and_Textiles", 2012, 2017, "LEGACY", ["design-and-technology"]),
    ("8100", "Citizenship_Studies", "GCSE", "", 2018, "PRESENT", "CURRENT", ["citizenship", "citizenship-studies"]),
    ("8201", "Art_and_Design", "GCSE", "Art_Craft_Design", 2017, "PRESENT", "CURRENT", ["art-and-design"]),
    ("8202", "Art_and_Design", "GCSE", "Fine_Art", 2017, "PRESENT", "CURRENT", ["art-and-design"]),
    ("8203", "Art_and_Design", "GCSE", "Graphic_Communication", 2017, "PRESENT", "CURRENT", ["art-and-design"]),
    ("8204", "Art_and_Design", "GCSE", "Textile_Design", 2017, "PRESENT", "CURRENT", ["art-and-design"]),
    ("8205", "Art_and_Design", "GCSE", "Three_Dimensional_Design", 2017, "PRESENT", "CURRENT", ["art-and-design"]),
    ("8206", "Art_and_Design", "GCSE", "Photography", 2017, "PRESENT", "CURRENT", ["art-and-design"]),
    ("8464", "Combined_Science", "GCSE", "Trilogy", 2018, "PRESENT", "CURRENT", ["science"]),
    ("8465", "Combined_Science", "GCSE", "Synergy", 2018, "PRESENT", "CURRENT", ["science"]),
    ("8585", "Food_Preparation_and_Nutrition", "GCSE", "", 2018, "PRESENT", "CURRENT", ["food", "food-preparation-and-nutrition"]),
    ("8668", "German", "GCSE", "", 2018, "PRESENT", "CURRENT", ["german"]),
    ("8688", "Persian", "GCSE", "", 2019, "PRESENT", "CURRENT", ["persian", "languages"]),
]

FS = "https://filestore.aqa.org.uk/resources/{slug}/specifications/{fn}"

# AQA publishes ONE spec covering both AS and A-level for many subjects:
# filename AQA-<AScode>-<A2code>-SP-<year>.PDF . Map AS code -> partner A2 code.
PAIR = {
    "7041": "7042", "7131": "7132", "7135": "7136", "7181": "7182", "7191": "7192",
    "7401": "7402", "7404": "7405", "7407": "7408", "7516": "7517",
    "7701": "7702", "7711": "7712", "7716": "7717",
    "7036": "7037", "7061": "7062", "7356": "7357", "7651": "7652",
    "7661": "7662", "7691": "7692", "7562": "7561",
}


def probe(code, slugs):
    """Return a working filestore PDF URL for this code, else None.
    Tries standalone, legacy, and combined AS+A-level filename patterns."""
    pats = [f"AQA-{code}-SP-{y}.PDF" for y in range(2021, 2013, -1)]
    pats += [f"AQA-{code}-W-SP-{y:02d}.PDF" for y in range(17, 8, -1)]
    partner = PAIR.get(code)
    if partner:
        lo, hi = sorted([code, partner])
        for y in range(2021, 2013, -1):
            pats.append(f"AQA-{lo}-{hi}-SP-{y}.PDF")
            pats.append(f"AQA-{hi}-{lo}-SP-{y}.PDF")
    for slug in slugs:
        for fn in pats:
            url = FS.format(slug=slug, fn=fn)
            if lib_fetch.head_ok(url, timeout=8):
                return url
            time.sleep(0.05)
    return None


def copy_sibling(code):
    """If the code shares a spec with a file we already hold, return that path.
    Covers AS codes (share the combined AS+A2 doc with their A-level sibling) and
    Art endorsement codes 8201-8206 (share the single Art & Design spec)."""
    import glob
    partner = PAIR.get(code)
    cands = []
    if partner:
        cands += glob.glob(os.path.join(SYLL, "AQA", "**", f"*_{partner}_*.pdf"), recursive=True)
    if code in ("8201", "8202", "8203", "8204", "8205", "8206"):
        cands += glob.glob(os.path.join(SYLL, "AQA", "GCSE", "Art_and_Design", "8201-8206_*", "*.pdf"))
    cands = [c for c in cands if os.path.getsize(c) > 10000]
    return cands[0] if cands else None


def main():
    rows = list(csv.DictReader(open(CSV_PATH, encoding="utf-8")))
    have_files = {r["Filename"] for r in rows if r.get("Filename")}
    new_rows, ok, skip, fail = [], 0, 0, 0

    for code, subj, qt, var, fy, ly, st, slugs in T:
        rec = {"board": "AQA", "qual_type": qt, "variant": var, "subject": subj,
               "spec_code": code, "first_year": fy, "last_year": ly, "status": st,
               "alt_codes": []}
        folder = naming.new_folder(SYLL, rec)
        fname = naming.new_filename(rec)
        fpath = os.path.join(folder, fname)
        if os.path.exists(fpath) or fname in have_files:
            print(f"  SKIP exists  {code} {subj} {qt}")
            skip += 1
            continue

        url = probe(code, slugs)
        data = lib_fetch.fetch_pdf(url) if url else None
        note_src = "filestore"
        if not data:
            # fallback: copy the spec this code shares with a sibling we already hold
            sib = copy_sibling(code)
            if sib:
                import shutil
                data = open(sib, "rb").read()
                url = ""
                note_src = f"shared spec copied from {os.path.basename(sib)}"

        if data:
            os.makedirs(folder, exist_ok=True)
            with open(fpath, "wb") as f:
                f.write(data)
            note = f"OK ({len(data)//1024} KB)" + ("" if note_src == "filestore" else f" [{note_src}]")
            new_rows.append(naming.csv_row(rec, fname, url, TODAY, note))
            print(f"  OK  {code} {subj:28} {qt:7} {len(data)//1024} KB {'' if note_src=='filestore' else '(shared)'}")
            ok += 1
        else:
            new_rows.append(naming.csv_row(rec, "", url or "", TODAY,
                            "NOT_FOUND: no filestore PDF (standalone/combined) and no shared sibling spec"))
            print(f"  --  {code} {subj:28} {qt:7} NOT FOUND")
            fail += 1

    rows += new_rows
    tmp = CSV_PATH + ".tmp"
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=naming.CSV_HEADER)
        w.writeheader(); w.writerows(rows)
    os.replace(tmp, CSV_PATH)
    print(f"\nTOTALS  ok={ok}  skip={skip}  not_found={fail}  (CSV now {len(rows)} rows)")


if __name__ == "__main__":
    main()
