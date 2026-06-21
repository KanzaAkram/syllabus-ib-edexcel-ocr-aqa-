import requests
url = "https://www.ibo.org/globalassets/new-structure/university-admission/pdfs/subject-guides/biology-guide.pdf"

H = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/pdf,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://www.ibo.org/programmes/diploma-programme/curriculum/sciences/biology/",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-User": "?1",
    "sec-ch-ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "Connection": "keep-alive",
}
S = requests.Session()
# warm up: hit the curriculum page first to get cookies
try:
    w = S.get("https://www.ibo.org/programmes/diploma-programme/curriculum/sciences/biology/",
              headers=H, timeout=40)
    print("warmup:", w.status_code, "cookies:", S.cookies.get_dict())
except Exception as e:
    print("warmup err", e)

r = S.get(url, headers=H, timeout=40, allow_redirects=True)
print("PDF GET ->", r.status_code, r.headers.get("Content-Type"), "len", len(r.content), "first", r.content[:8])
