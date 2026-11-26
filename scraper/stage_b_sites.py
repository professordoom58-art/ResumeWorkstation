# -*- coding: utf-8 -*-
"""Stage B: crawl pharma job sites for published application emails."""
import os, re, sys, csv, datetime, argparse, urllib.parse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C

POST_HINT = re.compile(r"/\d{4}/|hiring|vacanc|fresher|job|recruit|walk-?in", re.I)
LIST_HINT = re.compile(r"categor|/jobs?/?$|vacanc|pharma-jobs|job-location", re.I)


def collect_links(html, base):
    s = C.soup(html)
    out = []
    for a in s.find_all("a", href=True):
        u = urllib.parse.urljoin(base, a["href"])
        if urllib.parse.urlsplit(u).netloc != urllib.parse.urlsplit(base).netloc:
            continue
        if u.startswith(("mailto:", "tel:", "javascript:")):
            continue
        u = u.split("#")[0]
        if POST_HINT.search(u):
            out.append(u)
    return list(dict.fromkeys(out))


def company_role(h1, text):
    h1 = (h1 or "").strip()
    t = h1 or text[:120]
    m = re.match(r"(.+?)\s+(?:is\s+|are\s+)?(?:Hiring|Hirng)\s+(?:For|for)\s+(.+)", t, re.I)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    m = re.match(r"Freshers Needed In (.+?) At (.+)", t, re.I)
    if m:
        return m.group(2).strip(), m.group(1).strip()
    if " at " in t:
        left, right = t.split(" at ", 1)
        return right.split(" - ")[0].strip(), left.strip()
    return "", t[:90]


def grab(text, label, nxt, maxlen=55):
    m = re.search(label + r"\s*:?\s*(.{3,%d}?)\s*(?:" % maxlen + "|".join(nxt) + r"|$)", text, re.I)
    return m.group(1).strip(" .;:") if m else ""


def parse_post(url, cfg, days_back):
    if not C.robots_ok(url, cfg["request_delay_seconds"]):
        C.log_skip(f"robots disallow | {url}")
        return None
    html, status = C.polite_get(url, cfg["request_delay_seconds"])
    if not html:
        C.log_skip(f"fetch {status} | {url}")
        return None
    emails, text = C.page_emails(html)
    if not emails:
        return {"url": url, "emails": [], "stale": None}
    d = C.page_date(html)
    fresh = C.is_fresh(d, days_back)
    h1 = ""
    s = C.soup(html)
    if s.find("h1"):
        h1 = s.find("h1").get_text(" ", strip=True)
    comp, role = company_role(h1, text)
    flat = re.sub(r"\s+", " ", text)
    loc = grab(flat, r"Job Location", ["Job Type", "Work Mode", "Qualification", "Experience", "Salary", "Company"])
    exp = ""
    m = re.search(r"\b(0\s*[-–to]{1,3}\s*\d\s*(?:yrs?|years?)|freshers?(?:\s+can\s+apply)?|\d\s*[-–]\s*\d\s*years?|\d+\+?\s*years?)\b", flat, re.I)
    if m:
        exp = m.group(1).strip()
    return {"url": url, "emails": emails, "date": d.isoformat() if d else "",
            "fresh": bool(fresh), "company": comp[:80], "role": role[:120],
            "location": loc[:60], "experience": exp[:40],
            "scam": C.scam_hit(flat, cfg["scam_words"])}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--post", help="test a single post URL")
    ap.add_argument("--limit", type=int, default=40, help="max posts per seed")
    ap.add_argument("--allow-stale", action="store_true")
    args = ap.parse_args()
    cfg = C.cfg()
    C.ensure_out()
    days = cfg["days_back"]
    rows, seen = [], set()

    if args.post:
        r = parse_post(args.post, cfg, days)
        if not r:
            print("fetch/robots failed")
            return
        print("URL      :", r["url"])
        print("emails   :", r["emails"])
        print("date     :", r.get("date"), "| fresh:", r.get("fresh"))
        print("company  :", r.get("company"), "| role:", r.get("role"))
        print("location :", r.get("location"), "| exp:", r.get("experience"))
        print("scam     :", r.get("scam") or "no")
        return

    for seed in cfg["site_seeds"]:
        if not C.robots_ok(seed, cfg["request_delay_seconds"]):
            C.log_skip(f"robots disallow seed | {seed}")
            continue
        html, st = C.polite_get(seed, cfg["request_delay_seconds"])
        if not html:
            C.log_skip(f"seed fetch {st} | {seed}")
            print(f"seed failed {st}: {seed}")
            continue
        links = collect_links(html, seed)
        # one level deeper for homepages
        if len(links) < 5:
            for l in collect_links(html, seed)[:0]:
                pass
            s = C.soup(html)
            subs = [urllib.parse.urljoin(seed, a["href"]) for a in s.find_all("a", href=True)
                    if LIST_HINT.search(a["href"])]
            for sub in list(dict.fromkeys(subs))[:6]:
                if C.robots_ok(sub, cfg["request_delay_seconds"]):
                    h2, _ = C.polite_get(sub, cfg["request_delay_seconds"])
                    if h2:
                        links += collect_links(h2, sub)
            links = list(dict.fromkeys(links))
        print(f"seed {seed} -> {len(links)} post links")
        n = 0
        for u in links:
            if u in seen or n >= args.limit:
                continue
            seen.add(u); n += 1
            r = parse_post(u, cfg, days)
            if not r or not r["emails"]:
                continue
            if r.get("fresh") is False and not args.allow_stale:
                C.log_skip(f"stale {r.get('date')} | {u}")
                continue
            for em in r["emails"]:
                rows.append({
                    "stage": "B", "email": em, "company": r["company"], "role": r["role"],
                    "location": r["location"], "experience": r["experience"],
                    "date_posted": r.get("date", ""), "source_url": u,
                    "scam": ";".join(r.get("scam") or []),
                })
            print(f"  + {r['company'][:28]:28} {r['date']} {r['emails'][0]}")

    path = os.path.join(C.OUT, f"raw_sites_{datetime.date.today().isoformat()}.csv")
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["stage", "email", "company", "role", "location",
                                         "experience", "date_posted", "source_url", "scam"])
        w.writeheader(); w.writerows(rows)
    print(f"\nStage B: {len(rows)} email rows -> {path}")


if __name__ == "__main__":
    main()
