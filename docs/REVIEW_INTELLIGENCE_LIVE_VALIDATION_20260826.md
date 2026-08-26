# Review Intelligence live validation — 2026-08-26

The first live Dublin run produced `VERIDRA_REVIEW_INTELLIGENCE_20260826_121211.zip`.

Observed result:
- businesses requested: 10
- businesses reported with review evidence: 10
- businesses failed: 0
- actual review evidence items: 0
- every per-business sample size: 0

Conclusion: this run is **not a successful collector validation**. Google Maps business/review UI navigation succeeded far enough to produce business rows, but review-card extraction returned no usable review evidence. Zero-sized samples must not be represented as successful review evidence.

Required hardening before Phase 2B:
1. broaden/revalidate live review-card selectors against current Google Maps markup;
2. collect diagnostics about review-card selector counts and sort-state changes;
3. treat `reviews UI opened but zero review cards/evidence` as a collection failure;
4. never emit zero-valued recency/velocity distributions as if they were observed business statistics when the sample is empty;
5. keep all sample-derived language explicit;
6. rerun live Dublin validation and require non-zero evidence before wiring review evidence into the AI exchange.
