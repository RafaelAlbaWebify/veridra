# Review Intelligence hardening plan

Trigger: first live Dublin review run on 2026-08-26 returned 10 business rows but zero review evidence items.

Plan:

- Treat zero extracted review cards/evidence as a collection failure, never as a valid zero-value sample.
- Add selector diagnostics to record which review-card selectors matched and how many cards were visible after each sort strategy.
- Broaden review-card discovery to resilient structural selectors around `data-review-id`, review text, rating `aria-label`, and review-dialog containers rather than relying on one historic CSS class.
- Re-open/reselect the reviews tab after sort transitions when necessary.
- Preserve bounded sampling and deterministic statistics only.
- Keep owner-response capture optional and non-fatal.
- Do not integrate Review Intelligence into the AI export until a live Dublin rerun yields non-zero evidence with plausible dates/ratings and no false success state.
