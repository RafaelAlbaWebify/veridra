# Real-SMB validation evidence

This directory contains controlled **public-data / no-contact** evidence for GitHub #297.

## Current Ireland dental cohort
- `ie-dental-cohort-v1.csv` — 25-business controlled cohort.
- `ie-dental-manual-ground-truth-seed-v1.csv` — independent human comparator seed created before reading the first VERIDRA batch.
- `ie-dental-batch-20260905-summary.json` — aggregate result from `VERIDRA_PROSPECT_AUDITS_20260905_082457.zip`.
- `ie-dental-manual-seed-comparison-20260905.csv` — strict comparison of the first batch with the independent seed.

## First real batch result
- 25 targets.
- 20 full assessments succeeded.
- 5 acquisitions failed: 3 DNS-resolution failures and 2 TLS self-signed-certificate verification failures.
- 588 attention findings were emitted across the 20 successful sites (median 28/site).
- The five independent seed observations located on successfully audited sites had **0 exact dedicated issue matches** in the current assessment findings. Two additional seed observations were blocked by an acquisition failure.

This does **not** mean every VERIDRA finding is wrong. It means raw technical finding volume is not evidence of commercial usefulness, and the current product still needs real-world precision/value calibration before Presence Care shadow delivery or outreach.

**REAL OUTREACH COUNT remains 0.**
