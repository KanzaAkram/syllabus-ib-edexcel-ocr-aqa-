import requests, json
from bs4 import BeautifulSoup
from urllib.parse import urljoin
S = requests.Session(); S.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0"})

PAGES = {
    "Statistics": [
        "https://www.aqa.org.uk/subjects/mathematics/a-level/statistics-7382/specification",
        "https://www.aqa.org.uk/subjects/mathematics/as-and-a-level/statistics-7382/specification",
        "https://www.aqa.org.uk/subjects/statistics/a-level/statistics-7382/specification",
    ],
    "Art_and_Design": [
        "https://www.aqa.org.uk/subjects/art-and-design/a-level/art-and-design-7201-7206/specification",
        "https://www.aqa.org.uk/subjects/art-and-design/a-level/art-and-design-7201/specification",
        "https://www.aqa.org.uk/subjects/art-and-design/as-and-a-level/art-and-design-7201-7206/specification",
    ],
}
out = {}
for subj, urls in PAGES.items():
    for u in urls:
        try:
            r = S.get(u, timeout=30)
        except Exception as e:
            print(f"  {subj}: {u} ERR {e}"); continue
        if r.status_code != 200:
            print(f"  {subj}: {u} HTTP {r.status_code}"); continue
        soup = BeautifulSoup(r.text, "html.parser")
        pdfs = []
        for a in soup.find_all("a", href=True):
            full = urljoin(u, a["href"]); low = full.lower()
            if ".pdf" in low and ("spec" in low or "specification" in (a.get_text() or "").lower()):
                pdfs.append(full)
        pdfs = sorted(set(pdfs))
        print(f"  {subj}: {u} HTTP 200, spec-pdf links={len(pdfs)}")
        for p in pdfs[:5]:
            print("      ", p)
        if pdfs:
            out[subj] = {"page_url": u, "pdf_url": pdfs[0]}
            break
json.dump(out, open("aqa_holdouts_scraped.json", "w"), indent=2)
print("wrote aqa_holdouts_scraped.json:", list(out.keys()))
