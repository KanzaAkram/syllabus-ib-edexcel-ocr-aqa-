"""Recover Edexcel A-level: fetch the Pearson A-levels listing page(s) and
extract per-subject specification page URLs, then map to our 25 subjects."""
import requests, json, re
from bs4 import BeautifulSoup

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
S = requests.Session(); S.headers.update({"User-Agent": UA})

LISTINGS = [
    "https://qualifications.pearson.com/en/qualifications/edexcel-a-levels.html",
    "https://qualifications.pearson.com/en/qualifications/edexcel-a-levels.coursematerials.html",
]
links = {}
for url in LISTINGS:
    try:
        r = S.get(url, timeout=40)
        soup = BeautifulSoup(r.text, "html.parser")
        for a in soup.find_all("a", href=True):
            h = a["href"]
            if "/edexcel-a-levels/" in h and h.lower().endswith(".html"):
                full = requests.compat.urljoin(url, h)
                links[full] = (a.get_text() or "").strip()
        print(f"{url} -> HTTP {r.status_code}, found {len(links)} cumulative A-level links")
    except Exception as e:
        print(f"{url} ERROR {e}")

# map to our subjects by keyword
SUBJECT_KEYS = {
    "Mathematics": ["mathematics-2017", "/mathematics"], "Further_Mathematics": ["further-mathematics"],
    "Statistics": ["statistics"], "Psychology": ["psychology"], "Biology": ["biology"],
    "Chemistry": ["chemistry"], "Physics": ["physics"], "History": ["history"],
    "English_Literature": ["english-literature"], "English_Language": ["english-language"],
    "Geography": ["geography"], "Sociology": ["sociology"], "Art_and_Design": ["art-and-design"],
    "Business_Studies": ["business"], "Economics": ["economics"], "Computer_Science": ["computer-science"],
    "Religious_Studies": ["religious-studies"], "Spanish": ["spanish"], "French": ["french"],
    "Politics": ["politics", "government-and-politics"], "Physical_Education": ["physical-education"],
    "Music": ["music"], "Drama": ["drama"], "Design_and_Technology": ["design-and-technology", "design-technology"],
    "Media_Studies": ["media-studies"],
}
print("\n=== ALL A-LEVEL LINKS ===")
for u in sorted(links):
    print(" ", u.split("/edexcel-a-levels/")[-1])

result = {}
for subj, keys in SUBJECT_KEYS.items():
    for u in sorted(links):
        tail = u.split("/edexcel-a-levels/")[-1].lower()
        # english-language must not match english-literature etc.
        if any(k in tail for k in keys):
            if subj == "English_Language" and "literature" in tail: continue
            if subj == "Mathematics" and ("further" in tail or "statistics" in tail or "pure" in tail or "mechanics" in tail or "decision" in tail): continue
            result[subj] = u
            break

print("\n=== MAPPED ===")
for subj in SUBJECT_KEYS:
    print(f"  {subj:24} {result.get(subj, '-- NONE --')}")
with open("edexcel_alevel_pages.json", "w", encoding="utf-8") as f:
    json.dump(result, f, indent=2)
print(f"\nMapped {len(result)}/25 -> edexcel_alevel_pages.json")
