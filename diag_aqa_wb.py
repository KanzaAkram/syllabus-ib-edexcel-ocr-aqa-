import requests
S = requests.Session(); S.headers.update({"User-Agent": "Mozilla/5.0"})

# a few known AQA legacy A-level spec URLs (from the probe)
origs = [
    "http://www.aqa.org.uk/qual/gce/pdf/AQA-2410-W-SP-10.PDF",
    "http://www.aqa.org.uk:80/qual/gce/pdf/AQA-2410-W-SP-10.PDF",
    "http://www.aqa.org.uk/qual/gce/pdf/AQA-2180-W-SP-10.PDF",
]

def try_url(u, ts):
    wb = f"https://web.archive.org/web/{ts}id_/{u}"
    try:
        r = S.get(wb, timeout=60, allow_redirects=True)
        return f"HTTP {r.status_code} CT={r.headers.get('Content-Type')} len={len(r.content)} first={r.content[:6]} final={r.url[:70]}"
    except Exception as e:
        return f"ERR {e}"

# 1) get all snapshots for one URL via CDX (no collapse)
for orig in origs[:1]:
    cdx = "http://web.archive.org/cdx/search/cdx"
    r = S.get(cdx, params={"url": orig, "output": "json", "from": "2005", "to": "2016"}, timeout=60)
    rows = r.json()[1:] if r.text.strip().startswith("[") else []
    print(f"{orig}\n  snapshots: {len(rows)} -> timestamps: {[x[1][:8] for x in rows][:8]}")
    for x in rows[:4]:
        print("   ", x[1], "->", try_url(orig, x[1]))

# 2) test :80 vs no-:80 with a generic 'closest' timestamp
print("\n:80 vs clean host (using a 2008 timestamp guess 20080601):")
for o in origs:
    print(f"  {o[:55]:55} -> {try_url(o, '20080601000000')}")
