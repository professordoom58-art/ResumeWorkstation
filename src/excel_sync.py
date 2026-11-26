# -*- coding: utf-8 -*-
"""Bridge between the day's Excel (jobs/Job_Leads_<date>.xlsx) and the senders.

  python src/excel_sync.py manifest [--date YYYY-MM-DD]
      For every row whose Status is "To Send" or "Approved" and whose "Resume file" exists, pick up the message files
        outbox/<date>/<ID>.txt            email body; first line "Subject: ..."
        outbox/<date>/<ID>_whatsapp.txt   WhatsApp text (only used when the row has a phone)
      and write outbox/<date>/manifest_email.json (for src/browser/gmail_send.js)
            and outbox/<date>/manifest_whatsapp.json (for src/browser/wa_batch.js).
      Rows whose address/number is already in outbox/sent_all.json are left out.

  python src/excel_sync.py sync [--date YYYY-MM-DD]
      Copy results from outbox/sent_all.json back into the Excel: Status -> Sent, Date Sent, Notes.
"""
import os, sys, json, re, datetime, argparse
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SENT_F = os.path.join(ROOT, "outbox", "sent_all.json")


def load(date):
    import openpyxl
    path = os.path.join(ROOT, "jobs", f"Job_Leads_{date}.xlsx")
    if not os.path.exists(path):
        sys.exit(f"no Excel for {date}: {path}")
    wb = openpyxl.load_workbook(path)
    ws = wb.worksheets[0]
    hdr = {str(c.value): c.column for c in ws[1]}
    return path, wb, ws, hdr


def sent_map():
    s = json.load(open(SENT_F, encoding="utf-8")) if os.path.exists(SENT_F) else {}
    return s, {str(v.get("to", "")).lower(): (k, v) for k, v in s.items() if v.get("result") in ("SENT", "SKIP_EXISTING", "UNSURE")}


def manifest(date):
    path, wb, ws, H = load(date)
    _, by_to = sent_map()
    box = os.path.join("outbox", date)
    em, wa, missing = [], [], []
    for r in range(2, ws.max_row + 1):
        g = lambda name: ws.cell(r, H[name]).value
        rid, status, resume = g("ID"), str(g("Status") or ""), str(g("Resume file") or "").strip()
        if not rid or status not in ("To Send", "Approved"):
            continue
        if not resume or not os.path.exists(os.path.join(ROOT, resume)):
            missing.append(f"{rid}: resume file missing ({resume or 'blank'})")
            continue
        email = (str(g("HR Email") or "").split(",")[0]).strip().lower()
        phone = re.sub(r"\D", "", str(g("Phone / WhatsApp") or "").split(",")[0])
        body_e, body_w = os.path.join(box, f"{rid}.txt"), os.path.join(box, f"{rid}_whatsapp.txt")
        if email and email not in by_to:
            if os.path.exists(os.path.join(ROOT, body_e)):
                em.append(dict(id=rid, to=email, file=body_e.replace("\\", "/"), attach=resume.replace("\\", "/")))
            else:
                missing.append(f"{rid}: no email body {body_e}")
        if phone and f"whatsapp:+{phone}" not in by_to and os.path.exists(os.path.join(ROOT, body_w)):
            wa.append(dict(id=rid + "-WA", phone=phone, file=body_w.replace("\\", "/"), attach=resume.replace("\\", "/")))
    os.makedirs(os.path.join(ROOT, box), exist_ok=True)
    for name, data in (("manifest_email.json", em), ("manifest_whatsapp.json", wa)):
        json.dump(data, open(os.path.join(ROOT, box, name), "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print(f"email: {len(em)} -> {box}/manifest_email.json\nwhatsapp: {len(wa)} -> {box}/manifest_whatsapp.json")
    for m in missing:
        print("  skipped", m)


def sync(date):
    path, wb, ws, H = load(date)
    sent, by_to = sent_map()
    n = 0
    for r in range(2, ws.max_row + 1):
        rid = ws.cell(r, H["ID"]).value
        if not rid:
            continue
        recs = [(k, v) for k, v in sent.items() if k in (rid, rid + "-WA")]
        email = (str(ws.cell(r, H["HR Email"]).value or "").split(",")[0]).strip().lower()
        if not recs and email in by_to:
            recs = [by_to[email]]
        ok = [(k, v) for k, v in recs if v.get("result") == "SENT"]
        if not ok:
            if recs:
                ws.cell(r, H["Notes"]).value = "; ".join(f"{k}: {v.get('result')} {v.get('note', '')}" for k, v in recs)[:250]
            continue
        k, v = ok[0]
        ws.cell(r, H["Status"]).value = "Sent"
        ws.cell(r, H["Date Sent"]).value = datetime.date.fromisoformat(str(v.get("at", ""))[:10])
        ws.cell(r, H["Date Sent"]).number_format = "dd-mmm-yyyy"
        ws.cell(r, H["Notes"]).value = "; ".join(f"{kk} -> {vv.get('to')}" for kk, vv in ok)
        n += 1
    wb.save(path)
    print(f"marked {n} rows Sent in {path}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=("manifest", "sync"))
    ap.add_argument("--date", default=datetime.date.today().isoformat())
    a = ap.parse_args()
    manifest(a.date) if a.cmd == "manifest" else sync(a.date)
