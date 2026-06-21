#!/usr/bin/env python3
"""
legacy_harvester.py — recover 2005-2014 (pre-reform) specifications from the
Wayback Machine for our 25 subjects, place them in the Legacy/ folders, and
append to Syllabus_Master_Index.csv.

Strategy: query the Wayback CDX API per board domain for archived PDF specs,
filter client-side to our subjects + level (GCE=A-level / GCSE), pick the best
pre-2015 candidate per (board, level, subject), download via the Wayback
`id_` raw endpoint, verify it is a real PDF, rename and file it.
"""
import csv, os, re, time
from collections import defaultdict
import requests

ROOT = os.path.dirname(os.path.abspath(__file__))
SYL = os.path.join(ROOT, "Syllabuses")
CSV_PATH = os.path.join(ROOT, "Syllabus_Master_Index.csv")
CDX = "http://web.archive.org/cdx/search/cdx"
TODAY = "2026-06-13"

S = requests.Session()
S.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"})

LEVEL_FOLDER = {"A_Level": "A_Level", "GCSE": "GCSE"}
LEVEL_TAG = {"A_Level": "ALEVEL", "GCSE": "GCSE"}
CSV_HEADER = ["Board","Level","Subject","Spec_Code","Year_Version","Status",
              "Filename","Source_URL","Download_Date","Notes"]

# subject -> (positive keyword regexes, negative keyword regexes) matched on URL (lowercased)
SUBJ = {
    "Mathematics":          (r"math|maths", r"further|statistic|mechanic|additional|use[- ]?of[- ]?math"),
    "Further_Mathematics":  (r"further[\-% ]*math", r""),
    "Statistics":           (r"statistic", r""),
    "Psychology":           (r"psycholog", r""),
    "Biology":              (r"biolog", r"human[\-% ]?biolog"),
    "Chemistry":            (r"chemistry", r""),
    "Physics":              (r"physics", r""),
    "History":              (r"history", r"art[\-% ]?history|history[\-% ]?of[\-% ]?art"),
    "English_Literature":   (r"english[\-% ]*lit|englishlit", r""),
    "English_Language":     (r"english[\-% ]*lang|englishlang", r"literature"),
    "Geography":            (r"geography", r""),
    "Sociology":            (r"sociolog", r""),
    "Art_and_Design":       (r"art[\-% ]*and[\-% ]*design|art[\-% ]*design|artdesign", r""),
    "Business_Studies":     (r"business", r""),
    "Economics":            (r"economic", r"home[\-% ]?economic"),
    "Computer_Science":     (r"comput", r""),
    "Religious_Studies":    (r"religious|spec-gce-rs|spec-gcse-rs|/rs[\-.]", r""),
    "Spanish":              (r"spanish", r""),
    "French":               (r"french", r""),
    "Politics":             (r"politics|government", r""),
    "Physical_Education":   (r"physical[\-% ]*education|p\.?e\.?[\-_ ]spec|sport", r""),
    "Music":                (r"music", r"music[\-% ]?technolog"),
    "Drama":                (r"drama|theatre", r""),
    "Design_and_Technology":(r"design[\-% ]*and[\-% ]*technology|design[\-% ]*technology|resistant[\-% ]*material|product[\-% ]*design|graphic[\-% ]*product", r""),
    "Media_Studies":        (r"media", r"multimedia"),
}

BOARDS = [
    ("AQA",     "aqa.org.uk",                 "domain"),
    ("Edexcel", "edexcel.com",                "domain"),
    ("Edexcel", "qualifications.pearson.com", "domain"),
    ("OCR",     "ocr.org.uk",                 "domain"),
]

# A URL must look like a real specification document...
STRONG = re.compile(
    r"specif|spec-gce|spec-gcse|spec_gc|gce-lin-|gcse-in-|-spec-|spec-iss|"
    r"spec-20|spec-overview|-specification|gce-.*-spec|gcse-.*-spec", re.I)
# ...and must NOT look like any of these non-spec document types.
JUNK = re.compile(
    r"notice-to-centres|results|sow|scheme[\-% ]?of[\-% ]?work|examiner|mark[\-% ]?scheme|"
    r"-msc|grade[\-% ]?boundar|gde-bdy|timeline|cpd|guidance|guiance|order|factsheet|"
    r"summary|brochure|-broc|precourse|-sam|report|entry-cod|replacement|faq|newsletter|"
    r"poster|insert|unit-\d|topic-|writresp|training|webinar|teacher|delivery-guide|"
    r"sample[\-% ]?assessment|question[\-% ]?paper|-qp-|-ms-|specimen", re.I)


def acceptable(orig):
    u = orig.lower()
    return bool(STRONG.search(u)) and not JUNK.search(u)


def cdx_fetch(pattern, mt):
    params = {"url": pattern, "matchType": mt,
              "filter": ["mimetype:application/pdf", "statuscode:200"],
              "from": "2005", "to": "2014", "output": "json",
              "collapse": "urlkey", "limit": "50000"}
    try:
        r = S.get(CDX, params=params, timeout=120)
        data = r.json() if r.text.strip().startswith("[") else []
        return data[1:] if data else []
    except Exception as e:
        print("  CDX error:", e)
        return []


def classify_level(url):
    u = url.lower()
    if re.search(r"gcse", u):
        return "GCSE"
    if re.search(r"gce|a[\-% ]?level|as[\-% ]?and[\-% ]?a|/gce/", u):
        return "A_Level"
    return None


def match_subject(url):
    u = url.lower()
    for subj, (pos, neg) in SUBJ.items():
        if neg and re.search(neg, u):
            continue
        if re.search(pos, u):
            yield subj


def score(row):
    ts, orig = row[1], row[2]
    u = orig.lower()
    s = 0.0
    if "specification" in u: s += 8
    if "spec-gce" in u or "spec-gcse" in u or "gce-lin-" in u or "gcse-in-" in u: s += 5
    if "spec-2012" in u or "-spec-" in u or "spec-iss" in u: s += 3
    if "international" in u or "igcse" in u or re.search(r"4[a-z]{2}0", u): s -= 4  # prefer domestic
    if "draft" in u: s -= 1
    try:
        s += min(int(row[6]), 4_000_000) / 400_000     # prefer larger (fuller) specs
    except (ValueError, IndexError):
        pass
    s += (int(ts[:4]) - 2005) * 0.5                     # mild recency preference
    return s


def append_rows(rows):
    new = not os.path.exists(CSV_PATH) or os.path.getsize(CSV_PATH) == 0
    with open(CSV_PATH, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(CSV_HEADER)
        for r in rows:
            w.writerow([r.get(c, "") for c in CSV_HEADER])
        f.flush(); os.fsync(f.fileno())


def clean(s):
    return re.sub(r"[^A-Za-z0-9]+", "-", s or "").strip("-")[:40]


def download_wayback(ts, orig):
    url = f"https://web.archive.org/web/{ts}id_/{orig}"
    for attempt in range(3):
        try:
            r = S.get(url, timeout=90, allow_redirects=True)
            if r.status_code == 200 and r.content[:5].startswith(b"%PDF") and len(r.content) > 20000:
                return r.content, url
        except requests.RequestException:
            pass
        time.sleep(2)
    return None, url


def main():
    # 1) gather candidates: (board, level, subject) -> list of rows
    cand = defaultdict(list)
    for board, pattern, mt in BOARDS:
        print(f"CDX {board} <- {pattern} ...")
        rows = cdx_fetch(pattern, mt)
        print(f"  {len(rows)} pdf rows")
        for row in rows:
            orig = row[2]
            if not acceptable(orig):          # only real specification documents
                continue
            lvl = classify_level(orig)
            if not lvl:
                continue
            for subj in match_subject(orig):
                cand[(board, lvl, subj)].append(row)

    print(f"\nMatched cells: {len(cand)}")

    # 2) for each cell pick best 1, download, file
    logged, ok, fail = [], 0, 0
    for (board, lvl, subj), rows in sorted(cand.items()):
        rows.sort(key=score, reverse=True)
        placed = False
        for row in rows[:4]:                      # try up to 4 best before giving up
            ts, orig = row[1], row[2]
            yr = ts[:4]
            folder = os.path.join(SYL, board, LEVEL_FOLDER[lvl], subj, "Legacy")
            os.makedirs(folder, exist_ok=True)
            stem = clean(os.path.basename(orig).rsplit(".", 1)[0]) or "ARCHIVE"
            fname = f"{board.upper()}_{LEVEL_TAG[lvl]}_{subj}_{stem}_{yr}_LEGACY.pdf"
            fpath = os.path.join(folder, fname)
            if os.path.exists(fpath):
                placed = True; break
            time.sleep(0.5)
            data, src = download_wayback(ts, orig)
            if data:
                with open(fpath, "wb") as f:
                    f.write(data)
                logged.append({"Board": board, "Level": lvl, "Subject": subj,
                               "Spec_Code": "ARCHIVED", "Year_Version": yr, "Status": "LEGACY",
                               "Filename": fname, "Source_URL": src, "Download_Date": TODAY,
                               "Notes": f"OK ({len(data)//1024} KB) [Wayback {yr}]"})
                ok += 1; placed = True
                print(f"  OK  {board:8} {lvl:8} {subj:22} {yr}  {stem[:34]} ({len(data)//1024} KB)")
                break
        if not placed:
            logged.append({"Board": board, "Level": lvl, "Subject": subj, "Spec_Code": "ARCHIVED",
                           "Year_Version": "", "Status": "LEGACY", "Filename": "",
                           "Source_URL": rows[0][2] if rows else "", "Download_Date": TODAY,
                           "Notes": "NOT_FOUND: Wayback candidates failed to download"})
            fail += 1
            print(f"  --  {board:8} {lvl:8} {subj:22} no usable archive")
        append_rows(logged); logged = []

    print(f"\nLegacy harvest complete: {ok} downloaded, {fail} cells with no usable archive")


if __name__ == "__main__":
    main()
