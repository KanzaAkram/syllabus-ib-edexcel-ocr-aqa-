import csv, os
ROOT = os.path.dirname(os.path.abspath(__file__))
SYL = os.path.join(ROOT, "Syllabuses")
p = os.path.join(ROOT, "Syllabus_Master_Index.csv")
rows = list(csv.reader(open(p, encoding="utf-8")))
header, body = rows[0], rows[1:]
ni, fi = header.index("Notes"), header.index("Filename")
victims = {r[fi] for r in body if "AQA legacy code" in (r[ni] if len(r) > ni else "") and r[fi]}
deleted = 0
for dp, _, files in os.walk(SYL):
    if os.path.basename(dp) != "Legacy":
        continue
    for fn in files:
        if fn in victims:
            os.remove(os.path.join(dp, fn)); deleted += 1
kept = [r for r in body if "AQA legacy code" not in (r[ni] if len(r) > ni else "")]
with open(p, "w", newline="", encoding="utf-8") as f:
    csv.writer(f).writerow(header); csv.writer(f).writerows(kept)
print(f"Deleted {deleted} AQA-legacy files; CSV {len(body)}->{len(kept)} rows")
