import requests, json
from concurrent.futures import ThreadPoolExecutor
S = requests.Session(); S.headers.update({"User-Agent": "Mozilla/5.0"})

YEARS = [str(y) for y in range(2014, 2026)]
tests = []  # (subject, slug, filename)
# Art & Design A-level: try non-numeric + numeric names
for y in YEARS:
    for fn in [f"AQA-ART-A-SP-{y}.PDF", f"AQA-ART-ALEVEL-SP-{y}.PDF", f"AQA-ART-AS-A-SP-{y}.PDF",
               f"AQA-7201-SP-{y}.PDF", f"AQA-7201-7206-SP-{y}.PDF", f"AQA-7202-7206-SP-{y}.PDF"]:
        tests.append(("Art_and_Design", "art-and-design", fn))
# Statistics A-level
for y in YEARS:
    for slug in ["mathematics", "statistics"]:
        for fn in [f"AQA-7382-SP-{y}.PDF", f"AQA-7381-7382-SP-{y}.PDF", f"AQA-STAT-A-SP-{y}.PDF"]:
            tests.append(("Statistics", slug, fn))

def head(t):
    subj, slug, fn = t
    url = f"https://filestore.aqa.org.uk/resources/{slug}/specifications/{fn}"
    try:
        r = S.head(url, timeout=15, allow_redirects=True)
        if r.status_code == 200 and "pdf" in r.headers.get("Content-Type", "").lower():
            return (subj, slug, fn, int(r.headers.get("Content-Length", 0)), url)
    except Exception:
        pass
    return None

print(f"Probing {len(tests)} holdout candidates...")
with ThreadPoolExecutor(max_workers=12) as ex:
    res = [x for x in ex.map(head, tests) if x]
found = {}
for subj, slug, fn, size, url in res:
    print(f"  HIT {subj:16} {slug} {fn} ({size//1024} KB)")
    found.setdefault(subj, (slug, fn, url))
for s in ("Art_and_Design", "Statistics"):
    if s not in found:
        print(f"  MISS {s}")
json.dump({s: {"slug": v[0], "file": v[1], "url": v[2]} for s, v in found.items()},
          open("aqa_alevel_holdouts.json", "w"), indent=2)
