#!/usr/bin/env python3
"""
build_targets.py — merge discovered URLs into the enriched registry to produce
targets_v2.json for downloader_v2.

  python build_targets.py <discovered.json> [--subjects Biology Mathematics]

For every registry record (optionally filtered to subjects), attach any
pdf_url / page_url discovered for that exact version. Records with no URL are
still emitted so the downloader logs NOT_FOUND / NOT_OFFERED (never a blank).
Discovered targets not present in the registry are appended as new records.
"""
import json, os, sys

ROOT = os.path.dirname(os.path.abspath(__file__))
REG = json.load(open(os.path.join(ROOT, "enriched_registry.json"), encoding="utf-8"))


def norm(s):
    return str(s).strip().upper()


def key(r):
    return (norm(r["board"]), norm(r["qual_type"]), norm(r.get("variant", "")),
            norm(r["subject"]), norm(r.get("spec_code", "")))


def vkey(r):
    # version identity ignoring code (board,qual,variant,subject,first,last)
    return (norm(r["board"]), norm(r["qual_type"]), norm(r.get("variant", "")),
            norm(r["subject"]), str(r["first_year"]),
            str(r["last_year"]).upper())


def main():
    if len(sys.argv) < 2:
        print("usage: build_targets.py <discovered.json> [--subjects ...]")
        sys.exit(1)
    disc = json.load(open(sys.argv[1], encoding="utf-8"))
    if isinstance(disc, dict):
        disc = disc.get("targets", [])
    only = None
    if "--subjects" in sys.argv:
        only = set(sys.argv[sys.argv.index("--subjects") + 1:])

    # index discovered by exact code-key and by version-key
    by_code, by_ver = {}, {}
    for d in disc:
        if d.get("pdf_url") or d.get("page_url"):
            by_code.setdefault(key(d), d)
            by_ver.setdefault(vkey(d), d)

    targets, attached, newrecs = [], 0, 0
    seen_ver = set()
    for r in REG:
        if only and r["subject"] not in only:
            continue
        seen_ver.add(vkey(r))
        d = by_code.get(key(r)) or by_ver.get(vkey(r))
        rr = dict(r)
        if d:
            if d.get("pdf_url"):
                rr["pdf_url"] = d["pdf_url"]
            if d.get("page_url"):
                rr["page_url"] = d["page_url"]
            if str(d.get("notes", "")).startswith("NOT_OFFERED"):
                rr["not_offered"] = True
                rr["notes"] = d["notes"]
            attached += 1
        targets.append(rr)

    # discovered targets not represented in registry -> add
    for d in disc:
        if only and d.get("subject") not in only:
            continue
        if not (d.get("pdf_url") or d.get("page_url")):
            continue
        if vkey(d) in seen_ver:
            continue
        seen_ver.add(vkey(d))
        d2 = dict(d)
        d2.setdefault("alt_codes", [])
        targets.append(d2)
        newrecs += 1

    out = os.path.join(ROOT, "targets_v2.json")
    json.dump(targets, open(out, "w", encoding="utf-8"), indent=1)
    print(f"targets_v2.json: {len(targets)} records | URL-attached: {attached} | new-from-discovery: {newrecs}")
    if only:
        print("  (filtered to:", ", ".join(sorted(only)), ")")


if __name__ == "__main__":
    main()
