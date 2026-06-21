#!/usr/bin/env python3
"""
lib_fetch.py — robust PDF fetching + spec-page scraping + AQA filestore probing.
Shared by the v2 downloader and the discovery helpers.
"""
import re, time
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

try:
    from curl_cffi import requests as creq      # browser-TLS client (defeats Cloudflare)
    HAVE_CFFI = True
except Exception:
    HAVE_CFFI = False

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": UA, "Accept": "*/*"})

import os as _os
RETRIES = int(_os.environ.get("SYL_RETRIES", "3"))
RETRY_DELAY = int(_os.environ.get("SYL_RETRY_DELAY", "2"))
MIN_PDF_BYTES = 10_000


def valid_pdf(content, ctype=""):
    if not content or len(content) < MIN_PDF_BYTES:
        return False
    if content[:5].startswith(b"%PDF"):
        return True
    return "pdf" in (ctype or "").lower()


def head_ok(url, timeout=25):
    """True if a HEAD/GET reveals a real PDF at url (no full download for HEAD)."""
    try:
        r = SESSION.head(url, timeout=timeout, allow_redirects=True)
        if r.status_code == 200 and "pdf" in r.headers.get("Content-Type", "").lower():
            return True
        if r.status_code in (403, 405, 429):   # some servers block HEAD -> try ranged GET
            g = SESSION.get(url, timeout=timeout, allow_redirects=True,
                            headers={"Range": "bytes=0-1023"})
            return g.status_code in (200, 206) and (
                valid_pdf(g.content, g.headers.get("Content-Type")) or
                g.content[:5].startswith(b"%PDF"))
    except requests.RequestException:
        return False
    return False


def fetch_pdf(url, timeout=45):
    """Return PDF bytes or None. requests first, curl_cffi fallback on block."""
    blocked = False
    for attempt in range(1, RETRIES + 1):
        try:
            r = SESSION.get(url, timeout=timeout, allow_redirects=True)
            if r.status_code == 200 and valid_pdf(r.content, r.headers.get("Content-Type")):
                return r.content
            if r.status_code in (403, 429):
                blocked = True
                break
            if r.status_code in (404, 410):
                return None
        except requests.RequestException:
            pass
        if attempt < RETRIES:
            time.sleep(RETRY_DELAY)
    if (blocked or True) and HAVE_CFFI:
        for attempt in range(1, RETRIES + 1):
            try:
                r = creq.get(url, impersonate="chrome", timeout=timeout + 10, allow_redirects=True)
                if r.status_code == 200 and valid_pdf(r.content, r.headers.get("Content-Type")):
                    return r.content
                if r.status_code in (404, 410):
                    return None
            except Exception:
                pass
            if attempt < RETRIES:
                time.sleep(RETRY_DELAY)
    return None


BAD_HINTS = ("sample-assessment", "/sam", "mark-scheme", "question-paper",
             "past-paper", "insert", "examiner", "report-on-the-exam",
             "teacher", "specimen", "/sams")


def scrape_pdf_links(page_url, spec_code="", want_all=False, timeout=40):
    """Return best spec-PDF link from a page, or a ranked list if want_all."""
    html = None
    try:
        r = SESSION.get(page_url, timeout=timeout, allow_redirects=True)
        if r.status_code == 200:
            html = r.text
    except requests.RequestException:
        pass
    if html is None and HAVE_CFFI:
        try:
            r = creq.get(page_url, impersonate="chrome", timeout=timeout, allow_redirects=True)
            if r.status_code == 200:
                html = r.text
        except Exception:
            pass
    if not html:
        return [] if want_all else None

    soup = BeautifulSoup(html, "html.parser")
    code_l = (spec_code or "").lower()
    cands = []
    for a in soup.find_all("a", href=True):
        full = urljoin(page_url, a["href"].strip())
        low = full.lower()
        if ".pdf" not in low:
            continue
        text = (a.get_text() or "").lower()
        score = 0
        if "specification" in low or "specification" in text:
            score += 5
        if "-sp-" in low or "/sp-" in low:
            score += 3
        if code_l and code_l in low:
            score += 4
        for dom in ("filestore.aqa.org.uk", "/content/dam/pdf", "ocr.org.uk/images"):
            if dom in low:
                score += 2
        for bad in BAD_HINTS:
            if bad in low:
                score -= 5
        cands.append((score, full))
    if not cands:
        return [] if want_all else None
    cands.sort(key=lambda x: x[0], reverse=True)
    if want_all:
        seen, out = set(), []
        for sc, u in cands:
            if u not in seen:
                seen.add(u); out.append((sc, u))
        return out
    return cands[0][1]


# --- AQA filestore deterministic probing -----------------------------------
AQA_SLUG = {
    "Biology": "biology", "Chemistry": "chemistry", "Physics": "physics",
    "Mathematics": "mathematics", "Further_Mathematics": "mathematics",
    "Statistics": "mathematics", "English_Language": "english",
    "English_Literature": "english", "History": "history", "Geography": "geography",
    "Psychology": "psychology", "Sociology": "sociology", "Economics": "economics",
    "Business_Studies": "business", "Computer_Science": "computing",
    "Religious_Studies": "rs", "Spanish": "spanish", "French": "french",
    "Politics": "politics", "Physical_Education": "pe", "Music": "music",
    "Drama": "drama", "Design_and_Technology": "design-and-technology",
    "Media_Studies": "media-studies", "Art_and_Design": "art-and-design",
}


def aqa_filestore_probe(subject, code, year_lo=2010, year_hi=2024):
    """HEAD-probe AQA filestore for AQA-<CODE>-SP-<YEAR>.PDF across plausible years."""
    slug = AQA_SLUG.get(subject)
    if not slug or not code:
        return None
    base = "https://filestore.aqa.org.uk/resources/{}/specifications/AQA-{}-SP-{}.PDF"
    for y in range(year_hi, year_lo - 1, -1):
        url = base.format(slug, code, y)
        if head_ok(url):
            return url
        time.sleep(0.25)
    return None
