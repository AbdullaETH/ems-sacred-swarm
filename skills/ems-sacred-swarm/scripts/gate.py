#!/usr/bin/env python3
"""ems-sacred-swarm: security gate and findings store (stdlib only).

Usage:
  gate.py <out_dir>                              # print status, exit 2 on BLOCK
  gate.py <out_dir> --ingest scan.json --source script|agent
  gate.py <out_dir> --close ID --evidence "text"

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


def ingest(data, scan, source):
    existing = {f["id"]: f for f in data["findings"]}
    seen = set()
    added = reopened = 0
    for nf in scan.get("findings", []):
        i = fid(nf)
        seen.add(i)
        if i in existing:
            e = existing[i]
            e["last_seen"] = now()
            if source == "script" and e.get("source") == "script" and nf.get("severity"):
                e["severity"] = nf["severity"]  # scanner rules improve; agent re-rating is kept
            if e["status"] == "closed":
                e["status"] = "open"
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
    ap.add_argument("--close")
    ap.add_argument("--evidence", default="")
    args = ap.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)
    path = os.path.join(args.out_dir, "findings.json")
    data = load(path)
    result = {}

    if args.ingest:
        with open(args.ingest, encoding="utf-8") as f:
            scan = json.load(f)
        result["ingest"] = ingest(data, scan, args.source)
        save(path, data)

    if args.close:
        if not args.evidence.strip():
            print(json.dumps({"error": "--evidence is required to close a finding"}))
            return 1
        target = next((f for f in data["findings"] if f["id"] == args.close), None)
        if not target:
            print(json.dumps({"error": f"no finding with id {args.close}"}))
            return 1
        target["status"] = "closed"
        target["closed_by"] = "manual+evidence"
        target["closed_at"] = now()
        target["close_evidence"] = args.evidence.strip()
        save(path, data)
        result["closed"] = args.close

    result.update(status(data))
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 2 if result["status"] == "BLOCK" else 0


if __name__ == "__main__":
    sys.exit(main())
