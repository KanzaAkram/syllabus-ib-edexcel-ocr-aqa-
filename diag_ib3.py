from curl_cffi import requests as creq
urls = [
    "https://ibo.org/globalassets/new-structure/university-admission/pdfs/subject-guides/biology-guide.pdf",
    "https://www.ibo.org/globalassets/new-structure/university-admission/pdfs/subject-guides/history-guide.pdf",
]
for imp in ["chrome", "chrome124", "chrome120"]:
    try:
        r = creq.get(urls[0], impersonate=imp, timeout=40)
        print(f"impersonate={imp:10} -> {r.status_code}  CT={r.headers.get('Content-Type')}  len={len(r.content)}  first={r.content[:8]}")
        if r.status_code == 200 and r.content[:5] == b'%PDF-':
            print("   >>> SUCCESS with", imp)
            break
    except Exception as e:
        print(f"impersonate={imp:10} -> ERR {e}")
