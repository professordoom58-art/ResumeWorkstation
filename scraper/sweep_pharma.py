# -*- coding: utf-8 -*-
"""Pharma-only job sweep (JobSpy: Indeed, Naukri, Glassdoor), last 7 days.

Keeps a job only if
  - the title is not customer support / BPO / telecaller / data entry / generic sales (BAD_TITLE), and
  - the posting asks for a pharmacy or medical degree (DEGREE) or the title is inherently pharma (PHARMA_TITLE);
  - the location is Delhi / Gurugram / Faridabad / Ghaziabad / Chandigarh / Mohali / Panchkula / Zirakpur or remote,
    and never Noida, Ambala, Yamunanagar or Ludhiana;
  - the stated maximum pay is not below Rs 20,000/month (pay not stated -> kept).
Emails and WhatsApp numbers are taken only as printed in the posting; leads without either are kept for portal applies.

Run in two halves to stay polite:   PART=1 python scraper/sweep_pharma.py   and   PART=2 python scraper/sweep_pharma.py
Output: scraper/out/raw_pharma_<date>_p<PART>.json  ->  then  python scraper/build_sweep_tab.py"""
import os, sys, re, json, time, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C

PHARMA_TERMS = [
    "pharmacovigilance", "drug safety associate", "patient safety associate", "drug safety", "pharmacovigilance fresher",
    "clinical research coordinator", "clinical research associate", "clinical trial assistant", "clinical research fresher",
    "case processing associate", "safety associate", "medical reviewer", "clinical data coordinator", "clinical research",
    "regulatory affairs", "medical writer", "medical affairs", "medical information", "b pharm fresher", "pharmacist",
]
LOCS = ["New Delhi", "Gurugram", "Faridabad", "Ghaziabad", "Chandigarh", "Mohali", "Panchkula", "Zirakpur"]
if os.environ.get("PART"):
    LOCS = LOCS[:4] if os.environ["PART"] == "1" else LOCS[4:]
SITES = ["indeed", "naukri", "glassdoor"]
ALLOW = re.compile(r"delhi|gurugram|gurgaon|faridabad|ghaziabad|chandigarh|mohali|panchkula|zirakpur|\bncr\b|remote|work from home", re.I)
DENY = re.compile(r"noida|ambala|yamuna ?nagar|ludhiana", re.I)
PAY = re.compile(r"(?:₹|rs\.?|inr)\s*([\d,]{4,9})(?:\.\d+)?\s*(?:-|–|to)\s*(?:₹|rs\.?|inr)?\s*([\d,]{4,9})(?:\.\d+)?\s*(?:per|/|a)\s*(month|year|annum)", re.I)
PAY1 = re.compile(r"(?:₹|rs\.?|inr)\s*([\d,]{4,9})(?:\.\d+)?\s*(?:per|/|a)\s*(month|year|annum)", re.I)
WA = re.compile(r"(?:whats\s?app|wa\.me/|call|contact|mobile|phone|hr|number|no\.)[^0-9+]{0,25}(\+?91[\s-]?)?([6-9]\d{4}[\s-]?\d{5})", re.I)
DEGREE = re.compile(r"b\.?\s?pharm|m\.?\s?pharm|pharm\.?\s?d\b|d\.?\s?pharm|pharmacy (?:degree|graduate)|registered pharmacist|\bmbbs\b|\bbds\b|\bbams\b|\bbhms\b|\bbums\b|medical degree|medical graduate", re.I)
PHARMA_TITLE = re.compile(r"pharmac|pharma\b|pharmaceutical|drug safety|vigilance|clinical (?:research|trial|data)|regulatory|medical (?:representative|coder|coding|writer|affairs|officer|advisor|science|information)|\bmr\b|\bcra\b|\bcrc\b|\bqa\b|\bqc\b|quality (?:assurance|control)|formulation|chemist|doctor|physician|\bmbbs\b|\bbds\b|\bbams\b|\bbhms\b|dental|ayurved|homeopath", re.I)
BAD_TITLE = re.compile(r"customer (?:support|service|care)|call cent|\bbpo\b|voice|telecall|tele ?sales|back office|data entry|front office|receptionist|nurse|\bgnm\b|\banm\b|\bward\b|driver|delivery|insurance advisor|real estate|counsell?or|beautician|\bspa\b", re.I)
PAY_FLOOR = 20000  # Rs per month
TODAY = datetime.date.today().isoformat()


def monthly_max(j, desc):
    """(max_monthly, source) or (None, '')."""
    try:
        mx, iv = j.get("max_amount"), str(j.get("interval") or "").lower()
        if mx and str(mx) != "nan":
            mx = float(mx)
            return (mx / 12 if iv.startswith("year") else mx), "jobspy"
    except Exception:
        pass
    m = PAY.search(desc)
    if m:
        hi = float(m.group(2).replace(",", ""))
        return (hi / 12 if m.group(3).lower() != "month" else hi), "text"
    m = PAY1.search(desc)
    if m:
        v = float(m.group(1).replace(",", ""))
        return (v / 12 if m.group(2).lower() != "month" else v), "text"
    return None, ""


def main():
    from jobspy import scrape_jobs  # imported here so build_sweep_tab can reuse the filters without JobSpy
    rows, seen = [], set()
    stats = {"jobs": 0, "loc_drop": 0, "deny_drop": 0, "pay_drop": 0, "no_contact": 0, "bad_title": 0, "not_pharma": 0}
    kind = "pharma"
    for terms in (PHARMA_TERMS,):
        for term in terms:
            for loc in LOCS:
                try:
                    df = scrape_jobs(site_name=SITES, search_term=term, location=loc, results_wanted=40,
                                     hours_old=168, country_indeed="India", description_format="markdown", verbose=0)
                except Exception as e:
                    print(f"  ERR {term} @ {loc}: {str(e)[:100]}"); time.sleep(4); continue
                n = 0 if df is None else len(df); stats["jobs"] += n; kept = 0
                for _, j in (df.iterrows() if n else []):
                    url = next((str(u) for u in (j.get("job_url"), j.get("job_url_direct")) if u is not None and str(u) not in ("", "nan")), "")
                    if not url or url in seen:
                        continue
                    seen.add(url)
                    desc = str(j.get("description") or "")
                    jl = str(j.get("location") or "")
                    locline = " ".join(re.findall(r"(?:location|work location|job location)\W{0,6}([^\n*]{3,80})", desc, re.I))
                    where = (jl + " " + locline)
                    if DENY.search(where):
                        stats["deny_drop"] += 1; continue
                    if not ALLOW.search(where) and not ALLOW.search(loc if jl.strip() in ("", "IN", "India") else ""):
                        stats["loc_drop"] += 1; continue
                    title = str(j.get("title") or "")
                    if BAD_TITLE.search(title):
                        stats["bad_title"] += 1; continue
                    deg = DEGREE.search(title + " " + desc)
                    if not deg and not PHARMA_TITLE.search(title):
                        stats["not_pharma"] += 1; continue
                    pay, psrc = monthly_max(j, desc)
                    if pay is not None and pay < PAY_FLOOR:
                        stats["pay_drop"] += 1; continue
                    emails = C.clean_emails(desc + " " + str(j.get("emails") or ""))
                    phones = sorted({re.sub(r"\D", "", m.group(2))[-10:] for m in WA.finditer(desc)})
                    if not emails and not phones:
                        stats["no_contact"] += 1
                    exp = ""
                    m = re.search(r"\d+\s*(?:-|to|–)\s*\d+\s*(?:years?|yrs?)|\d+\+?\s*(?:years?|yrs?)|fresher", desc, re.I)
                    if m: exp = m.group(0)
                    rows.append(dict(kind=kind, term=term, company=str(j.get("company") or "")[:80],
                        role=str(j.get("title") or "")[:120], location=jl[:60], locline=locline[:80],
                        pay_month=round(pay) if pay else None, pay_src=psrc, experience=exp[:30],
                        date_posted=str(j.get("date_posted") or "")[:10], source_url=url, site=str(j.get("site")),
                        emails=emails, whatsapp=phones,
                        degree=(deg.group(0) if deg else ""), scam=";".join(C.scam_hit(desc, C.cfg()["scam_words"])), desc=desc[:5000]))
                    kept += 1
                print(f"  [{kind}] {term} @ {loc}: {n} jobs | kept {kept}", flush=True)
                time.sleep(3)
    out = os.path.join(C.OUT, f"raw_pharma_{TODAY}_p{os.environ.get('PART', '0')}.json")
    json.dump(rows, open(out, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print(f"\nSTATS {stats} | kept {len(rows)} -> {out}", flush=True)


if __name__ == "__main__":
    main()
