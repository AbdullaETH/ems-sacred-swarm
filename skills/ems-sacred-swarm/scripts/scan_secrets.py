#!/usr/bin/env python3
"""ems-sacred-swarm: read-only secret and exposure scan (stdlib only).

Usage: python scan_secrets.py <project_root> [--history N] [--out scan.json]

Secrets are never printed: values are masked as `AKIA…(20 chars)` (passwords
as `***(12 chars)`, no prefix). Output JSON: {"scopes": [...], "findings": [...],
"hints": [...]} - feed it to gate.py --ingest. `hints` are risky patterns for
the security agent to triage; they do not affect the gate.

Severity depends on where a value lives: tracked by git (or shipped in a web
bundle) = leaked; untracked, git-ignored or outside git = a risk with a trigger.
Git-ignored folders are not walked, except deployable web build output.
--history N (default 300) also scans the last N commits for provider secrets
and for .env files that were committed and later removed.
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
    ".terraform", ".dart_tool", "site-packages",
}
# build output is walked only when it looks like a deployable web bundle:
# keys and source maps shipped to browsers are a leak even if git ignores them
BUILD_DIRS = {"dist", "build", "out"}
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
    ".php", ".rb", ".go", ".rs", ".java", ".kt", ".cs", ".sh", ".ps1", ".bat", ".gd",
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
    ("huggingface-token", re.compile(r"\bhf_[A-Za-z0-9]{34,}\b")),
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
SECRET_KEY_RE = re.compile(
    r"(?i)(key|token|secret|pass|pwd|auth|credential|dsn|private|salt|cookie|session|webhook)")
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "0.0.0.0", "host.docker.internal",
               "db", "postgres", "mysql", "mariadb", "redis", "mongo"}
DEBUG_RE = re.compile(r"(?i)(\bDEBUG\s*=\s*True\b|\bapp\.run\([^)]*debug\s*=\s*True)")
CORS_RE = re.compile(
    r"""(?i)(access-control-allow-origin['"]?\s*[:,]\s*['"]?\*|origin\s*:\s*['"]\*['"])""")
HINT_RULES = [
    # builtin eval/exec only: not regex.exec(), model.eval(), def exec(
    ("eval-exec", re.compile(r"(?<![.\w])(?<!def )(?:eval|exec)\s*\((?!\s*\))")),
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
SEVERITY_ORDER = ("critical", "medium", "weak")
# rules whose value is a password chosen by a person: show no prefix at all
NO_PREFIX_RULES = {"db-url-with-password", "hardcoded-secret", "env-in-history"}


def mask(value, show=4):
    return f"{value[:show]}…({len(value)} chars)" if show else f"***({len(value)} chars)"


def sha(text):
    return hashlib.sha1(text.encode("utf-8", "replace")).hexdigest()


def git(root, *args, check=False):
    try:
        r = subprocess.run(
            ["git", "-C", root, *args], capture_output=True, text=True,
            timeout=60, encoding="utf-8", errors="replace")
        if check:
            return r.returncode == 0
        return r.stdout if r.returncode == 0 else None
    except Exception:
        return None if not check else False


def git_ignored(root):
    """Return (ignored_files, ignored_dirs) relative to root, as git sees them."""
    out = git(root, "ls-files", "-z", "--others", "--ignored", "--exclude-standard",
              "--directory") or ""
    files, dirs = set(), set()
    for p in out.split("\0"):
        if p:
            (dirs if p.endswith("/") else files).add(p.rstrip("/"))
    return files, dirs


def is_web_bundle(path):
    try:
        names = set(os.listdir(path))
    except OSError:
        return False
    return bool(names & {"index.html", "assets", "_next", "static"})


def has_web_child(path):
    """git collapses a folder holding only ignored files (frontend/ with just
    dist/ in it); look one level down before pruning it."""
    try:
        subs = [e for e in os.scandir(path) if e.is_dir()]
    except OSError:
        return False
    return any(e.name in WEB_DIRS and (e.name not in BUILD_DIRS or is_web_bundle(e.path))
               for e in subs)


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


def redact(text):
    """Mask every secret-looking value in a line (excerpts and hints)."""
    for rule, value in list(provider_matches(text)):
        text = text.replace(value, mask(value, 0 if rule in NO_PREFIX_RULES else 4))
    m = JWT_RE.search(text)
    if m:
        text = text.replace(m.group(0), mask(m.group(0)))
    m = GENERIC_RE.search(text)
    if m:
        text = text.replace(m.group(1), mask(m.group(1), 0))
    return text


class Collector:
    def __init__(self):
        self.findings = {}
        self.hints = {}

    def add(self, rule, severity, category, title, file, line, scope,
            value=None, needs_rotation=False, fix=None, excerpt=None, in_test=False):
        fid = sha(f"{rule}|{value if value is not None else file}")[:10]
        loc = {"file": file, "line": line, "scope": scope}
        if fid in self.findings:
            f = self.findings[fid]
            if loc not in f["locations"] and len(f["locations"]) < 5:
                f["locations"].append(loc)
            if scope == "tree":
                f["scope"] = "tree"
            # the same value in several places: the worst place decides
            if SEVERITY_ORDER.index(severity) < SEVERITY_ORDER.index(f["severity"]):
                f.update(severity=severity, category=category, title=title, file=file,
                         line=line, needs_rotation=needs_rotation, fix_hint=fix,
                         excerpt=excerpt, in_test_path=in_test)
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
            h["examples"].append({"file": file, "line": line,
                                  "text": redact(text.strip())[:140]})


def classify(rule, value, line, in_test):
    """Return (severity, needs_rotation). A DB URL pointing at a local host is a
    dev credential, not a leaked production secret."""
    if rule == "db-url-with-password":
        m = re.search(re.escape(value) + r"@([^\s:/'\"]+)", line)
        if m and m.group(1).lower() in LOCAL_HOSTS:
            return ("weak" if in_test else "medium"), False
    return "critical", True


def by_state(severity, rotate, fix, state, web):
    """Adjust a content finding to where the file lives. Only a value that git
    tracks (or that ships in a web bundle) has leaked; elsewhere it is a risk."""
    if state == "tracked" or severity == "weak":
        return severity, rotate, fix
    if state == "ignored" and web:
        return ("medium" if severity == "critical" else severity), False, (
            f"{fix} Ignored by git but inside web build output: critical once deployed.")
    if state == "ignored":
        return "weak", False, f"{fix} Git-ignored local file: keep it out of copies you hand over."
    trigger = ("critical once committed" if state == "untracked"
               else "no git here: critical when the folder is shared, sold or pushed")
    return ("medium" if severity == "critical" else severity), False, f"{fix} Not leaked yet, {trigger}."


def scan_line(c, line, rel, lineno, ext, state="tracked", web=False):
    in_test = bool(TEST_PATH_RE.search(rel))
    long_line = len(line) > MAX_LINE  # minified bundles: provider patterns only
    shown = redact(line[:400].strip() if long_line else line.strip())[:160]
    for rule, value in provider_matches(line):
        sev, rotate = classify(rule, value, line, in_test)
        fix = ("Rotate the credential, remove it from code and history, load it from the environment."
               if rotate else "Local dev credential: keep it out of committed files, use .env.")
        sev, rotate, fix = by_state(sev, rotate, fix, state, web)
        c.add(rule, sev, "secret" if sev == "critical" else "secret-generic",
              f"{rule} in source" if state == "tracked" else f"{rule} in {state} file",
              rel, lineno, "tree", value=value, needs_rotation=rotate, fix=fix,
              excerpt=shown, in_test=in_test)
    if long_line:
        return
    m = JWT_RE.search(line)
    if m:
        sev, _, fix = by_state(
            "medium", False,
            "Confirm whether this token is public by design (e.g. anon key); otherwise rotate.",
            state, web)
        c.add("jwt-in-code", sev, "secret-generic", "JWT-like token in source",
              rel, lineno, "tree", value=m.group(0), needs_rotation=False, fix=fix,
              excerpt=shown, in_test=in_test)
    m = GENERIC_RE.search(line)
    if m and not is_placeholder(m.group(1)):
        sev, _, fix = by_state("weak" if in_test else "medium", False,
                               "Move to environment variables; rotate if it is real.", state, web)
        c.add("hardcoded-secret", sev, "secret-generic",
              "Hard-coded password or key-like value", rel, lineno, "tree",
              value=m.group(1), fix=fix, excerpt=shown, in_test=in_test)
    if ext in CODE_EXT and state != "ignored":
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


def env_pair(raw):
    raw = raw.strip()
    if not raw or raw.startswith("#") or "=" not in raw:
        return None, None
    key, value = raw.split("=", 1)
    return key.replace("export ", "").strip(), value.strip().strip("'\"")


def env_secret_value(key, value):
    """True when an env assignment looks like a real secret, not plain config."""
    if not value:
        return False
    if any(True for _ in provider_matches(value)):
        return True
    if is_placeholder(value):
        return False
    return bool(SECRET_KEY_RE.search(key)) and len(value) >= 6


def env_kind(path):
    """'secret' (real secret-like values), 'config' (real values, none of them
    secret-like) or 'placeholder'."""
    kind = "placeholder"
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for raw in f:
                key, value = env_pair(raw)
                if key is None:
                    continue
                if env_secret_value(key, value):
                    return "secret"
                if value and not is_placeholder(value):
                    kind = "config"
    except OSError:
        pass
    return kind


def scan_history(root, depth, c, tracked):
    cmd = ["git", "-C", root, "log", "--all", "-n", str(depth), "-p", "-U0",
           "--no-color", "--diff-filter=AM", "--format=@@COMMIT %h"]
    try:
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    except Exception:
        return False
    commit, path, seen = "?", "?", 0
    try:
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
                text = line[1:]
                for rule, value in provider_matches(text):
                    if classify(rule, value, text, False)[1] is False:
                        continue  # local dev DB URL: not worth a history finding
                    c.add(rule, "critical", "secret", f"{rule} in git history",
                          f"(history) {commit}:{path}", None, "history", value=value,
                          needs_rotation=True,
                          fix="Rotate the credential; history rewrite alone does not undo a leak.",
                          excerpt=redact(text.strip())[:160])
                base = path.rsplit("/", 1)[-1]
                if (ENV_RE.match(base) and not ENV_EXAMPLE_RE.search(base)
                        and path not in tracked):
                    key, value = env_pair(text)
                    if key and env_secret_value(key, value):
                        c.add("env-in-history", "critical", "secret",
                              "Environment file with secrets is in git history",
                              f"(history) {commit}:{path}", None, "history", value=value,
                              needs_rotation=True,
                              fix=f"Rotate {key}; the file is gone from the tree but not from history.",
                              excerpt=f"{key}={mask(value, 0)}")
    finally:
        p.kill()
        p.wait()
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    ap.add_argument("--history", type=int, default=300,
                    help="also scan the last N commits (0 = tree only)")
    ap.add_argument("--out")
    args = ap.parse_args()
    root = os.path.abspath(args.root)
    if not os.path.isdir(root):
        print(json.dumps({"error": "not a directory", "root": root}))
        return 1

    c = Collector()
    is_repo = bool(git(root, "rev-parse", "--git-dir"))
    tracked, ign_files, ign_dirs = set(), set(), set()
    if is_repo:
        out = git(root, "ls-files", "-z") or ""
        tracked = {p for p in out.split("\0") if p}
        ign_files, ign_dirs = git_ignored(root)

    def state_of(rel):
        if not is_repo:
            return "norepo"
        if rel in tracked:
            return "tracked"
        if rel in ign_files or any(rel.startswith(d + "/") for d in ign_dirs):
            return "ignored"
        return "untracked"

    scanned = 0
    pruned = []
    for dp, dns, fns in os.walk(root):
        rel_dir = os.path.relpath(dp, root).replace(os.sep, "/")
        rel_dir = "" if rel_dir == "." else rel_dir
        parts = rel_dir.split("/") if rel_dir else []
        web = any(p in WEB_DIRS for p in parts)
        # nested .git inside a web-served folder
        if ".git" in dns and web:
            c.add("nested-git-in-web", "medium", "exposure",
                  "Git repository inside a web-served folder", rel_dir, None, "tree",
                  value=rel_dir, fix="Remove the .git folder from what gets deployed.")
        keep = []
        for d in sorted(dns):
            sub = f"{rel_dir}/{d}" if rel_dir else d
            if d in SKIP_DIRS:
                continue
            bundle = d in BUILD_DIRS and is_web_bundle(os.path.join(dp, d))
            if d in BUILD_DIRS and not bundle:
                continue  # compiler output, not something a browser downloads
            if sub in ign_dirs and not bundle and d not in WEB_DIRS and not has_web_child(
                    os.path.join(dp, d)):
                pruned.append(sub)
                continue
            keep.append(d)
        dns[:] = keep
        for fn in fns:
            full = os.path.join(dp, fn)
            rel = f"{rel_dir}/{fn}" if rel_dir else fn
            ext = os.path.splitext(fn)[1].lower()
            state = state_of(rel)

            if web and (ext in {".map", ".bak", ".old", ".zip", ".sql"} or ENV_RE.match(fn)):
                c.add("web-folder-exposure", "medium", "exposure",
                      "Source map, backup or dump inside a web-served folder", rel, None,
                      "tree", value=rel,
                      fix="Do not deploy this file; exclude it from the public folder.")

            env_private = False
            if ENV_RE.match(fn) and not ENV_EXAMPLE_RE.search(fn):
                if state == "tracked":
                    kind = env_kind(full)
                    if kind == "secret":
                        c.add("env-committed", "critical", "secret",
                              "Environment file with real secrets is committed", rel, None,
                              "tree", value=rel, needs_rotation=True,
                              fix="Untrack it, rotate every secret in it, keep only .env.example.")
                    elif kind == "config":
                        c.add("env-committed", "medium", "config",
                              "Environment file is committed (config values, no secret-looking keys)",
                              rel, None, "tree", value=rel,
                              fix="Untrack it and keep .env.example; becomes critical once a secret is added.")
                    else:
                        c.add("env-committed-empty", "weak", "hygiene",
                              "Environment file is committed (placeholders only)", rel,
                              None, "tree", value=rel,
                              fix="Rename to .env.example and ignore the real file.")
                elif state == "untracked":
                    c.add("env-not-ignored", "medium", "config",
                          "Environment file is not ignored by git", rel, None, "tree",
                          value=rel, fix="Add it to .gitignore before the first commit.")
                elif state == "ignored":
                    # where secrets belong; history is still scanned
                    env_private = True

            if state == "tracked" and (fn in KEY_FILE_NAMES or KEY_FILE_RE.search(fn)):
                c.add("key-file-committed", "critical", "secret",
                      "Key or credential file is committed", rel, None, "tree",
                      value=rel, needs_rotation=True,
                      fix="Untrack it, rotate the credential, keep it outside the repo.")
            if state == "tracked" and DATA_FILE_RE.search(fn):
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
                scan_line(c, raw, rel, lineno, ext, state, web)

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
    if args.history > 0 and is_repo and scan_history(root, args.history, c, tracked):
        scopes.append("history")

    result = {
        "root": root,
        "scanned_files": scanned,
        "is_git_repo": is_repo,
        "scopes": scopes,
        "skipped_ignored_dirs": pruned[:30],
        "findings": sorted(c.findings.values(),
                           key=lambda f: SEVERITY_ORDER.index(f["severity"])),
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
