# -*- coding: utf-8 -*-
"""Stage E: merge raw CSVs -> clean, verify, dedupe -> load into HR_Outreach_Tracker.xlsx."""
import os, re, sys, csv, glob, json, datetime, argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C

try:
    import dns.resolver
except Exception:
    dns = None
try:
    from email_validator import validate_email, EmailNotValidError
except Exception:
    validate_email = None
try:
    import tldextract
    _tld = tldextract.TLDExtract(suffix_list_urls=())
except Exception:
    _tld = None
import openpyxl
from openpyxl.styles import Font, Alignment, Border, Side
from openpyxl.formatting.rule import FormulaRule
from openpyxl.styles import PatternFill

TRACKER = os.path.join(C.ROOT, "HR_Outreach_Tracker.xlsx")
COLS = ["ID", "Company", "Role / Opening", "Category", "Location", "Experience asked",
        "HR Name", "HR Email", "Source URL", "Posted Date", "Priority", "Resume Sent",
        "Date Sent", "Follow-up 1 Due", "Follow-up Sent", "Status", "Notes"]
FREEMAIL_HINT = None
_mx_cache = {}


def mx_ok(domain):
    if domain in _mx_cache:
        return _mx_cache[domain]
    if dns is None:
        _mx_cache[domain] = True
        return True
    ok = False
    try:
        ans = dns.resolver.resolve(domain, "MX", lifetime=6)
        ok = len(ans) > 0
    except Exception:
        try:
            dns.resolver.resolve(domain, "A", lifetime=6)
            ok = True
        except Exception:
            ok = False
    _mx_cache[domain] = ok
    return ok


def domain_of(email):
    return email.split("@", 1)[1].lower()


def reg_domain(host):
    if _tld is None:
        return host
    e = _tld(host)
    return (e.domain + "." + e.suffix).lower() if e.domain else host


def company_matches(email, company, cfg):
    dom = domain_of(email)
    if dom in cfg["freemail"]:
        return "freemail"
    comp = re.sub(r"[^a-z0-9]", "", (company or "").lower())
    if not comp:
        return "unknown"
    root = reg_domain(dom).split(".")[0]
    if not root:
        return "unknown"
    if comp.startswith(root[:6]) or root.startswith(comp[:6]) or root in comp:
        return "match"
    return "mismatch"


def load_existing():
    if not os.path.exists(TRACKER):
        return set(), 0
    wb = openpyxl.load_workbook(TRACKER)
    ws = wb["Contacts"]
    emails, maxid = set(), 0
    for r in range(2, ws.max_row + 1):
        e = (ws.cell(r, 8).value or "").strip().lower()
        if e:
            emails.add(e)
        idv = str(ws.cell(r, 1).value or "")
        m = re.search(r"(\d+)", idv)
        if m:
            maxid = max(maxid, int(m.group(1)))
    return emails, maxid


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--test", action="store_true")
    ap.add_argument("--no-mx", action="store_true")
    ap.add_argument("--reacher", default=os.environ.get("REACHER_URL", ""),
                    help="optional http://localhost:8080 for mailbox checks")
    args = ap.parse_args()
    cfg = C.cfg(); C.ensure_out()
    today = datetime.date.today().isoformat()

    files = sorted(glob.glob(os.path.join(C.OUT, f"raw_*_{today}.csv")))
    if not files:
        files = sorted(glob.glob(os.path.join(C.OUT, "raw_*.csv")))
    raw = []
    for f in files:
        with open(f, encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                row["_file"] = os.path.basename(f)
                raw.append(row)
    print(f"merging {len(files)} file(s): {len(raw)} raw rows")

    per_stage = {}
    for r in raw:
        per_stage[r.get("stage", "?")] = per_stage.get(r.get("stage", "?"), 0) + 1

    drop = {"dup": 0, "invalid": 0, "no MX": 0, "scam": 0, "stale": 0, "placeholder": 0}
    tracker_emails, maxid = load_existing()
    seen_today = set()
    kept, scams = [], []

    for r in raw:
        em = (r.get("email") or "").strip().lower().strip(".,;:()[]<>'\"")
        if not em or "@" not in em:
            drop["placeholder"] += 1
            continue
        if r.get("scam"):
            drop["scam"] += 1
            scams.append(r)
            continue
        if validate_email:
            try:
                em = validate_email(em, check_deliverability=False).normalized.lower()
            except EmailNotValidError:
                drop["invalid"] += 1
                continue
        elif not re.fullmatch(r"[^@\s]+@[^@\s]+\.[A-Za-z]{2,}", em):
            drop["invalid"] += 1
            continue
        if em in seen_today or em in tracker_emails:
            drop["dup"] += 1
            continue
        if args.no_mx is False and not mx_ok(domain_of(em)):
            drop["no MX"] += 1
            continue
        d = r.get("date_posted") or ""
        if d and r.get("stage") != "D":
            try:
                age = (datetime.date.today() - datetime.date.fromisoformat(d[:10])).days
                if age > cfg["days_back"]:
                    drop["stale"] += 1
                    continue
            except Exception:
                pass
        match = company_matches(em, r.get("company"), cfg)
        status = "To Send"
        notes = []
        if match == "freemail":
            status = "Unverified"
            notes.append("free-mail address; verify it is a real hiring inbox")
        elif match == "mismatch":
            notes.append(f"domain does not match company ({domain_of(em)})")
        if r.get("stage") == "D":
            notes.append("from company careers/contact page")
        if not r.get("company"):
            status = "Unverified"
            notes.append("company not stated on the posting")
        seen_today.add(em)
        kept.append({"email": em, "company": (r.get("company") or "").strip()[:80],
                     "role": (r.get("role") or "").strip()[:120],
                     "location": (r.get("location") or "").strip()[:60],
                     "experience": (r.get("experience") or "").strip()[:40],
                     "date": d[:10], "url": (r.get("source_url") or "").strip(),
                     "status": status, "notes": "; ".join(notes),
                     "cat": C.category_of(r.get("role") or ""),
                     "prio": C.priority_of(r.get("location"), r.get("experience"))})

    print(f"kept {len(kept)} | dropped {drop}")

    # ---- write scams file for reference
    if scams:
        with open(os.path.join(C.OUT, "scams.csv"), "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(scams[0].keys()))
            w.writeheader(); w.writerows(scams)

    if not kept:
        print("nothing to add")
        return

    if args.test:
        for k in kept[:10]:
            print(f"  {k['prio']:6} {k['cat'][:14]:14} {k['company'][:26]:26} {k['email'][:34]:34} {k['status']}")
        print("\n(test mode: tracker not modified)")
        return

    # ---- load into tracker, preserving existing rows/formatting
    wb = openpyxl.load_workbook(TRACKER)
    ws = wb["Contacts"]
    start = ws.max_row + 1
    AR = "Arial"
    thin = Side(style="thin", color="D0D0D0")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    n = 0
    for k in kept:
        maxid += 1
        r = start + n
        vals = [f"HR-{maxid:03d}", k["company"], k["role"], k["cat"], k["location"],
                k["experience"], "", k["email"], k["url"],
                k["date"] or None, k["prio"], None, None, None, None, k["status"], k["notes"]]
        for c, v in enumerate(vals, start=1):
            cell = ws.cell(r, c, v)
            cell.font = Font(name=AR, size=10)
            cell.border = border
            cell.alignment = Alignment(vertical="top", wrap_text=c in (3, 9, 17))
        ws.cell(r, 14).value = f'=IF(M{r}="","",WORKDAY(M{r},4))'
        n += 1
    last = ws.max_row

    # extend validation + conditional formatting ranges to the new last row
    for dv in ws.data_validations.dataValidation:
        sq = str(dv.sqref)
        for token in sq.split():
            col = re.match(r"([A-Z]+)(\d+)", token)
            if col:
                dv.sqref = re.sub(r"([A-Z]+)(\d+):([A-Z]+)(\d+)",
                                  lambda m: f"{m.group(1)}2:{m.group(3)}{last}", token)
    green = PatternFill("solid", fgColor="C6EFCE")
    grey = PatternFill("solid", fgColor="D9D9D9")
    yellow = PatternFill("solid", fgColor="FFEB9C")
    ws.conditional_formatting.add(f"A{start}:Q{last}",
        FormulaRule(formula=[f'OR($P{start}="Replied",$P{start}="Interview",$P{start}="Offer")'], fill=green))
    ws.conditional_formatting.add(f"A{start}:Q{last}",
        FormulaRule(formula=[f'OR($P{start}="Bounced",$P{start}="Rejected",$P{start}="Scam – skipped")'], fill=grey))
    ws.conditional_formatting.add(f"A{start}:Q{last}",
        FormulaRule(formula=[f'AND($P{start}="Sent",$N{start}<>"",$N{start}<=TODAY())'], fill=yellow))

    # ---- daily log
    ds = wb["Daily Log"]
    lr = ds.max_row + 1
    ds.cell(lr, 1).value = datetime.date.today()
    ds.cell(lr, 2).value = sum(per_stage.values())
    ds.cell(lr, 3).value = n
    ds.cell(lr, 4).value = 0
    ds.cell(lr, 5).value = 0
    ds.cell(lr, 6).value = drop["dup"]
    ds.cell(lr, 1).number_format = "yyyy-mm-dd"

    wb.save(TRACKER)
    print(f"\nAdded {n} rows to tracker (rows {start}-{last})")

    report = {
        "date": today, "stages": per_stage, "dropped": drop,
        "added": n,
        "priority": {}, "unverified": sum(1 for k in kept if k["status"] == "Unverified"),
    }
    for k in kept:
        report["priority"][k["prio"]] = report["priority"].get(k["prio"], 0) + 1
    json.dump(report, open(os.path.join(C.OUT, "stage_e_report.json"), "w"), indent=1)

    if not args.reacher:
        print("NOTE: mailbox verification (Reacher) skipped - no REACHER_URL set, no Docker assumed.")
    print("\nTop new contacts (High first):")
    for k in sorted(kept, key=lambda x: {"High": 0, "Medium": 1, "Low": 2}[x["prio"]])[:20]:
        print(f"  {k['prio']:6} {k['company'][:24]:24} {k['role'][:30]:30} {k['email'][:32]:32} {k['url'][:44]}")


if __name__ == "__main__":
    main()
