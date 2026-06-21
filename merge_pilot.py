#!/usr/bin/env python3
"""
merge_pilot.py — build targets_v2.json for the pilot (Biology + Mathematics)
by attaching discovered URLs to the registry's MISSING versions.

Matching is by spec_code (robust across the agents' loose board/variant labels);
IB records (code 'NA') match by (subject, first_year, variant-family).
"""
import json, os
import naming

ROOT = os.path.dirname(os.path.abspath(__file__))
SYLL = os.path.join(ROOT, "Syllabuses")
PILOT = {"Biology", "Mathematics"}

reg = json.load(open("enriched_registry.json", encoding="utf-8"))
disc = json.load(open("discovered_pilot.json", encoding="utf-8"))


def has_pdf(folder):
    return os.path.isdir(folder) and any(f.lower().endswith(".pdf") for f in os.listdir(folder))


def code_norm(c):
    return (c or "").upper().replace(" ", "")


# index discovered: by code, and IB by (subject_lower_prefix, first_year)
disc_by_code = {}
disc_ib = {}
for d in disc:
    c = code_norm(d.get("spec_code"))
    if c and c not in ("NA",) and not c.startswith(("D_", "MYP_", "PYP_")):
        disc_by_code[c] = d
    if d.get("board") == "IB":
        disc_ib[(d.get("first_year"))] = disc_ib.get(d.get("first_year"), []) + [d]


def find_disc(r):
    if r["board"] == "IB":
        qt = r["qual_type"].upper()
        fy = str(r["first_year"])
        want = r["subject"].lower()[:4]
        vr = (r.get("variant") or "").upper()
        # require board+qual_type+first_year agreement, subject family match
        cands = [d for d in disc if d.get("board") == "IB"
                 and (d.get("qual_type") or "").upper() == qt
                 and str(d.get("first_year")) == fy
                 and (want in (d.get("subject") or "").lower())]
        if not cands:
            return None
        # for DP maths variants, prefer variant agreement
        if vr in ("SL", "HL", "AA", "AI"):
            for d in cands:
                blob = ((d.get("variant") or "") + " " + (d.get("subject") or "")).upper()
                if vr in blob:
                    return d
        return cands[0]
    rc = code_norm(r.get("spec_code"))
    if rc in disc_by_code:
        return disc_by_code[rc]
    # fuzzy: registry code is a prefix inside a discovered range code (e.g. 4721 in 4721-4729)
    for c, d in disc_by_code.items():
        if rc and (rc in c or c in rc):
            return d
    return None


targets = []
for r in reg:
    if r["subject"] not in PILOT:
        continue
    if has_pdf(naming.new_folder(SYLL, r)):
        continue
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
        rr["_disc_code"] = d.get("spec_code")
    targets.append(rr)

json.dump(targets, open("targets_v2.json", "w", encoding="utf-8"), indent=1)
withurl = sum(1 for t in targets if t.get("pdf_url") or t.get("page_url"))
print(f"pilot targets: {len(targets)} | with URL: {withurl} | NOT_OFFERED: {sum(1 for t in targets if t.get('not_offered'))}")
for t in targets:
    u = t.get("pdf_url") or t.get("page_url") or "(none)"
    print(f"  {t['board']:8} {t['qual_type']:9} {t.get('variant',''):6} {t['subject'][:12]:12} {t['spec_code']:7} -> {u[:70]}")
