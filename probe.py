"""Probe to discover real AQA filestore PDF URLs and test Edexcel/OCR scrapeability."""
import requests
from concurrent.futures import ThreadPoolExecutor

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
S = requests.Session()
S.headers.update({"User-Agent": UA})

# AQA A-level: subject -> (candidate slugs, candidate codes)
AQA = {
    "Mathematics":          (["mathematics"], ["7357"]),
    "Further_Mathematics":  (["mathematics"], ["7367"]),
    "Statistics":           (["mathematics", "statistics"], ["7382"]),
    "Psychology":           (["psychology"], ["7182"]),
    "Biology":              (["biology", "science"], ["7402"]),
    "Chemistry":            (["chemistry", "science"], ["7405"]),
    "Physics":              (["physics", "science"], ["7408"]),
    "History":              (["history"], ["7042"]),
    "English_Literature":   (["english"], ["7712"]),
    "English_Language":     (["english"], ["7702"]),
    "Geography":            (["geography"], ["7037"]),
    "Sociology":            (["sociology"], ["7192"]),
    "Art_and_Design":       (["art-and-design", "art"], ["7201", "7202", "7203", "7204", "7205", "7206"]),
    "Business_Studies":     (["business-subjects", "business"], ["7132"]),
    "Economics":            (["economics"], ["7136"]),
    "Computer_Science":     (["computing", "computer-science"], ["7517"]),
    "Religious_Studies":    (["rs", "religious-studies"], ["7062"]),
    "Spanish":              (["spanish", "mfl"], ["7692"]),
    "French":               (["french", "mfl"], ["7652"]),
    "Politics":             (["politics", "government-and-politics"], ["7152"]),
    "Physical_Education":   (["pe", "physical-education"], ["7582"]),
    "Music":                (["music"], ["7272"]),
    "Drama":                (["drama"], ["7261", "7262"]),
    "Design_and_Technology":(["design-and-technology", "dt"], ["7552", "7551"]),
    "Media_Studies":        (["media-studies", "media"], ["7572"]),
}
YEARS = [str(y) for y in range(2014, 2026)]

def head(url):
    for _ in range(2):
        try:
            r = S.head(url, timeout=15, allow_redirects=True)
            if r.status_code == 200 and "pdf" in (r.headers.get("Content-Type", "").lower()):
                return (url, int(r.headers.get("Content-Length", 0)))
            return None
        except Exception:
            pass
    return None

# Build candidate AQA URLs
candidates = []
meta = []
for subj, (slugs, codes) in AQA.items():
    for slug in slugs:
        for code in codes:
            for yr in YEARS:
                url = f"https://filestore.aqa.org.uk/resources/{slug}/specifications/AQA-{code}-SP-{yr}.PDF"
                candidates.append(url)
                meta.append((subj, slug, code, yr))

print(f"Probing {len(candidates)} AQA candidate URLs...")
hits = {}
with ThreadPoolExecutor(max_workers=12) as ex:
    results = list(ex.map(head, candidates))
for (subj, slug, code, yr), res in zip(meta, results):
    if res:
        hits.setdefault(subj, []).append((slug, code, yr, res[1]))

print("\n=== AQA A-LEVEL RESOLVED URLS ===")
for subj in AQA:
    if subj in hits:
        for slug, code, yr, size in sorted(hits[subj], key=lambda x: x[2]):
            print(f"  {subj:24} slug={slug:24} {code}  {yr}  ({size//1024} KB)")
    else:
        print(f"  {subj:24} -- NONE FOUND --")

print(f"\nSubjects with >=1 AQA hit: {len(hits)}/{len(AQA)}")

# Test Edexcel + OCR scrapeability
print("\n=== EDEXCEL / OCR PAGE FETCH TEST ===")
for name, url in [
    ("Edexcel Maths A-level", "https://qualifications.pearson.com/en/qualifications/edexcel-a-levels/mathematics-2017.html"),
    ("OCR Maths A-level", "https://www.ocr.org.uk/qualifications/as-and-a-level/mathematics-a-h230-h240-from-2017/"),
]:
    try:
        r = S.get(url, timeout=25)
        body = r.text.lower()
        n_pdf = body.count(".pdf")
        print(f"  {name}: HTTP {r.status_code}, len={len(r.text)}, '.pdf' occurrences={n_pdf}")
    except Exception as e:
        print(f"  {name}: ERROR {e}")
