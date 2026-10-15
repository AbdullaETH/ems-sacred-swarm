# Potential rubric: will it take off?

Order is fixed: audience -> willingness to pay -> potential revenue -> criteria and verdict -> effort -> value ladder. Cost to rebuild is a floor, never the headline.

## 1. Audience (bottom-up, always ranges)
Segment (one sentence) -> total target units from official statistics (grade A/B, with definition and date) -> reachable in 12 months (channel and sales capacity) -> realistic adopters at 12 and 36 months. Each step: low / base / high, the assumption and its basis. Top-down market figures are shown only as a spread and are never multiplied.

## 2. Willingness to pay
Analog prices (grade A/B, dated, one currency at the dated central-bank rate), the cost of the substitute used today (spreadsheet hours, freelancer, agency), and the chosen price range per unit per month or year.

## 3. Potential revenue
Adopters x price, per year, low / base / high, in USD and the local currency. Add "what must be true" (3 items).

## 4. Five criteria (0-5 each, total /25)

| Criterion | 0 | 3 | 5 |
|-----------|---|---|---|
| Audience size | cannot be counted or tiny | thousands of units, reachable part unclear | tens of thousands, channel known |
| Willingness to pay | no analogs, people use it free | analogs exist, price range wide | clear price benchmarks, substitute is costly |
| Competition strength (5 = weak or a gap) | strong local and global players, same offer | competitors exist, gaps in segment | no direct competitor in the region |
| Differentiation | nothing different | one real difference, easy to copy | hard-to-copy difference with proof |
| Time to first sale | more than 12 months | 3-12 months | under 3 months |

Scoring discipline (learned in the first full run, where four of five projects landed on exactly 12/25):
- Every score names the input that justifies it (a number, a grade, a source). A score without an input is not allowed.
- Do not default to 2 or 3. Start from the anchor row that the evidence matches and move only with a stated reason.
- If the total lands on a verdict boundary (12 or 18), re-check each criterion against its anchors and state which single point would flip the verdict.
- When several projects are scored in one queue, the orchestrator compares totals; identical totals trigger a re-check of the scoring, not a shrug.

Verdict: **стрельнёт** 18-25; **при условии** 12-17 (list the conditions); **не стрельнёт в нынешнем виде** 0-11. Confidence = share of inputs with grade A/B: high above 70%, medium 40-70%, low below. Name the single biggest unknown.

## 5. Effort and time
- Facts: git active days and span from `inventory.json`; the developer's own numbers (span, hours per week, people, hours already spent). Where git and the developer disagree, show both.
- Remaining work from the critic and the improver; time to first sale = remaining work + sales cycle.

## 6. Value ladder

| Row | What has to be done (hours) | Potential annual revenue | Cost-to-rebuild | **Sale price (range)** | Method |
|-----|-----------------------------|--------------------------|-----------------|------------------------|--------|
| Now | - | range | low-high | always filled | see below |
| After small fixes (weeks) | list + hours | range | | always filled | |
| Maximum (what a buyer pays most for) | list + hours | range | | always filled | |

**The sale price column is never empty.** The user asks "for how much can I sell it now and after work"; "no comparables" is not an answer. Pick the method by stage and label it:

- **No revenue:** price = cost-to-rebuild × buyer discount 10-30% (assumption: a buyer pays for saved time, not for your hours), adjusted for transferability (docs, tests, deploy without the author). Cost-to-rebuild is a range: low = git active days × realistic hours (AI-assisted rebuild), high = code size at a conventional pace (state the pace). Rate: local market salary from a dated source (job sites, hub reports), converted per hour.
- **With revenue:** price = annual profit (SDE) × marketplace multiple from a dated A/B source (for example Flippa H1 2026: SaaS average 2.47x profit, top quartile 4.06x). A multiple of revenue only with its own A/B benchmark. Less than 6 months of payment history: use the low end.
- **Strategic buyer** (a competitor or integrator who needs exactly this): may pay above both; name who and why, never put it in the base number.

Then list **what raises the price most**, ranked by price gain per hour of work (typically: first paying users and payment history > retention metrics > transferability (docs, deploy without the author, no secrets on personal machines) > features). Every item: hours, expected effect on the price row.

If a needed input is missing, write which one and how to get it. Not financial advice: say so once.
