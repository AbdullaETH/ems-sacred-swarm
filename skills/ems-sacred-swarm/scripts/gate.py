#!/usr/bin/env python3
"""ems-sacred-swarm: security gate and findings store (stdlib only).

Usage:
  gate.py <out_dir>                              # print status, exit 2 on BLOCK
  gate.py <out_dir> --ingest scan.json --source script|agent
  gate.py <out_dir> --ingest-md security-report.md   # last ```json block of an agent
  gate.py <out_dir> --close ID --evidence "text"     # sticks across re-scans
  gate.py <out_dir> --rate ID --severity medium --evidence "text"
  gate.py <out_dir> --reopen ID

<out_dir> is <output>/<project-slug>/ ; findings live in findings.json.

Statuses of a finding: open, pending_rotation, closed.
Gate: BLOCK if any critical is open or pending_rotation; NAG if any medium
is open; OK otherwise. There is no override for critical findings.
"""
import argparse
import datetime
import hashlib
import json
import os
import re
import sys

OPEN_STATES = {"open", "pending_rotation"}


def now():
    return datetime.datetime.now().replace(microsecond=0).isoformat()


def load(path):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {"findings": [], "updated": None}


def save(path, data):
    data["updated"] = now()
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def fid(f):
    if f.get("id"):
        return str(f["id"])
    base = f"{f.get('title', '')}|{f.get('file', '')}|{f.get('category', '')}"
    return hashlib.sha1(base.encode("utf-8", "replace")).hexdigest()[:10]


SEVERITY_ALIASES = {
    "critical": "critical", "crit": "critical", "high": "critical", "blocker": "critical",
    "severe": "critical", "критическая": "critical", "критический": "critical",
    "medium": "medium", "moderate": "medium", "med": "medium", "средняя": "medium",
    "weak": "weak", "low": "weak", "info": "weak", "minor": "weak", "слабая": "weak",
}


def normalise(f):
    """Agents write 'Critical', 'HIGH' or worse; an unknown level must never
    vanish from the gate, so it becomes medium and is flagged."""
    raw = str(f.get("severity", "")).strip().lower()
    sev = SEVERITY_ALIASES.get(raw)
    if sev is None:
        f["severity_raw"] = f.get("severity")
        sev = "medium"
    f["severity"] = sev
    return f


def extract_json_block(md):
    """Last fenced ```json block of an agent report that holds findings."""
    blocks = re.findall(r"```json\s*\n(.*?)\n```", md, re.S)
    for b in reversed(blocks):
        try:
            obj = json.loads(b)
        except ValueError:
            continue
        if isinstance(obj, dict) and "findings" in obj:
            return obj
    return None


def ingest(data, scan, source):
    existing = {f["id"]: f for f in data["findings"]}
    seen = set()
    added = reopened = 0
    for nf in scan.get("findings", []):
        nf = normalise(dict(nf))
        i = fid(nf)
        seen.add(i)
        if i in existing:
            e = existing[i]
            e["last_seen"] = now()
            if (source == "script" and e.get("source") == "script"
                    and e.get("rated_by") != "manual"):
                e["severity"] = nf["severity"]  # scanner rules improve; manual re-rating is kept
            if e["status"] == "closed" and e.get("closed_by") == "rescan":
                e["status"] = "open"  # came back after a re-scan had closed it
                e["reopened"] = True
                reopened += 1
        else:
            rec = dict(nf)
            rec["id"] = i
            rec["source"] = source
            rec["status"] = "open"
            rec["first_seen"] = rec["last_seen"] = now()
            data["findings"].append(rec)
            existing[i] = rec
            added += 1
    auto_closed = pending = 0
    if source == "script":
        covered = set(scan.get("scopes", ["tree"]))
        for e in data["findings"]:
            if (e.get("source") == "script" and e["status"] == "open"
                    and e["id"] not in seen and e.get("scope", "tree") in covered):
                if e.get("needs_rotation"):
                    e["status"] = "pending_rotation"
                    pending += 1
                else:
                    e["status"] = "closed"
                    e["closed_by"] = "rescan"
                    e["closed_at"] = now()
                    auto_closed += 1
    return {"added": added, "reopened": reopened, "auto_closed": auto_closed,
            "pending_rotation": pending}


def status(data):
    def pick(sev):
        return [f for f in data["findings"]
                if f.get("severity") == sev and f["status"] in OPEN_STATES]
    crit, med, weak = pick("critical"), pick("medium"), pick("weak")
    state = "BLOCK" if crit else ("NAG" if med else "OK")

    def brief(f):
        return {"id": f["id"], "title": f.get("title"), "file": f.get("file"),
                "line": f.get("line"), "status": f["status"],
                "fix_hint": f.get("fix_hint")}
    return {
        "status": state,
        "critical": [brief(f) for f in crit],
        "medium": [brief(f) for f in med],
        "weak_open": len(weak),
        "closed": sum(1 for f in data["findings"] if f["status"] == "closed"),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out_dir")
    ap.add_argument("--ingest")
    ap.add_argument("--source", choices=["script", "agent"], default="agent")
    ap.add_argument("--ingest-md", help="agent report: ingest its last ```json findings block")
    ap.add_argument("--close")
    ap.add_argument("--reopen")
    ap.add_argument("--rate", help="finding id to re-rate (needs --severity and --evidence)")
    ap.add_argument("--severity", choices=["critical", "medium", "weak"])
    ap.add_argument("--evidence", default="")
    args = ap.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)
    path = os.path.join(args.out_dir, "findings.json")
    data = load(path)
    result = {}

    def fail(msg):
        print(json.dumps({"error": msg}, ensure_ascii=False))
        return 1

    def find(i):
        return next((f for f in data["findings"] if f["id"] == i), None)

    if args.ingest:
        with open(args.ingest, encoding="utf-8") as f:
            scan = json.load(f)
        result["ingest"] = ingest(data, scan, args.source)
        save(path, data)

    if args.ingest_md:
        with open(args.ingest_md, encoding="utf-8", errors="replace") as f:
            scan = extract_json_block(f.read())
        if scan is None:
            return fail("no ```json block with \"findings\" in " + args.ingest_md)
        result["ingest"] = ingest(data, scan, "agent")
        save(path, data)

    if args.rate:
        target = find(args.rate)
        if not target:
            return fail(f"no finding with id {args.rate}")
        if not args.severity or not args.evidence.strip():
            return fail("--rate needs --severity and --evidence (what in the source proves the new level)")
        target["rated_from"] = target.get("severity")
        target["severity"] = args.severity
        target["rated_by"] = "manual"
        target["rate_evidence"] = args.evidence.strip()
        if args.severity != "critical":
            target["needs_rotation"] = False
            if target["status"] == "pending_rotation":
                target["status"] = "open"
        save(path, data)
        result["rated"] = args.rate

    if args.close:
        if not args.evidence.strip():
            return fail("--evidence is required to close a finding")
        target = find(args.close)
        if not target:
            return fail(f"no finding with id {args.close}")
        target["status"] = "closed"
        target["closed_by"] = "manual+evidence"  # stays closed on re-scans; --reopen undoes it
        target["closed_at"] = now()
        target["close_evidence"] = args.evidence.strip()
        save(path, data)
        result["closed"] = args.close

    if args.reopen:
        target = find(args.reopen)
        if not target:
            return fail(f"no finding with id {args.reopen}")
        target["status"] = "open"
        target["closed_by"] = None
        save(path, data)
        result["reopened"] = args.reopen

    result.update(status(data))
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 2 if result["status"] == "BLOCK" else 0


if __name__ == "__main__":
    sys.exit(main())
