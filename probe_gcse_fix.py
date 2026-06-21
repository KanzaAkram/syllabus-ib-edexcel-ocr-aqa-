"""Fix AQA GCSE MFL codes (French 8658, Spanish 8698) and retry Art & Design."""
import requests, json
from concurrent.futures import ThreadPoolExecutor

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
S = requests.Session(); S.headers.update({"User-Agent": UA})

FIX = {
    "French":         (["french"], ["8658"]),
    "Spanish":        (["spanish"], ["8698"]),
    "Art_and_Design": (["art-and-design"],
                       ["8201-8206", "8202-8206", "8201", "8202", "8203", "8204", "8205", "8206", "8241-8206"]),
}
YEARS = [str(y) for y in range(2014, 2026)]

def head(url):
    try:
        r = S.head(url, timeout=15, allow_redirects=True)
        if r.status_code == 200 and "pdf" in r.headers.get("Content-Type", "").lower():
            return int(r.headers.get("Content-Length", 0))
    except Exception:
        pass
    return None

cands, meta = [], []
for subj, (slugs, codes) in FIX.items():
    for sl in slugs:
        for code in codes:
            for yr in YEARS:
                cands.append(f"https://filestore.aqa.org.uk/resources/{sl}/specifications/AQA-{code}-SP-{yr}.PDF")
                meta.append((subj, sl, code, yr))

print(f"Probing {len(cands)} fix candidates...")
with ThreadPoolExecutor(max_workers=12) as ex:
    res = list(ex.map(head, cands))

found = {}
for (subj, sl, code, yr), r in zip(meta, res):
    if r:
        print(f"  HIT {subj:16} {sl} AQA-{code}-SP-{yr}.PDF ({r//1024} KB)")
        found.setdefault(subj, []).append({"subject": subj, "slug": sl, "spec_code": code,
                                            "year": yr, "file": f"AQA-{code}-SP-{yr}.PDF"})
for subj in FIX:
    if subj not in found:
        print(f"  MISS {subj}")

# patch verified_aqa_gcse.json: drop bad Spanish(8692)/French entries, add corrected
with open("verified_aqa_gcse.json", encoding="utf-8") as f:
    data = json.load(f)
data["entries"] = [e for e in data["entries"]
                   if not (e["subject"] in ("Spanish", "French", "Art_and_Design"))]
for subj, lst in found.items():
    data["entries"].extend(lst)
with open("verified_aqa_gcse.json", "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2)
print(f"\nPatched verified_aqa_gcse.json -> {len(data['entries'])} entries")
