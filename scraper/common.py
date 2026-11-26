# -*- coding: utf-8 -*-
"""Shared helpers: config, polite fetching, robots.txt, email + date extraction."""
import os, re, time, json, datetime, urllib.parse, urllib.robotparser
from email.utils import parsedate_to_datetime
from bs4 import BeautifulSoup
import requests, yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "scraper", "out")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/157.0 Safari/537.36")
HEADERS = {"User-Agent": UA, "Accept-Language": "en-IN,en;q=0.9"}

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
BAD_LOCAL = {"example", "test", "abc", "xyz", "noreply", "no-reply", "yourname", "email"}
IMAGE_EXT = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp")

_last_hit = {}
_robots = {}


def cfg(path=None):
    p = path or os.path.join(ROOT, "scraper", "config.yaml")
    with open(p, encoding="utf-8") as f:
        return yaml.safe_load(f)


def ensure_out():
    os.makedirs(OUT, exist_ok=True)


def robots_ok(url, delay=None):
    """True if robots.txt allows fetching url. Cached per host."""
    delay = delay or 3.0
    parts = urllib.parse.urlsplit(url)
    base = f"{parts.scheme}://{parts.netloc}"
    rp = _robots.get(base)
    if rp is None:
        rp = urllib.robotparser.RobotFileParser()
        try:
            rp.set_url(base + "/robots.txt")
            rp.read()
        except Exception:
            _robots[base] = "unreadable"
            rp = None
        _robots[base] = rp if rp is not None else "unreadable"
    got = _robots.get(base)
    if got == "unreadable":
        return True
    try:
        return got.can_fetch(UA, url)
    except Exception:
        return True


def polite_get(url, delay=None, timeout=30):
    """GET with per-host delay. Returns (text, status) or (None, reason)."""
    delay = delay or 3.0
    host = urllib.parse.urlsplit(url).netloc
    last = _last_hit.get(host, 0)
    wait = delay - (time.time() - last)
    if wait > 0:
        time.sleep(wait)
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout)
        _last_hit[host] = time.time()
        if r.status_code == 200:
            return r.text, 200
        return None, r.status_code
    except Exception as e:
        _last_hit[host] = time.time()
        return None, f"ERR:{type(e).__name__}"


def soup(html):
    try:
        return BeautifulSoup(html, "lxml")
    except Exception:
        return BeautifulSoup(html, "html.parser")


def clean_emails(text, mailtos=None):
    """Unique, normalised emails; drops placeholders, image names, site-own addresses."""
    found = set()
    for m in EMAIL_RE.finditer(text or ""):
        found.add(m.group(0))
    for m in (mailtos or []):
        e = m.replace("mailto:", "").split("?")[0].strip()
        if EMAIL_RE.fullmatch(e):
            found.add(e)
    out = []
    for e in found:
        e = e.lower().strip(".,;:()[]<>'\"")
        local, _, dom = e.partition("@")
        if local in BAD_LOCAL or e.endswith(IMAGE_EXT) or "@2x" in e:
            continue
        if any(x in dom for x in ("pharmabharat", "pharmatutor", "hiremr", "example.", "sentry.io", "wixpress")):
            continue
        out.append(e)
    return sorted(set(out))


def page_emails(html):
    s = soup(html)
    for tag in s(["script", "style", "noscript"]):
        tag.decompose()
    text = s.get_text(" ", strip=True)
    mailtos = [a["href"] for a in s.find_all("a", href=True) if a["href"].lower().startswith("mailto:")]
    return clean_emails(text, mailtos), text


def page_date(html):
    """Best-effort publication date -> datetime.date or None."""
    s = soup(html)
    cand = []
    for m in s.find_all("meta"):
        p = (m.get("property") or m.get("name") or "").lower()
        if p in ("article:published_time", "og:updated_time", "datepublished"):
            cand.append(m.get("content") or "")
    ld = re.search(r'"datePublished"\s*:\s*"([^"]+)"', html or "")
    if ld:
        cand.append(ld.group(1))
    t = s.find("time")
    if t and (t.get("datetime") or t.get_text(strip=True)):
        cand.append(t.get("datetime") or t.get_text(strip=True))
    m = re.search(r"(?:Published|Posted)\s*(?:on)?\s*[:\-]?\s*([0-9]{1,2}\s+\w+\s+[0-9]{4}|\w+\s+[0-9]{1,2},?\s+[0-9]{4})", html or "", re.I)
    if m:
        cand.append(m.group(1))
    for c in cand:
        if not c:
            continue
        d = _parse_date(c)
        if d:
            return d
    return None


def _parse_date(s):
    s = s.strip()
    s = re.sub(r"[TZ]" if False else r"T", " ", s)
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d %B %Y", "%d %b %Y",
                "%B %d, %Y", "%b %d, %Y", "%d %B, %Y"):
        try:
            return datetime.datetime.strptime(s[:len(fmt) + 4].strip(), fmt).date()
        except Exception:
            try:
                return datetime.datetime.strptime(s.strip(), fmt).date()
            except Exception:
                pass
    try:
        return parsedate_to_datetime(s).date()
    except Exception:
        pass
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        try:
            return datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except Exception:
            return None
    return None


def is_fresh(d, days_back):
    if not d:
        return None
    return (datetime.date.today() - d).days <= days_back


def scam_hit(text, words):
    t = (text or "").lower()
    return [w for w in words if w.lower() in t]


def log_skip(msg):
    ensure_out()
    with open(os.path.join(OUT, "skipped.log"), "a", encoding="utf-8") as f:
        f.write(f"{datetime.datetime.now().isoformat(timespec='seconds')} | {msg}\n")


def category_of(title):
    t = (title or "").lower()
    if "pharmacovigilance" in t or "drug safety" in t or "icsr" in t or "case processing" in t:
        return "PV"
    if "clinical data" in t or "cdm" in t or "data manager" in t:
        return "CDM"
    if "clinical research" in t or "clinical trial" in t or "crc" in t or "cra" in t:
        return "Clinical Research"
    if "medical coding" in t or "coder" in t:
        return "Med Coding"
    if "medical information" in t or "medical writing" in t:
        return "Medical Info"
    if "regulatory" in t:
        return "Regulatory"
    if "quality" in t or "qa" in t or "qc" in t or "microbiolog" in t:
        return "QA/QC"
    if "medical representative" in t or "business development" in t or "sales" in t or "marketing" in t:
        return "Sales/MR/BD"
    return "Other"


NCR = re.compile(r"noida|gurugram|gurgaon|delhi|ghaziabad|faridabad|ncr", re.I)


def priority_of(location, experience, remote=False):
    e = (experience or "").lower()
    loc = location or ""
    fresher = bool(re.search(r"fresher|0\s*[-–to]{1,3}\s*[12]\b|entry", e)) or not e
    yrs = re.findall(r"(\d+)\s*\+?\s*(?:year|yr)", e)
    low_exp = fresher or (yrs and min(int(x) for x in yrs) <= 2)
    in_ncr = bool(NCR.search(loc)) or remote
    if low_exp and in_ncr:
        return "High"
    if low_exp or (in_ncr and yrs and min(int(x) for x in yrs) <= 3):
        return "Medium"
    return "Low"
