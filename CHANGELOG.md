# Changelog

## 0.06 - 2026-10-15
- Output on screen first (screen card), files second; answers one question: will it take off, for whom, at what price, what to fix first.
- Audience-first analysis: bottom-up funnel (sizer), willingness to pay, potential revenue, five criteria and a verdict (potential), value ladder; cost to rebuild is only a floor.
- Source grades A/B/C on every number; referee role cross-checks research levels; currency rules (USD + user's currency, central-bank rate with date).
- Research S now covers global base, local base and substitutes; M goes deep on the region with official audience statistics.
- Demand check role (interview script, threshold, cheap test); developer's own effort numbers; git active days in inventory.
- Model presets (economy, balanced, strong), step-by-step or autopilot mode, run_plan.py, export_report.py (txt, docx via pandoc).
- verify_evidence.py: source grades. Tests in tests/ and CI on Linux and Windows.

## 0.05 - 2026-10-15
- README (EN, RU): requirements, status, quick start, trigger words. Repository made public.

## 0.04 - 2026-10-15
- Full run of phases 1-8 on five real projects; report files are written by the orchestrator (sub-agent writes are blocked by the harness).
- scan_secrets.py: local DB URLs are medium/weak, Cyrillic placeholders, git-ignored untracked .env skipped.
- severity.md: calibration rules 9-11 (accepted risks, verify before destructive advice, single-source extraordinary claims).
- critic, improver, common prompts: check deliberate owner decisions, no destructive advice without proof.

## 0.03 - 2026-10-15
- Russian triggers (Священный Рой, Рой агентов, ЕМС).
- Tested on 5 real projects; scanner: skips git-ignored untracked .env, local DB URLs are medium/weak, Cyrillic placeholders, test-path generic secrets are weak.
- gate.py: scanner re-rating updates severity of existing script findings.
- verify_evidence.py: git:<commit>, directory and glob tags.
- Calibration rules in rubrics/severity.md; re-rate step in the phase protocol.

## 0.02 - 2026-10-15
- Renamed to EMS - Sacred Swarm (Examen Machinarum Sacrum); skill name ems-sacred-swarm, triggers on 'Sacred Swarm' and 'EMS'.

## 0.01 - 2026-10-15
- First version: orchestrator skill, 9 role prompts, 3 rubrics, 4 stdlib-only scripts, templates, RU/EN README.
