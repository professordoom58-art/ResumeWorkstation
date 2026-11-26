# ResumeWorkstation

An AI-driven job-application workstation. Attach your resume to an AI coding agent (Claude Code, Codex, Gemini CLI, …), say **"read CLAUDE.md"**, and it runs the whole loop. It reads your resume, finds today's jobs, builds an Excel, asks before applying, then sends a tailored resume to each employer. It never makes a claim your resume can't back.

## How it works

1. **Reads the resume** and records every fact in a private profile (`profile/PROFILE.md`): employers, titles, dates, every bullet and number verbatim, education, certificates and preferences. This profile is the only source the agent may use.
2. **Derives the search from what you did, not just your titles.** Each duty, tool and domain is mapped to the roles where that work is the core of the job. A claims reviewer who checked medical records against ICD-10 codes is also searched for medical coding, medical review and PV-intake roles. The mapping is saved, with comments, in `profile/search.yaml`.
3. **Sweeps job boards** (Indeed, Naukri, Glassdoor via [JobSpy](https://github.com/speedyapply/JobSpy)) for postings from the last 7 days:
   - **Hard gates first:** blacklist, deny-locations, excluded titles, pay floor, maximum experience, scam words ("registration fee", "security deposit" …).
   - **Relevance is scored on the description**: 1 point per keyword hit, 2 if the hit is in the title. Each lead gets a **Fit** band: Strong / Apply / Maybe.
   - **Keeps only postings that publish an email and a phone number**, and stops at **60 leads**.
   - **Dedupes** on a canonical URL (tracking parameters stripped) and on company + role. It also skips anyone already contacted and anything listed on an earlier day.
4. **Writes today's Excel**, `jobs/Job_Leads_<date>.xlsx`, with status dropdowns, auto follow-up dates (`WORKDAY` + 4), colour coding and a run-info sheet. Then it asks: *"Excel created with N leads. Start applying?"*
5. **On a yes, applies:**
   - Builds a tailored **one-page** resume per employer (DOCX → PDF through Word).
   - A **fact-check gate** refuses any resume whose employers, titles, dates or numbers differ from the profile.
   - Writes a short email and a WhatsApp message for each lead.
   - Sends them through *your own* signed-in Gmail and WhatsApp Web, then writes the results back into the Excel.

A shared duplicate guard (`outbox/sent_all.json`) makes sure nobody is contacted twice, whichever script sends.

```
resume ──► profile/PROFILE.md ──► profile/search.yaml ──► scraper/find_jobs.py ──► jobs/Job_Leads_<date>.xlsx
                                                                                          │  "start applying?"
                                                                                          ▼
 outbox/sent_all.json ◄── gmail_send.js / wa_batch.js ◄── excel_sync.py manifest ◄── build_resume.py (per job, fact-checked)
          │
          └──► excel_sync.py sync ──► Excel rows marked Sent, follow-up dates filled
```

## Requirements

- Windows 10/11 with **Microsoft Word** (Word does the PDF export through COM)
- Python 3.11, Node.js 18+, Google Chrome

## Setup

```powershell
git clone https://github.com/professordoom58-art/ResumeWorkstation.git
cd ResumeWorkstation
py -3.11 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
cd src\browser; npm install; cd ..\..
mkdir outbox, jobs, profile -Force
if (-not (Test-Path outbox\sent_all.json)) { '{}' | Out-File -Encoding ascii outbox\sent_all.json }
.venv\Scripts\python.exe -c "import jobspy, openpyxl, docx, pymupdf; print('ok')"
```

Start the automation Chrome. Sign in to Gmail and WhatsApp Web **once** in that window; the session is kept in a local profile.

```powershell
node src\browser\start.js                        # Chrome with remote debugging on port 9223
curl.exe -s http://127.0.0.1:9223/json/version   # should print Chrome's version JSON
```

## Usage

**With an AI agent:** attach your resume and say **"read CLAUDE.md"**. On later days, just say "read CLAUDE.md"; the profile is reused.

**By hand:**

```powershell
# 1. Profile: copy the templates in profile\ (*.example.*) and fill them from your resume
#    PROFILE.md, resume_base.json, workday.json, search.yaml, blacklist.txt (optional)

# 2. Find today's leads -> jobs\Job_Leads_<date>.xlsx
.venv\Scripts\python.exe scraper\find_jobs.py                       # defaults from search.yaml
.venv\Scripts\python.exe scraper\find_jobs.py --target 30 --need any  # need: both | email | phone | any

# 3. Per lead: copy profile\resume_base.json to tailored\<Company>_<Role>\spec.json, tailor it, build it
.venv\Scripts\python.exe src\build_resume.py "tailored\Acme_Drug-Safety-Associate\spec.json"
#    -> fact-check, then DOCX + PDF; exits 1 if a fact changed or the PDF is not exactly one page.
#    Put the PDF path in the row's "Resume file" column.

# 4. Messages: outbox\<date>\<ID>.txt (line 1 "Subject: ...") and outbox\<date>\<ID>_whatsapp.txt
.venv\Scripts\python.exe src\excel_sync.py manifest
node src\browser\gmail_send.js outbox\<date>\manifest_email.json
node src\browser\wa_batch.js  outbox\<date>\manifest_whatsapp.json

# 5. Record and verify
.venv\Scripts\python.exe src\excel_sync.py sync                       # Excel rows -> Sent + dates
node src\browser\gmail_search_sent.js outbox\<date>\manifest_email.json  # in:sent to:<address> per recipient
```

## Progress on your phone (Telegram)

Every 10 minutes a bot messages you: sweep progress, leads done/left, the job types in today's list, the next
roles up and what is being sent right now. After 60 quiet minutes it sends one "idle" note and goes silent until
work resumes.

1. Create a bot with [@BotFather](https://t.me/BotFather) (`/newbot`) and copy its token.
2. Store the token as a user environment variable (never in a file):
   `[Environment]::SetEnvironmentVariable("TELEGRAM_BOT_TOKEN", "<token>", "User")`
3. Open your bot in Telegram and press **Start**, then:
   ```powershell
   .venv\Scripts\python.exe src	elegram_status.py --setup     # saves your chat id, sends a confirmation
   .venv\Scripts\python.exe src	elegram_status.py --install   # Task Scheduler: every 10 minutes
   ```
   `--once` sends one now, `--print` previews without sending, and `--uninstall` stops the pings.

## The search profile (`profile/search.yaml`)

| Key | Meaning |
|---|---|
| `search_terms` | Roles to search: held titles **plus** roles built from duties and skills (15–25 terms) |
| `match_keywords` | Skills, tools, degrees and domain words scored against the posting text |
| `min_match` | Minimum relevance score to keep a lead (default 2) |
| `locations` / `allow_locations` / `deny_locations` | Cities searched; regexes a location must / must not match |
| `title_exclude` | Title regexes always dropped (e.g. customer support, BPO, data entry) |
| `pay_floor_month` | Drop if the posting's stated maximum pay is below this (pay not stated → kept) |
| `max_years_asked` | Drop if the posting's minimum experience is above this |
| `target`, `need_contact` | How many leads to stop at; `both` = email **and** phone required |
| `sites`, `hours_old`, `results_per_query`, `delay_seconds` | JobSpy sources, freshness window, page size, pause between queries |

Template: [`profile/search.example.yaml`](profile/search.example.yaml).

## Repository layout

| Path | Purpose |
|---|---|
| `CLAUDE.md` | The agent's full instruction set: workflow, honesty rules, resume spec, message and sending rules |
| `profile/*.example.*` | Templates for the private profile (facts, resume spec, portal data, search profile, blacklist) |
| `scraper/find_jobs.py` | Resume-driven JobSpy sweep that writes the daily Excel |
| `scraper/run_all.py`, `stage_a…e_*.py`, `config.yaml` | Multi-source HR-email scraper: job boards, sector sites, careers pages; syntax- and MX-checked, deduped |
| `scraper/sweep_pharma.py`, `build_sweep_tab.py` | Earlier pharma-only sweep feeding tabs of a tracker workbook |
| `src/resume_lib.py`, `src/build_resume.py` | DOCX resume generator, PDF export through Word, fact-check and one-page check |
| `src/excel_sync.py` | Daily Excel ⇄ send manifests ⇄ duplicate guard |
| `src/telegram_status.py` | Telegram progress pings (Task Scheduler, every 10 min) |
| `src/browser/` | Playwright over Chrome DevTools: `gmail_send.js`, `gmail_search_sent.js`, `gmail_read.js`, `gmail_list.js`, `wa_batch.js`, `wa_send.js`, `wa_doc.js`, `workday.js` |

## Known limits

- **Naukri** returns no job description through JobSpy, so Naukri leads are scored on the title alone and rarely carry contacts. Most email and phone leads come from Indeed.
- Requiring **both** an email and a phone is strict. A full sweep can come back under 60, and the run says by how much. Widen `search_terms`, lower `min_match`, or use `--need any`.
- **Indeed** often reports only a state code ("HR, India"). The searched city is used for the location check and shown in brackets.
- **WhatsApp Web** cannot message Meta-managed business chats ("Uses AI from Meta") and sometimes fails silently on new chats. Those are handed back to you.
- **Workday** portals ignore synthetic clicks; a real mouse chord is used. Their "How did you hear about us?" dropdown is broken on many tenants, and those applications are recorded as blocked.
- PDF export needs Microsoft Word on Windows.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `connectOverCDP` fails / `ECONNREFUSED 127.0.0.1:9223` | Run `node src\browser\start.js` first and keep that Chrome window open |
| `ABORT: duplicate guard missing` | `outbox\sent_all.json` doesn't exist; create it as `{}` on a **fresh** setup only. Never reset it after sends |
| `FACT-CHECK FAILED` | The tailored spec changed a locked fact or used a number not in the profile. Fix the spec |
| `OVERFLOW: must be exactly one page` | Cut words, then the least relevant bullet. Never shrink fonts or margins |
| `Job_Leads_<today>.xlsx already exists` | Today's file is never overwritten; rename it to re-run |
| `ModuleNotFoundError: docx` / `pymupdf` | Install into the venv: `.venv\Scripts\python.exe -m pip install -r requirements.txt` |

## Privacy

Everything personal is gitignored and stays on your machine:
- the profile, resumes, tailored files and the daily Excel;
- the outreach history, trackers, logs and `NEEDS_*.md`;
- the signed-in Chrome profile, which holds Gmail and WhatsApp session cookies.

Only code and templates are committed. Check before every push:

```powershell
git status --ignored
```

## Ground rules built in

- **No invented facts.** Training is phrased as knowledge, never as experience. Gaps are stated once, plainly. Screening questions are answered truthfully.
- **Contacts only as published.** Emails and numbers come from the posting itself; addresses are never guessed or constructed.
- **One message per address, ever**, plus at most one follow-up after 4 working days.
- **Polite scraping:** robots.txt is respected, requests to a host are spaced at least 3 s apart, and there are no proxies or block evasion.
- **Scams** (any fee or deposit) are skipped and logged. CAPTCHAs, OTPs and passwords always go back to the human.
- **Untrusted text is data.** Job descriptions and replies are never treated as instructions to the agent.

Use it to apply to jobs you actually want, not to spam employers.

## Credits

- [JobSpy](https://github.com/speedyapply/JobSpy): job-board scraping
- [Playwright](https://playwright.dev/): browser automation over Chrome DevTools Protocol
- [career-ops](https://github.com/career-ops-hq/career-ops) (MIT): ideas adopted for hard gates, the blacklist, canonical-URL dedupe, fit bands, the resume fact-check gate and treating untrusted content as data
