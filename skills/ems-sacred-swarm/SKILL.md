---
name: ems-sacred-swarm
description: Use when the user says "Sacred Swarm", "EMS" or "Examen Machinarum Sacrum", or wants a staged audit of software projects - current state, readiness to sell, security gaps, competitors, audience and willingness to pay, will-it-take-off verdict, price range, sales advice. RU - священный рой, рой агентов, рой, ЕМС, аудит проекта, проверь проект, стрельнёт ли проект, готовность к продаже, оценка стоимости, конкуренты.
---

# EMS - Sacred Swarm (Examen Machinarum Sacrum)

Also known as **Sacred Swarm**, **Священный Рой**, **Рой агентов**, **ЕМС**. When the user calls it by any of these names, run this skill.

Staged, evidence-based audit of software projects. Cheap read-only sub-agents gather facts; **you** (the main model) verify, decide and talk to the user. The point of the whole run is one answer: **will this project take off, for whom, at what price, and what to fix first.**

`<skill>` = the directory this SKILL.md was loaded from: role prompts `<skill>/agents/`, rules `<skill>/rubrics/`, helpers `<skill>/scripts/` (Python 3, stdlib only, read-only), templates `<skill>/templates/`.

## Hard rules

1. **Read-only on the user's projects.** Never write to, build, run, install or execute project code. Sub-agents are launched as `Explore` (no Edit/Write); only you write, and only into the output folder.
2. **Permissions first, once** (phase 0): project folders, `gh` read-only (private repositories only if the user says so), web search, output folder. Not granted = skipped and listed as a gap. If a project folder is outside the directories this session may read, request access before launching agents.
3. **Evidence or silence.** Every claim carries `[src: path:line]`, `[src: URL; A|B|C]` or `[UNVERIFIED]`. Run `scripts/verify_evidence.py` on what you save.
4. **Grade every number.** A = official statistics, filings, laws; B = press, vendor pages with date; C = aggregators, snippets, undated pages. Only A and B go into calculations. C is shown as "unreliable".
5. **No invented numbers.** Ranges with stated assumptions. A multiple, a share or an adoption rate needs a dated A/B source or is labelled "assumption" with its reason.
6. **Never reveal secrets** in reports, chat or agent prompts (masked form only).
7. **Web queries stay generic:** product category and region, never the private project name, code or client names.
8. **Blunt, not cruel.** "This is a prototype, not a product" is allowed. Insults and padding are not.
9. **Language:** the user's language; agent prompts stay English with the report language stated.
10. **Show on screen first, then save.** At every checkpoint and at the end print the result in the chat (the screen card from `templates/screen-card.md`). Files are the archive and the backup, never the only place the answer lives. Never answer "see the file".
11. **Short.** Screen card ≤ 25 lines. No filler: every sentence carries a fact, a number or a decision.

## Phase 0 - setup (ask once)

Ask, with AskUserQuestion where it fits:
- permissions (rule 2); output folder (kept outside the projects);
- **country, city, language**; currency: base **USD** plus the currency of the user's country (detect from the answers, confirm). Rates only from the central bank of that country with the date (`rubrics/currency.md`);
- **mode:** step-by-step (default: card before each phase, question after) or autopilot (approve a run plan once; stops only on a critical finding or an ambiguity);
- **preset:** economy (default), balanced, strong (table below), or per-role override;
- security first pass: scripts, Haiku, or both;
- **the developer's honest numbers:** calendar span, real hours per week, number of people, hours already spent, whether the work will continue. These feed the effort estimate; git only shows when commits happened.

Ask everything in **one** AskUserQuestion call (up to 4 questions), not one by one. If the user says "just run it" or is away, use the defaults: autopilot, economy, lean, research S+M, scripts for security, and list the unanswered developer numbers as a gap.

Save the answers to `<out>/state.json`:

```json
{"date": "YYYY-MM-DD", "country": "", "city": "", "language": "ru",
 "currency": {"base": "USD", "local": "KZT", "rate": null, "rate_date": null, "rate_source": null},
 "mode": "step|autopilot", "preset": "economy", "lean": true, "levels": ["S", "M"],
 "web_search": true, "gh": false,
 "projects": {"<slug>": {"root": "D:/path", "fingerprint": null, "phases_done": [],
              "developer": {"span": null, "hours_per_week": null, "people": null,
                            "hours_spent": null, "continues": null}}}}
```

Then print the run plan: `python <skill>/scripts/run_plan.py --projects N --preset P --levels S,M,L` (number of agent runs by model, no invented token counts).

**More than two projects:** default to "scan all first" (phases 1-2 for every project, then a comparison table on screen, the user or the autopilot picks up to 3 for phases 3-8). Projects with no product intent (a personal script, a mod for friends) get phases 1-3 and 7 only; say so in the table.

## Presets (role -> model)

| Role | economy | balanced | strong |
|------|---------|----------|--------|
| scout, appraiser, critic, security, researcher S and M, referee | haiku | haiku | sonnet |
| researcher L, sizer, potential, demand | haiku | sonnet | sonnet |
| collector, improver, sales-finance | sonnet | sonnet | sonnet |

**haiku-main:** Haiku only gathers facts (scout, security, researcher S/M/L); every judgment role (appraiser, critic, referee, sizer, potential, demand, collector, improver, sales-finance) is done by you, the main model, following the same role file. No Sonnet runs. Use it when the user wants Haiku for legwork and the strongest model for conclusions.

Lean option: when readiness is below 15/40 or the preset is economy, run appraiser and critic as one agent and skip research L unless the user asks.

## Phases

| # | Phase | Roles | Saves | Screen |
|---|-------|-------|-------|--------|
| 0 | Setup | - | `state.json` | run plan |
| 1 | State and readiness | scout, appraiser | `phases/01-*.md` | label, score, 3 facts |
| 2 | Security gate | scripts, security | `phases/02-security.md`, `findings.json` | gate status |
| 3 | Weak spots | critic | `phases/03-weak.md` | top 5 |
| 4 | Research | researcher S (global base + local base + substitutes), M (region deep: players, channels, regulation, statistics), L (global), then referee | `phases/04-research-{s,m,l}.md`, `04-referee.md` | competitors, spread flags |
| 5 | Audience and potential | sizer, potential | `phases/05-potential.md` | verdict, price, audience |
| 5b | Demand check | demand | `DEMAND-CHECK.md` | who to ask, threshold |
| 6 | Collect | collector | `SCREEN.md`, `REPORT-SHORT.md`, `REPORT-FULL.md` on request | screen card |
| 7 | Improve | improver | `phases/07-improve.md`, `ideas.md` | top fixes |
| 8 | Sell | sales-finance | `phases/08-sales.md` | channels, price options |

Gate (2) runs before 3-8; with status BLOCK only phase 7 may run.

## Scripts per phase (run them, do not improvise)

`S=<skill>/scripts`, `O=<out>/<slug>`, `P=<project root>`. Scripts are read-only on the project.

| Phase | Command | Then |
|-------|---------|------|
| 1 | `python S/inventory.py P --out O/inventory.json` | compare `fingerprint` with `state.json`; equal = offer to reuse phases 1-2 |
| 2 | `python S/scan_secrets.py P --out O/scan.json` (history: last 300 commits by default; `--history 0` = tree only) | `python S/gate.py O --ingest O/scan.json --source script` |
| 2 | security agent report saved as `O/phases/02-security.md` | `python S/gate.py O --ingest-md O/phases/02-security.md` |
| 2 | you re-rate after opening the cited lines | `python S/gate.py O --rate ID --severity medium --evidence "what the source shows"` |
| any | after saving a phase file | `python S/verify_evidence.py P O/phases/<file>.md` |
| 6 | export on request | `python S/export_report.py O/REPORT-FULL.md --txt --docx` |

Scanner severity already depends on git state: a key that git tracks is `critical`; the same key in an untracked file, a git-ignored file or a folder without git is `medium`/`weak` with its trigger ("critical once committed"). Git-ignored folders are not walked, except deployable web build output (`dist`, `build`, `out` with an `index.html`).

## Phase protocol

1. **Card** (step mode): agents, goal, models, what they read, what goes online, number of runs. Ask: run / skip / change model.
2. **Gate:** `python <skill>/scripts/gate.py <out>/<slug>`.
3. **Run:** Agent tool, `subagent_type: "Explore"` (never a fork of this conversation), model from the preset. Build the prompt with `python S/agent_prompt.py --role <role> --project P --out O [--level S|M|L] --file O/prompts/<role>.txt` and pass that text verbatim: common rules, the role file (only the asked research level), a compact digest of inventory/scan, region and currency from `state.json`, and the list of phase files the role may open. Add nothing from the conversation; if the agent needs more, it opens the listed files itself. Independent agents in parallel (up to 5), dependent ones in sequence. If sub-agents have no WebSearch in this harness, run research yourself with the same role prompt and caps.
4. **Verify and re-rate:** save the text, run `verify_evidence.py` (bad tag = wrong claim: re-check). Agent severities are proposals: open the cited lines of every critical and downgrade what is not proven with `gate.py --rate` (`rubrics/severity.md`). Never edit `findings.json` by hand. Run the referee before any number leaves research.
5. **Save** files yourself (sub-agents cannot write report files). Update `state.json` (`phases_done`, `fingerprint`).
6. **Screen and checkpoint:** print the phase result in the chat; then summary, 1-3 pieces of advice, open medium findings, new ideas to `ideas.md`, and the question (continue / deeper / stop). In autopilot print the same and continue.

## Potential and verdict (phase 5)

Rubric: `rubrics/potential.md`. Order is fixed: **audience first** (bottom-up, official statistics), **willingness to pay** (analog prices, dated, one currency), **potential revenue**, **five criteria** (audience size, willingness to pay, competition strength, differentiation, time to first sale) -> verdict *стрельнёт / при условии / не стрельнёт* with confidence and the single biggest unknown. Cost to rebuild is a floor, never the headline. "Four paying customers" is not a verdict: audience potential decides.

## Security gate

Rubric `rubrics/severity.md`; findings in `<out>/<slug>/findings.json`, managed only through `scripts/gate.py`.

| Level | Behaviour |
|-------|-----------|
| weak | Listed, no interruption |
| medium | Repeated at every checkpoint until closed |
| critical | BLOCK: only phase 7 may run |

- No override for critical. A leaked secret is closed only after rotation: `gate.py <dir> --close ID --evidence "..."`. A manual close sticks across re-scans (the rotated key stays in history; that is fine once it is dead); `--reopen ID` undoes it.
- A script finding you proved false is closed the same way with the proof as evidence (and fix the scanner rule). A finding that is real but over-rated is re-rated with `--rate`, which re-scans keep.
- Agents may write `Critical`, `high` or an unknown level: `gate.py` maps them (`high` = critical, unknown = medium with `severity_raw` kept) so nothing silently drops out of the gate.
- Ideas the user does not want to do now go to `ideas.md`; the gate still applies.

## Economy

- Scripts first (`inventory.py`, `scan_secrets.py`); agents get compact inputs and word/search caps.
- Cache: `inventory.py` returns a `fingerprint`; if it matches `state.json`, offer to reuse phases 1-2.
- Queue mode: finish one project before the next, or "scan all first": phases 1-2 for every project, a comparison table on screen, the user picks who goes deeper.
- Without Python the security agent works with Grep (slower, less thorough).

## Output layout

```
<out>/<slug>/
  state.json  findings.json  ideas.md
  SCREEN.md  REPORT-SHORT.md  REPORT-FULL.md  DEMAND-CHECK.md
  inventory.json  scan.json  prompts/  (script outputs and the exact agent prompts)
  phases/  (01-scout, 01-appraisal, 02-security, 03-weak, 04-research-s/m/l, 04-referee, 05-sizer, 05-potential, 07-improve, 08-sales)
```

Exports: `python <skill>/scripts/export_report.py <file.md> --txt --docx` (txt always; docx when pandoc is present, otherwise say so).

## Red flags - stop and fix

| Thought | Reality |
|---------|---------|
| "The report is in the file, no need to show it" | Rule 10. Print the screen card. |
| "Critical finding, but quickly look at the market" | Gate says BLOCK. Fix first. |
| "A grade C number will do for the estimate" | Only A and B enter calculations. |
| "Total market is $6 billion, so potential is big" | Bottom-up funnel or nothing. |
| "Cost to rebuild is the value" | It is the floor. Potential decides. |
| "No A/B comparables, so no sale price" | The sale price is never empty: rebuild × discount or profit × dated multiple, labelled. Plus what raises it, with hours. |
| "Four paying customers prove it" | They prove nothing about the audience. |
| "Every project scored 12/25" | Anchoring. Re-check each criterion against its anchors (rubrics/potential.md). |
| "Hours from lines of code" | Use git active days and ask the developer; lines are a weak proxy. |
| "Run all three research levels, just in case" | Show the plan and let the user choose. |
| "I'll just fix the severity in findings.json" | `gate.py --rate` with evidence; hand edits are lost on the next scan. |
| "The scanner found a key in an ignored file, BLOCK" | Not leaked. Weak or medium with its trigger; check git state first. |
| "Ten projects, full run each" | Scan all first, compare, go deep on up to 3. |
