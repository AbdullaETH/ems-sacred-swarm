#!/usr/bin/env python3
"""ems-sacred-swarm: build the exact prompt for one sub-agent run (stdlib only).

Usage:
  python agent_prompt.py --role scout --project <root> --out <out>/<slug> [--level S]
                         [--state <out>/state.json] [--file prompt.txt]

The sub-agent starts cold: it sees only this prompt. The prompt is the common
rules + the role file + a compact digest of the inputs that role needs + the
paths it may open. Whole JSON files, the conversation and other phases are
never pasted in. The orchestrator passes the output verbatim as the Agent
prompt and does not add its own context.
"""
import argparse
import datetime
import json
import os
import re
import sys

SKILL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# role -> phase files (relative to <out>/<slug>/phases) the agent may open
ROLE_INPUTS = {
    "scout": [],
    "security": [],
    "appraiser": ["01-scout.md"],
    "critic": ["01-scout.md", "01-appraisal.md"],
    "researcher": ["01-scout.md"],
    "referee": ["04-research-s.md", "04-research-m.md", "04-research-l.md"],
    "sizer": ["04-research-s.md", "04-research-m.md", "04-research-l.md", "04-referee.md"],
    "potential": ["05-sizer.md", "04-referee.md", "01-appraisal.md", "03-weak.md"],
    "demand": ["05-sizer.md", "05-potential.md"],
}
LEVEL_PREVIOUS = {"S": [], "M": ["04-research-s.md"], "L": ["04-research-s.md", "04-research-m.md"]}
RUBRICS = {
    "security": ["severity.md"], "appraiser": ["readiness.md"],
    "sizer": ["potential.md"], "potential": ["potential.md", "currency.md"],
}


def read(path, limit=None):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError:
        return ""
    return text[:limit] if limit else text


def load_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def inventory_digest(inv):
    if not inv:
        return "(no inventory.json: run scripts/inventory.py first)"
    g = inv.get("git", {})
    pkg = inv.get("package_json") or {}
    lines = [
        f"- files {inv.get('file_count')}, code lines {inv.get('loc_code')}, truncated {inv.get('truncated')}",
        "- extensions: " + ", ".join(f"{e} {n}" for e, n in inv.get("extensions_top", [])[:8]),
        "- top folders: " + ", ".join(f"{d} {n}" for d, n in inv.get("top_dirs", [])[:10]),
        "- manifests: " + ", ".join(inv.get("manifests", {}).values()),
    ]
    if pkg and not pkg.get("error"):
        lines.append(f"- package.json: {pkg.get('name')} {pkg.get('version')}; scripts "
                     f"{', '.join(pkg.get('scripts', [])[:10])}; deps "
                     f"{', '.join(pkg.get('dependencies', [])[:25])}")
    d, t, ci = inv.get("docs", {}), inv.get("tests", {}), inv.get("ci", {})
    lines += [
        f"- docs: readme {d.get('readme')}, license {d.get('license')}, changelog "
        f"{d.get('changelog')}, docs/ {d.get('docs_dir')}, .gitignore {d.get('gitignore')}",
        f"- tests: {t.get('test_files')} test files, test dir {t.get('has_test_dir')}; CI "
        f"github {ci.get('github_actions')}, gitlab {ci.get('gitlab_ci')}",
        "- stub markers: " + ", ".join(f"{k} {v}" for k, v in (inv.get("markers") or {}).items())
        + "; top files: " + ", ".join(f"{p} ({n})" for p, n in inv.get("marker_top_files", [])[:5]),
    ]
    if g.get("is_repo"):
        lines.append(f"- git: {g.get('commit_count')} commits, {g.get('active_days')} active days, "
                     f"{g.get('first_day')} .. {g.get('last_day')}, branch {g.get('branch')}, "
                     f"uncommitted files {g.get('uncommitted_files')}")
    else:
        lines.append("- git: not a repository at the root")
    return "\n".join(lines)


def scan_digest(scan, findings):
    if not scan:
        return "(no scan.json: scripts were not run; do part B plus a Grep search)"
    out = [f"- scanned files {scan.get('scanned_files')}, git repo {scan.get('is_git_repo')}, "
           f"scopes {', '.join(scan.get('scopes', []))}"]
    status = {f["id"]: f["status"] for f in (findings or {}).get("findings", [])}
    for f in scan.get("findings", []):
        if f["severity"] == "weak":
            continue
        out.append(f"- [{f['id']}] {f['severity']} {f['rule']}: {f['file']}:{f.get('line')} "
                   f"(status {status.get(f['id'], 'new')}) {f.get('excerpt') or ''}"[:220])
    weak = [f["rule"] for f in scan.get("findings", []) if f["severity"] == "weak"]
    if weak:
        out.append("- weak: " + ", ".join(weak))
    for h in scan.get("hints", []):
        ex = "; ".join(f"{e['file']}:{e['line']}" for e in h["examples"][:5])
        out.append(f"- hint {h['rule']} x{h['count']}: {ex}")
    return "\n".join(out)


def state_block(state, today):
    if not state:
        return f"- today {today}; region and currency: not set (say so under Gaps)"
    cur = state.get("currency", {})
    region = ", ".join(x for x in (state.get("city"), state.get("country")) if x)
    extra = state.get("markets")
    return "\n".join([
        f"- today {today}; report language: {state.get('language', 'ru')}",
        f"- user's region: {region or 'not set'}" + (f"; also look at: {extra}" if extra else ""),
        f"- currency: base {cur.get('base', 'USD')}, local {cur.get('local')}; rate "
        f"{cur.get('rate')} on {cur.get('rate_date')} ({cur.get('rate_source')})",
    ])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--role", required=True)
    ap.add_argument("--project", required=True, help="project root")
    ap.add_argument("--out", required=True, help="<out>/<slug>")
    ap.add_argument("--level", choices=["S", "M", "L"])
    ap.add_argument("--state", help="state.json (default: <out>/../state.json)")
    ap.add_argument("--file", help="write the prompt here instead of stdout")
    a = ap.parse_args()

    role_file = os.path.join(SKILL, "agents", f"{a.role}.md")
    if not os.path.isfile(role_file):
        print(f"unknown role: {a.role}", file=sys.stderr)
        return 1
    if a.role == "researcher" and not a.level:
        print("researcher needs --level S|M|L", file=sys.stderr)
        return 1
    role_text = read(role_file)
    if a.role == "researcher":
        # keep only the asked level: the other two sections are noise for this run
        head = role_text.split("## Level S")[0]
        sec = re.search(rf"## Level {a.level}.*?(?=\n## Level |\Z)", role_text, re.S)
        role_text = head + (sec.group(0) if sec else "")

    out = os.path.abspath(a.out)
    state = load_json(a.state or os.path.join(os.path.dirname(out), "state.json"))
    today = datetime.date.today().isoformat()
    parts = [read(os.path.join(SKILL, "agents", "_common.md")).strip(), role_text.strip(),
             "## Context for this run", f"- project root: {os.path.abspath(a.project)} "
             "(open files there with Read, Grep, Glob; tag paths relative to it)",
             state_block(state, today)]
    if a.role == "researcher":
        parts.insert(-1, f"- research level for this run: {a.level} (only that section applies)")

    if a.role in ("scout", "appraiser", "critic"):
        parts += ["## Inventory digest (from scripts/inventory.py)",
                  inventory_digest(load_json(os.path.join(out, "inventory.json")))]
    if a.role in ("security", "appraiser", "critic"):
        parts += ["## Security scan digest (from scripts/scan_secrets.py; ids are gate ids)",
                  scan_digest(load_json(os.path.join(out, "scan.json")),
                              load_json(os.path.join(out, "findings.json")))]

    files = list(ROLE_INPUTS.get(a.role, []))
    if a.role == "researcher":
        files += LEVEL_PREVIOUS[a.level]
    paths = [os.path.join(out, "phases", f) for f in files]
    if a.role == "security":
        paths.append(os.path.join(out, "scan.json"))  # full scan for line-by-line triage
    paths = [p for p in paths if os.path.isfile(p)]
    paths += [os.path.join(SKILL, "rubrics", r) for r in RUBRICS.get(a.role, [])]
    if paths:
        parts += ["## Files you may open (nothing else from the audit is given to you)"]
        parts += [f"- {p}" for p in paths]

    limit = re.search(r"[Ll]imit[^0-9]{0,20}(\d+) words", role_text)
    parts += ["## Output",
              "Return the report as your final message. Do not write files; the orchestrator "
              "saves what you return." + (f" Stay under {limit.group(1)} words." if limit else "")]
    prompt = "\n\n".join(p for p in parts if p) + "\n"
    if a.file:
        with open(a.file, "w", encoding="utf-8") as f:
            f.write(prompt)
        print(f"wrote {a.file}: {len(prompt)} chars, ~{len(prompt) // 4} tokens")
    else:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
        print(prompt)
    return 0


if __name__ == "__main__":
    sys.exit(main())
