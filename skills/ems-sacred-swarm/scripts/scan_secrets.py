#!/usr/bin/env python3
"""ems-sacred-swarm: read-only secret and exposure scan (stdlib only).

Usage: python scan_secrets.py <project_root> [--history N] [--out scan.json]

Secrets are never printed: values are masked as `AKIA…(20 chars)`.
Output JSON: {"scopes": [...], "findings": [...], "hints": [...]} - feed it to
gate.py --ingest. `hints` are risky patterns for the security agent to triage;
they do not affect the gate.
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys

SKIP_DIRS = {
    ".git", "node_modules", ".venv", "venv", "env", "__pycache__", ".next", ".nuxt",
    "target", ".idea", ".vscode", "vendor", ".gradle", ".cache", "coverage",
    ".pytest_cache", ".mypy_cache", "bower_components", ".svn", ".hg", "Pods",
    ".terraform", ".dart_tool", "site-packages", "dist", "build",
}
SKIP_EXT = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".svg", ".mp4", ".mov", ".mp3",
    ".wav", ".woff", ".woff2", ".ttf", ".otf", ".eot", ".zip", ".gz", ".tar", ".7z",
    ".rar", ".pdf", ".psd", ".ai", ".exe", ".dll", ".so", ".dylib", ".class", ".jar",
    ".pyc", ".lock", ".map",
}
SKIP_NAMES = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock", "Cargo.lock",
    "composer.lock", "go.sum",
}
CODE_EXT = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".vue", ".svelte", ".html",
    ".php", ".rb", ".go", ".rs", ".java", ".kt", ".cs", ".sh", ".ps1", ".bat",
}
MAX_FILE = 1_000_000
MAX_LINE = 5000
WEB_DIRS = {"public", "static", "www", "dist", "build", "out", "site", "docs"}
TEST_PATH_RE = re.compile(
    r"(^|/)(tests?|__tests__|fixtures?|examples?|samples?|docs?)(/|$)", re.I)

PROVIDER_RULES = [
    ("anthropic-key", re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{20,}")),
    ("openai-key", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_\-]{32,}")),
    ("aws-access-key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("github-token", re.compile(
        r"\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{50,})\b")),
    ("google-api-key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
    ("slack-token", re.compile(r"\bxox[baprs]-[A-Za-z0-9\-]{10,}")),
    ("stripe-live-key", re.compile(r"\b[sr]k_live_[0-9a-zA-Z]{16,}")),
    ("telegram-bot-token", re.compile(r"\b\d{8,10}:[A-Za-z0-9_\-]{35}\b")),
    ("private-key-block", re.compile(
        r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP |ENCRYPTED )?PRIVATE KEY(?: BLOCK)?-----")),
    ("db-url-with-password", re.compile(
        r"\b(?:postgres(?:ql)?|mysql|mariadb|mongodb(?:\+srv)?|redis|amqp)://"
        r"[^\s:/@'\"]+:([^\s@'\"]{3,})@[^\s'\"]+")),
]
JWT_RE = re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}")
GENERIC_RE = re.compile(
    r"""(?i)\b[A-Za-z0-9_.\-]*(?:password|passwd|pwd|secret|api[_-]?key|apikey|"""
    r"""access[_-]?token|auth[_-]?token|private[_-]?key)[A-Za-z0-9_.\-]*\s*[:=]\s*"""
    r"""['"]([^'"\s]{8,})['"]""")
PLACEHOLDER_RE = re.compile(
    r"(?i)(example|your[_\-]?|xxx+|changeme|change_me|dummy|sample|placeholder|"
    r"<[^>]+>|\$\{|\{\{|process\.env|os\.environ|getenv|\*{3,}|\.\.\.|todo|"
    r"password|secret|none|null|undefined|123456|test|"
    r"парол|секрет|ключ|токен|пример|твой|ваш|замени|вставь)")
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "0.0.0.0", "host.docker.internal",
               "db", "postgres", "mysql", "mariadb", "redis", "mongo"}
DEBUG_RE = re.compile(r"(?i)(\bDEBUG\s*=\s*True\b|\bapp\.run\([^)]*debug\s*=\s*True)")
CORS_RE = re.compile(
    r"""(?i)(access-control-allow-origin['"]?\s*[:,]\s*['"]?\*|origin\s*:\s*['"]\*['"])""")
HINT_RULES = [
    ("eval-exec", re.compile(r"\b(?:eval|exec)\s*\(")),
    ("shell-call", re.compile(r"\bos\.system\(|shell\s*=\s*True|child_process")),
    ("html-injection", re.compile(r"\.innerHTML\s*=|dangerouslySetInnerHTML")),
    ("tls-verify-off", re.compile(r"verify\s*=\s*False|rejectUnauthorized\s*:\s*false")),
    ("sql-string-build", re.compile(
        r"""(?i)(execute|query)\s*\(\s*(f["']|["'][^"']*["']\s*\+|["'][^"']*%s)""")),
    ("cors-default", re.compile(r"\bcors\(\s*\)")),
]
KEY_FILE_NAMES = {
    "id_rsa", "id_ed25519", "id_dsa", "credentials.json", ".pypirc", "secrets.json",
}
KEY_FILE_RE = re.compile(
    r"(\.p12$|\.pfx$|\.jks$|\.keystore$|\.kdbx$|^service[-_]?account.*\.json$)", re.I)
DATA_FILE_RE = re.compile(r"(\.sqlite3?$|\.db$|^dump.*\.sql$|^backup.*\.(sql|zip)$)", re.I)
ENV_RE = re.compile(r"^\.env(\..+)?$")
ENV_EXAMPLE_RE = re.compile(r"\.(example|sample|template|dist)$", re.I)


def mask(value):
    return f"{value[:4]}…({len(value)} chars)"


def sha(text):
    return hashlib.sha1(text.encode("utf-8", "replace")).hexdigest()


def git(root, *args, check=False):
    try:
        r = subprocess.run(
            ["git", "-C", root, *args], capture_output=True, text=True,
            timeout=30, encoding="utf-8", errors="replace")
        if check:
            return r.returncode == 0
        return r.stdout if r.returncode == 0 else None
    except Exception:
        return None if not check else False


class Collector:
    def __init__(self):
        self.findings = {}
        self.hints = {}

    def add(self, rule, severity, category, title, file, line, scope,
            value=None, needs_rotation=False, fix=None, excerpt=None, in_test=False):
        fid = sha(f"{rule}|{value if value is not None else file}")[:10]
        loc = {"file": file, "line": line, "scope": scope}
        if fid in self.findings:
            locs = self.findings[fid]["locations"]
            if loc not in locs and len(locs) < 5:
                locs.append(loc)
            if scope == "tree":
                self.findings[fid]["scope"] = "tree"
            return
        self.findings[fid] = {
            "id": fid, "severity": severity, "category": category, "rule": rule,
            "title": title, "file": file, "line": line, "scope": scope,
            "locations": [loc], "source": "script", "needs_rotation": needs_rotation,
            "in_test_path": in_test, "excerpt": excerpt, "fix_hint": fix,
        }

    def hint(self, rule, file, line, text):
        h = self.hints.setdefault(rule, {"rule": rule, "count": 0, "examples": []})
        h["count"] += 1
        if len(h["examples"]) < 5:
            h["examples"].append({"file": file, "line": line, "text": text.strip()[:140]})


def is_placeholder(value):
    return bool(PLACEHOLDER_RE.search(value)) or len(set(value)) <= 2


def provider_matches(line):
    """Yield (rule, value) for provider-specific secrets, dropping overlapping spans."""
    taken = []
    for rule, rx in PROVIDER_RULES:
        for m in rx.finditer(line):
            span = m.span()
            if any(s[0] <= span[0] and span[1] <= s[1] for s in taken):
                continue
            value = m.group(1) if rule == "db-url-with-password" else m.group(0)
            if "EXAMPLE" in value or (rule == "db-url-with-password"
                                      and is_placeholder(value)):
                continue
            taken.append(span)
            yield rule, value


def classify(rule, value, line, in_test):
    """Return (severity, needs_rotation). A DB URL pointing at a local host is a
    dev credential, not a leaked production secret."""
    if rule == "db-url-with-password":
        m = re.search(re.escape(value) + r"@([^\s:/'\"]+)", line)
        if m and m.group(1).lower() in LOCAL_HOSTS:
            return ("weak" if in_test else "medium"), False
    return "critical", True


def scan_line(c, line, rel, lineno, ext):
    in_test = bool(TEST_PATH_RE.search(rel))
    redacted = line.strip()
    for rule, value in provider_matches(line):
        shown = redacted.replace(value, mask(value))[:160]
        sev, rotate = classify(rule, value, line, in_test)
        fix = ("Rotate the credential, remove it from code and history, load it from the environment."
               if rotate else "Local dev credential: keep it out of committed files, use .env.")
        c.add(rule, sev, "secret" if rotate else "secret-generic",
              f"{rule} in source" if rotate else "Local DB URL with password in source",
              rel, lineno, "tree", value=value, needs_rotation=rotate, fix=fix,
              excerpt=shown, in_test=in_test)
    m = JWT_RE.search(line)
    if m:
        c.add("jwt-in-code", "medium", "secret-generic", "JWT-like token in source",
              rel, lineno, "tree", value=m.group(0), needs_rotation=False,
              fix="Confirm whether this token is public by design (e.g. anon key); otherwise rotate.",
              excerpt=redacted.replace(m.group(0), mask(m.group(0)))[:160], in_test=in_test)
    m = GENERIC_RE.search(line)
    if m and not is_placeholder(m.group(1)):
        v = m.group(1)
        c.add("hardcoded-secret", "weak" if in_test else "medium", "secret-generic",
              "Hard-coded password or key-like value", rel, lineno, "tree", value=v,
              fix="Move to environment variables; rotate if it is real.",
              excerpt=redacted.replace(v, mask(v))[:160], in_test=in_test)
    if ext in CODE_EXT:
        if DEBUG_RE.search(line):
            c.add("debug-mode-on", "medium", "config", "Debug mode enabled in code",
                  rel, lineno, "tree", value=f"{rel}:{lineno}",
                  fix="Drive debug from environment; off in production.")
        if CORS_RE.search(line):
            c.add("cors-wildcard", "medium", "config", "CORS allows any origin",
                  rel, lineno, "tree", value=f"{rel}:{lineno}",
                  fix="Restrict origins to the real front-end domains.")
        for rule, rx in HINT_RULES:
            if rx.search(line):
                c.hint(rule, rel, lineno, line)


def env_has_real_values(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for raw in f:
                raw = raw.strip()
                if not raw or raw.startswith("#") or "=" not in raw:
                    continue
                value = raw.split("=", 1)[1].strip().strip("'\"")
                if value and not is_placeholder(value):
                    return True
    except OSError:
        pass
    return False


def scan_history(root, depth, c):
    cmd = ["git", "-C", root, "log", "--all", "-n", str(depth), "-p", "-U0",
           "--no-color", "--diff-filter=AM", "--format=@@COMMIT %h"]
    try:
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    except Exception:
        return False
    commit, path, seen = "?", "?", 0
    for raw in p.stdout:
        seen += 1
        if seen > 5_000_000:
            break
        line = raw.decode("utf-8", "replace").rstrip("\n")
        if line.startswith("@@COMMIT "):
            commit = line[9:]
        elif line.startswith("+++ b/"):
            path = line[6:]
        elif line.startswith("+") and not line.startswith("+++") and len(line) < MAX_LINE:
            for rule, value in provider_matches(line[1:]):
                if classify(rule, value, line[1:], False)[1] is False:
                    continue  # local dev DB URL: not worth a history finding
                c.add(rule, "critical", "secret", f"{rule} in git history",
                      f"(history) {commit}:{path}", None, "history", value=value,
                      needs_rotation=True,
                      fix="Rotate the credential; history rewrite alone does not undo a leak.",
                      excerpt=line[1:].strip().replace(value, mask(value))[:160])
    p.kill()
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    ap.add_argument("--history", type=int, default=0,
                    help="also scan the last N commits for provider-specific secrets")
    ap.add_argument("--out")
    args = ap.parse_args()
    root = os.path.abspath(args.root)
    if not os.path.isdir(root):
        print(json.dumps({"error": "not a directory", "root": root}))
        return 1

    c = Collector()
    is_repo = bool(git(root, "rev-parse", "--git-dir"))
    tracked = set()
    if is_repo:
        out = git(root, "ls-files", "-z") or ""
        tracked = {p for p in out.split("\0") if p}

    scanned = 0
    for dp, dns, fns in os.walk(root):
        rel_dir = os.path.relpath(dp, root).replace(os.sep, "/")
        # nested .git inside a web-served folder
        if ".git" in dns and rel_dir != ".":
            top = rel_dir.split("/")[0]
            if top in WEB_DIRS:
                c.add("nested-git-in-web", "medium", "exposure",
                      "Git repository inside a web-served folder", rel_dir, None, "tree",
                      value=rel_dir, fix="Remove the .git folder from what gets deployed.")
        dns[:] = [d for d in dns if d not in SKIP_DIRS]
        for fn in fns:
            full = os.path.join(dp, fn)
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            ext = os.path.splitext(fn)[1].lower()
            top = rel.split("/")[0]
            is_tracked = rel in tracked

            if top in WEB_DIRS and "/" in rel and (
                    ext in {".map", ".bak", ".old", ".zip", ".sql"} or ENV_RE.match(fn)):
                c.add("web-folder-exposure", "medium", "exposure",
                      "Source map, backup or dump inside a web-served folder", rel, None,
                      "tree", value=rel,
                      fix="Do not deploy this file; exclude it from the public folder.")

            env_private = False
            if ENV_RE.match(fn) and not ENV_EXAMPLE_RE.search(fn):
                if is_tracked:
                    if env_has_real_values(full):
                        c.add("env-committed", "critical", "secret",
                              "Environment file with real values is committed", rel, None,
                              "tree", value=rel, needs_rotation=True,
                              fix="Untrack it, rotate every value in it, keep only .env.example.")
                    else:
                        c.add("env-committed-empty", "weak", "hygiene",
                              "Environment file is committed (placeholders only)", rel,
                              None, "tree", value=rel,
                              fix="Rename to .env.example and ignore the real file.")
                elif is_repo and not git(root, "check-ignore", "-q", "--", rel, check=True):
                    c.add("env-not-ignored", "medium", "config",
                          "Environment file is not ignored by git", rel, None, "tree",
                          value=rel, fix="Add it to .gitignore before the first commit.")
                elif is_repo:
                    # untracked and git-ignored: this is where secrets belong; the
                    # tree scan skips it (git history is still scanned)
                    env_private = True

            if is_tracked and (fn in KEY_FILE_NAMES or KEY_FILE_RE.search(fn)):
                c.add("key-file-committed", "critical", "secret",
                      "Key or credential file is committed", rel, None, "tree",
                      value=rel, needs_rotation=True,
                      fix="Untrack it, rotate the credential, keep it outside the repo.")
            if is_tracked and DATA_FILE_RE.search(fn):
                c.add("data-file-committed", "medium", "data",
                      "Database or dump file is committed", rel, None, "tree", value=rel,
                      fix="Remove from the repo; check what personal data it holds.")

            if ext in SKIP_EXT or fn in SKIP_NAMES or env_private:
                continue
            try:
                if os.path.getsize(full) > MAX_FILE:
                    continue
                with open(full, "rb") as f:
                    data = f.read()
            except OSError:
                continue
            if b"\0" in data[:1024]:
                continue
            scanned += 1
            for lineno, raw in enumerate(data.decode("utf-8", "replace").splitlines(), 1):
                if len(raw) > MAX_LINE:
                    continue
                scan_line(c, raw, rel, lineno, ext)

    names = {n.lower() for n in os.listdir(root)}
    if is_repo and ".gitignore" not in names:
        c.add("no-gitignore", "weak", "hygiene", "No .gitignore", ".gitignore", None,
              "tree", value="no-gitignore", fix="Add a .gitignore for build output, env files and secrets.")
    if not any(n.startswith("readme") for n in names):
        c.add("no-readme", "weak", "hygiene", "No README", "README", None, "tree",
              value="no-readme", fix="Add a README: what it is, how to run it.")
    if not any(n.startswith(("license", "copying")) for n in names):
        c.add("no-license", "weak", "hygiene", "No LICENSE file", "LICENSE", None, "tree",
              value="no-license", fix="Add a license or state that the code is proprietary.")

    scopes = ["tree"]
    history_ok = False
    if args.history > 0 and is_repo:
        history_ok = scan_history(root, args.history, c)
        if history_ok:
            scopes.append("history")

    result = {
        "root": root,
        "scanned_files": scanned,
        "is_git_repo": is_repo,
        "scopes": scopes,
        "findings": sorted(c.findings.values(),
                           key=lambda f: ("critical", "medium", "weak").index(f["severity"])),
        "hints": sorted(c.hints.values(), key=lambda h: -h["count"]),
    }
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
