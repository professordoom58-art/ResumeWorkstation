# -*- coding: utf-8 -*-
"""Stage A: JobSpy across public job boards, harvesting published emails."""
import os, re, sys, csv, time, datetime, argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C

def run(terms, locations, sites, results, hours, use_linkedin, delay, google_terms=None):
    try:
        from jobspy import scrape_jobs
    except Exception as e:
        print("jobspy import failed:", e)
        return []
    rows, li_dead, errors = [], False, []
    for term in terms:
        for loc in locations:
            query_sites = list(sites)
            if use_linkedin and not li_dead:
                query_sites = query_sites + ["linkedin"]
            rw = results
            if "linkedin" in query_sites:
                rw = min(results, 25)
            kwargs = dict(site_name=query_sites, search_term=term, location=loc,
                          results_wanted=rw, hours_old=hours,
                          description_format="markdown", verbose=0)
            if "indeed" in query_sites:
                kwargs["country_indeed"] = "India"
            if google_terms and "google" in query_sites:
                kwargs["google_search_term"] = google_terms
            try:
                df = scrape_jobs(**kwargs)
            except Exception as e:
                msg = str(e)[:160]
                errors.append(f"{term}/{loc}: {msg}")
                print(f"  ERR {term} @ {loc}: {msg}")
                if "429" in msg or "rate" in msg.lower():
                    li_dead = True
                    print("  LinkedIn disabled for this run (429)")
                continue
            if df is None or len(df) == 0:
                print(f"  {term} @ {loc}: 0 jobs")
                time.sleep(delay)
                continue
            n_email = 0
            for _, j in df.iterrows():
                desc = " ".join(str(j.get(k, "") or "") for k in
                                ("description", "emails", "job_description"))
                emails = C.clean_emails(desc)
                if not emails:
                    continue
                per = [e for e in str(j.get("emails", "") or "").replace(";", ",").split(",")
                       if "@" in e]
                emails = sorted(set(emails + C.clean_emails(" ".join(per))))
                d = j.get("date_posted")
                d = str(d)[:10] if d is not None else ""
                for em in emails:
                    rows.append({
                        "stage": "A", "email": em,
                        "company": str(j.get("company", "") or "")[:80],
                        "role": str(j.get("title", "") or "")[:120],
                        "location": str(j.get("location", "") or "")[:60],
                        "experience": "",
                        "date_posted": d,
                        "source_url": str(j.get("job_url", "") or ""),
                        "scam": ";".join(C.scam_hit(desc, C.cfg()["scam_words"])),
                    })
                    n_email += 1
            print(f"  {term} @ {loc}: {len(df)} jobs | {n_email} with email")
            time.sleep(delay)
    if errors:
        C.log_skip("stageA errors: " + " || ".join(errors[:10]))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--test", action="store_true")
    args = ap.parse_args()
    cfg = C.cfg(); C.ensure_out()
    if args.test:
        terms, locs, sites, res = ["pharmacovigilance"], ["Noida, Uttar Pradesh"], ["indeed"], 10
        hours = 168
    else:
        terms, locs, sites = cfg["search_terms"], cfg["locations"], cfg["jobspy_sites"]
        res, hours = cfg["results_per_query"], cfg["days_back"] * 24
    rows = run(terms, locs, sites, res, hours, cfg.get("use_linkedin", True),
               cfg["request_delay_seconds"],
               google_terms="pharmacovigilance jobs in Noida since last week")
    path = os.path.join(C.OUT, f"raw_jobspy_{datetime.date.today().isoformat()}.csv")
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["stage", "email", "company", "role", "location",
                                         "experience", "date_posted", "source_url", "scam"])
        w.writeheader(); w.writerows(rows)
    print(f"\nStage A: {len(rows)} email rows -> {path}")
    if rows:
        print("\nsample with emails:")
        for r in rows[:12]:
            print(f"  {r['company'][:24]:24} | {r['role'][:34]:34} | {r['email']}")


if __name__ == "__main__":
    main()
