# Security severity rubric

When unsure between two levels for anything touching secrets, user data or authentication, choose the higher one.

| Level | Gate behaviour | What counts |
|-------|----------------|-------------|
| **critical** | BLOCK - nothing runs except fixing | Real keys, tokens or passwords in code or git history. Private key files. `.env` with real values committed. DB URL with a real password. Open DB or admin with no authentication. SQL injection or command execution reachable from user input. Customers' personal data in the repository. Closed-source code in a public repository. |
| **medium** | Repeated at every checkpoint until closed | No input validation on public endpoints. No rate limit on login or paid API. Missing auth on secondary endpoints. Debug mode on in production config. CORS `*` on authenticated APIs. Personal data written to logs. Source maps or backups reachable from a public web folder. `.env` present, not ignored, not yet committed. DB files committed. JWT-like tokens in code (may be public by design, e.g. anon keys - confirm). |
| **weak** | Report only | No README, no `.gitignore`, no license. Unpinned or outdated dependencies with no known issue. No tests. `.env.example` missing. |

## Calibration rules (learned on real projects)

1. **A check you could not perform is a Gap, never a finding.** Repository visibility, network reachability, live configuration: if you did not check it, list it under Gaps.
2. **A finding needs evidence of the condition itself.** Possible but unproven means `medium` at most, labelled "not verified".
3. **Name the trigger.** Write "becomes critical when ..." in the fix hint (a second organisation, real documents, network access, a public repository).
4. `.env` that is untracked and git-ignored is the right place for secrets: not a finding. The same file committed or present in history is critical.
5. A DB URL with a password pointing to `localhost` or an internal dev host is a local dev credential: `medium`, `weak` inside tests. Placeholders in any language ("PASSWORD", "ПАРОЛЬ", `<your-key>`) are not secrets.
6. A control that is documented but not built (claimed encryption, a feature not started) is `weak` unless the asset it should protect already exists.
7. Dev-only servers (preview, bench stands) bound to all interfaces: `medium`, and only while they run.
8. A protection that is out of scope by the roadmap (for example multi-tenant isolation planned for phase 2 while one tenant exists) is `medium` with its trigger, not `critical`.

9. **A risk the project's own documents show as a deliberate owner decision is an accepted risk.** Report it as such (medium at most), name the mitigation, do not order destructive cleanup. Example: unencrypted backup copy in a cloud folder, decided and dated by the owner, containing hashes only.
10. **Verify before you recommend anything destructive** (deleting copies, rotating every password, rewriting history): open the cited source and show what proves it is needed.
11. **An extraordinary claim from one web source** (a vendor shutdown, an outright ban) is `[UNVERIFIED]` and stays out of conclusions until a second independent source confirms it.

## Script categories (scan_secrets.py)

| Category | Typical levels |
|----------|----------------|
| `secret` | critical (provider-specific patterns, private keys, DB URLs with password) |
| `secret-generic` | medium (hard-coded password-like assignments; confirm manually) |
| `config` | medium (debug mode, CORS wildcard) |
| `exposure` | medium (maps, backups, nested `.git` in web folders) |
| `data` | medium (database or dump files committed) |
| `hygiene` | weak |

Secrets: removing from code is not closing. Rotate the key, then close with evidence.
