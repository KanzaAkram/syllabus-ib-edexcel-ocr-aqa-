"""Explore the Wayback archive for genuine AQA legacy specification PDFs."""
import requests, re
from collections import Counter
S = requests.Session(); S.headers.update({"User-Agent": "Mozilla/5.0"})
CDX = "http://web.archive.org/cdx/search/cdx"

# pull ALL aqa pdf rows 2005-2014, then look for spec-like URL shapes
params = {"url": "aqa.org.uk", "matchType": "domain",
          "filter": ["mimetype:application/pdf", "statuscode:200"],
          "from": "2005", "to": "2014", "output": "json",
          "collapse": "urlkey", "limit": "60000"}
r = S.get(CDX, params=params, timeout=120)
rows = r.json()[1:] if r.text.strip().startswith("[") else []
print("total AQA pdf rows:", len(rows))

# candidate spec patterns
pat_wsp = re.compile(r"aqa-\d{3,4}.*?-w-sp", re.I)
pat_sp  = re.compile(r"-w-sp|-sp-1\d|/specifications?/|spec[\-_]?(gce|gcse|a-?level)", re.I)
pat_code = re.compile(r"aqa-(\d{4})", re.I)

wsp = [row for row in rows if pat_wsp.search(row[2])]
spish = [row for row in rows if pat_sp.search(row[2]) and "resinf" not in row[2].lower()
         and "special_pdf" not in row[2].lower()]
print("rows matching AQA-####-...-W-SP :", len(wsp))
print("rows matching broader spec-ish  :", len(spish))

print("\n--- sample W-SP urls ---")
for row in wsp[:25]:
    print(f"  {row[1][:4]}  {row[2][:100]}")

print("\n--- sample broader spec-ish urls (host breakdown) ---")
hosts = Counter(re.sub(r"https?://", "", row[2]).split("/")[0] for row in spish)
for h, n in hosts.most_common(12):
    print(f"  {n:5}  {h}")
print("\n  examples:")
for row in spish[:25]:
    print(f"  {row[1][:4]}  {row[2][:100]}")
