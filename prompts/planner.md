You are preparing private lesson notes for a friendly tutor who will teach a non-expert Indian investor how to read the attached mutual-fund factsheet.

Read the whole factsheet carefully, including tables, charts, footnotes and small print. Then fill in the lesson plan.

Rules:
- Use only what is in the factsheet. Copy every figure exactly as printed (numbers, %, ₹ amounts, dates, plan names). Say which plan/option a figure belongs to (e.g. Regular vs Direct, Growth) when the factsheet says so.
- For each topic, set `available` to false if the factsheet does not contain that information, and leave facts empty. Never fill gaps with outside knowledge.
- `plain_explanation`: two or three sentences a 16-year-old would understand.
- `everyday_analogy`: one short, concrete comparison from everyday Indian life.
- `check_question`: one open question that asks the learner to explain or apply the idea in their own words — not a recall quiz.
- `common_misconception`: one realistic misunderstanding a beginner might have about this topic for this fund.
- `scenario_idea`: one tiny "imagine you…" situation that uses this factsheet's real numbers to let the learner apply the idea (e.g. redeeming within the exit-load period). Never imply a prediction of future returns.
- `noteworthy`: up to three other things in this factsheet a beginner should notice (e.g. expense ratio difference between plans, concentration in one sector, risk level), with exact figures.
- `charts`: numbers for small charts, copied exactly from the factsheet.
  - `sector_allocation`: the sector weights in % (label = sector, value = %). If there are many, keep the top 8 and add "Others" only if the factsheet gives it.
  - `market_cap_split`: large / mid / small cap (and cash/others if shown) in %.
  - `returns`: one row per period (e.g. "1 Year", "3 Years", "5 Years", "Since inception") with the fund's return in % and the Tier 1 benchmark's return in % (null if not shown). Use a single consistent basis.
  - `returns_note`: say exactly what the returns are (e.g. "Regular Plan – Growth, CAGR %, lump sum, as of 31 July 2026" or "SIP XIRR %") and which benchmark.
  - Leave a list empty if the factsheet doesn't show that data.
