#!/usr/bin/env python3
"""ems-sacred-swarm: export a Markdown report to plain text and, if pandoc is
available, to .docx.

Usage: python export_report.py REPORT.md [--txt] [--docx]
Default is --txt. Prints what was written and what was skipped.
"""
import argparse
import os
import re
import shutil
import subprocess
import sys


def md_to_txt(md):
    out = []
    in_code = False
    for line in md.splitlines():
        if line.strip().startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            out.append(line)
            continue
        if re.match(r"^\s*\|?\s*:?-{2,}", line) and "|" in line:
            continue  # table separator
        line = re.sub(r"^\s{0,3}#{1,6}\s*", "", line)
        line = re.sub(r"\*\*(.+?)\*\*", r"\1", line)
        line = re.sub(r"(?<!\*)\*(?!\s)(.+?)\*(?!\*)", r"\1", line)
        line = re.sub(r"`([^`]*)`", r"\1", line)
        line = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1 (\2)", line)
        if "|" in line:
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            line = " | ".join(cells)
        out.append(line.rstrip())
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip() + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("report")
    ap.add_argument("--txt", action="store_true")
    ap.add_argument("--docx", action="store_true")
    a = ap.parse_args()
    if not os.path.isfile(a.report):
        print(f"not found: {a.report}")
        return 1
    base = os.path.splitext(a.report)[0]
    want_txt = a.txt or not a.docx
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if want_txt:
        with open(a.report, encoding="utf-8") as f:
            text = md_to_txt(f.read())
        with open(base + ".txt", "w", encoding="utf-8") as f:
            f.write(text)
        print("wrote", base + ".txt")
    if a.docx:
        pandoc = shutil.which("pandoc")
        if not pandoc:
            print("skipped .docx: pandoc is not installed (install it or use an available docx skill)")
        else:
            r = subprocess.run([pandoc, a.report, "-o", base + ".docx"], capture_output=True, text=True)
            print("wrote " + base + ".docx" if r.returncode == 0 else "pandoc failed: " + r.stderr[:200])
    return 0


if __name__ == "__main__":
    sys.exit(main())
