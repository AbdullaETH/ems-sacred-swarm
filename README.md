# EMS - Sacred Swarm

**EMS** = *Examen Machinarum Sacrum* - "the sacred swarm of machines". In Latin *examen* means both a swarm (of bees) and an examination, a weighing: a swarm of agents that examines your project.

A Claude Code skill that audits your software projects in stages: current state, readiness to sell, security gaps, competitors, regional and global market, rough valuation, sales advice.

Cheap read-only Haiku sub-agents gather the facts. The main model verifies them, asks you questions after every phase and keeps the cost low. A critical security finding blocks everything except fixing it.

*Русская версия: [README.ru.md](README.ru.md)*

## What it answers

**Will this project take off, for whom, at what price, and what to fix first.** The answer is printed on screen as a verdict card first and saved to files second.

| Phase | What happens |
|-------|--------------|
| 0 Setup | Permissions, country and city, currency (USD + yours), mode (step-by-step or autopilot), model preset, your honest effort numbers. Prints the run plan |
| 1 State and readiness | What the project is today, scored on an 8-criteria rubric |
| 2 Security gate | Secret and exposure scan, manual checks; weak = warning, medium = repeated at every checkpoint, critical = blocks |
| 3 Weak spots | Blunt list of what is awful, absent or embryonic |
| 4 Research | S: global base + local base + substitutes. M: your city and region in depth, with official audience statistics. L: global picture. Referee: cross-checks the levels |
| 5 Audience and potential | Bottom-up audience funnel, willingness to pay, potential revenue per year, five criteria, verdict *take off / on condition / will not*, value ladder |
| 5b Demand check | Who to ask, interview script, success threshold, a cheap test |
| 6 Collect | Screen card, one-page report; full document on request (md, txt, docx) |
| 7 Improve | Prioritised fix plan, idea backlog |
| 8 Sell | Buyers, channels, price options inside the willingness-to-pay range, deck and plan advice |

Every number carries a source grade: **A** official, **B** press or vendor with a date, **C** aggregator or snippet. Only A and B enter calculations.

## Requirements and status

- Claude Code with sub-agents (the skill launches `Explore` agents on `haiku`, and `sonnet` for synthesis). Web search for research phases. `gh` is optional (repository visibility).
- Status: **v0.06**. v0.04 was run end to end on five real projects; v0.06 reworks the analysis (audience first, verdict, source grades, screen-first output). Scripts have regression tests in `tests/` (CI on Linux and Windows). Not yet adversarially tested against rule-bending prompts. Expect rough edges; issues and PRs are welcome.
- Model presets: economy (Haiku gathers, Sonnet synthesises), balanced (Sonnet also for research L, audience and verdict), strong (Sonnet everywhere); any role can be overridden.
- Agents return text, the main model writes the report files into your output folder.

## Quick start

1. Install (below).
2. Say: *"Run Sacred Swarm on `<path to your project>`"* or *"audit my project before I try to sell it"*.
3. Answer the phase-0 questions (folders, region, language, mode). After every phase you get a short summary, advice and a question; research depth (S / M / L) is your choice.
4. Reports land in `<output>/<project>/`: `REPORT-SHORT.md`, `phases/`, `findings.json`, `ideas.md`.

Trigger words: *Sacred Swarm, EMS, Examen Machinarum Sacrum*, and in Russian *Священный Рой, Рой агентов, ЕМС, аудит проекта*.

## Install

Clone and copy the skill folder to your Claude Code skills directory:

```bash
cp -r skills/ems-sacred-swarm ~/.claude/skills/ems-sacred-swarm
```

On Windows copy `skills\ems-sacred-swarm` to `%USERPROFILE%\.claude\skills\ems-sacred-swarm`. Then ask Claude: *"audit my project"*, *"is my project ready to sell?"*.

Python 3.8+ is optional but recommended: the scripts do the first pass for free. Without Python the security agent falls back to Grep (slower, less thorough).

## Safety and cost design

- **Read-only.** The skill never writes to your projects, never builds or runs them. Reports go to a separate output folder you choose. GitHub access is read-only `gh`; private repositories only with your explicit consent.
- **Evidence or silence.** Every claim carries a `[src: file:line]` or URL tag; `verify_evidence.py` checks that the cited lines exist. Unprovable claims are marked `[UNVERIFIED]`.
- **No invented numbers.** Valuation is a range with stated assumptions.
- **Secrets are masked** everywhere and never sent to agents or the web.
- **Economy.** Scripts first, agents get compact inputs and word/search caps, results are cached by a fingerprint, you choose research depth per phase and see a load card before each run.
- **Gate.** Critical findings (leaked keys, committed `.env`, open admin, closed code in a public repo...) block all phases but fixing. Deleting a leaked secret is not enough: the key must be rotated.

## Layout

```
skills/ems-sacred-swarm/
  SKILL.md          orchestrator (read by Claude)
  agents/           role prompts: scout, appraiser, critic, security, researcher, referee, sizer, potential, demand, collector, improver, sales-finance
  rubrics/          readiness, severity, potential, currency
  scripts/          inventory.py, scan_secrets.py, gate.py, verify_evidence.py, run_plan.py, export_report.py
  templates/        screen card, short and full report, ideas backlog
tests/              regression tests for the scripts (python -m unittest discover -s tests)
```

## Limits

- Haiku gathers, it does not reason deeply. Treat valuations as orientation, not appraisal. Not financial advice.
- The secret scanner is pattern-based: it misses unusual formats and can raise false positives. The security agent triages them.
- Web research quality depends on what is publicly findable for your niche and region.

## License

MIT, see [LICENSE](LICENSE).
