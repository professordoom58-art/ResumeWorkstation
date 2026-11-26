# -*- coding: utf-8 -*-
"""Load one sweep into its own tracker tab, "Pharma Only <dd-Mon>".

Usage:  python scraper/build_sweep_tab.py [--date YYYY-MM-DD] [--log]
Reads   scraper/out/raw_pharma_<date>_p*.json (written by sweep_pharma.py; default date = today).
Rows    leads that pass the same pharma-only filters and carry a published email or WhatsApp number.
Status  'Sent' if the address/number is already in outbox/sent_all.json (ID noted), 'Skipped – scam' on scam words,
        'Unverified' on a malformed address, else 'To Send'.
The tracker is backed up to scraper/out/ before it is written. --log appends a Daily Log row for the run."""
import os, sys, json, glob, datetime, re, shutil
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C
from sweep_pharma import DEGREE, PHARMA_TITLE, BAD_TITLE
import openpyxl
from openpyxl.styles import Font, Alignment, Border, Side, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.formatting.rule import FormulaRule
from openpyxl.comments import Comment

def _arg(name, default=None):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


RUN_DATE = datetime.date.fromisoformat(_arg("--date", datetime.date.today().isoformat()))
TAB = f"Pharma Only {RUN_DATE:%d-%b}"
TRACKER = os.path.join(C.ROOT, "HR_Outreach_Tracker.xlsx")
COLS = ["ID", "Company", "Role / Opening", "Category", "Location", "Experience asked", "HR Name", "HR Email", "Source URL",
        "Posted Date", "Priority", "Resume Sent", "Date Sent", "Follow-up 1 Due", "Follow-up Sent", "Status", "Notes"]
RULE = ("SEARCH RULE (since 25 Nov 2026): pharma / medical-field roles only that require a B.Pharm, M.Pharm, Pharm.D, D.Pharm "
        "or medical degree (MBBS/BDS/BAMS/BHMS/BUMS), or are inherently pharma (pharmacist, PV, clinical research, CDM, "
        "regulatory, QA/QC, medical coding/writing/affairs, MR). Never customer support / BPO / telecaller / data entry / "
        "front office / generic sales. Locations and pay floor unchanged.")

def main():
    sent = json.load(open(os.path.join(C.ROOT, "outbox", "sent_all.json"), encoding="utf-8"))
    by_to = {}
    for k, v in sent.items():
        if v.get("result") in ("SENT", "SKIP_EXISTING") or (v.get("result") == "ERROR" and "filechooser" in v.get("note", "")):
            by_to.setdefault(str(v.get("to", "")).lower(), (k, str(v.get("at", ""))[:10]))
    files = sorted(glob.glob(os.path.join(C.OUT, f"raw_pharma_{RUN_DATE.isoformat()}_p*.json")))
    if not files:
        sys.exit(f"no sweep files for {RUN_DATE} in {C.OUT} - run sweep_pharma.py first")
    rows, seen = [], set()
    for f in files:
        if not os.path.exists(f):
            continue
        tag = os.path.basename(f).replace("raw_", "").replace(".json", "")
        for r in json.load(open(f, encoding="utf-8")):
            title, desc = r["role"], r.get("desc", "")
            if r.get("kind") == "video" or BAD_TITLE.search(title):
                continue
            deg = DEGREE.search(title + " " + desc)
            if not deg and not PHARMA_TITLE.search(title):
                continue
            to = (r["emails"] or [])[:1] or ["whatsapp:+91" + w[-10:] for w in r.get("whatsapp", [])][:1]
            if not to:
                continue
            to = to[0].lower()
            if (to, r["source_url"]) in seen or r["source_url"] in {x[1] for x in seen}:
                continue
            seen.add((to, r["source_url"]))
            loc = (r.get("locline") or r.get("location") or "").strip()[:60]
            pay = r.get("pay_month")
            pays = "pay not stated" if not pay else (f"₹{pay:,}/month" if pay < 200000 else f"₹{pay / 100000:.1f} LPA")
            if r.get("scam"):
                status, d, note = "Skipped – scam", "", f"scam words: {r['scam']}"
            elif not re.match(r"^(whatsapp:\+91\d{10}|[a-z0-9][^@\s]*@[a-z0-9.-]+\.[a-z]{2,})$", to):
                status, d, note = "Unverified", "", "malformed address in posting – do not guess the real one; apply via the portal link"
            elif to in by_to:
                k, d = by_to[to]
                status, note = "Sent", f"already contacted as {k} on {d}"
            else:
                status, d, note = "To Send", "", "not yet contacted"
            rows.append([r["company"].strip(), re.sub(r"\s+", " ", title).strip()[:110], C.category_of(title), loc, (r.get("experience") or "")[:30],
                         to, r["source_url"], r.get("date_posted") or None, C.priority_of(loc, r.get("experience") or ""), d, status,
                         f"{tag}; degree match: {deg.group(0) if deg else 'pharma title'}; {pays}; {note}"])
    order = {"To Send": 0, "Unverified": 1, "Sent": 2, "Skipped – scam": 3}
    rows.sort(key=lambda x: (order.get(x[10], 3), {"High": 0, "Medium": 1, "Low": 2}.get(x[8], 3)))

    shutil.copy2(TRACKER, os.path.join(C.OUT, f"HR_Outreach_Tracker.backup_{datetime.datetime.now():%Y-%m-%d_%H%M}.xlsx"))
    wb = openpyxl.load_workbook(TRACKER)
    if TAB in wb.sheetnames:
        del wb[TAB]
    ws = wb.create_sheet(TAB, 1)
    thin = Side(style="thin", color="D0D0D0"); border = Border(left=thin, right=thin, top=thin, bottom=thin)
    srcws = wb["Contacts"]
    for c, h in enumerate(COLS, 1):
        cell = ws.cell(1, c, h)
        cell.font = Font(name="Arial", size=10, bold=True, color="FFFFFF"); cell.fill = PatternFill("solid", fgColor="375623")
        cell.alignment = Alignment(vertical="center", wrap_text=True); cell.border = border
        ws.column_dimensions[cell.column_letter].width = srcws.column_dimensions[cell.column_letter].width or 14
    ws["A1"].comment = Comment(RULE, "Claude")
    ws.freeze_panes = "A2"
    for i, r in enumerate(rows, start=2):
        co, role, cat, loc, ex, to, url, posted, pr, d, s, note = r
        vals = [f"PH-{i - 1:02d}", co, role, cat, loc, ex, "", to, url,
                datetime.date.fromisoformat(posted[:10]) if posted and re.match(r"\d{4}-\d\d-\d\d", str(posted)) else None,
                pr, "", datetime.date.fromisoformat(d) if d else None, None, None, s, note]
        for c, v in enumerate(vals, 1):
            cell = ws.cell(i, c, v); cell.font = Font(name="Arial", size=10); cell.border = border
            cell.alignment = Alignment(vertical="top", wrap_text=c in (3, 9, 17))
        for c in (10, 13, 14):
            ws.cell(i, c).number_format = "dd-mmm-yyyy"
        ws.cell(i, 14).value = f'=IF(M{i}="","",WORKDAY(M{i},4))'
    last = max(2, len(rows) + 1)
    for col, lst in (("D", "PV,Clinical Research,CDM,Regulatory,QA/QC,Medical Info,Med Coding,Sales/MR/BD,Other"), ("K", "High,Medium,Low"),
                     ("P", "To Send,Drafted,Sent,Followed Up,Replied,Interview,Offer,Rejected,Bounced,Expired,Unverified,Skipped – not eligible,Skipped – scam")):
        dv = DataValidation(type="list", formula1=f'"{lst}"', allow_blank=True); dv.add(f"{col}2:{col}{last + 200}"); ws.add_data_validation(dv)
    rng = f"A2:Q{last + 200}"
    ws.conditional_formatting.add(rng, FormulaRule(formula=['OR($P2="Replied",$P2="Interview",$P2="Offer")'], fill=PatternFill("solid", fgColor="C6EFCE")))
    ws.conditional_formatting.add(rng, FormulaRule(formula=['OR($P2="Bounced",$P2="Rejected",LEFT($P2,7)="Skipped")'], fill=PatternFill("solid", fgColor="D9D9D9")))
    ws.conditional_formatting.add(rng, FormulaRule(formula=['AND($P2="Sent",$N2<>"",$N2<=TODAY())'], fill=PatternFill("solid", fgColor="FFEB9C")))
    ws.auto_filter.ref = f"A1:Q{last}"
    from collections import Counter
    cnt = Counter(r[10] for r in rows)
    if "--log" in sys.argv:
        dl = wb["Daily Log"]
        for rr in range(dl.max_row, 1, -1):
            if str(dl.cell(rr, 7).value or "").startswith(TAB):
                dl.delete_rows(rr)
        lr = dl.max_row + 1
        for c, v in enumerate([RUN_DATE, len(rows), 0, 0, 0, 0,
                               f"{TAB} – pharma-only sweep; {dict(cnt)}"], 1):
            dl.cell(lr, c, v)
        dl.cell(lr, 1).number_format = "yyyy-mm-dd"
    wb.save(TRACKER)
    print(f"tab '{TAB}': {len(rows)} rows |", dict(cnt), "| by category:", dict(Counter(r[2] for r in rows)))


if __name__ == "__main__":
    main()
