import requests
S = requests.Session(); S.headers.update({"User-Agent": "Mozilla/5.0"})
base = "https://qualifications.pearson.com/en/qualifications/edexcel-a-levels/{}.html"
slugs = ["further-mathematics-2017", "further-mathematics-2018",
         "sociology-2015", "sociology-2017",
         "computer-science-2015", "computer-science-2017",
         "media-studies-2017", "media-studies-2015"]
for slug in slugs:
    try:
        r = S.get(base.format(slug), timeout=30)
        low = r.text.lower()
        nf = ("page not found" in low) or ("page can" in low) or ("sorry" in low)
        ok = (r.status_code == 200) and ("specification" in low) and not nf
        print(f"{slug:30} HTTP {r.status_code}  spec={'specification' in low}  notfound={nf}  -> {'OFFERED' if ok else 'no'}")
    except Exception as e:
        print(slug, "ERR", e)
