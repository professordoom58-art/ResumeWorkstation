# -*- coding: utf-8 -*-
"""Stage D: official careers / contact pages + optional Hunter.io Domain Search."""
import os, re, sys, csv, json, datetime, argparse, urllib.parse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C

CAREERS = {
    "IQVIA": "https://jobs.iqvia.com/en/search-jobs",
    "ICON": "https://careers.iconplc.com/",
    "Parexel": "https://jobs.parexel.com/",
    "Fortrea": "https://careers.fortrea.com/",
    "Syneos Health": "https://www.syneoshealth.com/careers",
    "Labcorp": "https://careers.labcorp.com/",
    "APCER Life Sciences": "https://www.apcerls.com/careers/",
    "Clarivate": "https://careers.clarivate.com/",
    "TCS": "https://www.tcs.com/careers",
    "Cognizant": "https://careers.cognizant.com/",
    "Accenture": "https://www.accenture.com/in-en/careers",
    "Wipro": "https://careers.wipro.com/",
    "Mankind Pharma": "https://www.mankindpharma.com/careers",
    "Sun Pharma": "https://www.sunpharma.com/careers",
    "Cipla": "https://www.cipla.com/careers",
    "Dr Reddy's": "https://www.drreddys.com/careers/",
    "Lupin": "https://www.lupin.com/careers.php",
    "Glenmark": "https://www.glenmarkpharma.com/careers",
    "Alkem": "https://www.alkemlabs.com/careers",
    "Zydus": "https://www.zyduslife.com/careers",
    "Intas": "https://www.intaspharma.com/careers/",
    "Biocon": "https://www.biocon.com/careers/",
    "Piramal": "https://www.piramal.com/careers",
    "Jubilant": "https://www.jubilantpharmova.com/careers",
    "Lambda Therapeutic": "https://www.lambdaclinicalresearch.com/careers/",
    "Veeda": "https://www.veedacr.com/careers/",
    "Cliantha": "https://www.cliantha.com/careers/",
}
GENERIC = re.compile(r"^(careers?|jobs?|hr|recruit(ment)?|talent|joinus|apply)[@.]", re.I)


def hunter(domain, key, min_conf):
    """Hunter Domain Search. Returns [(email, source_url)] for HR/generic, high confidence."""
    import requests
    out = []
    try:
        r = requests.get("https://api.hunter.io/v2/domain-search",
                         params={"domain": domain, "api_key": key, "limit": 10}, timeout=30)
        if r.status_code != 200:
            return out
        for e in r.json().get("data", {}).get("emails", []):
            conf = e.get("confidence", 0)
            dept = (e.get("department") or "").lower()
            typ = (e.get("type") or "").lower()
            srcs = e.get("sources") or []
            if conf < min_conf or not srcs:
                continue
            if typ in ("generic", "personal") and (dept in ("hr", "human_resources", "") or typ == "generic"):
                out.append((e["value"], srcs[0].get("uri", "")))
    except Exception as ex:
        C.log_skip(f"hunter failed {domain}: {ex}")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=27)
    args = ap.parse_args()
    cfg = C.cfg(); C.ensure_out()
    key = os.environ.get("HUNTER_API_KEY", "")
    rows = []
    names = list(CAREERS.keys())[:args.limit]
    for name in names:
        url = CAREERS[name]
        if not C.robots_ok(url, cfg["request_delay_seconds"]):
            C.log_skip(f"robots disallow careers | {url}")
            continue
        html, st = C.polite_get(url, cfg["request_delay_seconds"])
        got = []
        if html:
            got, _ = C.page_emails(html)
            got = [e for e in got if GENERIC.match(e.split("@")[0]) or "career" in e]
        for em in got:
            rows.append({"stage": "D", "email": em, "company": name, "role": "Careers page",
                         "location": "", "experience": "", "date_posted": datetime.date.today().isoformat(),
                         "source_url": url, "scam": ""})
        print(f"{name[:22]:22} {'OK ' if got else ('-  ' + str(st)):6} {got[:2]}")
    if key:
        for name in names[:20]:
            dom = urllib.parse.urlsplit(CAREERS[name]).netloc.replace("www.", "")
            for em, src in hunter(dom, key, cfg["min_hunter_confidence"]):
                rows.append({"stage": "D", "email": em, "company": name, "role": "Hunter Domain Search",
                             "location": "", "experience": "", "date_posted": datetime.date.today().isoformat(),
                             "source_url": src, "scam": ""})
                print(f"  hunter + {name[:18]:18} {em}")
    else:
        print("\nHUNTER_API_KEY not set -> Hunter stage skipped (no guessed addresses).")

    path = os.path.join(C.OUT, f"raw_careers_{datetime.date.today().isoformat()}.csv")
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["stage", "email", "company", "role", "location",
                                         "experience", "date_posted", "source_url", "scam"])
        w.writeheader(); w.writerows(rows)
    print(f"\nStage D: {len(rows)} email rows -> {path}")


if __name__ == "__main__":
    main()
