#!/usr/bin/env python3
"""ems-sacred-swarm: print the run plan (number of sub-agent runs by model).

Usage:
  python run_plan.py --projects 5 --preset economy --levels S,M,L [--lean] [--no-demand]

No token counts are invented: the output is the number of agent runs per phase
and model, plus a relative load label.
"""
import argparse
import sys

PRESETS = {
    "economy":  {"haiku": ["scout", "appraiser", "critic", "security", "researcher_S", "researcher_M",
                           "researcher_L", "referee", "sizer", "potential", "demand"],
                 "sonnet": ["collector", "improver", "sales"]},
    "balanced": {"haiku": ["scout", "appraiser", "critic", "security", "researcher_S", "researcher_M",
                           "referee"],
                 "sonnet": ["researcher_L", "sizer", "potential", "demand", "collector", "improver", "sales"]},
    "strong":   {"haiku": [],
                 "sonnet": ["scout", "appraiser", "critic", "security", "researcher_S", "researcher_M",
                            "researcher_L", "referee", "sizer", "potential", "demand", "collector",
                            "improver", "sales"]},
}
PHASES = [
    ("1 state and readiness", ["scout", "appraiser"]),
    ("2 security gate", ["security"]),
    ("3 weak spots", ["critic"]),
    ("4 research", ["researcher_S", "researcher_M", "researcher_L", "referee"]),
    ("5 audience and potential", ["sizer", "potential"]),
    ("5b demand check", ["demand"]),
    ("6 collect", ["collector"]),
    ("7 improve", ["improver"]),
    ("8 sell", ["sales"]),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--projects", type=int, default=1)
    ap.add_argument("--preset", choices=sorted(PRESETS), default="economy")
    ap.add_argument("--levels", default="S,M,L")
    ap.add_argument("--lean", action="store_true",
                    help="merge appraiser and critic into one run")
    ap.add_argument("--no-demand", action="store_true")
    a = ap.parse_args()

    levels = {x.strip().upper() for x in a.levels.split(",") if x.strip()}
    model_of = {}
    for model, roles in PRESETS[a.preset].items():
        for r in roles:
            model_of[r] = model

    rows, totals = [], {"haiku": 0, "sonnet": 0}
    for title, roles in PHASES:
        n = {"haiku": 0, "sonnet": 0}
        for r in roles:
            if r.startswith("researcher_") and r[-1] not in levels:
                continue
            if r == "referee" and not (levels & {"S", "M", "L"}):
                continue
            if r == "critic" and a.lean:
                continue
            if r == "demand" and a.no_demand:
                continue
            n[model_of[r]] += a.projects
        if sum(n.values()):
            rows.append((title, n))
            for m in n:
                totals[m] += n[m]

    sys.stdout.reconfigure(encoding="utf-8") if hasattr(sys.stdout, "reconfigure") else None
    print(f"Run plan: {a.projects} project(s), preset {a.preset}, research levels {','.join(sorted(levels)) or '-'}"
          f"{', lean' if a.lean else ''}")
    print(f"{'phase':28} {'haiku':>6} {'sonnet':>7}")
    for title, n in rows:
        print(f"{title:28} {n['haiku']:>6} {n['sonnet']:>7}")
    total = totals["haiku"] + totals["sonnet"]
    print(f"{'TOTAL agent runs':28} {totals['haiku']:>6} {totals['sonnet']:>7}   = {total}")
    load = "low" if total <= 12 else ("medium" if total <= 40 else "high")
    print(f"Relative load: {load}. Scripts (inventory, secret scan, gate, evidence check) cost no model tokens.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
