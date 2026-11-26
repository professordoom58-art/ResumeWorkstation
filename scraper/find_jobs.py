# -*- coding: utf-8 -*-
"""Find today's job leads for the applicant and write them to an Excel file.

Usage:  .venv/Scripts/python.exe scraper/find_jobs.py [--config profile/search.yaml] [--target 60] [--need both|email|phone|any]
Output: jobs/Job_Leads_<YYYY-MM-DD>.xlsx   (one sheet per run, plus a "Run info" sheet)
        jobs/Job_Leads_<YYYY-MM-DD>.json   (same rows, used to skip these leads on later days)

How a lead is chosen
  1. JobSpy searches every `search_terms` x `locations` pair (Indeed, Naukri, Glassdoor ...) for the last `hours_old` hours.
     search_terms are built from the resume's *duties and skills*, not only its job titles (see CLAUDE.md step 2).
  2. Relevance is scored on the posting text, not the title: each `match_keywords` entry found in title + description
     scores 1 (2 if it is in the title). Leads below `min_match` are dropped.
  3. Dropped: `title_exclude` hits, `deny_locations`, locations outside `allow_locations`, stated max pay below
     `pay_floor_month`, minimum experience asked above `max_years_asked`, scam words, and anything already contacted
     (outbox/sent_all.json) or already listed in an earlier day's Job_Leads file.
  4. Contacts are taken only as printed in the posting. `need: both` keeps a lead only if it has an email AND a phone.
  5. Stops once `target` leads are found; rows are sorted by match score.
"""
import os, sys, re, json, time, glob, datetime, argparse
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import common as C
import yaml
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

ROOT = C.ROOT
JOBS_DIR = os.path.join(ROOT, "jobs")
TODAY = datetime.date.today()
STATUSES = ("To Send,Approved,Drafted,Sent,Followed Up,Replied,Interview,Offer,Rejected,Bounced,Expired,"
            "Unverified,Skipped – not eligible,Skipped – scam")
BOARD_DOMAINS = ("naukri.com", "indeed.com", "glassdoor", "linkedin.com", "foundit", "shine.com", "monster", "apna.co",
                 "workindia", "timesjobs", "internshala")
PAY = re.compile(r"(?:₹|rs\.?|inr)\s*([\d,]{4,9})(?:\.\d+)?\s*(?:-|–|to)\s*(?:₹|rs\.?|inr)?\s*([\d,]{4,9})(?:\.\d+)?\s*(?:per|/|a)\s*(month|year|annum)", re.I)
PAY1 = re.compile(r"(?:₹|rs\.?|inr)\s*([\d,]{4,9})(?:\.\d+)?\s*(?:per|/|a)\s*(month|year|annum)", re.I)
# a phone counts only when it sits next to a contact word, so job IDs and pin codes are not picked up
PHONE = re.compile(r"(?:whats\s?app|wa\.me/|call|contact|mobile|mob|phone|ph|hr|number|no\.|reach)[^0-9+]{0,25}"
                   r"(\+?91[\s-]?)?([6-9]\d{4}[\s-]?\d{5})", re.I)
EXP = re.compile(r"(\d+)\s*(?:-|to|–)\s*(\d+)\s*(?:\+\s*)?(?:years?|yrs?)|(\d+)\s*\+?\s*(?:years?|yrs?)|fresher", re.I)


def canon_url(u):
    """Canonical job key (career-ops style): drop tracking params, fragment, trailing slash; lowercase host and path."""
    p = urlsplit(u.strip())
    q = [(k, v) for k, v in parse_qsl(p.query) if not k.lower().startswith(("utm_", "ref", "src", "from", "trk", "tracking"))]
    return urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path.rstrip("/").lower(), urlencode(q), ""))


def load_blacklist():
    """profile/blacklist.txt: one company name or email domain per line (# comments). Checked before scoring."""
    f = os.path.join(ROOT, "profile", "blacklist.txt")
    if not os.path.exists(f):
        return []
    return [l.strip().lower() for l in open(f, encoding="utf-8") if l.strip() and not l.startswith("#")]


def fit_band(score):
    return "Strong" if score >= 7 else "Apply" if score >= 4 else "Maybe"


def load_cfg(path):
    cfg = yaml.safe_load(open(path, encoding="utf-8"))
    for k in ("search_terms", "match_keywords", "locations"):
        if not cfg.get(k):
            sys.exit(f"{path}: '{k}' is empty - build it from the resume first (CLAUDE.md step 2)")
    return cfg


def kw_regex(words):
    return [(w, re.compile(r"(?<![a-z0-9])" + re.escape(w.lower()).replace(r"\ ", r"[\s\-/]*") + r"(?![a-z0-9])", re.I))
            for w in words]


def monthly_max(j, desc):
    try:
        mx, iv = j.get("max_amount"), str(j.get("interval") or "").lower()
        if mx and str(mx) != "nan":
            mx = float(mx)
            return round(mx / 12 if iv.startswith("year") else mx)
    except Exception:
        pass
    m = PAY.search(desc)
    if m:
        hi = float(m.group(2).replace(",", ""))
        return round(hi / 12 if m.group(3).lower() != "month" else hi)
    m = PAY1.search(desc)
    if m:
        v = float(m.group(1).replace(",", ""))
        return round(v / 12 if m.group(2).lower() != "month" else v)
    return None


def min_years(text):
    m = EXP.search(text or "")
    if not m:
        return None, ""
    if m.group(0).lower() == "fresher":
        return 0, "Fresher"
    return int(m.group(1) or m.group(3)), m.group(0)


def already_known():
    """Addresses/numbers already contacted and URLs listed on earlier days."""
    contacted, urls = set(), set()
    sf = os.path.join(ROOT, "outbox", "sent_all.json")
    if os.path.exists(sf):
        for v in json.load(open(sf, encoding="utf-8")).values():
            if v.get("result") in ("SENT", "SKIP_EXISTING", "UNSURE"):
                contacted.add(str(v.get("to", "")).lower())
    for f in glob.glob(os.path.join(JOBS_DIR, "Job_Leads_*.json")):
        if TODAY.isoformat() in f:
            continue
        for r in json.load(open(f, encoding="utf-8")):
            urls.add(canon_url(r["source_url"]))
    return contacted, urls


PROGRESS_F = os.path.join(ROOT, "jobs", "progress.json")


def progress(**kw):
    """Live sweep state for src/telegram_status.py."""
    os.makedirs(os.path.dirname(PROGRESS_F), exist_ok=True)
    kw["updated"] = datetime.datetime.now().isoformat(timespec="seconds")
    json.dump(kw, open(PROGRESS_F, "w", encoding="utf-8"), ensure_ascii=False)


def sweep(cfg, target, need):
    from jobspy import scrape_jobs
    match = kw_regex(cfg["match_keywords"])
    excl = re.compile("|".join(cfg.get("title_exclude") or ["$^"]), re.I)
    allow = re.compile("|".join(cfg.get("allow_locations") or [".*"]), re.I)
    deny = re.compile("|".join(cfg.get("deny_locations") or ["$^"]), re.I)
    must = re.compile("|".join(cfg["require_any"]), re.I) if cfg.get("require_any") else None
    floor, max_yrs = cfg.get("pay_floor_month"), cfg.get("max_years_asked")
    min_match, cc = int(cfg.get("min_match", 2)), str(cfg.get("phone_country_code", "91"))
    scam_words = C.cfg()["scam_words"]
    contacted, old_urls = already_known()
    black = load_blacklist()
    rows, seen = [], set()
    stats = dict(fetched=0, dup=0, blacklist=0, location=0, title=0, relevance=0, pay=0, experience=0, contact=0, contacted=0, scam=0)
    total_q, done_q = len(cfg["search_terms"]) * len(cfg["locations"]), 0
    started = datetime.datetime.now().isoformat(timespec="seconds")
    for term in cfg["search_terms"]:
        for loc in cfg["locations"]:
            if len(rows) >= target:
                break
            try:
                df = scrape_jobs(site_name=cfg.get("sites", ["indeed", "naukri"]), search_term=term, location=loc,
                                 results_wanted=int(cfg.get("results_per_query", 40)), hours_old=int(cfg.get("hours_old", 168)),
                                 country_indeed=cfg.get("country", "India"), description_format="markdown", verbose=0)
            except Exception as e:
                print(f"  ERR {term} @ {loc}: {str(e)[:100]}", flush=True)
                time.sleep(5)
                continue
            n = 0 if df is None else len(df)
            stats["fetched"] += n
            kept = 0
            for _, j in (df.iterrows() if n else []):
                url = next((str(u) for u in (j.get("job_url"), j.get("job_url_direct")) if u is not None and str(u) not in ("", "nan")), "")
                company = str(j.get("company") or "").strip()
                title = re.sub(r"\s+", " ", str(j.get("title") or "")).strip()
                key = (company.lower(), title.lower())
                ck = canon_url(url) if url else ""
                if not url or ck in seen or ck in old_urls or key in seen:
                    stats["dup"] += 1
                    continue
                seen.update((ck, key))
                desc = str(j.get("description") or "")
                if black and any(b in company.lower() or ("@" + b) in desc.lower() for b in black):
                    stats["blacklist"] += 1
                    continue
                jl = str(j.get("location") or "")
                locline = " ".join(re.findall(r"(?:location|work location|job location)\W{0,6}([^\n*]{3,80})", desc, re.I))
                locline = re.sub(r"\b(?:in person|on-?site|work from office)\b", "", locline, flags=re.I).strip()
                # Indeed often reports only a state code ("DL, India", "HR, India"): then judge by the searched city,
                # but still apply the deny-list to the title and the posting's own location line.
                vague = bool(re.fullmatch(r"\s*(?:[A-Z]{2}\s*,\s*)?(?:India|IN)?\s*", jl))
                where = f"{jl} {locline} {title}"
                if deny.search(where) or not (allow.search(f"{jl} {locline}") or (vague and allow.search(loc))):
                    stats["location"] += 1
                    continue
                if excl.search(title):
                    stats["title"] += 1
                    continue
                text = f"{title}\n{desc}"
                hits = [w for w, rx in match if rx.search(text)]
                score = len(hits) + sum(1 for w, rx in match if rx.search(title))
                if score < min_match or (must and not must.search(text)):
                    stats["relevance"] += 1
                    continue
                pay = monthly_max(j, desc)
                if floor and pay is not None and pay < floor:
                    stats["pay"] += 1
                    continue
                yrs, exp_txt = min_years(desc)
                if max_yrs is not None and yrs is not None and yrs > max_yrs:
                    stats["experience"] += 1
                    continue
                emails = [e for e in C.clean_emails(desc + " " + str(j.get("emails") or ""))
                          if not any(b in e.split("@")[1] for b in BOARD_DOMAINS)]
                phones = sorted({re.sub(r"\D", "", m.group(2))[-10:] for m in PHONE.finditer(desc)})
                ok = {"both": emails and phones, "email": emails, "phone": phones, "any": emails or phones}[need]
                if not ok:
                    stats["contact"] += 1
                    continue
                if any(e in contacted for e in emails) or any(f"whatsapp:+{cc}{p}" in contacted for p in phones):
                    stats["contacted"] += 1
                    continue
                scam = C.scam_hit(desc, scam_words)
                if scam:
                    stats["scam"] += 1
                    continue
                rows.append(dict(score=score, company=company[:80], role=title[:120], location=(f"{loc} ({jl.strip()})" if vague else jl.strip() or locline)[:70],
                                 experience=exp_txt[:30], pay_month=pay, emails=emails, phones=phones, matched=hits,
                                 term=term, site=str(j.get("site")), date_posted=str(j.get("date_posted") or "")[:10],
                                 source_url=url, desc=desc[:4000]))
                kept += 1
                if len(rows) >= target:
                    break
            print(f"  {term} @ {loc}: {n} fetched | kept {kept} | total {len(rows)}/{target}", flush=True)
            done_q += 1
            progress(state="running", date=TODAY.isoformat(), started=started, queries_done=done_q, queries_total=total_q,
                     term=term, location=loc, leads=len(rows), target=target)
            time.sleep(float(cfg.get("delay_seconds", 3)))
        if len(rows) >= target:
            break
    rows.sort(key=lambda r: (r["score"], r["date_posted"] or ""), reverse=True)  # best match first, then newest
    return rows, stats


def write_excel(rows, stats, cfg, need, path):
    import openpyxl
    from openpyxl.styles import Font, Alignment, Border, Side, PatternFill
    from openpyxl.worksheet.datavalidation import DataValidation
    from openpyxl.formatting.rule import FormulaRule
    cols = [("ID", 11), ("Match", 7), ("Fit", 7), ("Company", 26), ("Role / Opening", 36), ("Location", 20), ("Experience asked", 13),
            ("Pay / month", 11), ("HR Email", 30), ("Phone / WhatsApp", 15), ("Matched keywords", 34), ("Search term", 20),
            ("Site", 9), ("Posted", 11), ("Source URL", 40), ("Status", 14), ("Resume file", 28), ("Date Sent", 11),
            ("Follow-up Due", 12), ("Notes", 34)]
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = f"Leads {TODAY:%d-%b}"
    thin = Side(style="thin", color="D0D0D0")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    for c, (h, w) in enumerate(cols, 1):
        cell = ws.cell(1, c, h)
        cell.font = Font(name="Arial", size=10, bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="1F4E78")
        cell.alignment = Alignment(vertical="center", wrap_text=True)
        cell.border = border
        ws.column_dimensions[cell.column_letter].width = w
    ws.freeze_panes = "D2"
    from openpyxl.utils import get_column_letter
    col = {h: i for i, (h, _) in enumerate(cols, 1)}
    L = {h: get_column_letter(i) for h, i in col.items()}
    st, sent_c, fu = L["Status"], L["Date Sent"], L["Follow-up Due"]
    for i, r in enumerate(rows, start=2):
        r["id"] = f"J{TODAY:%m%d}-{i - 1:02d}"
        posted = datetime.date.fromisoformat(r["date_posted"]) if re.match(r"\d{4}-\d\d-\d\d$", r["date_posted"]) else None
        vals = [r["id"], r["score"], fit_band(r["score"]), r["company"], r["role"], r["location"], r["experience"],
                r["pay_month"] if r["pay_month"] else "not stated", ", ".join(r["emails"]),
                ", ".join(f"+{cfg.get('phone_country_code', '91')} {p}" for p in r["phones"]), ", ".join(r["matched"]),
                r["term"], r["site"], posted, r["source_url"], "To Send", "", None, None, ""]
        for c, v in enumerate(vals, 1):
            cell = ws.cell(i, c, v)
            cell.font = Font(name="Arial", size=10)
            cell.border = border
            cell.alignment = Alignment(vertical="top", wrap_text=c in (col["Role / Opening"], col["Matched keywords"], col["Notes"]))
        ws.cell(i, col["Source URL"]).hyperlink = r["source_url"]
        for c in (col["Posted"], col["Date Sent"], col["Follow-up Due"]):
            ws.cell(i, c).number_format = "dd-mmm-yyyy"
        ws.cell(i, col["Follow-up Due"]).value = f'=IF({sent_c}{i}="","",WORKDAY({sent_c}{i},4))'
    last = max(2, len(rows) + 1)
    dv = DataValidation(type="list", formula1=f'"{STATUSES}"', allow_blank=True)
    dv.add(f"{st}2:{st}{last + 100}")
    ws.add_data_validation(dv)
    end = get_column_letter(len(cols))
    rng = f"A2:{end}{last + 100}"
    ws.conditional_formatting.add(rng, FormulaRule(formula=[f'OR(${st}2="Replied",${st}2="Interview",${st}2="Offer")'], fill=PatternFill("solid", fgColor="C6EFCE")))
    ws.conditional_formatting.add(rng, FormulaRule(formula=[f'OR(${st}2="Bounced",${st}2="Rejected",LEFT(${st}2,7)="Skipped")'], fill=PatternFill("solid", fgColor="D9D9D9")))
    ws.conditional_formatting.add(rng, FormulaRule(formula=[f'AND(${st}2="Sent",${fu}2<>"",${fu}2<=TODAY())'], fill=PatternFill("solid", fgColor="FFEB9C")))
    ws.auto_filter.ref = f"A1:{end}{last}"
    info = wb.create_sheet("Run info")
    for k, v in [("Run date", TODAY.isoformat()), ("Leads", len(rows)), ("Contact rule", need)] + \
                [(f"dropped: {k}", v) for k, v in stats.items()] + \
                [("search_terms", ", ".join(cfg["search_terms"])), ("match_keywords", ", ".join(cfg["match_keywords"])),
                 ("locations", ", ".join(cfg["locations"]))]:
        info.append([k, v])
    info.column_dimensions["A"].width, info.column_dimensions["B"].width = 22, 120
    os.makedirs(os.path.dirname(path), exist_ok=True)
    wb.save(path)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=os.path.join(ROOT, "profile", "search.yaml"))
    ap.add_argument("--target", type=int)
    ap.add_argument("--need", choices=("both", "email", "phone", "any"))
    a = ap.parse_args()
    cfg = load_cfg(a.config)
    target = a.target or int(cfg.get("target", 60))
    need = a.need or cfg.get("need_contact", "both")
    xlsx = os.path.join(JOBS_DIR, f"Job_Leads_{TODAY.isoformat()}.xlsx")
    if os.path.exists(xlsx):
        sys.exit(f"{xlsx} already exists - today's file is not overwritten. Rename or delete it to re-run.")
    print(f"target {target} leads, contact rule '{need}', {len(cfg['search_terms'])} terms x {len(cfg['locations'])} locations", flush=True)
    rows, stats = sweep(cfg, target, need)
    write_excel(rows, stats, cfg, need, xlsx)
    json.dump(rows, open(xlsx[:-5] + ".json", "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print(f"\nDROPPED {stats}")
    print(f"WROTE {len(rows)} leads -> {xlsx}")
    progress(state="finished", date=TODAY.isoformat(), leads=len(rows), target=target, excel=os.path.relpath(xlsx, ROOT))
    if len(rows) < target:
        print(f"SHORT by {target - len(rows)}: widen search_terms/locations, lower min_match, or use --need any")


if __name__ == "__main__":
    main()
