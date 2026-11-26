# -*- coding: utf-8 -*-
"""Stage C: turn public Google results (recruiter posts) into rows.

Searches are run in the browser / WebSearch (Past week filter), because a scripted
Google crawl gets CAPTCHAs. Put results into scraper/out/google_results.json:

    [{"title": "...", "url": "https://...", "snippet": "... hr@acme.com ..."}, ...]

then run:  python scraper/stage_c_google.py
"""
import os, sys, csv, json, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C


def main():
    cfg = C.cfg(); C.ensure_out()
    src = os.path.join(C.OUT, "google_results.json")
    if not os.path.exists(src):
        print("no scraper/out/google_results.json -> Stage C skipped")
        return
    items = json.load(open(src, encoding="utf-8"))
    rows = []
    for it in items:
        emails = C.clean_emails(it.get("snippet", "") + " " + it.get("title", ""))
        for em in emails:
            rows.append({"stage": "C", "email": em,
                         "company": (it.get("company") or "").strip(),
                         "role": (it.get("role") or it.get("title", ""))[:120],
                         "location": it.get("location", ""), "experience": it.get("experience", ""),
                         "date_posted": it.get("date", datetime.date.today().isoformat()),
                         "source_url": it.get("url", ""),
                         "scam": ";".join(C.scam_hit(it.get("snippet", ""), cfg["scam_words"]))})
    path = os.path.join(C.OUT, f"raw_google_{datetime.date.today().isoformat()}.csv")
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["stage", "email", "company", "role", "location",
                                         "experience", "date_posted", "source_url", "scam"])
        w.writeheader(); w.writerows(rows)
    print(f"Stage C: {len(rows)} email rows from {len(items)} search results -> {path}")


if __name__ == "__main__":
    main()
