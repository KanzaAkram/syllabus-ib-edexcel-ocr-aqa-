"""Extract the segments array from the workflow .output JSON file."""
import json, os

OUT = r"C:\Users\kanza\AppData\Local\Temp\claude\c--Users-kanza-Desktop-syllabus-ib-edexcel-ocr-aqa-\b6e7fd14-13b0-4ede-bb1d-de57b5f75099\tasks\wnh57cke0.output"
with open(OUT, encoding="utf-8") as f:
    data = json.load(f)

print("Top-level keys:", list(data.keys()))

# find the value that is a list of dicts each having 'segment'
segments = None
for k, v in data.items():
    if isinstance(v, list) and v and isinstance(v[0], dict) and "segment" in v[0]:
        segments = v
        print(f"Segments under key: '{k}'  (count={len(v)})")
        break

if segments is None:
    raise SystemExit("Could not locate segments array")

for seg in segments:
    n = len(seg.get("entries", [])) if seg.get("entries") else 0
    print(f"  {seg['segment']:24} entries={n}")

with open("workflow_output.json", "w", encoding="utf-8") as f:
    json.dump(segments, f, indent=2)
print("Wrote workflow_output.json")
