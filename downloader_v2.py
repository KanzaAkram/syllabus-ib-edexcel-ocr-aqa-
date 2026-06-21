#!/usr/bin/env python3
"""
downloader_v2.py — expansion downloader for the NEW year-range convention.

Input  : targets_v2.json  (list of registry records, each optionally carrying
                            pdf_url / page_url / alt_urls discovered upstream)
Output : files placed in the year-based tree + rows appended to
         Syllabus_Master_Index.csv (12-col schema), checkpointed per subject.

Key behaviours (per brief):
  * version-level skip: if a file already satisfies (board,qual,variant,subject,
    first,last) it is logged SKIPPED_EXISTS and not re-fetched (resume-safe);
    this also dedupes prompt-code vs discovered-code variants of one version.
  * never overwrites; never crashes (logs NOT_FOUND and continues)
  * AQA targets with no URL are auto-probed on the filestore
  * 2-5 s random delay between network requests; 3 retries per URL (in lib_fetch)
  * NOT_OFFERED / NOT_FOUND rows are always logged (never a blank row)

Usage:
  python downloader_v2.py                  # all subjects in targets_v2.json
  python downloader_v2.py --subjects Biology Mathematics
"""
import csv, json, os, random, sys, time
from datetime import date

import naming, lib_fetch

ROOT = os.path.dirname(os.path.abspath(__file__))
SYLL = os.path.join(ROOT, "Syllabuses")
CSV_PATH = os.path.join(ROOT, "Syllabus_Master_Index.csv")
TARGETS = os.path.join(ROOT, "targets_v2.json")
TODAY = date.today().isoformat()

SUBJECT_ORDER = [
    "Mathematics", "Psychology", "Biology", "Chemistry", "Further_Mathematics",
    "History", "Physics", "English_Literature", "English_Language", "Geography",
    "Sociology", "Art_and_Design", "Business_Studies", "Economics", "Computer_Science",
    "Religious_Studies", "Spanish", "French", "Politics", "Physical_Education",
    "Music", "Drama", "Design_and_Technology", "Statistics", "Media_Studies",
]

DELAY_LO = float(os.environ.get("SYL_DELAY_LO", "2.0"))
DELAY_HI = float(os.environ.get("SYL_DELAY_HI", "5.0"))

# direct-URL guard: a question paper / mark scheme is still a valid PDF, so the
# %PDF byte-check won't reject it — filter such URLs by name before fetching.
BAD_URL_HINTS = ("-que-", "-que_", "_que_", "/que", "-msc-", "-ms-", "mark-scheme",
                 "markscheme", "question-paper", "-rms-", "examiner", "-pef-",
                 "past-paper", "/pastpaper", "-ms.pdf", "-qp.pdf")
# hosts that only serve an HTML viewer (never a clean PDF) — skip to save time
BAD_HOSTS = ("scribd.com", "pdfcoffee.com", "superprof.", "studocu.com",
             "coursehero.com", "/interactive_syllabus/")


def looks_like_paper(url):
    u = (url or "").lower()
    return any(h in u for h in BAD_URL_HINTS) or any(h in u for h in BAD_HOSTS)


def vkey(board, qual, variant, subject, first, last):
    return (board, qual, variant or "", subject, str(first), naming.last_str(last))


def load_csv():
    if not os.path.exists(CSV_PATH):
        return []
    with open(CSV_PATH, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(rows):
    tmp = CSV_PATH + ".tmp"
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=naming.CSV_HEADER)
        w.writeheader()
        w.writerows(rows)
        f.flush(); os.fsync(f.fileno())
    os.replace(tmp, CSV_PATH)


def folder_has_pdf(folder):
    if not os.path.isdir(folder):
        return False
    return any(fn.lower().endswith(".pdf") for fn in os.listdir(folder))


def main():
    args = sys.argv[1:]
    only = None
    if "--subjects" in args:
        only = args[args.index("--subjects") + 1:]

    targets = json.load(open(TARGETS, encoding="utf-8"))
    rows = load_csv()

    # satisfied versions from existing CSV (have a file, not a failure row)
    satisfied = set()
    for r in rows:
        if r.get("Filename") and not r.get("Notes", "").startswith(("NOT_FOUND", "NOT_OFFERED")):
            satisfied.add(vkey(r["Board"], r["Qualification_Type"], r["Variant"],
                               r["Subject"], r["First_Assessment_Year"], r["Last_Assessment_Year"]))

    by_subj = {}
    for t in targets:
        by_subj.setdefault(t["subject"], []).append(t)

    subjects = [s for s in SUBJECT_ORDER if (not only or s in only)]
    stats = {}
    for si, subject in enumerate(subjects, 1):
        new_rows, ok, skip, fail = [], 0, 0, 0
        for t in by_subj.get(subject, []):
            board, qual, variant = t["board"], t["qual_type"], t.get("variant", "")
            first, last = t["first_year"], t["last_year"]
            key = vkey(board, qual, variant, subject, first, last)
            folder = naming.new_folder(SYLL, t)
            fname = naming.new_filename(t)
            fpath = os.path.join(folder, fname)

            if key in satisfied or folder_has_pdf(folder):
                skip += 1
                continue

            # gather candidate urls
            urls = []
            if t.get("pdf_url"):
                urls.append(t["pdf_url"])
            urls += t.get("alt_urls", []) or []

            data, src = None, ""
            for u in urls:
                if not u or looks_like_paper(u):
                    continue
                time.sleep(random.uniform(DELAY_LO, DELAY_HI))
                data = lib_fetch.fetch_pdf(u)
                if data:
                    src = u; break

            # AQA filestore auto-probe
            if data is None and board == "AQA":
                probe = lib_fetch.aqa_filestore_probe(subject, t.get("spec_code", ""))
                if probe:
                    time.sleep(random.uniform(DELAY_LO, DELAY_HI))
                    data = lib_fetch.fetch_pdf(probe)
                    if data:
                        src = probe

            # scrape page_url
            if data is None and t.get("page_url"):
                time.sleep(random.uniform(DELAY_LO, DELAY_HI))
                for sc, link in (lib_fetch.scrape_pdf_links(t["page_url"], t.get("spec_code", ""), want_all=True) or [])[:4]:
                    time.sleep(random.uniform(DELAY_LO, DELAY_HI))
                    data = lib_fetch.fetch_pdf(link)
                    if data:
                        src = link; break

            if data is None:
                if t.get("not_offered"):
                    n = t.get("notes", "not offered")
                    note = n if n.startswith("NOT_OFFERED") else "NOT_OFFERED: " + n
                else:
                    note = "NOT_FOUND: no URL resolved to a valid PDF"
                new_rows.append(naming.csv_row(t, "", src or t.get("pdf_url") or t.get("page_url", ""),
                                               TODAY, note))
                fail += 1
                continue

            os.makedirs(folder, exist_ok=True)
            with open(fpath, "wb") as f:
                f.write(data)
            satisfied.add(key)
            new_rows.append(naming.csv_row(t, fname, src, TODAY, f"OK ({len(data)//1024} KB)"))
            ok += 1

        rows += new_rows
        write_csv(rows)
        stats[subject] = (ok, skip, fail)
        print(f"[{si:2}/{len(subjects)}] {subject:24} new={ok:3} skip={skip:3} fail={fail:3}")

    print("-" * 60)
    tot_ok = sum(v[0] for v in stats.values())
    tot_skip = sum(v[1] for v in stats.values())
    tot_fail = sum(v[2] for v in stats.values())
    print(f"TOTALS  new={tot_ok}  skipped={tot_skip}  not_found={tot_fail}")


if __name__ == "__main__":
    main()
