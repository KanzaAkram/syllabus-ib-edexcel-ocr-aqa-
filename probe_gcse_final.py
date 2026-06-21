"""Definitive AQA GCSE probe: collect ALL year-versions per subject, label
newest=CURRENT / older=LEGACY. Handles MFL dual codes + non-numeric Art filename."""
import requests, json
from concurrent.futures import ThreadPoolExecutor
S = requests.Session(); S.headers.update({"User-Agent": "Mozilla/5.0"})

# subject -> (slug, [numeric codes]); Art handled specially below
G = {
    "Mathematics":          ("mathematics", ["8300"]),
    "Further_Mathematics":  ("mathematics", ["8365"]),
    "Statistics":           ("mathematics", ["8382"]),
    "Psychology":           ("psychology",  ["8182"]),
    "Biology":              ("biology",     ["8461"]),
    "Chemistry":            ("chemistry",   ["8462"]),
    "Physics":              ("physics",     ["8463"]),
    "History":              ("history",     ["8145"]),
    "English_Literature":   ("english",     ["8702"]),
    "English_Language":     ("english",     ["8700"]),
    "Geography":            ("geography",   ["8035"]),
    "Sociology":            ("sociology",   ["8192"]),
    "Business_Studies":     ("business",    ["8132"]),
    "Economics":            ("economics",   ["8136"]),
    "Computer_Science":     ("computing",   ["8525", "8520"]),
    "Religious_Studies":    ("rs",          ["8062", "8061"]),
    "Spanish":              ("spanish",     ["8692", "8698"]),
    "French":               ("french",      ["8652", "8658"]),
    "Physical_Education":   ("pe",          ["8582"]),
    "Music":                ("music",       ["8271"]),
    "Drama":                ("drama",       ["8261"]),
    "Design_and_Technology":("design-and-technology", ["8552"]),
    "Media_Studies":        ("media-studies", ["8572"]),
}
YEARS = [str(y) for y in range(2014, 2026)]

def head(args):
    subj, slug, code, yr, fname = args
    for ext in (".PDF", ".pdf"):
        url = f"https://filestore.aqa.org.uk/resources/{slug}/specifications/{fname}{ext}"
        try:
            r = S.head(url, timeout=15, allow_redirects=True)
            if r.status_code == 200 and "pdf" in r.headers.get("Content-Type", "").lower():
                return (subj, slug, code, yr, int(r.headers.get("Content-Length", 0)),
                        f"{fname}{ext}")
        except Exception:
            pass
    return None

jobs = []
for subj, (slug, codes) in G.items():
    for code in codes:
        for yr in YEARS:
            jobs.append((subj, slug, code, yr, f"AQA-{code}-SP-{yr}"))
# Art special non-numeric filename
for yr in YEARS:
    jobs.append(("Art_and_Design", "art-and-design", "8201-8206", yr, f"AQA-ART-GCSE-SP-{yr}"))

print(f"Probing {len(jobs)} GCSE jobs...")
with ThreadPoolExecutor(max_workers=16) as ex:
    hits = [h for h in ex.map(head, jobs) if h]

by_subj = {}
for subj, slug, code, yr, size, fname in hits:
    by_subj.setdefault(subj, []).append({"subject": subj, "slug": slug, "spec_code": code,
                                          "year": yr, "file": fname, "size_kb": size // 1024})

entries = []
print("\n=== AQA GCSE (CURRENT/LEGACY) ===")
for subj in list(G) + ["Art_and_Design"]:
    if subj not in by_subj:
        continue
    rows = by_subj[subj]
    maxyear = max(r["year"] for r in rows)
    for r in sorted(rows, key=lambda x: x["year"]):
        r["status"] = "CURRENT" if r["year"] == maxyear else "LEGACY"
        entries.append(r)
        print(f"  {subj:22} {r['spec_code']:10} {r['year']}  {r['status']:7} {r['file']:26} ({r['size_kb']} KB)")

# de-dupe (subject, file)
seen, final = set(), []
for e in entries:
    k = (e["subject"], e["file"])
    if k in seen: continue
    seen.add(k); final.append(e)

json.dump({"entries": final}, open("verified_aqa_gcse.json", "w"), indent=2)
print(f"\nWrote verified_aqa_gcse.json with {len(final)} entries across {len(by_subj)} subjects")
