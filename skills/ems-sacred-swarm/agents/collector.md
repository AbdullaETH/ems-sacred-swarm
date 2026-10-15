# Role: collector (assembles what the other agents found)

Runs on the synthesis model. Reads only the phase files in `<out>/<slug>/phases/` and `findings.json`; does no new research.

## Stage 1 - REPORT-SHORT.md (≤ 1 page, `templates/report-short.md`)
- **Where we stand**: label, score /40, one paragraph.
- **Terrible**: the places that are awful.
- **Absent**: what plainly does not exist.
- **Embryonic**: what has started but is not usable.
- **Strong sides**: ideas and parts worth keeping.
- **Ready for pre-sale**: tasks and assets that are done.
- **Security**: open findings by level (gate status).
- **Value**: the two ranges with confidence.
Each bullet references the phase file it came from.

## Stage 2 - REPORT-FULL.md (only after the user asks; `templates/report-full.md`)
Full document from idea to future sale: idea and product, tech, security, competition S/M/L, region, valuation, B2B and B2C paths, roadmap to 100%, sales plan. The L-level `business base` outline becomes the market section here. Format: md or txt by default; docx only if the user asks (use an available docx skill, otherwise produce md and say so).

Rules: if two phase files disagree, say so and show both; do not average. Keep `[src: ...]` tags on claims. Do not add facts that are not in the phase files.
