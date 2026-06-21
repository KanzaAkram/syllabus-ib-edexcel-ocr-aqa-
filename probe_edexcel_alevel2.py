"""Recover Edexcel A-level by probing candidate subject-page slugs, then scraping
the spec PDF from each working page. Writes edexcel_alevel.json (downloader seeds)."""
import requests, json, sys
from bs4 import BeautifulSoup

sys.argv = ["t"]
import syllabus_downloader as d   # reuse scrape_pdf_link

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
S = requests.Session(); S.headers.update({"User-Agent": UA})
BASE = "https://qualifications.pearson.com/en/qualifications/edexcel-a-levels/{slug}.html"

# subject -> (spec_code, [candidate slugs in priority order])
SUBJ = {
    "Mathematics":          ("9MA0", ["mathematics-2017"]),
    "Further_Mathematics":  ("9FM0", ["further-mathematics-2017"]),
    "Biology":              ("9BI0", ["biology-b-2015", "biology-a-salters-nuffield-2015", "biology-2015"]),
    "Chemistry":            ("9CH0", ["chemistry-2015"]),
    "Physics":              ("9PH0", ["physics-2015"]),
    "Psychology":           ("9PS0", ["psychology-2015"]),
    "History":              ("9HI0", ["history-2015"]),
    "English_Literature":   ("9ET0", ["english-literature-2015"]),
    "English_Language":     ("9EN0", ["english-language-2015"]),
    "Geography":            ("9GE0", ["geography-2016"]),
    "Sociology":            ("9SO0", ["sociology-2015"]),
    "Business_Studies":     ("9BS0", ["business-2015"]),
    "Economics":            ("9EC0", ["economics-a-2015", "economics-b-2015", "economics-2015"]),
    "Computer_Science":     ("9CP0", ["computer-science-2015"]),
    "Religious_Studies":    ("9RS0", ["religious-studies-2016"]),
    "Spanish":              ("9SP0", ["spanish-2016"]),
    "French":               ("9FR0", ["french-2016"]),
    "Politics":             ("9PL0", ["politics-2017", "government-and-politics-2017"]),
    "Physical_Education":   ("9PE0", ["physical-education-2016"]),
    "Music":                ("9MU0", ["music-2016"]),
    "Drama":                ("9DR0", ["drama-and-theatre-2016", "drama-2016"]),
    "Design_and_Technology":("9DT0", ["design-technology-2017", "design-and-technology-2017",
                                       "design-technology-product-design-2017"]),
    "Media_Studies":        ("9MD0", ["media-studies-2017", "media-studies-2015"]),
    "Art_and_Design":       ("9AD0", ["art-and-design-2015"]),
    "Statistics":           ("",     ["statistics-2017"]),
}
YEARS_FALLBACK = ["2015", "2016", "2017", "2018"]

def page_ok(html):
    low = html.lower()
    if "page not found" in low or "page can’t be found" in low or "sorry, we" in low:
        return False
    return "specification" in low

result = {}
for subj, (code, slugs) in SUBJ.items():
    # expand: also try swapping year suffix
    cand = list(slugs)
    for s in slugs:
        stem = "-".join(s.split("-")[:-1]) if s.split("-")[-1].isdigit() else s
        for y in YEARS_FALLBACK:
            c = f"{stem}-{y}"
            if c not in cand:
                cand.append(c)
    found = None
    for slug in cand:
        url = BASE.format(slug=slug)
        try:
            r = S.get(url, timeout=30)
        except Exception:
            continue
        if r.status_code == 200 and page_ok(r.text):
            pdf = d.scrape_pdf_link(url, code)
            found = {"subject": subj, "spec_code": code, "page_url": url, "pdf_url": pdf or ""}
            break
    if found:
        tag = found["pdf_url"][:70] + "..." if found["pdf_url"] else "(page only, will scrape at run)"
        print(f"  OK   {subj:24} {found['page_url'].split('/')[-1]:40} pdf={tag}")
        result[subj] = found
    else:
        print(f"  MISS {subj:24} (no working page among {len(cand)} candidates)")

with open("edexcel_alevel.json", "w", encoding="utf-8") as f:
    json.dump(result, f, indent=2)
print(f"\nRecovered {len(result)}/25 Edexcel A-level -> edexcel_alevel.json")
