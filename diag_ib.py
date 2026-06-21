import requests
url = "https://ibo.org/globalassets/new-structure/university-admission/pdfs/subject-guides/biology-guide.pdf"
S = requests.Session()
S.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"})

for label, kw in [("plain GET", {}),
                  ("GET +Accept pdf", {"headers": {"Accept": "application/pdf,*/*"}}),
                  ("GET www host", {})]:
    u = url.replace("https://ibo.org", "https://www.ibo.org") if label == "GET www host" else url
    try:
        r = S.get(u, timeout=40, allow_redirects=True, **kw)
        ct = r.headers.get("Content-Type")
        print(f"{label:18} -> HTTP {r.status_code}  CT={ct}  len={len(r.content)}  final={r.url[:80]}")
        print(f"                    first bytes: {r.content[:12]}")
    except Exception as e:
        print(f"{label:18} -> ERR {e}")
