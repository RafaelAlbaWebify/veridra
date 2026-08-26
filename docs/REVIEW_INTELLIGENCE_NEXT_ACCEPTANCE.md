# Review Intelligence next acceptance criteria

Before Phase 2B begins, the next live Dublin run must satisfy all of the following:

1. `review_evidence_items > 0`.
2. At least one business has a non-empty review sample.
3. Empty samples are reported as failures/unavailable, not as successful zero-valued statistics.
4. Captured ratings are plausible integers 1–5 when present.
5. Relative review dates are preserved and approximate dates are clearly labelled approximate.
6. Owner-response fields remain optional and do not break collection.
7. Evidence IDs are stable within the pack and present in `evidence_index.json`.
8. Sampling remains bounded across newest / lowest / highest strategies.
9. No sentiment, theme, fake-review, persistence or outreach inference is added in VERIDRA.
