# VERIDRA functional audit — Batch 08: HTML/PDF reports and delivery

Source: local ZIP, 2026-10-17. **Seven modules, 2,205 physical lines:** `reports.py`, `report_profiles.py`, `pdf_reports.py`, `report_delivery.py`, `tenant_report_api.py`, `agency_report_web.py`, `agency_report_profile_web.py`. Reviewed report source trust, HTML construction, brand validation, render limits, Playwright resource restrictions, tenant/project authorization, evidence export, SMTP delivery ledger and error paths.

## Findings
- **F52 P1 — Sender success and delivery-record persistence are not atomic.** `report_delivery.py:126-179` invokes SMTP sender then saves attempt. If `store.save` fails, network delivery may have occurred but no durable ledger entry exists; retry risks duplicate email. Add explicit attempt state and idempotency before side effects.
- **F53 P2 — Corrupted attempt records disappear from UI/history.** `report_delivery.py:69-87` skips `OSError` and `ValueError` for each JSON delivery entry, silently hiding historical evidence. Surface a recoverable integrity warning; do not delete bad files.
- **F54 P2 — Retry numbering can collide under concurrency.** `report_delivery.py:157-177` determines attempt number as `len(prior)+1` before send, with no cross-worker serialization. Distinct content-hash filenames avoid simple overwrite, but attempt numbers need not be unique or ordered.
- **F55 P2 — Report rendering failures are not all from Playwright.** `pdf_reports.py:59-109` catches Playwright errors/OSError and closes Chromium in finally. Input HTML size is limited, outbound resources aborted, PDF magic/size checked. Validation of report-derived HTML and `report_brand_from_html` occurs outside catch; ensure user-safe error mapping at callers. This is a review finding, not a confirmed renderer crash.
- **F56 P2 — Delivery status conflates accepted SMTP send with recipient receipt.** `report_delivery.py:161-177` uses `EmailStatus.delivered` after `sender` returns; this demonstrates accepted transport only, not actual inbox delivery. Rename/document semantics in UI and audit evidence.

## Positive controls
Explicit PDF input/output sizes, timeout, Playwright network abort, tenant capability gates, report profile logo size/format validation, saved delivery attempt fingerprints.

## Evidence
Local ZIP focused report profile/report delivery/report web tests included in 48-pass shared gate. No SMTP production send. No changes to app or external data. **Cumulative 68/243 = 27.98%.** Findings require reconciliation to current GitHub head.
