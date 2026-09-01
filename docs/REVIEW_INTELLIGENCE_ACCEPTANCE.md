# Review Intelligence acceptance

This is the compact operator gate for issue #229.

## 1. Collect bounded review evidence

From the VERIDRA repository root on Windows:

```bat
VERIDRA_REVIEW_INTELLIGENCE.bat
```

The collector is read-only and bounded. It attempts the `newest`, `lowest`, and `highest` Google Maps review strategies. Transient review-tab and sort failures are retried automatically. Consent, sign-in, and CAPTCHA surfaces are treated as explicit manual interruptions and are not bypassed.

Success requires at least one actual review evidence row. Opening a review UI but collecting zero rows is a failure.

## 2. Validate the review artifact

```bat
VERIDRA_REVIEW_ACCEPTANCE.bat
```

The validator automatically selects the newest `VERIDRA_REVIEW_INTELLIGENCE_*.zip` in Downloads and checks:

- non-zero review evidence;
- at least one business with a non-empty sample;
- manifest/index consistency;
- plausible integer ratings from 1 through 5 when present;
- parseable approximate review/owner-response dates when present;
- stable, unique, indexed evidence IDs;
- bounded newest/lowest/highest sampling;
- absence of deterministic sentiment/theme/fake-review inference.

Exit code `0` means PASS. Exit code `2` means the artifact did not satisfy the deterministic gate.

## 3. Build the AI evidence export

```bat
VERIDRA_AI_EXPORT.bat
```

The review-aware AI exporter recomputes sampling-safe statistics from raw review rows and adds traceable `google_review` entries to its `evidence_index.json`. VERIDRA does not infer review themes; external AI may interpret them only by citing evidence IDs.

## 4. Verify review evidence reached the AI export

Pass the current AI export explicitly to the acceptance checker:

```bat
VERIDRA_REVIEW_ACCEPTANCE.bat --ai-export "%USERPROFILE%\Downloads\VERIDRA_AI_EXPORT_YYYYMMDD_HHMMSS.zip"
```

The report must show:

```text
"passed": true
"ai_export_contains_traceable_review_evidence": true
```

## Final #229 boundary

The deterministic repository work is not, by itself, the final live acceptance. Issue #229 is complete only when a real Dublin dental Google Maps run produces non-zero bounded review evidence and the acceptance checker passes that artifact (plus the review-aware AI export when supplied).

No real prospect outreach is part of this gate.
