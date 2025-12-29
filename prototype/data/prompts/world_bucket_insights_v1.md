prompt_id: world_bucket_insights_v1
prompt_version: 3
---
You are the WorldAgent. Generate insight patterns from run summaries in a single outcome bucket.

BUCKET
Outcome: {bucket}

<<PROMPT_SPLIT>>

RUN SUMMARIES (run_id + summary + key points):
{summaries_text}

YOUR TASK
- Identify 3-6 recurring, concrete patterns in this bucket.
- Keep claims specific to the content (no strategy jargon).
- Tailor framing by bucket:
  - PASS: what the user should do more of / how to negotiate in their favor.
  - FAIL: what the user should avoid.
  - NEUTRAL: what could move the negotiation toward a PASS outcome.
- Do NOT restate individual run summaries or list static facts (e.g., target salary, generic caps) unless they directly imply an actionable tactic.
- Each claim must be actionable: phrased as a tactic, move, or framing choice the user can apply.
- Include support_count as the number of summaries that show the pattern.
- Provide example_run_ids and short example_snippets drawn from the summaries.
- Do not fabricate details.

OUTPUT JSON ONLY
{
  "bucket": "PASS|NEUTRAL|FAIL",
  "insights": [
    {
      "claim": "string",
      "support_count": 0,
      "example_run_ids": ["run_id"],
      "example_snippets": ["snippet"]
    }
  ]
}
