"""Probe AQA combined AS+A-level code pattern for the subjects that missed."""
import requests
from concurrent.futures import ThreadPoolExecutor

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
S = requests.Session(); S.headers.update({"User-Agent": UA})

# subject -> (slug, [code-fragments to try in filename])
TESTS = {
    "Psychology":          ("psychology", ["7181-7182", "7182"]),
    "Biology":             ("biology",    ["7401-7402", "7402"]),
    "Chemistry":           ("chemistry",  ["7404-7405", "7405"]),
    "Physics":             ("physics",    ["7407-7408", "7408"]),
    "History":             ("history",    ["7041-7042", "7042"]),
    "English_Literature":  ("english",    ["7711-7712", "7712", "7716-7717"]),
    "English_Language":    ("english",    ["7701-7702", "7702"]),
    "Sociology":           ("sociology",  ["7191-7192", "7192"]),
    "Business_Studies":    ("business-subjects", ["7131-7132", "7132"]),
    "Economics":           ("economics",  ["7135-7136", "7136"]),
    "Computer_Science":    ("computer-science", ["7516-7517", "7517"]),
    "Statistics":          ("mathematics", ["7381-7382", "7382"]),
    "Art_and_Design":      ("art-and-design", ["7201-7206", "7201", "7202-7206", "7241-7206"]),
    "Drama":               ("drama",      ["7261", "7261-7262"]),
}
# also retry computer-science under 'computing'
ALT_SLUGS = {"Computer_Science": ["computing", "computer-science"],
             "Business_Studies": ["business-subjects", "business"],
             "Economics": ["economics"]}
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
for subj, (slug, frags) in TESTS.items():
    slugs = ALT_SLUGS.get(subj, [slug])
    for sl in slugs:
        for frag in frags:
            for yr in YEARS:
                cands.append(f"https://filestore.aqa.org.uk/resources/{sl}/specifications/AQA-{frag}-SP-{yr}.PDF")
                meta.append((subj, sl, frag, yr))

print(f"Probing {len(cands)} combined-code candidates...")
with ThreadPoolExecutor(max_workers=12) as ex:
    res = list(ex.map(head, cands))

hits = {}
for (subj, sl, frag, yr), r in zip(meta, res):
    if r:
        hits.setdefault(subj, []).append((sl, frag, yr, r[1], r[0]))

print("\n=== COMBINED-CODE RESOLVED ===")
for subj in TESTS:
    if subj in hits:
        for sl, frag, yr, size, url in sorted(set(hits[subj]), key=lambda x: x[2]):
            print(f"  {subj:22} {sl:18} AQA-{frag}-SP-{yr}  ({size//1024} KB)")
    else:
        print(f"  {subj:22} -- still none --")
