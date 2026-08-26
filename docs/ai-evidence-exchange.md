# VERIDRA AI Evidence Exchange

This is the Phase 1 manual bridge between deterministic VERIDRA evidence and external AI interpretation.

## Principle

AI may interpret evidence, but it must not manufacture evidence.

The authoritative provenance chain is:

`raw evidence -> deterministic VERIDRA analysis -> AI interpretation`

AI interpretation is always a separate read-only layer. It does not overwrite raw evidence, prospect state, funnel state, or outreach state.

## Export

Run `VERIDRA_AI_EXPORT.bat` from any path. By default it selects the newest `VERIDRA_COMPETITIVE_*.zip` and newest `VERIDRA_VISUAL_EVIDENCE_STRICT_*.zip` from Downloads and produces:

`VERIDRA_AI_EXPORT_YYYYMMDD_HHMMSS.zip`

Important files:

- `manifest.json` — export identity and provenance.
- `cohort/local_benchmark.json` — deterministic local benchmark.
- `evidence_index.json` — evidence IDs the AI must cite.
- `AI_RESPONSE_CONTRACT.json` — required enrichment contract.
- `prospects/<business>/competitive_context.json` — deterministic prospect context.
- `prospects/<business>/website_evidence.json` — traceable website evidence with evidence IDs.

## Enrichment returned by AI

The returned ZIP must be named like:

`VERIDRA_AI_ENRICHMENT_YYYYMMDD_HHMMSS.zip`

It must contain `manifest.json` and `enrichment.json` and match the `source_export_id` from the export pack.

Commercial claims use evidence levels:

- **A** — direct factual evidence.
- **B** — multiple corroborating signals.
- **C** — reasonable commercial hypothesis grounded in evidence.
- **D** — speculation; analysis-only and automatically suppressed from commercial use.

Every commercial claim must include `evidence_refs`, and each reference must exist in the source export's `evidence_index.json`.

## Import

Place the returned enrichment ZIP in Downloads and run `VERIDRA_AI_IMPORT.bat` from any path. The importer selects the newest enrichment pack and newest source AI export unless explicit paths are supplied.

The output is:

`VERIDRA_AI_IMPORTED_YYYYMMDD_HHMMSS.zip`

It contains:

- `validation_report.json`
- `normalized_enrichment.json`
- source enrichment manifest
- a read-only import manifest

A/B/C claims with valid evidence refs become `commercial_ready_claims`. Level D becomes `analysis_only_claims`. Claims with missing/unknown evidence refs or invalid evidence levels become `rejected_claims`.

## Non-goals for Phase 1

- no direct model/API integration;
- no automatic outreach;
- no prospect-state mutation;
- no CRM replacement;
- no raw evidence mutation.
