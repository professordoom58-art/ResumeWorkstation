# -*- coding: utf-8 -*-
"""Telegram progress pings: what is done, what is left, and what kind of jobs are being applied to.

Setup (once):
  1. Store the bot token as a Windows *user environment variable* (never in a file):
       [Environment]::SetEnvironmentVariable("TELEGRAM_BOT_TOKEN", "<token>", "User")
  2. Send any message (e.g. /start) to your bot in Telegram, then run:
       .venv\\Scripts\\python.exe src\\telegram_status.py --setup     # saves your chat id to profile/telegram.json
  3. Schedule it every 10 minutes:
       .venv\\Scripts\\python.exe src\\telegram_status.py --install   # Windows Task Scheduler, runs --once every 10 min

Run by hand:
  --once     send one status message now
  --always   with --once: send even when nothing has changed (default: after 60 idle minutes it sends a single
             "idle" note and then stays quiet until something moves again)
  --test     send a test message
  --uninstall  remove the scheduled task

Reads: jobs/progress.json (sweep), jobs/Job_Leads_<today>.xlsx (rows and statuses), outbox/sent_all.json (sends),
NEEDS_*.md (open items for the user). Sends nothing but counts, companies and role titles.
"""
import os, sys, json, glob, re, datetime, argparse, hashlib, subprocess
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if sys.stdout is None:  # pythonw.exe (Task Scheduler) has no console: log to a file instead
    os.makedirs(os.path.join(ROOT, "jobs"), exist_ok=True)
    sys.stdout = sys.stderr = open(os.path.join(ROOT, "jobs", "telegram.log"), "a", encoding="utf-8", buffering=1)
    print(f"--- {datetime.datetime.now():%Y-%m-%d %H:%M:%S}")
else:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.join(ROOT, "scraper"))
CFG_F = os.path.join(ROOT, "profile", "telegram.json")
STATE_F = os.path.join(ROOT, "profile", "telegram_state.json")
TASK = "ResumeWorkstation Telegram Status"
IDLE_MIN = 60
API = "https://api.telegram.org/bot{}/{}"


# ---------------------------------------------------------------- telegram
def token():
    t = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not t and os.name == "nt":  # a scheduled task may not see a freshly set variable: read the registry
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
                t = winreg.QueryValueEx(k, "TELEGRAM_BOT_TOKEN")[0]
        except OSError:
            pass
    if not t:
        sys.exit("TELEGRAM_BOT_TOKEN is not set (user environment variable) - see --help")
    return t.strip()


def call(method, **params):
    import requests
    r = requests.post(API.format(token(), method), json=params, timeout=30)
    data = r.json()
    if not data.get("ok"):
        raise RuntimeError(f"telegram {method} failed: {data.get('description')}")
    return data["result"]


def chat_id():
    if not os.path.exists(CFG_F):
        sys.exit("no chat id yet - message the bot, then run --setup")
    return json.load(open(CFG_F, encoding="utf-8"))["chat_id"]


def send(text):
    call("sendMessage", chat_id=chat_id(), text=text, parse_mode="HTML", disable_web_page_preview=True)


# ---------------------------------------------------------------- status
def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def local_dt(iso):
    try:
        return datetime.datetime.fromisoformat(str(iso).replace("Z", "+00:00")).astimezone().replace(tzinfo=None)
    except ValueError:
        return None


def category(title):
    try:
        import common
        c = common.category_of(title)
    except Exception:
        c = "Other"
    if c == "Other" and re.search(r"pharmac", title or "", re.I):
        c = "Pharmacist"
    return c


def read_excel(today):
    path = os.path.join(ROOT, "jobs", f"Job_Leads_{today}.xlsx")
    if not os.path.exists(path):
        return None
    import openpyxl
    ws = openpyxl.load_workbook(path, read_only=True, data_only=True).worksheets[0]
    rows = list(ws.iter_rows(values_only=True))
    hdr = [str(h) for h in rows[0]]
    return [dict(zip(hdr, r)) for r in rows[1:] if r and r[0]]


def build_status():
    now = datetime.datetime.now()
    today = now.date().isoformat()
    lines = [f"<b>📋 Job hunt — {now:%d %b, %H:%M}</b>"]

    # sweep
    pf = os.path.join(ROOT, "jobs", "progress.json")
    p = json.load(open(pf, encoding="utf-8")) if os.path.exists(pf) else {}
    if p.get("date") == today and p.get("state") == "running":
        age = (now - datetime.datetime.fromisoformat(p["updated"])).total_seconds() / 60
        stale = " ⚠️ no update for %d min — stopped?" % age if age > 15 else ""
        lines.append(f"🔎 <b>Sweep running</b>: query {p['queries_done']}/{p['queries_total']} "
                     f"({esc(p['term'])} @ {esc(p['location'])}) — {p['leads']}/{p['target']} leads{stale}")
    elif p.get("date") == today and p.get("state") == "finished":
        lines.append(f"🔎 Sweep done: <b>{p['leads']}/{p['target']}</b> leads found")
    else:
        lines.append("🔎 Sweep: not run yet today")

    # excel
    rows = read_excel(today) or []
    by_id = {str(r.get("ID")): r for r in rows}
    if rows:
        st = Counter(str(r.get("Status") or "") for r in rows)
        left = st.get("To Send", 0) + st.get("Approved", 0)
        done = sum(v for k, v in st.items() if k in ("Sent", "Followed Up", "Replied", "Interview", "Offer"))
        skipped = sum(v for k, v in st.items() if k.startswith("Skipped") or k in ("Rejected", "Bounced", "Expired"))
        lines.append(f"📊 Excel: {len(rows)} leads — ✅ {done} done · ⏳ {left} left · ⛔ {skipped} skipped")
        good = [k for k in ("Replied", "Interview", "Offer") if st.get(k)]
        if good:
            lines.append("🎉 " + ", ".join(f"{st[k]} {k}" for k in good))
        types = Counter(category(r.get("Role / Opening")) for r in rows if str(r.get("Status") or "") in ("To Send", "Approved", "Sent"))
        if types:
            lines.append("🧪 Job types: " + ", ".join(f"{k} {v}" for k, v in types.most_common(6)))
        fits = Counter(str(r.get("Fit") or "") for r in rows if str(r.get("Status") or "") in ("To Send", "Approved"))
        if fits:
            lines.append("🎯 Left by fit: " + ", ".join(f"{k} {v}" for k, v in fits.most_common()))
        nxt = [r for r in rows if str(r.get("Status") or "") in ("To Send", "Approved")][:3]
        if nxt:
            lines.append("⏭️ Next: " + "; ".join(f"{esc(r.get('Role / Opening'))[:45]} @ {esc(r.get('Company'))[:30]}" for r in nxt))

    # sends today
    sf = os.path.join(ROOT, "outbox", "sent_all.json")
    sent = json.load(open(sf, encoding="utf-8")) if os.path.exists(sf) else {}
    todays = [(k, v, local_dt(v.get("at"))) for k, v in sent.items()]
    todays = sorted([t for t in todays if t[2] and t[2].date() == now.date()], key=lambda t: t[2])
    if todays:
        res = Counter(v.get("result") for _, v, _ in todays)
        wa = sum(1 for _, v, _ in todays if str(v.get("to", "")).startswith("whatsapp:") and v.get("result") == "SENT")
        em = res.get("SENT", 0) - wa
        fail = sum(c for r, c in res.items() if r not in ("SENT", "SKIP_EXISTING"))
        lines.append(f"📤 Sent today: <b>{em} email · {wa} WhatsApp</b>" + (f" · ❌ {fail} failed" if fail else ""))
        k, v, t = todays[-1]
        row = by_id.get(k.replace("-WA", ""))
        what = f"{esc(row.get('Role / Opening'))[:50]} @ {esc(row.get('Company'))[:35]}" if row else esc(v.get("to"))
        active = (now - t).total_seconds() < 15 * 60
        lines.append(f"{'▶️ Now' if active else '🕘 Last'}: {what} — {esc(v.get('result'))} at {t:%H:%M}")
    else:
        lines.append("📤 Sent today: none yet")

    # open items for the user
    for f in glob.glob(os.path.join(ROOT, "NEEDS_*.md")):
        open_items = [l for l in open(f, encoding="utf-8") if re.match(r"\s*[-*] \[ \]", l)]
        if open_items:
            lines.append(f"🙋 Waiting on you: {len(open_items)} item(s) in {os.path.basename(f)}")

    fp = hashlib.sha1("\n".join(lines[1:]).encode()).hexdigest()
    return "\n".join(lines), fp


# ---------------------------------------------------------------- commands
def once(always=False):
    text, fp = build_status()
    st = json.load(open(STATE_F, encoding="utf-8")) if os.path.exists(STATE_F) else {}
    now = datetime.datetime.now()
    if fp != st.get("fp"):
        st.update(fp=fp, changed=now.isoformat(timespec="seconds"), idle_sent=False)
    idle_for = (now - datetime.datetime.fromisoformat(st["changed"])).total_seconds() / 60
    if not always and idle_for >= IDLE_MIN:
        if not st.get("idle_sent"):
            send(text + f"\n\n💤 Nothing has moved for {int(idle_for)} min. Pausing pings until something changes.")
            st["idle_sent"] = True
            print("sent idle note")
        else:
            print("idle - skipped")
    else:
        send(text)
        print(text)
    json.dump(st, open(STATE_F, "w", encoding="utf-8"))


def setup():
    ups = call("getUpdates")
    chats = {u["message"]["chat"]["id"]: u["message"]["chat"] for u in ups if "message" in u}
    if not chats:
        sys.exit("no messages yet - open your bot in Telegram, press Start (or send any message), then run --setup again")
    cid, chat = list(chats.items())[-1]
    os.makedirs(os.path.dirname(CFG_F), exist_ok=True)
    json.dump({"chat_id": cid}, open(CFG_F, "w", encoding="utf-8"))
    print(f"saved chat id for {chat.get('first_name') or chat.get('title')} -> {CFG_F}")
    send("✅ ResumeWorkstation connected. You'll get progress here every 10 minutes while work is running.")


def install():
    pyw = os.path.join(ROOT, ".venv", "Scripts", "pythonw.exe")
    script = os.path.abspath(__file__)
    ps = (f"$a = New-ScheduledTaskAction -Execute '{pyw}' -Argument '\"{script}\" --once' -WorkingDirectory '{ROOT}';"
          f"$t = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 10);"
          f"$s = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopIfGoingOnBatteries -AllowStartIfOnBatteries "
          f"-ExecutionTimeLimit (New-TimeSpan -Minutes 5);"
          f"Register-ScheduledTask -TaskName '{TASK}' -Action $a -Trigger $t -Settings $s -Force | Out-Null;"
          f"Get-ScheduledTask -TaskName '{TASK}' | Select-Object TaskName, State | Format-List")
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=True)


def uninstall():
    subprocess.run(["powershell", "-NoProfile", "-Command",
                    f"Unregister-ScheduledTask -TaskName '{TASK}' -Confirm:$false"], check=True)
    print("removed scheduled task", TASK)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    for f in ("once", "setup", "install", "uninstall", "test", "print"):
        g.add_argument("--" + f, action="store_true")
    ap.add_argument("--always", action="store_true")
    a = ap.parse_args()
    if a.setup:
        setup()
    elif a.install:
        install()
    elif a.uninstall:
        uninstall()
    elif a.test:
        send("🔔 Test from ResumeWorkstation")
        print("sent")
    elif a.print:
        print(build_status()[0])
    else:
        once(a.always)
