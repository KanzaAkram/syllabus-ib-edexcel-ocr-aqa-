import csv, os
from collections import Counter
rows = list(csv.DictReader(open("Syllabus_Master_Index.csv", encoding="utf-8")))
ok = [r for r in rows if r["Notes"].startswith("OK") or r["Notes"].startswith("SKIPPED")]
yc = Counter(r["Year_Version"] for r in ok)
sc = Counter(r["Status"] for r in ok)
print("Downloaded files by Year_Version (the spec's publication/first-teaching year):")
for y in sorted(yc, key=lambda x: (x == "", x)):
    print(f"  {y or '(blank)':10} {yc[y]}")
print("\nBy Status:", dict(sc))
print("Earliest year:", min(y for y in yc if y), " Latest:", max(y for y in yc if y))
print("Total OK files:", len(ok))
pre2015 = sum(n for y, n in yc.items() if y and y.isdigit() and int(y) < 2015)
print("Files dated before 2015 (true 'legacy' era 2005-2014):", pre2015)
