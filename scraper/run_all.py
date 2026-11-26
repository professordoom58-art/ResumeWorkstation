# -*- coding: utf-8 -*-
"""Run everything: Stage A -> B -> C (if results exist) -> D (if HUNTER_API_KEY) -> E."""
import os, sys, csv, glob, json, subprocess, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C

PY = sys.executable
HERE = os.path.dirname(os.path.abspath(__file__))


def run(script, *args):
    cmd = [PY, os.path.join(HERE, script), *args]
    r = subprocess.run(cmd, text=True, capture_output=True, encoding="utf-8", errors="replace")
    tail = (r.stdout or "").strip().splitlines()[-14:]
    print("\n".join(tail) if tail else "")
    if r.returncode != 0:
        print(f"[{script}] exit {r.returncode}")
        if r.stderr:
            print(r.stderr.strip().splitlines()[-4:])
    return r.returncode


def count_with_email(stage, today):
    n = 0
    for f in glob.glob(os.path.join(C.OUT, f"raw_*_{today}.csv")):
        with open(f, encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                if row.get("stage") == stage and row.get("email"):
                    n += 1
    return n


def main():
    C.ensure_out()
    today = datetime.date.today().isoformat()
    print(f"=== run {today} ===")
    print("\n--- Stage A: JobSpy")
    run("stage_a_jobspy.py")
    print("\n--- Stage B: pharma sites")
    run("stage_b_sites.py")
    c = os.path.join(C.OUT, "google_results.json")
    if os.path.exists(c):
        print("\n--- Stage C: Google results")
        run("stage_c_google.py")
    else:
        print("\n--- Stage C: skipped (no google_results.json)")
    if os.environ.get("HUNTER_API_KEY"):
        print("\n--- Stage D: careers pages + Hunter")
        run("stage_d_careers.py")
    else:
        print("\n--- Stage D: careers pages only (no HUNTER_API_KEY)")
        run("stage_d_careers.py")
    print("\n--- Stage E: clean, verify, load")
    run("stage_e_clean.py")

    rep = {}
    p = os.path.join(C.OUT, "stage_e_report.json")
    if os.path.exists(p):
        rep = json.load(open(p))
    d = rep.get("dropped", {})
    pr = rep.get("priority", {})
    print("\n=== REPORT ===")
    print(f"Run {today}")
    print(f"Stage A JobSpy:   emails {count_with_email('A', today)}")
    print(f"Stage B sites:    emails {count_with_email('B', today)}")
    print(f"Stage C Google:   emails {count_with_email('C', today)}")
    print(f"Stage D careers:  emails {count_with_email('D', today)}")
    print("Dropped: " + " | ".join(f"{k} {v}" for k, v in d.items() if v))
    print(f"Added to tracker: {rep.get('added', 0)} "
          f"(High {pr.get('High',0)}, Medium {pr.get('Medium',0)}, Low {pr.get('Low',0)}) "
          f"| Unverified {rep.get('unverified',0)}")


if __name__ == "__main__":
    main()
