"""Probe AQA GCSE filestore PDFs deterministically (same pattern as A-level)."""
import requests, json
from concurrent.futures import ThreadPoolExecutor

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
S = requests.Session(); S.headers.update({"User-Agent": UA})

# subject -> (slug candidates, code-fragment candidates)
G = {
    "Mathematics":          (["mathematics"], ["8300"]),
    "Further_Mathematics":  (["mathematics"], ["8365"]),
    "Statistics":           (["mathematics", "statistics"], ["8382"]),
    "Psychology":           (["psychology"], ["8182"]),
    "Biology":              (["biology", "science"], ["8461"]),
    "Chemistry":            (["chemistry", "science"], ["8462"]),
    "Physics":              (["physics", "science"], ["8463"]),
    "History":              (["history"], ["8145"]),
    "English_Literature":   (["english"], ["8702"]),
    "English_Language":     (["english"], ["8700"]),
    "Geography":            (["geography"], ["8035"]),
    "Sociology":            (["sociology"], ["8192"]),
    "Art_and_Design":       (["art-and-design"], ["8201", "8202", "8203", "8204", "8205", "8206", "8201-8206"]),
    "Business_Studies":     (["business-subjects", "business"], ["8132"]),
    "Economics":            (["economics"], ["8136"]),
    "Computer_Science":     (["computer-science", "computing"], ["8525"]),
    "Religious_Studies":    (["rs", "religious-studies"], ["8062", "8061"]),
    "Spanish":              (["spanish"], ["8692"]),
    "French":               (["french"], ["8652"]),
    "Physical_Education":   (["pe"], ["8582"]),
    "Music":                (["music"], ["8271"]),
    "Drama":                (["drama"], ["8261"]),
    "Design_and_Technology":(["design-and-technology", "dt"], ["8552"]),
    "Media_Studies":        (["media-studies"], ["8572"]),
    # Politics: AQA offers no GCSE Politics
}
YEARS = [str(y) for y in range(2014, 2026)]

def head(url):
    try:
        r = S.head(url, timeout=15, allow_redirects=True)
        if r.status_code == 200 and "pdf" in r.headers.get("Content-Type", "").lower():
            return (url, int(r.headers.get("Content-Length", 0)))
    except Exception:
        pass
    return None

cands, meta = [], []
for subj, (slugs, codes) in G.items():
    for sl in slugs:
        for code in codes:
            for yr in YEARS:
                cands.append(f"https://filestore.aqa.org.uk/resources/{sl}/specifications/AQA-{code}-SP-{yr}.PDF")
                meta.append((subj, sl, code, yr))

print(f"Probing {len(cands)} AQA GCSE candidates...")
with ThreadPoolExecutor(max_workers=14) as ex:
    res = list(ex.map(head, cands))

hits, entries = {}, []
for (subj, sl, code, yr), r in zip(meta, res):
    if r:
        hits.setdefault(subj, []).append((sl, code, yr, r[1]))

print("\n=== AQA GCSE RESOLVED ===")
for subj in G:
    if subj in hits:
        # keep one per (slug,code) — newest year as the version
        best = sorted(set(hits[subj]), key=lambda x: x[2])
        for sl, code, yr, size in best:
            print(f"  {subj:22} {sl:18} {code:10} {yr}  ({size//1024} KB)")
            entries.append({"subject": subj, "slug": sl, "spec_code": code, "year": yr,
                            "file": f"AQA-{code}-SP-{yr}.PDF"})
    else:
        print(f"  {subj:22} -- none --")

print(f"\nGCSE subjects with hits: {len(hits)}/{len(G)}")
with open("verified_aqa_gcse.json", "w", encoding="utf-8") as f:
    json.dump({"entries": entries}, f, indent=2)
print("Wrote verified_aqa_gcse.json")
