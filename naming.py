#!/usr/bin/env python3
"""
naming.py — single source of truth for the NEW year-range convention.

Filename : [BOARD]_[QUALTAG]_[SUBJECT][_VARIANT]_[CODE]_[FIRST]_to_[LAST]_[STATUS].pdf
Folder   : year-based tree (NO Current/Legacy folders); leaf = [CODE]_[FIRST]_to_[LAST]

Both migration and the v2 downloader import from here so naming never diverges.
"""
import os

# qual_type -> level folder name, per board
LEVEL_FOLDER = {
    ("AQA", "ALEVEL"): "A_Level",
    ("AQA", "AS"): "AS_Level",
    ("AQA", "GCSE"): "GCSE",
    ("AQA", "ELC"): "Entry_Level_Certificate",
    ("AQA", "L2CERT"): "Level_2_Certificate",
    ("Edexcel", "ALEVEL"): "A_Level",
    ("Edexcel", "AS"): "AS_Level",
    ("Edexcel", "GCSE"): "GCSE",
    ("Edexcel", "IGCSE"): "IGCSE",
    ("Edexcel", "IAL"): "International_A_Level",
    ("Edexcel", "IPRIMARY"): "iPrimary",
    ("Edexcel", "ILOWERSEC"): "iLowerSecondary",
    ("OCR", "ALEVEL"): "A_Level",
    ("OCR", "AS"): "AS_Level",
    ("OCR", "GCSE"): "GCSE",
    ("OCR", "CAMNAT"): "Cambridge_Nationals",
    ("IB", "DP"): "DP",
    ("IB", "MYP"): "MYP",
    ("IB", "PYP"): "PYP",
    ("IB", "CP"): "CP",
}

# qual_type -> filename tag
QUALTAG = {
    "ALEVEL": "ALEVEL", "AS": "AS", "GCSE": "GCSE", "ELC": "ELC", "L2CERT": "L2CERT",
    "IGCSE": "IGCSE", "IAL": "IAL", "IPRIMARY": "IPRIMARY", "ILOWERSEC": "ILOWERSEC",
    "CAMNAT": "CAMNAT", "DP": "DP", "MYP": "MYP", "PYP": "PYP", "CP": "CP",
}

# variants that act as a SUBJECT discriminator -> go INTO the filename
INLINE_VARIANTS = {"A", "B", "AA", "AI"}
# variants that only split FOLDERS (Edexcel IGCSE / OCR CamNat suites)
FOLDER_ONLY_VARIANTS = {"Linear", "Modular", "Old_Suite_2012", "New_Suite_2022"}


def last_str(last_year):
    return "PRESENT" if str(last_year).upper() == "PRESENT" else str(last_year)


def qual_tag(r):
    qt = r["qual_type"]
    if qt == "DP":
        v = r.get("variant", "")
        if v == "HL":
            return "DP_HL"
        if v == "SL":
            return "DP_SL"
        return "DP"
    return QUALTAG.get(qt, qt)


def code_token(r):
    return (r.get("spec_code") or "NA").replace(" ", "-").replace("/", "-")


def new_filename(r):
    board = r["board"]
    tag = qual_tag(r)
    subj = r["subject"]
    var = r.get("variant", "")
    parts = [board, tag, subj]
    if var in INLINE_VARIANTS:
        parts.append(var)
    parts.append(code_token(r))
    parts.append(str(r["first_year"]))
    parts.append("to")
    parts.append(last_str(r["last_year"]))
    parts.append(r["status"])
    return "_".join(parts) + ".pdf"


def version_leaf(r):
    """Folder leaf identifying this exact version, e.g. 7402_2017_to_PRESENT."""
    return f"{code_token(r)}_{r['first_year']}_to_{last_str(r['last_year'])}"


def new_folder(syllabuses_root, r):
    board = r["board"]
    qt = r["qual_type"]
    subj = r["subject"]
    var = r.get("variant", "")
    level = LEVEL_FOLDER[(board, qt)]
    base = os.path.join(syllabuses_root, board, level, subj)

    if board == "IB" and qt == "DP":
        # DP/[Subject]/[SL|HL|SL_HL|AA|AI]/[FIRST_YEAR]
        sub = var if var else "SL_HL"
        return os.path.join(base, sub, str(r["first_year"]))
    if board == "IB" and qt in ("MYP", "PYP", "CP"):
        return os.path.join(base, version_leaf(r))
    if board == "Edexcel" and qt == "IGCSE":
        sub = var if var in ("Linear", "Modular") else "Linear"
        return os.path.join(base, sub, version_leaf(r))
    if board == "OCR" and qt == "CAMNAT":
        sub = var if var else "New_Suite_2022"
        return os.path.join(base, sub, version_leaf(r))
    if board == "OCR" and qt in ("ALEVEL", "AS", "GCSE") and var in ("A", "B"):
        return os.path.join(base, f"Variant_{var}", version_leaf(r))
    # default
    return os.path.join(base, version_leaf(r))


# CSV schema for the new convention
CSV_HEADER = [
    "Board", "Qualification_Type", "Variant", "Subject", "Spec_Code",
    "First_Assessment_Year", "Last_Assessment_Year", "Status",
    "Filename", "Source_URL", "Download_Date", "Notes",
]


def csv_row(r, filename, source_url, download_date, notes):
    return {
        "Board": r["board"],
        "Qualification_Type": r["qual_type"],
        "Variant": r.get("variant", ""),
        "Subject": r["subject"],
        "Spec_Code": r.get("spec_code", ""),
        "First_Assessment_Year": r["first_year"],
        "Last_Assessment_Year": last_str(r["last_year"]),
        "Status": r["status"],
        "Filename": filename,
        "Source_URL": source_url,
        "Download_Date": download_date,
        "Notes": notes,
    }


if __name__ == "__main__":
    import spec_registry
    for r in spec_registry.RECORDS[:6] + spec_registry.RECORDS[-8:]:
        print(new_filename(r))
        print("   ->", new_folder("Syllabuses", r))
