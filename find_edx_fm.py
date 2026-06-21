import requests, json
from bs4 import BeautifulSoup
from urllib.parse import urljoin
S = requests.Session(); S.headers.update({"User-Agent": "Mozilla/5.0"})

pages = [
    "https://qualifications.pearson.com/en/qualifications/edexcel-a-levels/mathematics-2017.html",
    "https://qualifications.pearson.com/en/qualifications/edexcel-a-levels/mathematics-2017.coursematerials.html",
]
fm = []
for p in pages:
    try:
        r = S.get(p, timeout=30)
    except Exception as e:
        print(p, "ERR", e); continue
    soup = BeautifulSoup(r.text, "html.parser")
    for a in soup.find_all("a", href=True):
        full = urljoin(p, a["href"])
        low = full.lower()
        if ".pdf" in low and "further" in low and "specification" in low:
            fm.append(full)
    print(f"{p} -> {r.status_code}")
fm = sorted(set(fm))
for u in fm:
    print("  FM-SPEC:", u)
if fm:
    # verify download
    import sys; sys.argv=["t"]; import syllabus_downloader as d
    b = d.fetch_pdf(fm[0])
    print("  download:", "OK %d KB" % (len(b)//1024) if b else "FAILED")
    json.dump({"Further_Mathematics": {"subject":"Further_Mathematics","spec_code":"9FM0",
              "page_url": pages[0], "pdf_url": fm[0]}}, open("edx_fm.json","w"), indent=2)
    print("  wrote edx_fm.json")
else:
    print("  no Further Maths spec PDF found on Maths page")
