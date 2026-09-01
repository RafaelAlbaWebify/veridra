# VERIDRA full-product human operator acceptance

This is the final human usability gate tracked by issue #279.

Automated Playwright/CI is supporting evidence only. It does not complete this gate.

## Hard boundary

- Synthetic/internal test data only.
- No real prospect outreach or customer delivery.
- Use normal VERIDRA launchers and browser UI.
- Do not edit SQLite/files/stores to advance business state.
- Do not work around confusing or missing UI: record it as a defect.
- A section passes only after the operator has personally used it and considers the workflow understandable.

## Start a session

From the repository root run:

```powershell
.\VERIDRA_HUMAN_ACCEPTANCE.bat
```

The launcher creates a timestamped folder under Downloads:

`VERIDRA_HUMAN_ACCEPTANCE_<timestamp>`

It contains:

- `CHECKLIST.md` — the ordered walkthrough and pass/fail/not-tested controls.
- `DEFECTS.md` — compact UX/functional defect log.
- `SESSION.txt` — branch/commit/runtime/session facts.
- `diagnostics\` — copy of the generated VERIDRA diagnostics file when available.
- `screenshots\` — operator screenshots/evidence.

It then starts VERIDRA through the supported local launcher and opens the product in the browser. The checklist and defect log are opened locally for editing.

## How to test

Use one synthetic customer journey from beginning to end. Do not jump to direct URLs unless the product itself provides the navigation.

For each checklist item mark exactly one:

- `[x] PASS` — personally exercised and acceptable.
- `[!] DEFECT` — exercised but a functional/UX problem was found; add it to `DEFECTS.md`.
- `[-] ACCEPTED GAP` — consciously accepted/backlogged; explain why in `DEFECTS.md`.
- `[ ] NOT TESTED` — not yet exercised.

A section is not complete while any item remains `NOT TESTED`.

## UX standard

During every section judge more than correctness. Record defects for:

- wording that requires technical knowledge unnecessarily;
- actions hidden behind unexpected navigation;
- excessive clicks or repeated data entry;
- text-heavy screens where status/buttons/cards would be clearer;
- weak hierarchy or grouping;
- missing Back/Next/open-related-item paths;
- unclear loading/success/error feedback;
- destructive or surprising defaults;
- duplicate concepts or labels;
- controls whose purpose is not obvious on first use.

## Completion rule

Issue #279 can close only when:

1. the current `main` has been personally walked through end to end;
2. every checklist item is PASS or an explicitly accepted/backlogged gap;
3. defects discovered during the run have been fixed/retested or explicitly accepted;
4. the operator explicitly approves moving to real-world validation.

Do not treat a previous automated E2E pass as a substitute.
