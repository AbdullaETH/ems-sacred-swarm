#!/usr/bin/env python3
"""ems-sacred-swarm: check that evidence tags in an agent report point at real code.

Usage: python verify_evidence.py <project_root> <report.md>

Tags: [src: path/to/file.ext:LINE]  [src: path:START-END]  [src: https://url]
      [src: absent:path]               claim that a file does not exist
      [src: git:<commit>:<path>:LINE]  claim about a file in git history
Several sources may share one tag, separated by ';'.
Checks that the file exists inside the project root and the line is in range.
URLs are counted but not fetched. Exit code 1 if any tag is bad.
"""
import json
import os
import re
import subprocess
import sys

TAG_RE = re.compile(r"\[src:\s*([^\]]+?)\s*\]")
LINE_RE = re.compile(r"^(\d+)(?:-(\d+))?$")


def line_count(path):
    n = 0
    with open(path, "rb") as f:
        for _ in f:
            n += 1
    return n


def inside(root, rel):
    full = os.path.realpath(os.path.join(root, rel))
    real_root = os.path.realpath(root)
    ok = full == real_root or full.startswith(real_root + os.sep)
    return ok, full


def check_line(line, total):
    m = LINE_RE.match(line)
    if not m:
        return "bad", "line is not a number or range"
    start, end = int(m.group(1)), int(m.group(2) or m.group(1))
    if start < 1 or end < start or end > total:
        return "bad", f"line out of range (file has {total} lines)"
    return "ok", None


def check_absent(root, rel):
    ok, full = inside(root, rel.strip())
    if not ok:
        return "bad", "path escapes the project root"
    return ("bad", "file exists") if os.path.exists(full) else ("ok", None)


def check_git(root, spec):
    parts = spec.split(":")
    if not parts[0] or not re.match(r"^[0-9a-fA-F]{4,40}$", parts[0].strip()):
        return "bad", "expected git:<commit>[:path[:line]]"
    if len(parts) == 1 or not parts[1].strip():
        try:
            r = subprocess.run(["git", "-C", root, "cat-file", "-e", f"{parts[0].strip()}^{{commit}}"],
                               capture_output=True, timeout=20)
        except Exception:
            return "bad", "git not available"
        return ("ok", None) if r.returncode == 0 else ("bad", "commit not found")
    commit, path = parts[0].strip(), parts[1].strip().replace("\\", "/")
    if path.startswith("-") or ".." in path:
        return "bad", "invalid path"
    try:
        r = subprocess.run(["git", "-C", root, "show", f"{commit}:{path}"],
                           capture_output=True, timeout=20)
    except Exception:
        return "bad", "git not available"
    if r.returncode != 0:
        return "bad", "file not found in that commit"
    if len(parts) > 2 and parts[2].strip():
        return check_line(parts[2].strip(), r.stdout.count(b"\n") + 1)
    return "ok", None


def check(root, item):
    if re.match(r"^https?://", item, re.I):
        return "url", None
    if item.lower().startswith("absent:"):
        return check_absent(root, item[7:])
    if item.lower().startswith("git:"):
        return check_git(root, item[4:])
    path, line = item, None
    if ":" in item:
        head, tail = item.rsplit(":", 1)
        if LINE_RE.match(tail.strip()):
            path, line = head, tail.strip()
    path = path.strip().strip("`\"'")
    full = os.path.realpath(os.path.join(root, path))
    real_root = os.path.realpath(root)
    if not (full == real_root or full.startswith(real_root + os.sep)):
        return "bad", "path escapes the project root"
    if not line and any(ch in path for ch in "*?["):
        import glob
        hits = glob.glob(os.path.join(real_root, path))
        return ("ok", None) if hits else ("bad", "glob matches nothing")
    if not line and os.path.isdir(full):
        return "ok", None
    if not os.path.isfile(full):
        return "bad", "file not found"
    if line:
        m = LINE_RE.match(line)
        start = int(m.group(1))
        end = int(m.group(2) or m.group(1))
        total = line_count(full)
        if start < 1 or end < start or end > total:
            return "bad", f"line out of range (file has {total} lines)"
    return "ok", None


def main():
    if len(sys.argv) != 3:
        print("usage: verify_evidence.py <project_root> <report.md>")
        return 2
    root, report = sys.argv[1], sys.argv[2]
    with open(report, encoding="utf-8", errors="replace") as f:
        text = f.read()
    counts = {"ok": 0, "url": 0, "bad": 0}
    bad = []
    for tag in TAG_RE.findall(text):
        for item in (s.strip() for s in tag.split(";") if s.strip()):
            kind, reason = check(root, item)
            counts[kind] += 1
            if kind == "bad":
                bad.append({"tag": item, "reason": reason})
    result = {
        "ok": counts["ok"], "urls_not_fetched": counts["url"], "bad": bad,
        "unverified_marks": len(re.findall(r"\[UNVERIFIED\]", text)),
        "claims_without_any_tag_hint": "review manually if the report has few tags",
    }
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
