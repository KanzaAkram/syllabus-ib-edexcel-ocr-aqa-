"""Feasibility probe: how many 2005-2014 spec PDFs are recoverable from the
Wayback Machine CDX API across AQA / Edexcel / OCR domains?"""
import requests, json
S = requests.Session(); S.headers.update({"User-Agent": "Mozilla/5.0"})

CDX = "http://web.archive.org/cdx/search/cdx"

QUERIES = [
    # (label, url-pattern, matchType)
    ("AQA *.aqa.org.uk",        "aqa.org.uk",        "domain"),
    ("Edexcel edexcel.com",     "edexcel.com",       "domain"),
    ("Pearson qualifications",  "qualifications.pearson.com", "domain"),
    ("OCR ocr.org.uk",          "ocr.org.uk",        "domain"),
]

for label, pattern, mt in QUERIES:
    params = {
        "url": pattern, "matchType": mt,
        "filter": ["mimetype:application/pdf", "statuscode:200", "original:.*[Ss]pec.*"],
        "from": "2005", "to": "2014",
        "output": "json", "collapse": "urlkey", "limit": "20000",
    }
    try:
        r = S.get(CDX, params=params, timeout=90)
        data = r.json() if r.text.strip().startswith("[") else []
        rows = data[1:] if data else []
        print(f"\n### {label}: {len(rows)} archived spec PDFs (2005-2014, status200)")
        for row in rows[:12]:
            ts, orig = row[1], row[2]
            print(f"    {ts[:4]}  {orig[:95]}")
    except Exception as e:
        print(f"\n### {label}: ERROR {e}")
