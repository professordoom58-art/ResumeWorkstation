# -*- coding: utf-8 -*-
"""Build one tailored resume (DOCX + PDF) from a JSON spec and check that it is exactly one page.

Usage:  python src/build_resume.py tailored/<Company>_<Role>/spec.json
Writes  tailored/<Company>_<Role>/<file_name>.docx and .pdf next to the spec.

The spec is profile/resume_base.json with the per-job parts changed (title_line, summary, bullet order and wording,
additional-information order). Every fact must already be in profile/PROFILE.md - see CLAUDE.md "Honesty rules".
Keys: name, title_line[list], contact{location,email,phone,linkedin_url?,linkedin_text?}, summary[list],
      experience[{company,location,title,dates,bullets[]}], education[{school,location,degree,years}],
      additional[[label,text]], file_name ("<First>'s Resume <CODE>")
Fact-check (before anything is rendered): name, contact, every employer/title/location/dates and every education entry
must match profile/resume_base.json exactly, and every number in the text (25%, 120+, 99.7%, 300+ ...) must already
appear in resume_base.json or profile/PROFILE.md. Any miss stops the build. --skip-fact-check only for a reviewed reason.
Exit code 1 if the PDF is not exactly one page (cut words, then the least relevant bullet - never shrink fonts)."""
import json, os, re, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import resume_lib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")


def fact_check(spec):
    """career-ops-style guard: block a resume whose locked facts or numbers are not in the applicant's own record."""
    base_f, prof_f = os.path.join(ROOT, "profile", "resume_base.json"), os.path.join(ROOT, "profile", "PROFILE.md")
    if not os.path.exists(base_f):
        return ["profile/resume_base.json missing - write it from the resume first"]
    base = json.load(open(base_f, encoding="utf-8"))
    known = json.dumps(base, ensure_ascii=False) + (open(prof_f, encoding="utf-8").read() if os.path.exists(prof_f) else "")
    known_nums = set(NUM.findall(known.replace(",", "")))
    errs = []
    if spec["name"] != base["name"]:
        errs.append(f"name changed: {spec['name']!r}")
    for k, v in base["contact"].items():
        if spec["contact"].get(k) != v:
            errs.append(f"contact.{k} changed: {spec['contact'].get(k)!r}")
    lock = lambda e: (e["company"], e["location"], e["title"], e["dates"])
    base_jobs = {lock(e) for e in base["experience"]}
    for e in spec["experience"]:
        if lock(e) not in base_jobs:
            errs.append(f"experience entry not in profile: {' | '.join(lock(e))}")
    base_edu = [tuple(sorted(e.items())) for e in base["education"]]
    for e in spec["education"]:
        if tuple(sorted(e.items())) not in base_edu:
            errs.append(f"education entry not in profile: {e}")
    text = " ".join(spec["summary"] + spec["title_line"] + [b for e in spec["experience"] for b in e["bullets"]]
                    + [f"{a} {t}" for a, t in spec["additional"]])
    for n in sorted(set(NUM.findall(text.replace(",", "")))):
        if n not in known_nums:
            errs.append(f"number {n} is not in the applicant's record")
    return errs


REQUIRED = ("name", "title_line", "contact", "summary", "experience", "education", "additional", "file_name")


def main(spec_path, skip_check=False):
    spec = json.load(open(spec_path, encoding="utf-8"))
    missing = [k for k in REQUIRED if k not in spec]
    if missing:
        sys.exit(f"spec is missing: {', '.join(missing)}")
    if any("<tailor" in s for s in spec["summary"]):
        sys.exit("summary still holds the placeholder from resume_base.json - write the tailored summary first")
    errs = fact_check(spec)
    if errs and not skip_check:
        print("FACT-CHECK FAILED - nothing built:")
        for e in errs:
            print("  -", e)
        sys.exit(1)
    if errs:
        print("WARNING fact-check skipped:", "; ".join(errs))
    spec["doc_title"] = spec["file_name"]
    out_dir = os.path.dirname(os.path.abspath(spec_path))
    docx_path = os.path.join(out_dir, spec["file_name"] + ".docx")
    pdf_path = os.path.join(out_dir, spec["file_name"] + ".pdf")
    resume_lib.build(spec, docx_path)
    resume_lib.to_pdf(docx_path, pdf_path)
    n, chars = resume_lib.pages(pdf_path)
    print(f"{pdf_path}  pages={n}  chars={sum(chars)}")
    if n != 1:
        print("OVERFLOW: must be exactly one page")
        sys.exit(1)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--skip-fact-check"]
    if len(args) != 1:
        sys.exit(__doc__)
    main(args[0], skip_check="--skip-fact-check" in sys.argv)
