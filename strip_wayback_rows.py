import csv, os
ROOT = os.path.dirname(os.path.abspath(__file__))
p = os.path.join(ROOT, "Syllabus_Master_Index.csv")
rows = list(csv.reader(open(p, encoding="utf-8")))
header, body = rows[0], rows[1:]
notes_i = header.index("Notes")
kept = [r for r in body if "Wayback" not in (r[notes_i] if len(r) > notes_i else "")]
with open(p, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f); w.writerow(header); w.writerows(kept)
print(f"CSV: {len(body)} -> {len(kept)} rows (removed {len(body)-len(kept)} Wayback rows)")
