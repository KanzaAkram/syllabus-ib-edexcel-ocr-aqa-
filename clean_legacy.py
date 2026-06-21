"""Delete only the files the Wayback harvester created (CSV Notes contain 'Wayback'),
leaving the main downloader's current+legacy files intact."""
import csv, os
ROOT = os.path.dirname(os.path.abspath(__file__))
SYL = os.path.join(ROOT, "Syllabuses")
rows = list(csv.DictReader(open(os.path.join(ROOT, "Syllabus_Master_Index.csv"), encoding="utf-8")))
wb_names = {r["Filename"] for r in rows if "Wayback" in r["Notes"] and r["Filename"]}
print(f"Harvester files to delete (from CSV): {len(wb_names)}")
deleted = 0
for dp, _, files in os.walk(SYL):
    if os.path.basename(dp) != "Legacy":
        continue
    for fn in files:
        if fn in wb_names:
            os.remove(os.path.join(dp, fn))
            deleted += 1
print(f"Deleted {deleted} harvester PDFs.")
remaining = sum(1 for dp, _, fs in os.walk(SYL) for x in fs if x.lower().endswith(".pdf"))
print(f"PDFs remaining on disk: {remaining}")
