#!/usr/bin/env python3
"""
syllabus_downloader.py
----------------------
Downloads official exam-board specification (syllabus) PDFs for AQA, Edexcel,
OCR and IB across 25 subjects, A-level + GCSE (+ IB DP), Current & Legacy.

Features
  * requests + BeautifulSoup
  * Direct-PDF download when a verified pdf_url is known
  * Fallback: scrape the official spec PAGE and extract the spec PDF link
  * Rename: [BOARD]_[LEVEL]_[SUBJECT]_[SPEC-CODE]_[YEAR]_[STATUS].pdf
  * Correct folder placement under Syllabuses/...
  * Appends every result to Syllabus_Master_Index.csv (flushed after each subject)
  * Retry logic: 3 attempts per URL, 2s delay between retries
  * Skips files that already exist on disk
  * Logs failures as NOT_FOUND in the CSV Notes column (never crashes)
  * Prints progress after every 5 subjects + a final summary table
"""

import csv
import io
import json
import os
import re
import sys
import time
from datetime import date
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

try:
    from curl_cffi import requests as creq   # browser-TLS client to pass Cloudflare (e.g. ibo.org)
    HAVE_CFFI = True
except Exception:
    HAVE_CFFI = False

# ----------------------------------------------------------------------------- config
ROOT = os.path.dirname(os.path.abspath(__file__))
SYLLABUSES = os.path.join(ROOT, "Syllabuses")
CSV_PATH = os.path.join(ROOT, "Syllabus_Master_Index.csv")
SEEDS_PATH = os.path.join(ROOT, "seeds.json")              # merged target table
TODAY = date.today().isoformat()

RETRIES = 3
RETRY_DELAY = 2          # seconds
POLITE_DELAY = 0.4       # seconds between network calls
MIN_PDF_BYTES = 10_000   # smaller -> probably an error page, not a real spec

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": UA, "Accept": "*/*"})

SUBJECT_ORDER = [
    "Mathematics", "Psychology", "Biology", "Chemistry", "Further_Mathematics",
    "History", "Physics", "English_Literature", "English_Language", "Geography",
    "Sociology", "Art_and_Design", "Business_Studies", "Economics", "Computer_Science",
    "Religious_Studies", "Spanish", "French", "Politics", "Physical_Education",
    "Music", "Drama", "Design_and_Technology", "Statistics", "Media_Studies",
]

BOARD_FOLDER = {"AQA": "AQA", "Edexcel": "Edexcel", "OCR": "OCR", "IB": "IB"}
LEVEL_FOLDER = {"A_Level": "A_Level", "GCSE": "GCSE", "Diploma_Programme": "Diploma_Programme"}
LEVEL_TAG = {"A_Level": "ALEVEL", "GCSE": "GCSE", "Diploma_Programme": "IBDP"}

CSV_HEADER = ["Board", "Level", "Subject", "Spec_Code", "Year_Version",
              "Status", "Filename", "Source_URL", "Download_Date", "Notes"]


# ----------------------------------------------------------------------------- helpers
def ensure_csv():
    if not os.path.exists(CSV_PATH) or os.path.getsize(CSV_PATH) == 0:
        with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(CSV_HEADER)


def append_rows(rows):
    """Append rows and flush immediately (called after each subject)."""
    with open(CSV_PATH, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        for r in rows:
            w.writerow([r.get(c, "") for c in CSV_HEADER])
        f.flush()
        os.fsync(f.fileno())


def _clean(s):
    """Filesystem-safe token: keep alnum, collapse everything else to a single hyphen."""
    return re.sub(r"[^A-Za-z0-9]+", "-", s or "").strip("-")


def make_filename(t):
    board = t["board"].upper()
    level = LEVEL_TAG[t["level"]]
    subj = t["subject"]
    code = _clean(t.get("spec_code")) or "NA"
    year = t.get("year") or "NA"
    status = t["status"].upper()
    return f"{board}_{level}_{subj}_{code}_{year}_{status}.pdf"


def target_folder(t):
    status_dir = "Current" if t["status"].upper() == "CURRENT" else "Legacy"
    return os.path.join(SYLLABUSES, BOARD_FOLDER[t["board"]],
                        LEVEL_FOLDER[t["level"]], t["subject"], status_dir)


def looks_like_pdf(resp):
    ctype = resp.headers.get("Content-Type", "").lower()
    if "pdf" in ctype:
        return True
    # some servers mislabel; sniff the magic bytes
    return resp.content[:5].startswith(b"%PDF")


def _valid_pdf_bytes(content, ctype):
    if len(content) < MIN_PDF_BYTES:
        return False
    if content[:5].startswith(b"%PDF"):
        return True
    return "pdf" in (ctype or "").lower()


def _fetch_requests(url):
    blocked = False
    for attempt in range(1, RETRIES + 1):
        try:
            r = SESSION.get(url, timeout=40, allow_redirects=True)
            if r.status_code == 200 and _valid_pdf_bytes(r.content, r.headers.get("Content-Type")):
                return r.content, False
            if r.status_code in (403, 429):
                blocked = True       # likely WAF/Cloudflare -> let curl_cffi try
                break
            if r.status_code in (404, 410):
                return None, False
        except requests.RequestException:
            pass
        if attempt < RETRIES:
            time.sleep(RETRY_DELAY)
    return None, blocked


def _fetch_cffi(url):
    """Fallback using a browser TLS fingerprint to defeat Cloudflare bot management."""
    if not HAVE_CFFI:
        return None
    for attempt in range(1, RETRIES + 1):
        try:
            r = creq.get(url, impersonate="chrome", timeout=50, allow_redirects=True)
            if r.status_code == 200 and _valid_pdf_bytes(r.content, r.headers.get("Content-Type")):
                return r.content
            if r.status_code in (404, 410):
                return None
        except Exception:
            pass
        if attempt < RETRIES:
            time.sleep(RETRY_DELAY)
    return None


def fetch_pdf(url):
    """Return PDF bytes via requests; fall back to curl_cffi on block/failure."""
    data, _ = _fetch_requests(url)
    if data:
        return data
    return _fetch_cffi(url)


def scrape_pdf_link(page_url, spec_code):
    """Fetch a spec page and return the best direct-PDF link found, else None."""
    try:
        r = SESSION.get(page_url, timeout=40, allow_redirects=True)
        if r.status_code != 200:
            return None
    except requests.RequestException:
        return None

    soup = BeautifulSoup(r.text, "html.parser")
    code_l = (spec_code or "").lower()
    candidates = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        full = urljoin(page_url, href)
        low = full.lower()
        if ".pdf" not in low:
            continue
        text = (a.get_text() or "").lower()
        score = 0
        if "specification" in low or "specification" in text:
            score += 5
        if "-sp-" in low or "/sp-" in low or "spec" in low:
            score += 3
        if code_l and code_l in low:
            score += 4
        for dom in ("filestore.aqa.org.uk", "/content/dam/pdf", "ocr.org.uk/images",
                    "ocr.org.uk/Images"):
            if dom.lower() in low:
                score += 2
        # de-prioritise sample assessment / mark scheme / past paper PDFs
        for bad in ("sam", "sample-assessment", "mark-scheme", "question-paper",
                    "past-paper", "insert", "examiner"):
            if bad in low:
                score -= 4
        candidates.append((score, full))

    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0], reverse=True)
    best_score, best_url = candidates[0]
    return best_url if best_score > 0 else candidates[0][1]


def process_target(t):
    """
    Returns (csv_row, downloaded_bool).
    Tries pdf_url first, then scrapes page_url. Never raises.
    """
    folder = target_folder(t)
    os.makedirs(folder, exist_ok=True)
    fname = make_filename(t)
    fpath = os.path.join(folder, fname)

    base_row = {
        "Board": t["board"], "Level": LEVEL_FOLDER[t["level"]], "Subject": t["subject"],
        "Spec_Code": t.get("spec_code", ""), "Year_Version": t.get("year", ""),
        "Status": t["status"].upper(), "Filename": fname,
        "Source_URL": t.get("pdf_url") or t.get("page_url", ""),
        "Download_Date": TODAY, "Notes": "",
    }

    # skip already-downloaded
    if os.path.exists(fpath) and os.path.getsize(fpath) >= MIN_PDF_BYTES:
        base_row["Notes"] = "SKIPPED_EXISTS"
        return base_row, True

    # 'not offered' sentinel from discovery
    if (t.get("spec_code", "").upper() in ("N/A", "NA")) and not t.get("pdf_url") and not t.get("page_url"):
        base_row["Filename"] = ""
        base_row["Notes"] = "NOT_FOUND: not offered by this board at this level"
        return base_row, False

    data = None
    src_used = ""

    # 1) direct pdf url
    pdf_url = (t.get("pdf_url") or "").strip()
    if pdf_url.lower().endswith(".pdf") or "pdf" in pdf_url.lower():
        time.sleep(POLITE_DELAY)
        data = fetch_pdf(pdf_url)
        if data:
            src_used = pdf_url

    # 2) scrape the spec page for a pdf link
    if data is None:
        page_url = (t.get("page_url") or "").strip()
        if page_url:
            time.sleep(POLITE_DELAY)
            found = scrape_pdf_link(page_url, t.get("spec_code", ""))
            if found:
                time.sleep(POLITE_DELAY)
                data = fetch_pdf(found)
                if data:
                    src_used = found

    if data is None:
        base_row["Filename"] = ""
        why = "no working pdf_url or page_url" if not pdf_url and not t.get("page_url") \
              else "url(s) did not return a valid PDF"
        base_row["Notes"] = f"NOT_FOUND: {why}"
        return base_row, False

    # save
    try:
        with open(fpath, "wb") as f:
            f.write(data)
        base_row["Source_URL"] = src_used or base_row["Source_URL"]
        base_row["Notes"] = "OK ({} KB)".format(len(data) // 1024)
        if src_used and src_used != pdf_url:
            base_row["Notes"] += " [scraped]"
        return base_row, True
    except OSError as e:
        base_row["Filename"] = ""
        base_row["Notes"] = f"NOT_FOUND: write error {e}"
        return base_row, False


# ----------------------------------------------------------------------------- main
def load_targets():
    if not os.path.exists(SEEDS_PATH):
        print(f"!! {SEEDS_PATH} not found. Run the seed-merge step first.")
        sys.exit(1)
    with open(SEEDS_PATH, encoding="utf-8") as f:
        targets = json.load(f)
    # group by subject preserving the required order
    by_subject = {s: [] for s in SUBJECT_ORDER}
    extras = []
    for t in targets:
        if t["subject"] in by_subject:
            by_subject[t["subject"]].append(t)
        else:
            extras.append(t)
    if extras:
        # subject variants (e.g. English_Literature_B) -> fold into base subject
        for t in extras:
            base = t["subject"].rsplit("_", 1)[0]
            (by_subject.get(base) or by_subject.setdefault(t["subject"], [])).append(t)
    return by_subject


def main():
    ensure_csv()
    by_subject = load_targets()

    boards = ["AQA", "Edexcel", "OCR", "IB"]
    tally = {s: {b: 0 for b in boards} for s in SUBJECT_ORDER}
    issues = {s: set() for s in SUBJECT_ORDER}
    total_ok = total_fail = total_skip = 0

    print("=" * 78)
    print("SYLLABUS DOWNLOADER  —  starting")
    print("=" * 78)

    for idx, subject in enumerate(SUBJECT_ORDER, 1):
        rows = []
        targets = by_subject.get(subject, [])
        for t in targets:
            row, ok = process_target(t)
            rows.append(row)
            note = row["Notes"]
            if ok and note.startswith("SKIPPED"):
                total_skip += 1
                tally[subject][t["board"]] += 1
            elif ok:
                total_ok += 1
                tally[subject][t["board"]] += 1
            else:
                total_fail += 1
        # which boards produced nothing for this subject?
        for b in boards:
            present = any(x["board"] == b for x in targets)
            if not present or tally[subject][b] == 0:
                issues[subject].add(b)
        append_rows(rows)   # flush CSV after each subject

        got = sum(tally[subject].values())
        print(f"[{idx:2}/25] {subject:24} downloaded={got:2}  "
              f"(AQA {tally[subject]['AQA']}, Edx {tally[subject]['Edexcel']}, "
              f"OCR {tally[subject]['OCR']}, IB {tally[subject]['IB']})")

        if idx % 5 == 0:
            print("-" * 78)
            print(f"  >>> PROGRESS after {idx} subjects: "
                  f"OK={total_ok}  SKIPPED={total_skip}  NOT_FOUND={total_fail}")
            print("-" * 78)

    # ---- summary table
    print("\n" + "=" * 78)
    print("SUMMARY TABLE  (count of PDFs downloaded per board)")
    print("=" * 78)
    print(f"{'Subject':24} | {'AQA':>3} | {'Edx':>3} | {'OCR':>3} | {'IB':>2} | Issues")
    print("-" * 78)
    for s in SUBJECT_ORDER:
        iss = ", ".join(sorted(issues[s])) if issues[s] else "-"
        print(f"{s:24} | {tally[s]['AQA']:>3} | {tally[s]['Edexcel']:>3} | "
              f"{tally[s]['OCR']:>3} | {tally[s]['IB']:>2} | {iss}")
    print("-" * 78)
    print(f"TOTAL downloaded (new+skipped): {total_ok + total_skip}   "
          f"(new {total_ok}, already-present {total_skip})")
    print(f"TOTAL not found / failed:       {total_fail}")
    print("=" * 78)


if __name__ == "__main__":
    main()
