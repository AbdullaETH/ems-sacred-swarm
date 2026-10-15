"""Regression tests for the helper scripts (stdlib only).

Run:  python -m unittest discover -s tests -v
All "secrets" are built from fragments at runtime and are not real.
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SK = os.path.join(os.path.dirname(HERE), "skills", "ems-sacred-swarm", "scripts")

FAKE_AWS = "AKIA" + "QWERTYUIOPASDFGH"
FAKE_DB_PW = "S3cret" + "Pass99"
LOCAL_DB_PW = "localpw" + "1234"


def script(name, *args):
    return subprocess.run([sys.executable, os.path.join(SK, name), *args],
                          capture_output=True, text=True, encoding="utf-8")


def git(path, *args):
    subprocess.run(["git", "-C", path, "-c", "user.name=t", "-c", "user.email=t@t", *args],
                   check=True, capture_output=True)


def write(root, rel, text):
    p = os.path.join(root, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(text)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = os.path.join(self.tmp.name, "proj")
        os.makedirs(self.root)
        self.out = os.path.join(self.tmp.name, "out")
        git(self.root, "init", "-q")

    def commit(self, msg="init"):
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", msg)

    def scan(self, *extra):
        path = os.path.join(self.tmp.name, "scan.json")
        r = script("scan_secrets.py", self.root, "--out", path, *extra)
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(path, encoding="utf-8") as f:
            return json.load(f), r.stdout


class ScanSecrets(Base):
    def test_masking_and_classification(self):
        write(self.root, "app.py", f'AWS = "{FAKE_AWS}"\nDEBUG = True\n')
        scheme = "postgres" + "://"
        write(self.root, "cfg.js",
              'const a = "' + scheme + "admin:" + FAKE_DB_PW + '@db.internal:5432/app";\n'
              'const b = "' + scheme + "dev:" + LOCAL_DB_PW + '@localhost:5432/dev";\n')
        write(self.root, ".env", "MODE=prod\nTOKEN=" + "sk_live_" + "abcdefghij1234567890XYZ\n")
        write(self.root, "node_modules/x/leak.js", f'const k = "{FAKE_AWS}";\n')
        self.commit()
        data, raw = self.scan("--history", "10")
        for secret in (FAKE_AWS, FAKE_DB_PW, LOCAL_DB_PW):
            self.assertNotIn(secret, raw)
        rules = {(f["rule"], f["severity"]) for f in data["findings"]}
        self.assertIn(("aws-access-key", "critical"), rules)
        self.assertIn(("env-committed", "critical"), rules)
        self.assertIn(("debug-mode-on", "medium"), rules)
        db = [f for f in data["findings"] if f["rule"] == "db-url-with-password"]
        self.assertEqual(sorted(f["severity"] for f in db), ["critical", "medium"])
        tree_files = {loc["file"] for f in data["findings"] for loc in f["locations"]
                      if loc["scope"] == "tree"}
        self.assertFalse(any(p.startswith("node_modules") for p in tree_files))
        self.assertEqual(data["scopes"], ["tree", "history"])

    def test_ignored_untracked_env_is_skipped(self):
        write(self.root, ".gitignore", ".env\n")
        write(self.root, ".env", "KEY=" + FAKE_AWS + "\n")
        write(self.root, "README.md", "x\n")
        self.commit()
        data, _ = self.scan()
        self.assertFalse(any(loc["file"] == ".env" for f in data["findings"]
                             for loc in f["locations"]))

    def test_cyrillic_placeholder_is_not_a_secret(self):
        write(self.root, "doc.md", "source: postgresql://postgres:ПАРОЛЬ@db.internal:5432/x\n")
        self.commit()
        data, _ = self.scan()
        self.assertFalse([f for f in data["findings"] if f["rule"] == "db-url-with-password"])


    def by_rule(self, data, rule):
        return [f for f in data["findings"] if f["rule"] == rule]

    def test_web_build_folders_are_checked(self):
        write(self.root, "frontend/dist/index.html", "<html></html>\n")
        write(self.root, "frontend/dist/app.js.map", "{}\n")
        write(self.root, "backend/build/lib/x.py", f'K = "{FAKE_AWS}"\n')  # compiler output, skipped
        key = "AIza" + "SyA1234567890abcdefghijklmnopqrstuv"
        write(self.root, "frontend/dist/app.js", "var a=1;" * 900 + f'var k="{key}";\n')
        write(self.root, ".gitignore", "dist/\n")
        self.commit()
        data, raw = self.scan()
        self.assertNotIn(key, raw)
        self.assertTrue(self.by_rule(data, "web-folder-exposure"))
        g = self.by_rule(data, "google-api-key")
        self.assertTrue(g)
        self.assertEqual(g[0]["severity"], "medium")  # ignored build output: critical once deployed

    def test_git_status_decides_secret_severity(self):
        write(self.root, ".gitignore", "secrets/\nlocal.json\n")
        write(self.root, "secrets/k.py", f'K = "{FAKE_AWS}"\n')
        write(self.root, "local.json", '{"k": "' + FAKE_AWS + '"}\n')
        write(self.root, "README.md", "x\n")
        self.commit()
        write(self.root, "new.py", f'K = "{FAKE_AWS}"\n')  # untracked, not ignored
        data, _ = self.scan()
        aws = self.by_rule(data, "aws-access-key")
        self.assertEqual(len(aws), 1)
        files = {loc["file"] for loc in aws[0]["locations"]}
        self.assertNotIn("secrets/k.py", files)  # ignored folders are not walked
        self.assertEqual(aws[0]["severity"], "medium")  # worst location: untracked, not ignored
        self.assertFalse(aws[0]["needs_rotation"])

    def test_committed_env_without_secrets_is_not_critical(self):
        write(self.root, ".env", "PORT=3000\nHOST=0.0.0.0\nLOG_LEVEL=info\n")
        self.commit()
        data, _ = self.scan()
        env = self.by_rule(data, "env-committed")
        self.assertEqual([f["severity"] for f in env], ["medium"])

    def test_env_in_history(self):
        val = "q8Zt" + "Lw3mVn7Xk2Rp9s"
        write(self.root, ".env", f"API_KEY={val}\n")
        write(self.root, "README.md", "x\n")
        self.commit()
        os.remove(os.path.join(self.root, ".env"))
        write(self.root, ".gitignore", ".env\n")
        self.commit("drop env")
        data, raw = self.scan("--history", "10")
        self.assertNotIn(val, raw)
        hist = self.by_rule(data, "env-in-history")
        self.assertTrue(hist)
        self.assertEqual(hist[0]["severity"], "critical")

    def test_password_prefix_is_not_shown(self):
        scheme = "postgres" + "://"
        write(self.root, "cfg.js", 'const a = "' + scheme + "admin:" + FAKE_DB_PW + '@db.internal/x";\n')
        self.commit()
        _, raw = self.scan()
        self.assertNotIn(FAKE_DB_PW[:4], raw)

    def test_hint_examples_are_redacted(self):
        write(self.root, "run.py", f'os.system("deploy --key {FAKE_AWS}")\n')
        self.commit()
        _, raw = self.scan()
        self.assertNotIn(FAKE_AWS, raw)


class Gate(Base):
    def ingest(self, findings, source="agent"):
        path = os.path.join(self.tmp.name, "agent.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"findings": findings}, f)
        return script("gate.py", self.out, "--ingest", path, "--source", source)

    def test_severity_is_normalised(self):
        r = self.ingest([{"title": "Admin open", "severity": "Critical", "file": "a.py"}])
        self.assertEqual(json.loads(r.stdout)["status"], "BLOCK")
        r = self.ingest([{"title": "x", "severity": "HIGH", "file": "b.py"},
                         {"title": "y", "severity": "banana", "file": "c.py"}])
        j = json.loads(r.stdout)
        self.assertEqual(len(j["critical"]), 2)
        self.assertEqual(len(j["medium"]), 1)

    def test_ingest_markdown_report(self):
        md = os.path.join(self.tmp.name, "sec.md")
        with open(md, "w", encoding="utf-8") as f:
            f.write("Narrative.\n\n```json\n" + json.dumps(
                {"findings": [{"title": "No rate limit", "severity": "medium", "file": "api.py"}]})
                + "\n```\n")
        r = script("gate.py", self.out, "--ingest-md", md)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(json.loads(r.stdout)["status"], "NAG")

    def test_manual_rating_and_close_survive_rescan(self):
        write(self.root, "app.py", f'AWS = "{FAKE_AWS}"\nDEBUG = True\n')
        self.commit()
        self.scan("--history", "0")
        scan_path = os.path.join(self.tmp.name, "scan.json")
        j = json.loads(script("gate.py", self.out, "--ingest", scan_path, "--source", "script").stdout)
        crit, med = j["critical"][0]["id"], j["medium"][0]["id"]
        self.assertEqual(script("gate.py", self.out, "--rate", crit, "--severity", "weak").returncode, 1)
        r = script("gate.py", self.out, "--rate", crit, "--severity", "weak",
                   "--evidence", "test fixture, never a real key")
        self.assertEqual(json.loads(r.stdout)["status"], "NAG")
        script("gate.py", self.out, "--close", med, "--evidence", "dev-only flag")
        j = json.loads(script("gate.py", self.out, "--ingest", scan_path, "--source", "script").stdout)
        self.assertEqual(j["status"], "OK")

    def test_block_rotation_close(self):
        write(self.root, "app.py", f'AWS = "{FAKE_AWS}"\n')
        self.commit()
        data, _ = self.scan("--history", "0")
        scan_path = os.path.join(self.tmp.name, "scan.json")
        r = script("gate.py", self.out, "--ingest", scan_path, "--source", "script")
        self.assertEqual(r.returncode, 2)
        self.assertEqual(json.loads(r.stdout)["status"], "BLOCK")
        # remove the secret, rescan: critical secrets stay blocked until rotation is confirmed
        write(self.root, "app.py", 'import os\nAWS = os.environ["AWS"]\n')
        self.commit("fix")
        self.scan("--history", "0")
        r = script("gate.py", self.out, "--ingest", scan_path, "--source", "script")
        j = json.loads(r.stdout)
        self.assertEqual(j["status"], "BLOCK")
        self.assertTrue(all(c["status"] == "pending_rotation" for c in j["critical"]))
        fid = j["critical"][0]["id"]
        bad = script("gate.py", self.out, "--close", fid)
        self.assertEqual(bad.returncode, 1)
        ok = script("gate.py", self.out, "--close", fid, "--evidence", "rotated in provider console")
        self.assertNotEqual(json.loads(ok.stdout)["status"], "BLOCK")


class VerifyEvidence(Base):
    def test_tags(self):
        write(self.root, "app.py", "a = 1\nb = 2\nc = 3\n")
        self.commit()
        head = subprocess.run(["git", "-C", self.root, "rev-parse", "--short", "HEAD"],
                              capture_output=True, text=True).stdout.strip()
        md = os.path.join(self.tmp.name, "rep.md")
        with open(md, "w", encoding="utf-8") as f:
            f.write(
                "ok [src: app.py:2]. range [src: app.py:1-3]. bad line [src: app.py:99]. "
                "missing [src: nope.py:1]. escape [src: ../../etc/passwd:1]. "
                "absent ok [src: absent:README.md]. absent wrong [src: absent:app.py]. "
                f"commit [src: git:{head}]. hist [src: git:{head}:app.py:2]. "
                "url graded [src: https://example.com/a; A]. url ungraded [src: https://example.com/b]. "
                "[UNVERIFIED]\n")
        r = script("verify_evidence.py", self.root, md)
        j = json.loads(r.stdout)
        self.assertEqual(r.returncode, 1)
        self.assertEqual(j["ok"], 5)
        self.assertEqual(sorted(b["tag"] for b in j["bad"]),
                         sorted(["app.py:99", "nope.py:1", "../../etc/passwd:1", "absent:app.py"]))
        self.assertEqual(j["source_grades"]["A"], 1)
        self.assertEqual(j["urls_without_grade"], 1)
        self.assertEqual(j["unverified_marks"], 1)


class Inventory(Base):
    def test_active_days_and_fingerprint(self):
        write(self.root, "README.md", "hello\n")
        write(self.root, "main.py", "print(1)\n")
        self.commit()
        out = os.path.join(self.tmp.name, "inv.json")
        r1 = script("inventory.py", self.root, "--out", out)
        a = json.loads(r1.stdout)
        self.assertEqual(a["git"]["active_days"], 1)
        self.assertTrue(a["docs"]["readme"])
        r2 = script("inventory.py", self.root)
        self.assertEqual(a["fingerprint"], json.loads(r2.stdout)["fingerprint"])
        write(self.root, "main.py", "print(2)\n")
        r3 = script("inventory.py", self.root)
        self.assertNotEqual(a["fingerprint"], json.loads(r3.stdout)["fingerprint"])

    def test_redaction_and_ignored_dirs(self):
        pw = "hunter" + "2xyz77"
        write(self.root, "docker-compose.yml",
              f"services:\n  db:\n    environment:\n      POSTGRES_PASSWORD: {pw}\n      K: {FAKE_AWS}\n")
        write(self.root, ".gitignore", "data/\n")
        write(self.root, "data/big.py", "x = 1\n" * 50)
        write(self.root, "main.py", "print(1)\n")
        self.commit()
        r = script("inventory.py", self.root)
        self.assertNotIn(pw, r.stdout)
        self.assertNotIn(FAKE_AWS, r.stdout)
        j = json.loads(r.stdout)
        self.assertFalse(any(d == "data" for d, _ in j["top_dirs"]))


class RunPlan(unittest.TestCase):
    def total(self, *args):
        r = script("run_plan.py", *args)
        self.assertEqual(r.returncode, 0, r.stderr)
        m = re.search(r"TOTAL agent runs\s+(\d+)\s+(\d+)", r.stdout)
        self.assertTrue(m, r.stdout)
        return int(m.group(1)), int(m.group(2))

    def test_economy_and_lean(self):
        self.assertEqual(self.total("--projects", "5", "--preset", "economy"), (55, 15))
        h, s = self.total("--projects", "5", "--preset", "economy", "--lean")
        self.assertEqual(h + s, 65)
        h, s = self.total("--projects", "1", "--preset", "strong", "--levels", "S,M")
        self.assertEqual((h, s), (0, 13))  # 14 roles minus researcher L


class Export(Base):
    def test_txt(self):
        md = os.path.join(self.tmp.name, "r.md")
        with open(md, "w", encoding="utf-8") as f:
            f.write("# Title\n\n**bold** and `code`\n\n| a | b |\n|---|---|\n| 1 | 2 |\n")
        r = script("export_report.py", md, "--txt")
        self.assertEqual(r.returncode, 0)
        with open(os.path.join(self.tmp.name, "r.txt"), encoding="utf-8") as f:
            text = f.read()
        self.assertNotIn("**", text)
        self.assertIn("a | b", text)
        self.assertNotIn("---", text)


if __name__ == "__main__":
    unittest.main()
