#!/usr/bin/env python3
"""ems-sacred-swarm: read-only project inventory (stdlib only, never runs project code).

Usage: python inventory.py <project_root> [--out inventory.json]
Prints JSON with structure, stack hints, maturity signals and a fingerprint
(used to skip unchanged phases on a re-run).
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from collections import Counter

SKIP_DIRS = {
    ".git", "node_modules", ".venv", "venv", "env", "__pycache__", "dist", "build",
    ".next", ".nuxt", "target", ".idea", ".vscode", "vendor", ".gradle", ".cache",
    "coverage", ".pytest_cache", ".mypy_cache", "bower_components", ".svn", ".hg",
    "Pods", ".terraform", ".dart_tool", "site-packages",
}
CODE_EXT = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".vue", ".svelte", ".html",
    ".css", ".scss", ".php", ".rb", ".go", ".rs", ".java", ".kt", ".swift", ".cs",
    ".cpp", ".c", ".h", ".dart", ".sql", ".sh", ".ps1", ".bat", ".lua",
}
MANIFESTS = [
    "package.json", "pyproject.toml", "requirements.txt", "Pipfile", "go.mod",
    "Cargo.toml", "pom.xml", "build.gradle", "composer.json", "Gemfile",
    "pubspec.yaml", "Dockerfile", "docker-compose.yml", "docker-compose.yaml",
    "vercel.json", "netlify.toml", "wrangler.toml",
]
MAX_FILE = 1_000_000
MAX_FILES = 60_000
MARKER_RE = re.compile(
    r"\b(TODO|FIXME|XXX|HACK|NotImplemented\w*|lorem ipsum|placeholder)\b", re.I)
SECRET_LIKE = re.compile(
    r"(?i)\b(password|passwd|secret|token|api[_-]?key)\b(\s*[:=]\s*)\S+")
TEST_FILE_RE = re.compile(
    r"(^test_.*\.py$|.*_test\.(py|go)$|.*\.(test|spec)\.[jt]sx?$)", re.I)
TEST_DIRS = {"test", "tests", "__tests__", "spec", "specs", "e2e"}


def git(root, *args):
    try:
        r = subprocess.run(
            ["git", "-C", root, *args], capture_output=True, text=True,
            timeout=20, encoding="utf-8", errors="replace")
        return r.stdout.strip() if r.returncode == 0 else None
    except Exception:
        return None


def head(path, limit=1500):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read(limit)
    except OSError:
        return ""
    return SECRET_LIKE.sub(r"\1\2***", text)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    ap.add_argument("--out")
    args = ap.parse_args()
    root = os.path.abspath(args.root)
    if not os.path.isdir(root):
        print(json.dumps({"error": "not a directory", "root": root}))
        return 1

    ext_count = Counter()
    top_dirs = Counter()
    manifests_found = {}
    markers = Counter()
    marker_files = Counter()
    tests = 0
    has_test_dir = False
    total_bytes = 0
    loc = 0
    files = 0
    truncated = False
    fp = hashlib.sha1()
    root_names = set()

    entries = []
    for dp, dns, fns in os.walk(root):
        dns[:] = sorted(d for d in dns if d not in SKIP_DIRS)
        rel_dir = os.path.relpath(dp, root)
        if rel_dir == ".":
            root_names = set(fns) | set(dns)
        if any(d.lower() in TEST_DIRS for d in dns):
            has_test_dir = True
        for fn in sorted(fns):
            files += 1
            if files > MAX_FILES:
                truncated = True
                break
            full = os.path.join(dp, fn)
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            try:
                st = os.stat(full)
            except OSError:
                continue
            entries.append((rel, full, st.st_size))
            total_bytes += st.st_size
            fp.update(f"{rel}|{st.st_size}|{int(st.st_mtime)}\n".encode())
        if truncated:
            break

    for rel, full, size in entries:
        ext = os.path.splitext(rel)[1].lower()
        ext_count[ext or "(none)"] += 1
        parts = rel.split("/")
        top_dirs[parts[0] if len(parts) > 1 else "(root)"] += 1
        base = parts[-1]
        if base in MANIFESTS and base not in manifests_found:
            manifests_found[base] = rel
        if TEST_FILE_RE.match(base):
            tests += 1
        if ext in CODE_EXT and size <= MAX_FILE:
            try:
                with open(full, "rb") as f:
                    data = f.read()
            except OSError:
                continue
            if b"\0" in data[:1024]:
                continue
            loc += data.count(b"\n") + 1
            if size <= 200_000:
                hits = MARKER_RE.findall(data.decode("utf-8", "replace"))
                if hits:
                    markers.update(h.lower() for h in hits)
                    marker_files[rel] += len(hits)

    lower_root = {n.lower() for n in root_names}

    def has_prefix(prefix):
        return any(n.startswith(prefix) for n in lower_root)

    pkg = {}
    if "package.json" in manifests_found:
        try:
            with open(os.path.join(root, manifests_found["package.json"]),
                      encoding="utf-8", errors="replace") as f:
                p = json.load(f)
            pkg = {
                "name": p.get("name"),
                "description": p.get("description"),
                "version": p.get("version"),
                "scripts": sorted((p.get("scripts") or {}).keys())[:20],
                "dependencies": sorted((p.get("dependencies") or {}).keys())[:40],
                "devDependencies_count": len(p.get("devDependencies") or {}),
            }
        except Exception:
            pkg = {"error": "unreadable package.json"}

    git_info = {"is_repo": False}
    if os.path.isdir(os.path.join(root, ".git")) or git(root, "rev-parse", "--git-dir"):
        remote = git(root, "config", "--get", "remote.origin.url") or ""
        git_info = {
            "is_repo": True,
            "head": git(root, "rev-parse", "--short", "HEAD"),
            "branch": git(root, "rev-parse", "--abbrev-ref", "HEAD"),
            "last_commit": git(root, "log", "-1", "--format=%cI"),
            "first_commit": (git(root, "log", "--reverse", "--format=%cI", "--max-parents=0")
                             or "").splitlines()[:1],
            "commit_count": git(root, "rev-list", "--count", "HEAD"),
            "remote": re.sub(r"//[^/@\s]+@", "//***@", remote),
            "uncommitted_files": len((git(root, "status", "--porcelain") or "").splitlines()),
        }
        dates = sorted(set((git(root, "log", "--format=%cs") or "").split()))
        git_info["active_days"] = len(dates)
        git_info["first_day"] = dates[0] if dates else None
        git_info["last_day"] = dates[-1] if dates else None
        if len(dates) > 1:
            from datetime import date
            try:
                a = date.fromisoformat(dates[0])
                b = date.fromisoformat(dates[-1])
                git_info["span_days"] = (b - a).days + 1
            except ValueError:
                pass
        fp.update(str(git_info.get("head")).encode())

    readme = next((n for n in sorted(root_names) if n.lower().startswith("readme")), None)
    out = {
        "root": root,
        "truncated": truncated,
        "fingerprint": fp.hexdigest(),
        "file_count": min(files, MAX_FILES),
        "total_bytes": total_bytes,
        "loc_code": loc,
        "extensions_top": ext_count.most_common(15),
        "top_dirs": top_dirs.most_common(15),
        "manifests": manifests_found,
        "package_json": pkg,
        "manifest_heads": {
            k: head(os.path.join(root, v), 1200)
            for k, v in list(manifests_found.items())[:6] if k != "package.json"
        },
        "docs": {
            "readme": readme,
            "license": has_prefix("license") or has_prefix("copying"),
            "changelog": has_prefix("changelog"),
            "docs_dir": "docs" in lower_root,
            "gitignore": ".gitignore" in lower_root,
        },
        "tests": {"test_files": tests, "has_test_dir": has_test_dir},
        "ci": {
            "github_actions": os.path.isdir(os.path.join(root, ".github", "workflows")),
            "gitlab_ci": ".gitlab-ci.yml" in root_names,
        },
        "markers": dict(markers),
        "marker_top_files": marker_files.most_common(8),
        "git": git_info,
        "readme_head": head(os.path.join(root, readme), 1800) if readme else "",
    }
    text = json.dumps(out, ensure_ascii=False, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
