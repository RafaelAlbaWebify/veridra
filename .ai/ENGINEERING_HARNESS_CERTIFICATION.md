# Engineering Harness — certification and adoption (2026-10-24)

## Evidence boundary
Certified against the GitHub branch `engineering/change-impact-gate`, not against the operator's local Windows checkout. Successful GitHub Actions run **40085678177** at commit **e2655ec0d6f2a3daaea41375c6d4bafa96daceb1**: Linux `verify` and Windows `windows-portability` both passed. The tests run in disposable GitHub runner environments. No production/customer data or operator workstation was inspected.

## Verified mechanisms
- Pre-edit Python import analysis, transitive consumers and candidate tests: `python tools/change_impact.py --base main --working-tree --strict`.
- Detect unknown, deleted, untracked and modified files conservatively. Changed route modules and domain-critical tenant storage, worker or billing components require comprehensive review.
- Parse literal `include_router` registrations in `app.py` and `runtime.py`; conditional registration is recorded.
- Dynamic imports in impacted modules are surfaced and escalated.
- CI computes the real PR diff and archives `artifacts/ci/change-impact.json`; it runs isolated fixture certification followed by Ruff, strict mypy, pytest, audit and browser checks. Windows CI checks portability and operator flows.
- The existing local Windows `VERIDRA_PRE_PR_CHECK.ps1` now calls the analyzer before Ruff/mypy/pytest.
- Existing backups tests check quiescence, integrity, rejected unsafe archive members, no overwrite without explicit opt-in and multi-tenant restoration.

## Controlled certification cases
| Case | Expected observation | Evidence |
| --- | --- | --- |
| Change Python dependency | Reverse importer and related test appear | `tests/test_change_impact.py::test_transitive_consumers_and_test_discovery` |
| Break a function signature | Isolated consumer raises `TypeError`; impact points to the corresponding test | `test_signature_regression_maps_failing_consumer` |
| Change serialised field name | Independent consumer raises `KeyError` | `test_serialization_contract_regression_detected` |
| Change tenant customer store | Full-gate recommendation includes backup contract tests | `test_tenant_store_requires_cross_boundary_review`, `test_persistence_boundary_suggests_backup_contract` |
| Change conditional router | Registered route source is identified and full-gate recommendation enabled | `test_guarded_fastapi_router_registration_is_traced` |
| Remove module | Actual Git deletion appears in diff; missing module escalates | `test_git_diff_captures_deleted_modules`, `test_removed_module_requires_full_gate` |
| Corrupt snapshot or unsafe archive | Restore rejects archive before replacing target | `tests/test_backup_restore.py` |
| Restore two tenants | Both projects remain in distinct namespaces | `test_backup_restore_preserves_distinct_tenant_records` |

## What is deliberately NOT certified
- Exhaustive dynamic runtime relationships, FastAPI middleware and route shadowing, external APIs, PowerShell subprocess/data contracts, billing-provider behavior, network or real-device acceptance.
- Every persisted schema migration, cross-store atomicity or all possible regression classes.
- Actual running installation, uncommitted files, external providers or operator's credentials/data.
- The `requires_full_gate` flag is an **advisory escalation**: CI always runs its full configured suite; a flagged impact report does not itself fail CI. Manual reviewer attention is still required.

## Reconciliation and acceptance
PR #401 and operator-only refactor PR #399 both modify `.github/workflows/ci.yml`; reconcile changes when either is merged or rebased. Their other changed file paths do not overlap in the first 100 files returned by the GitHub PR file listing (PR #399 may contain more than 100, so this is not exhaustive).

**Engineering Harness status: repository/CI adoption certified at the scope above; local operator adoption unverified.** Do not use the term "fully covered" or "bug-free". Continue feature work with pre-edit impact, targeted contracts, full regression CI, evidence and handover as defined in `.ai/SESSION_PROTOCOL.md`.

**Safe local adoption check** on the operator's own checked-out branch (read-only; does not touch application data):
```powershell
git status --short
python tools/change_impact.py --base main --working-tree --strict
.\scripts\windows\VERIDRA_PRE_PR_CHECK.ps1
```
The local script uses an existing `.venv\Scripts\python.exe`; installing dependencies or changing a checkout is not part of this evidence.
