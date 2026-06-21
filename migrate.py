#!/usr/bin/env python3
"""
migrate.py — relabel/relocate the existing PDFs into the NEW year-range
convention, emit the new 12-column CSV, and write an ENRICHED registry
(prompt-known specs UNION specs actually discovered on disk).

Resolution priority for each existing file:
  1. exact spec-code match in registry  -> registry range/variant/status
  2. slot match (board,subject,qual,status); prefer the record whose
     year-range contains the old year, else the lone record in that slot
     -> adopt its range/variant; keep the file's REAL code if it has one
  3. heuristic from (qual_type, status, old year) with reform-year rules

Collisions (>1 file -> same target, e.g. two issues of spec 7132) are kept,
disambiguated with a _pub<origYear> suffix.

DRY RUN: python migrate.py        EXECUTE: python migrate.py --go
"""
import csv, json, os, shutil, sys
from datetime import date

import spec_registry, naming

ROOT = os.path.dirname(os.path.abspath(__file__))
SYLL = os.path.join(ROOT, "Syllabuses")
CSV_PATH = os.path.join(ROOT, "Syllabus_Master_Index.csv")
TODAY = date.today().isoformat()
GO = "--go" in sys.argv

REG = spec_registry.RECORDS
by_bs = {}
for r in REG:
    by_bs.setdefault((r["board"], r["subject"]), []).append(r)

LEVEL2QT = {"A_Level": "ALEVEL", "GCSE": "GCSE", "Diploma_Programme": "DP"}
PLACEHOLDER = {"ARCHIVED", "NA", "N/A", ""}
IB_LEGACY_LAST = {"Further_Mathematics": 2020}


def lastnum(ly):
    return 2026 if str(ly).upper() == "PRESENT" else int(ly)


def is_real_code(code):
    return code and code.upper() not in PLACEHOLDER


def adopt(r, file_code):
    """Use registry record r's range/variant/status, but keep file's real code."""
    out = dict(r)
    if is_real_code(file_code):
        out["spec_code"] = file_code
        out["alt_codes"] = []
    return out


def heuristic(board, qt, status, oy, code):
    if status == "CURRENT":
        if oy and (oy > 2017 or (board == "OCR" and 2015 <= oy <= 2017)):
            first = oy
        else:
            first = 2017
        last = "PRESENT"
    else:  # LEGACY
        first = oy if oy else 2009
        last = 2016 if not oy or oy <= 2016 else oy
    return {"board": board, "qual_type": qt, "variant": "", "subject": None,
            "spec_code": code if is_real_code(code) else "NA",
            "first_year": first, "last_year": last, "status": status, "alt_codes": []}


def resolve(old):
    board, subj, code = old["Board"], old["Subject"], old["Spec_Code"]
    qt = LEVEL2QT.get(old["Level"], old["Level"])
    st = old["Status"].upper()
    oy = int(str(old["Year_Version"]).strip()) if str(old["Year_Version"]).strip().isdigit() else None
    cands = by_bs.get((board, subj), [])

    if board == "IB":
        return resolve_ib(old, oy, st), "ib"

    # 1 exact code
    for r in cands:
        if r["qual_type"] == qt and (code == r["spec_code"] or code in r.get("alt_codes", [])):
            return adopt(r, code), "registry-code"
    # 2 slot match
    slot = [r for r in cands if r["qual_type"] == qt and r["status"] == st]
    if oy is not None:
        contain = [r for r in slot if r["first_year"] <= oy <= lastnum(r["last_year"])]
        if len(contain) == 1:
            return adopt(contain[0], code), "registry-slot(year)"
    if len(slot) == 1:
        return adopt(slot[0], code), "registry-slot(only)"
    # 3 heuristic
    h = heuristic(board, qt, st, oy, code)
    h["subject"] = subj
    return h, "heuristic"


def resolve_ib(old, oy, st):
    cl = (old["Spec_Code"] or "").lower()
    if "analysis and approaches" in cl:
        variant = "AA"
    elif "applications" in cl:
        variant = "AI"
    elif "further" in cl:
        variant = "HL"
    else:
        variant = "SL_HL"
    last = "PRESENT" if st == "CURRENT" else IB_LEGACY_LAST.get(old["Subject"], oy or 2016)
    return {"board": "IB", "qual_type": "DP", "variant": variant, "subject": old["Subject"],
            "spec_code": "NA", "first_year": oy, "last_year": last, "status": st, "alt_codes": []}


def main():
    om = json.load(open(os.path.join(ROOT, "_ondisk_map.json"), encoding="utf-8"))
    by_name, ondisk = om["by_name"], om["ondisk"]

    plans, methods = [], {}
    for d in ondisk:
        old = by_name[d["name"]]
        r, method = resolve(old)
        methods[method] = methods.get(method, 0) + 1
        old_abs = os.path.join(ROOT, d["rel"].replace("/", os.sep))
        plans.append({"old_abs": old_abs, "rec": r, "old": old,
                      "oy": old["Year_Version"], "method": method})

    # assign target paths; detect collisions -> disambiguate
    groups = {}
    for p in plans:
        base = os.path.join(naming.new_folder(SYLL, p["rec"]), naming.new_filename(p["rec"]))
        p["base_target"] = base
        groups.setdefault(base, []).append(p)
    for base, members in groups.items():
        if len(members) == 1:
            members[0]["target"] = base
        else:
            for m in members:
                stem = base[:-4]  # strip .pdf
                m["target"] = f"{stem}_pub{m['oy']}.pdf"

    print("resolution methods:", methods)
    final_targets = {}
    for p in plans:
        final_targets.setdefault(p["target"], []).append(p["old"]["Filename"])
    dups = {t: v for t, v in final_targets.items() if len(v) > 1}
    print(f"files: {len(plans)} | unique final targets: {len(final_targets)} | residual collisions: {len(dups)}")
    for t, v in dups.items():
        print("  !! STILL COLLIDES:", os.path.basename(t), v)

    if not GO:
        print("\n--- sample of disambiguated / heuristic / slot results ---")
        shown = 0
        for p in plans:
            if p["method"] != "registry-code" or "pub" in p["target"]:
                print(f"  [{p['method']:20}] {os.path.relpath(p['target'], ROOT)}")
                shown += 1
            if shown >= 22:
                break
        print("\nRun with --go to execute.")
        return

    # EXECUTE -------------------------------------------------------------
    rows = []
    moved = 0
    for p in plans:
        tgt = p["target"]
        os.makedirs(os.path.dirname(tgt), exist_ok=True)
        if os.path.abspath(p["old_abs"]) != os.path.abspath(tgt):
            if os.path.exists(tgt):
                os.remove(p["old_abs"])
            else:
                shutil.move(p["old_abs"], tgt)
            moved += 1
        kb = os.path.getsize(tgt) // 1024 if os.path.exists(tgt) else 0
        note = f"MIGRATED [{p['method']}] from {p['old']['Filename']} ({kb} KB)"
        if is_real_code(p["old"]["Spec_Code"]) and p["old"]["Spec_Code"] != p["rec"].get("spec_code"):
            note += f"; orig_code={p['old']['Spec_Code']}"
        rows.append(naming.csv_row(p["rec"], os.path.basename(tgt),
                                   p["old"].get("Source_URL", ""), TODAY, note))

    with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=naming.CSV_HEADER)
        w.writeheader()
        w.writerows(rows)
    print(f"moved {moved} files | wrote {len(rows)} CSV rows")

    # enriched registry = prompt records UNION discovered on-disk specs
    enriched = list(REG)
    seen = {(r["board"], r["qual_type"], r.get("variant", ""), r["subject"],
             r["spec_code"], r["first_year"]) for r in REG}
    added = 0
    for p in plans:
        r = p["rec"]
        key = (r["board"], r["qual_type"], r.get("variant", ""), r["subject"],
               r.get("spec_code"), r["first_year"])
        if key not in seen:
            seen.add(key)
            rr = dict(r); rr["notes"] = "discovered on disk (prior run)"
            enriched.append(rr)
            added += 1
    json.dump(enriched, open(os.path.join(ROOT, "enriched_registry.json"), "w", encoding="utf-8"), indent=1)
    print(f"enriched_registry.json: {len(REG)} prompt + {added} discovered = {len(enriched)} records")

    removed = 0
    for dp, dn, fn in os.walk(SYLL, topdown=False):
        if os.path.basename(dp) in ("Current", "Legacy") and not os.listdir(dp):
            os.rmdir(dp); removed += 1
    print(f"removed {removed} empty Current/Legacy folders")


if __name__ == "__main__":
    main()
