#!/usr/bin/env python3
"""
aqa_legacy_harvester.py — recover AQA pre-2015 specifications from the Wayback
Machine. AQA's archived spec PDFs are code-named (AQA-####-W-SP-##.PDF) with no
subject in the URL, so we DOWNLOAD each, READ its first pages, and identify the
subject + level from the document text. Best match per (subject, level) is filed
into the AQA Legacy/ folders and logged to Syllabus_Master_Index.csv.
"""
import csv, io, os, re, time
from collections import defaultdict
import requests
from pypdf import PdfReader

ROOT = os.path.dirname(os.path.abspath(__file__))
SYL = os.path.join(ROOT, "Syllabuses")
CSV_PATH = os.path.join(ROOT, "Syllabus_Master_Index.csv")
CDX = "http://web.archive.org/cdx/search/cdx"
TODAY = "2026-06-13"
S = requests.Session()
S.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"})

CSV_HEADER = ["Board","Level","Subject","Spec_Code","Year_Version","Status",
              "Filename","Source_URL","Download_Date","Notes"]
LEVEL_TAG = {"A_Level": "ALEVEL", "GCSE": "GCSE"}

# subject detection from PDF text, MOST SPECIFIC FIRST (returns folder slug)
DETECT = [
    ("Further_Mathematics", r"further mathematics"),
    ("Statistics",          r"\bstatistics\b"),
    ("Mathematics",         r"\bmathematics\b|\bmaths\b"),
    ("English_Literature",  r"english literature"),
    ("English_Language",    r"english language"),
    ("Art_and_Design",      r"art and design|art & design"),
    ("Religious_Studies",   r"religious studies"),
    ("Physical_Education",  r"physical education"),
    ("Design_and_Technology", r"design and technology|design & technology"),
    ("Media_Studies",       r"media studies"),
    ("Computer_Science",    r"\bcomputing\b|computer science"),
    ("Politics",            r"government and politics|\bpolitics\b"),
    ("Business_Studies",    r"business studies|\bbusiness\b"),
    ("Psychology",          r"\bpsychology\b"),
    ("Sociology",           r"\bsociology\b"),
    ("Biology",             r"\bbiology\b"),
    ("Chemistry",           r"\bchemistry\b"),
    ("Physics",             r"\bphysics\b"),
    ("Geography",           r"\bgeography\b"),
    ("Economics",           r"\beconomics\b"),
    ("History",             r"\bhistory\b"),
    ("Spanish",             r"\bspanish\b"),
    ("French",              r"\bfrench\b"),
    ("Music",               r"\bmusic\b"),
    ("Drama",               r"\bdrama\b|theatre studies"),
]
OURS = {d[0] for d in DETECT}

SPEC_RE = re.compile(r"aqa-(\d{3,4})-w-sp(?:-\d+)?\.pdf$", re.I)


def classify_level(url):
    u = url.lower()
    if "/gcse/" in u:
        return "GCSE"
    if "/gce/" in u:
        return "A_Level"
    return None


def _parse_cdx(text):
    """Tolerant CDX-JSON parse: salvage complete rows even if the tail is truncated."""
    import json
    text = text.strip()
    if not text.startswith("["):
        return []
    try:
        return json.loads(text)[1:]
    except json.JSONDecodeError:
        rows = []
        for line in text.splitlines():
            line = line.strip().rstrip(",")
            if line.startswith("[") and line.endswith("]"):
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
        return rows[1:] if rows else []


def cdx_aqa():
    # server-side filter to the W-SP spec files only -> ~20x smaller, avoids truncation
    params = {"url": "aqa.org.uk", "matchType": "domain",
              "filter": ["mimetype:application/pdf", "statuscode:200", "urlkey:.*-w-sp.*"],
              "from": "2005", "to": "2014", "output": "json",
              "collapse": "urlkey", "limit": "60000"}
    for attempt in range(4):
        try:
            r = S.get(CDX, params=params, timeout=120)
            rows = _parse_cdx(r.text)
            if rows:
                return rows
        except requests.RequestException:
            pass
        time.sleep(3)
    return []


def snapshots(orig):
    """All distinct status-200 capture timestamps for a URL (newest first)."""
    try:
        r = S.get(CDX, params={"url": orig, "output": "json", "from": "2005", "to": "2016",
                               "filter": "statuscode:200", "collapse": "timestamp:8"}, timeout=60)
        rows = r.json()[1:] if r.text.strip().startswith("[") else []
        return [x[1] for x in rows][::-1]      # try later captures first
    except Exception:
        return []


def wb_download(orig):
    """Try every snapshot of `orig` until one returns a complete real PDF.
    Handles Wayback IncompleteRead / 403-HTML captures by moving to the next."""
    for ts in snapshots(orig):
        url = f"https://web.archive.org/web/{ts}id_/{orig}"
        try:
            r = S.get(url, timeout=90)
            if (r.status_code == 200 and r.content[:5].startswith(b"%PDF")
                    and len(r.content) > 20000):
                return r.content, url, ts
        except requests.RequestException:
            pass                                # IncompleteRead/ChunkedEncoding -> next snapshot
        time.sleep(0.2)
    return None, orig, ""


def identify(pdf_bytes):
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        txt = ""
        for page in reader.pages[:3]:
            txt += " " + (page.extract_text() or "")
        low = re.sub(r"\s+", " ", txt.lower())[:6000]
    except Exception:
        return None, ""
    for subj, pat in DETECT:
        if re.search(pat, low):
            return subj, low[:120]
    return None, low[:120]


def append_rows(rows):
    with open(CSV_PATH, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        for r in rows:
            w.writerow([r.get(c, "") for c in CSV_HEADER])
        f.flush(); os.fsync(f.fileno())


def clean(s):
    return re.sub(r"[^A-Za-z0-9]+", "-", s or "").strip("-")[:40]


def main():
    rows = cdx_aqa()
    print("AQA pdf rows:", len(rows))
    # collect clean spec candidates, dedupe by (level, code) keeping latest snapshot
    best_by_code = {}
    for row in rows:
        ts, orig = row[1], row[2]
        m = SPEC_RE.search(orig)
        if not m:
            continue
        lvl = classify_level(orig)
        if not lvl:
            continue
        code = m.group(1)
        size = int(row[6]) if len(row) > 6 and row[6].isdigit() else 0
        key = (lvl, code)
        if key not in best_by_code or ts > best_by_code[key][0]:
            best_by_code[key] = (ts, orig, size)
    print(f"Unique AQA spec codes to inspect: {len(best_by_code)}")

    # download + identify
    found = defaultdict(list)   # (subject, level) -> list of (size, ts, code, bytes, src)
    n = 0
    for (lvl, code), (ts0, orig, size) in sorted(best_by_code.items()):
        n += 1
        time.sleep(0.2)
        data, src, ts = wb_download(orig)
        if not data:
            print(f"  [{n:3}/{len(best_by_code)}] {lvl:8} AQA-{code}  -- no usable snapshot --")
            continue
        subj, snippet = identify(data)
        tag = subj if subj in OURS else "(other/skip)"
        print(f"  [{n:3}/{len(best_by_code)}] {lvl:8} AQA-{code}  {ts[:4]}  {len(data)//1024:5}KB -> {tag}")
        if subj in OURS:
            found[(subj, lvl)].append((len(data), ts, code, data, src))

    # pick best per cell (largest = fullest spec), file + log
    logged, ok = [], 0
    for (subj, lvl), items in sorted(found.items()):
        items.sort(reverse=True)            # largest first
        size, ts, code, data, src = items[0]
        folder = os.path.join(SYL, "AQA", lvl, subj, "Legacy")
        os.makedirs(folder, exist_ok=True)
        fname = f"AQA_{LEVEL_TAG[lvl]}_{subj}_{code}_{ts[:4]}_LEGACY.pdf"
        fpath = os.path.join(folder, fname)
        with open(fpath, "wb") as f:
            f.write(data)
        ok += 1
        logged.append({"Board": "AQA", "Level": lvl, "Subject": subj, "Spec_Code": code,
                       "Year_Version": ts[:4], "Status": "LEGACY", "Filename": fname,
                       "Source_URL": src, "Download_Date": TODAY,
                       "Notes": f"OK ({size//1024} KB) [Wayback {ts[:4]} AQA legacy code {code}]"})
        print(f"  FILED  AQA {lvl:8} {subj:22} code {code} {ts[:4]} ({size//1024} KB)")
    append_rows(logged)
    print(f"\nAQA legacy harvest: filed {ok} specs across {len(found)} subject/level cells")


if __name__ == "__main__":
    main()
