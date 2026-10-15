---
name: ems-sacred-swarm
description: Use when the user says "Sacred Swarm", "EMS" or "Examen Machinarum Sacrum", or wants a staged audit of software projects - current state, readiness to sell, security gaps, competitors, market, rough valuation, sales advice. RU - священный рой, рой агентов, рой, ЕМС, аудит проекта, проверь проект, готовность к продаже, оценка стоимости, конкуренты.
---

# EMS - Sacred Swarm (Examen Machinarum Sacrum)

Also known as **Sacred Swarm**, **Священный Рой**, **Рой агентов**, **ЕМС**. When the user calls it by any of these names, run this skill. Staged, evidence-based audit of software projects. Cheap read-only Haiku sub-agents gather facts; **you** (the main model) verify, decide and talk to the user. A critical security finding stops everything except fixing it.

`<skill>` below = the directory this SKILL.md was loaded from. Role prompts are in `<skill>/agents/`, scoring rules in `<skill>/rubrics/`, helpers in `<skill>/scripts/` (Python 3, stdlib only, read-only).

## Hard rules

1. **Read-only on the user's projects.** Never write to, build, run, install or execute project code. Sub-agents are launched as `Explore` (no Edit/Write); only you write, and only into the output folder.
2. **Permissions first, once.** In phase 0 ask for: project folders, GitHub via `gh` (read-only), web search, output folder, storing the output path in `~/.claude/ems-sacred-swarm/config.json`. Anything not granted is skipped and listed as a gap in the report. `gh` is read-only (`gh repo view`, GET calls) and reaches private repositories only if the user says so. If a project folder is outside the directories this session may read, request access before launching agents.
3. **Evidence or silence.** Every claim carries `[src: path:line]`, `[src: URL]` or `[UNVERIFIED]`. Check agent output with `scripts/verify_evidence.py`; remove or mark claims that fail.
4. **No invented numbers.** Valuation is a range with assumptions and confidence. Market figures need a URL and a date.
5. **Never reveal secrets** - not in reports, chat or agent prompts. Masked form only (`AKIA…(20 chars)`).
6. **Web queries stay generic.** Describe the product category and region; do not send the project's private name, code or client names unless the user approves.
7. **Blunt, not cruel.** "This is a prototype, not a product" is allowed. Insults, sarcasm and softening padding are not.
8. **Language:** talk and write reports in the user's language. Agent prompts stay English; tell each agent the report language.
9. **Checkpoint after every phase** (protocol below). Never chain phases silently.

## Phases

| # | Phase | Agents (model) | Saves | Ask the user |
|---|-------|----------------|-------|--------------|
| 0 | Setup | none | `state.json` | permissions, region(s), mode (one project / queue), synthesis model, security first pass |
| 1 | State & readiness | `scout` + `appraiser` (haiku) | `phases/01-state.md` | continue? |
| 2 | Security gate | scripts + `security` (haiku) | `phases/02-security.md`, `findings.json` | close findings? |
| 3 | Weak spots | `critic` (haiku) | `phases/03-weak.md` | continue? |
| 4 | Research | `researcher` S → M → L (haiku) | `phases/04-research-{s,m,l}.md` | which levels |
| 5 | Value | `valuer` (haiku) | `phases/05-valuation.md` | continue? |
| 6 | Collect | `collector` (synthesis model) | `REPORT-SHORT.md`, then `REPORT-FULL.md` | write the full document? format txt / md / docx |
| 7 | Improve | `improver` (synthesis model) | `phases/07-improve.md`, `ideas.md` | which fixes first |
| 8 | Sell | `sales-finance` (synthesis model) | `phases/08-sales.md` | existing deck / business plan to review? |

Synthesis model defaults to `sonnet`; the user may choose `haiku` in phase 0 for maximum economy. Research level S runs on request, M and L only after the user picks them in phase 4 (L reads the S and M outputs; final market synthesis is done by the collector, not by Haiku).

## Phase protocol (every phase)

1. **Card.** Show: agents, goal, what they read / which sites they search, load (low / medium / high - never invented token counts). Ask: run / adjust / skip. Use AskUserQuestion.
2. **Gate.** `python <skill>/scripts/gate.py <out>/<slug>`. Status `BLOCK` → only phase 7 may run. Status `NAG` → continue, but see checkpoint.
3. **Run.** Agent tool, `subagent_type: "Explore"`, `model: "haiku"` (or the synthesis model). Prompt = `agents/_common.md` + `agents/<role>.md` + exact input paths + report language. Independent agents in parallel (max 4); dependent ones in sequence.
4. **Verify and re-rate.** Save the agent text first, then `python <skill>/scripts/verify_evidence.py <project_root> <file>`. A bad tag is a wrong claim: re-check it against the project and fix or drop it. Agent severities are proposals: open the cited lines of every `critical` and downgrade anything whose condition is not proven (calibration rules in `rubrics/severity.md`). Spot-check two other claims yourself.
5. **Save.** Write the phase file yourself. Sub-agents never write: the harness blocks report-file writes from sub-agents anyway, so phases 6-8 also return text and you save `REPORT-SHORT.md`, `07-improve.md`, `08-sales.md`, `ideas.md`.
6. **Checkpoint.** (a) ≤5-line summary, (b) 1-3 concrete pieces of advice, (c) every open `medium` finding from the gate, with "close it now?", (d) new improvement ideas appended to `ideas.md`, (e) AskUserQuestion: continue / go deeper / stop.

## Security gate

Rubric: `rubrics/severity.md`. Findings live in `<out>/<slug>/findings.json`, managed only through `scripts/gate.py`.

| Level | Behaviour |
|-------|-----------|
| weak | Listed in the report, no interruption |
| medium | Repeated at **every** checkpoint until closed |
| critical | `BLOCK`: phases 3-6 and 8 refuse to run; only phase 7 (fixing) is allowed |

- No override, no "accept the risk" for critical.
- A leaked secret is not closed by deleting it. After removal it becomes `pending_rotation`; close only when the user confirms rotation: `gate.py <dir> --close ID --evidence "..."`.
- Re-run the scan after fixes: `scan_secrets.py` → `gate.py --ingest scan.json --source script`. Script findings that disappear are closed automatically; agent findings close only with fresh evidence.
- A script finding you proved false is closed the same way, with the proof as evidence (and fix the scanner rule).
- Ideas the user does not want to do now go to `ideas.md`; the gate still applies.

## Economy

- Scripts first: `inventory.py` and `scan_secrets.py` cost almost nothing. Agents receive their JSON, not raw trees.
- Agents get compact inputs, a word cap and (researchers) a search cap. Never let two agents read the same thing.
- Cache: `inventory.py` returns a `fingerprint`. If it matches `state.json`, offer to reuse phases 1-2.
- Queue mode: finish one project before the next; for "scan all first" run phases 1-2 for every project, show a comparison table, let the user pick who goes deeper.
- If the user has no Python: the `security` agent does the first pass with Grep/Glob; say that it is slower and less thorough.

## Output layout

```
<out>/<slug>/
  state.json      # phases done, permissions, region, language, fingerprint
  findings.json   # security + critic findings (gate.py owns it)
  ideas.md        # backlog of improvement ideas, never lost
  phases/         # one file per phase
  REPORT-SHORT.md
  REPORT-FULL.md
```

Templates: `templates/`. Start a new project with `ideas.md` from `templates/ideas.md`.

## Red flags - stop and fix

| Thought | Reality |
|---------|---------|
| "Critical finding, but let's just look at the market quickly" | Gate says BLOCK. Fix first. |
| "The agent said it, so it's true" | Run verify_evidence.py. No tag = no claim. |
| "A single price estimate is cleaner" | Range or nothing. |
| "Run all three research levels, just in case" | Show the card, let the user choose. |
| "I'll write the report from memory of the phase" | Read the phase files; they are the source of truth. |
| "The project is bad, let me phrase it gently" | State the verdict from the rubric, with evidence. |
