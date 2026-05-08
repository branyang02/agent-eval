# LLM Judge Prompt

Judge whether the agent successfully completed the Chicago apartment
commute-analysis task.

## Task Requirements

- User is moving to Chicago on July 1, 2026.
- Maximum rent is $2,400/month, excluding one-time move-in costs.
- Apartment must be 1 bedroom or larger.
- Preferred neighborhoods are Lakeview, Lincoln Park, Wicker Park, or Logan
  Square.
- User has one 45 lb dog.
- Hard requirement: in-unit laundry; laundry in building is not sufficient.
- Strong preference: no garden or basement units.
- Work address is 233 S Wacker Dr, Chicago, IL 60606.
- User is in office Monday, Wednesday, and Friday and must arrive by 8:40am.
- Each finalist should have an address-level public-transit commute estimate of
  35 minutes or less for that arrival time; options over 35 minutes should be
  rejected or clearly marked as near-matches, not treated as full passes.
- The agent should use real apartment sources plus real map/geocoding/transit
  evidence. It should not guess commute times from neighborhood names.
- The final output should include `/app/apartment_shortlist.json`,
  `/app/apartment_commute_analysis.csv`, and `/app/apartment_shortlist.md`.
- The CSV should contain 3 to 5 candidates and include exact address, latitude,
  longitude, source URL, rent, total monthly cost, budget margin,
  Monday/Wednesday/Friday commute minutes, worst commute minutes, commute
  pass/fail, geocoding source, commute source, route summary, laundry status,
  dog policy status, garden/basement risk, score/rank, uncertainty flags, and
  follow-up questions.
- If exact rent, pet, laundry, availability, geocode, or commute facts cannot be
  verified, the agent should clearly mark uncertainty instead of inventing
  details.
- The simulated user should eventually send exactly "You may exit now." after
  the agent confirms completion.
- The conversation should be genuinely multi-turn; the user should not reveal
  all private facts in the first message, and there should be at least four
  non-exit simulated-user messages.
- If this is a direct human/oracle solve with no agent replies in the
  transcript, do not penalize the missing conversation or exit message. In that
  case, grade the artifacts and evidence directly.

Accept semantically equivalent schemas and Markdown formats. Do not require
exact key names if the content clearly satisfies the task. This is a realistic
web/map research task: reward evidence, precise geocoding, address-level transit
reasoning, constraint tracking, and honest uncertainty. Do not grade as only
pass/fail. Assign a careful numeric score from 0.0 to 1.0, where 1.0 means an
excellent, decision-ready result and 0.0 means the task was not meaningfully
completed.

## Rubric

- 0.10 conversation: multi-turn, asks useful clarifying questions, does not
  frontload all hidden facts, reaches the exit message only after completion.
  For a direct human/oracle solve with no agent replies in the transcript, award
  this category based on whether the final artifacts clearly satisfy the user's
  implied needs.
- 0.15 artifacts/data shape: requested JSON, commute CSV, and Markdown
  recommendation exist, are readable, contain 3 to 5 candidates, and are
  internally consistent.
- 0.25 map/transit evidence: uses exact addresses, numeric latitude/longitude,
  real geocoding/map/transit sources, and route summaries; commute times are not
  neighborhood guesses.
- 0.20 constraint coverage: tracks budget, neighborhoods, bedrooms, 45 lb dog,
  in-unit laundry, no garden/basement, work address, Monday/Wednesday/Friday
  days, 8:40am arrival, and 35-minute commute limit.
- 0.15 commute filtering/ranking: computes or clearly derives day-specific and
  worst-case commute minutes, rejects or marks over-limit candidates, and ranks
  finalists using commute reliability plus housing fit.
- 0.10 uncertainty discipline: does not hallucinate live availability,
  pet/laundry policy, rent, geocodes, or commute facts; clearly marks uncertain
  facts and lists follow-ups.
- 0.05 usefulness: recommendation is concise, actionable, and explains tradeoffs
  and next steps.

## Major Penalties

Major penalties: missing artifacts, no exact addresses, no numeric
latitude/longitude, no day-specific commute estimates, no map/transit source,
treating over-35-minute options as full passes, hard constraints ignored,
unsupported facts presented as certain, or missing final exit message in an
agent conversation. Award partial credit for imperfect but useful work.

## Required Response Format

Return this JSON shape exactly:

```json
{
  "score": 0.82,
  "reason": "short overall explanation",
  "subscores": {
    "conversation": 0.10,
    "artifacts_data_shape": 0.15,
    "map_transit_evidence": 0.25,
    "constraint_coverage": 0.20,
    "commute_filtering_ranking": 0.15,
    "uncertainty_discipline": 0.10,
    "usefulness": 0.05
  },
  "strengths": ["specific strength"],
  "problems": ["specific weakness"],
  "recommended_score_explanation": "why this score is fair"
}
```

The subscores should be the actual points awarded in each rubric category, not
normalized per-category scores. Their sum should approximately equal the overall
score.

## Evaluation Payload

```json
{{EVALUATION_PAYLOAD}}
```
