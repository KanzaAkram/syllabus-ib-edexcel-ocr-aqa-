#!/usr/bin/env python3
"""
merge_all.py <discovered.json> — attach discovered URLs to ALL missing registry
versions (missing_all.json) and write targets_v2.json for the full download.

Matching: by spec_code (exact, then fuzzy substring) for non-IB; for IB
(code 'NA') by board+qual_type+first_year+subject-family+variant.
"""
import json, os, sys

ROOT = os.path.dirname(os.path.abspath(__file__))
missing = json.load(open(os.path.join(ROOT, "missing_all.json"), encoding="utf-8"))
disc = json.load(open(sys.argv[1] if len(sys.argv) > 1 else "discovered_scale.json", encoding="utf-8"))
if isinstance(disc, dict):
    disc = disc.get("targets", [])


def cn(c):
    return (c or "").upper().replace(" ", "")


disc_by_code = {}
for d in disc:
    c = cn(d.get("spec_code"))
    if c and c != "NA" and not c.startswith(("D_", "MYP_", "PYP_")) and (d.get("pdf_url") or d.get("page_url") or str(d.get("notes", "")).startswith("NOT_OFFERED")):
        disc_by_code.setdefault(c, d)


def find_disc(r):
    if r["board"] == "IB":
        qt = r["qual_type"].upper()
        fy = str(r["first_year"])
        want = r["subject"].lower()[:4]
        vr = (r.get("variant") or "").upper()
        cands = [d for d in disc if d.get("board") == "IB"
                 and (d.get("qual_type") or "").upper() == qt
                 and str(d.get("first_year")) == fy
                 and want in (d.get("subject") or "").lower()]
        if not cands:
            return None
        if vr in ("SL", "HL", "AA", "AI"):
            for d in cands:
                if vr in ((d.get("variant") or "") + " " + (d.get("subject") or "")).upper():
                    return d
        return cands[0]
    rc = cn(r.get("spec_code"))
    if rc in disc_by_code:
        return disc_by_code[rc]
    for c, d in disc_by_code.items():
        if rc and len(rc) >= 3 and (rc in c or c in rc):
            return d
    return None


targets, withurl, noff = [], 0, 0
for r in missing:
    rr = dict(r)
    d = find_disc(r)
    if d:
        if d.get("pdf_url"):
            rr["pdf_url"] = d["pdf_url"]
        if d.get("page_url"):
            rr["page_url"] = d["page_url"]
        if str(d.get("notes", "")).startswith("NOT_OFFERED"):
            rr["not_offered"] = True
            rr["notes"] = d["notes"]
            noff += 1
        if rr.get("pdf_url") or rr.get("page_url"):
            withurl += 1
    targets.append(rr)

json.dump(targets, open(os.path.join(ROOT, "targets_v2.json"), "w", encoding="utf-8"), indent=1)
print(f"targets_v2.json: {len(targets)} missing records | with URL: {withurl} | NOT_OFFERED: {noff}")
