#!/usr/bin/env python3
"""
build_seeds.py  —  merge every discovered/verified source into one seeds.json
consumed by syllabus_downloader.py

Sources (in priority order; deterministic data wins over workflow guesses):
  verified_aqa_alevel.json     AQA A-level filestore URLs (HEAD-verified)
  verified_aqa_gcse.json       AQA GCSE filestore URLs (HEAD-verified, CURRENT/LEGACY)
  aqa_holdouts_scraped.json    AQA A-level Art (scraped from AQA page -> Sanity CDN)
  edexcel_alevel.json          Edexcel A-level pages + scraped spec PDFs
  edx_fm.json                  Edexcel A-level Further Maths spec PDF
  workflow_output.json         segments: edexcel-gcse, ocr-alevel, ocr-gcse, ib-availability,
                               + aqa-gcse (only for subjects not already verified)
Output: seeds.json
"""
import json, os, re
from collections import Counter

ROOT = os.path.dirname(os.path.abspath(__file__))
AQA_BASE = "https://filestore.aqa.org.uk/resources/{slug}/specifications/{file}"

SEGMENT_MAP = {
    "aqa-gcse":        ("AQA", "GCSE"),
    "edexcel-alevel":  ("Edexcel", "A_Level"),
    "edexcel-gcse":    ("Edexcel", "GCSE"),
    "ocr-alevel":      ("OCR", "A_Level"),
    "ocr-gcse":        ("OCR", "GCSE"),
    "ib-availability": ("IB", "Diploma_Programme"),
}

targets = []
verified_keys = set()   # (board, level, subject) where we trust local data over the workflow


def load(name):
    p = os.path.join(ROOT, name)
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else None


# --- 1) verified AQA A-level -------------------------------------------------
aqa = load("verified_aqa_alevel.json")["entries"]
biz_years = sorted(e["year"] for e in aqa if e["subject"] == "Business_Studies")
for e in aqa:
    subject = e["subject"]
    status = "CURRENT"
    if subject == "Business_Studies" and len(biz_years) > 1 and e["year"] != biz_years[-1]:
        status = "LEGACY"
    if subject == "English_Literature_B":
        subject = "English_Literature"
    targets.append({"board": "AQA", "level": "A_Level", "subject": subject,
                    "spec_code": e["spec_code"], "year": e["year"], "status": status,
                    "pdf_url": AQA_BASE.format(slug=e["slug"], file=e["file"]),
                    "page_url": "", "notes": "verified by HEAD probe"})
    verified_keys.add(("AQA", "A_Level", subject))

# --- 1b) verified AQA GCSE (with CURRENT/LEGACY) -----------------------------
gcse = load("verified_aqa_gcse.json")
if gcse:
    for e in gcse["entries"]:
        targets.append({"board": "AQA", "level": "GCSE", "subject": e["subject"],
                        "spec_code": e["spec_code"], "year": e["year"],
                        "status": e.get("status", "CURRENT"),
                        "pdf_url": AQA_BASE.format(slug=e["slug"], file=e["file"]),
                        "page_url": "", "notes": "verified by HEAD probe"})
        verified_keys.add(("AQA", "GCSE", e["subject"]))

# --- 1c) AQA A-level holdouts scraped (Art via CDN) --------------------------
hold = load("aqa_holdouts_scraped.json") or {}
AQA_AL_META = {"Art_and_Design": ("7201", "2015"), "Statistics": ("7382", "2017")}
for subj, info in hold.items():
    code, yr = AQA_AL_META.get(subj, ("", ""))
    targets.append({"board": "AQA", "level": "A_Level", "subject": subj,
                    "spec_code": code, "year": yr, "status": "CURRENT",
                    "pdf_url": info.get("pdf_url", ""), "page_url": info.get("page_url", ""),
                    "notes": "scraped from AQA spec page (CDN)"})
    verified_keys.add(("AQA", "A_Level", subj))
# AQA A-level Statistics was discontinued (last exams 2019) -> not currently available
if ("AQA", "A_Level", "Statistics") not in verified_keys:
    targets.append({"board": "AQA", "level": "A_Level", "subject": "Statistics",
                    "spec_code": "7382", "year": "", "status": "CURRENT",
                    "pdf_url": "", "page_url": "", "notes": "NOT_FOUND: AQA A-level Statistics (7382) discontinued, last exams 2019; spec PDF not on filestore"})
    verified_keys.add(("AQA", "A_Level", "Statistics"))

# --- 1d) Edexcel A-level (recovered: page probe + scrape) --------------------
edx = load("edexcel_alevel.json") or {}
fm = load("edx_fm.json")
if fm:
    edx.update(fm)
EDX_CODE_FALLBACK = {"Statistics": "9ST0"}
for subj, info in edx.items():
    page = info.get("page_url", "")
    m = re.search(r"-(\d{4})\.html", page)
    yr = m.group(1) if m else ""
    code = info.get("spec_code") or EDX_CODE_FALLBACK.get(subj, "")
    targets.append({"board": "Edexcel", "level": "A_Level", "subject": subj,
                    "spec_code": code, "year": yr, "status": "CURRENT",
                    "pdf_url": info.get("pdf_url", ""), "page_url": page,
                    "notes": "recovered: Edexcel page probe + scrape"})
    verified_keys.add(("Edexcel", "A_Level", subj))
for subj in ["Sociology", "Computer_Science", "Media_Studies"]:
    if ("Edexcel", "A_Level", subj) not in verified_keys:
        targets.append({"board": "Edexcel", "level": "A_Level", "subject": subj,
                        "spec_code": "N/A", "year": "", "status": "CURRENT",
                        "pdf_url": "", "page_url": "",
                        "notes": "NOT_FOUND: not offered by Edexcel at A-level"})
        verified_keys.add(("Edexcel", "A_Level", subj))

# --- 2) workflow discovery output -------------------------------------------
wf = load("workflow_output.json") or []
for seg in wf:
    if not seg:
        continue
    board, level = SEGMENT_MAP.get(seg.get("segment", ""), (None, None))
    if not board:
        continue
    for e in seg.get("entries", []):
        subj = (e.get("subject") or "").strip()
        if not subj:
            continue
        if board == "AQA" and (board, level, subj) in verified_keys:
            continue          # local verified AQA data wins
        targets.append({"board": board, "level": level, "subject": subj,
                        "spec_code": e.get("spec_code", ""), "year": e.get("year", ""),
                        "status": (e.get("status") or "CURRENT").upper(),
                        "pdf_url": e.get("pdf_url", "") or "",
                        "page_url": e.get("page_url", "") or "",
                        "notes": ((e.get("notes", "") or "") + f" (conf:{e.get('confidence','?')})").strip()})

# de-dupe
seen, deduped = set(), []
for t in targets:
    key = (t["board"], t["level"], t["subject"], t["spec_code"], t["year"], t["status"], t["pdf_url"])
    if key in seen:
        continue
    seen.add(key)
    deduped.append(t)

json.dump(deduped, open(os.path.join(ROOT, "seeds.json"), "w", encoding="utf-8"), indent=2)

c = Counter((t["board"], t["level"]) for t in deduped)
print(f"Wrote seeds.json with {len(deduped)} targets:")
for (b, l), n in sorted(c.items()):
    print(f"  {b:8} {l:18} {n}")
with_pdf = sum(1 for t in deduped if t["pdf_url"])
with_page = sum(1 for t in deduped if not t["pdf_url"] and t["page_url"])
none = sum(1 for t in deduped if not t["pdf_url"] and not t["page_url"])
print(f"  direct pdf_url: {with_pdf}   page_url only (scrape): {with_page}   no url (not offered): {none}")
