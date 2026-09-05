# AI Session Protocol

## Evidence precedence
When sources disagree, use:
1. directly verified runtime/test evidence;
2. current source code;
3. current configuration/data;
4. authoritative current project documentation;
5. older project documentation;
6. chat history;
7. assumptions.
Record discrepancies rather than silently rewriting history.

## Session start
1. Read `.ai/CONTEXT.md`.
2. Read `.ai/PROJECT_STATE.json`.
3. Read `.ai/KNOWN_ISSUES.md`.
4. Read `.ai/OPERABILITY.md`.
5. Inspect Git status, branch and current commit.
6. Read `.ai/TEST_STATUS.json` and relevant `docs/modules/*.CONTRACT.md`.
7. Load only source/tests/docs needed for the requested workstream.
8. Verify assumptions against current code before editing.

## During work
- keep changes bounded to active objective;
- preserve module contracts and product/safety boundaries;
- add/update tests with behavior changes;
- prefer supported UI/API/operator paths over direct store mutation for acceptance;
- verify runtime behavior when appropriate;
- classify status precisely: IMPLEMENTED, TESTED LOCALLY, TESTED IN CI, DEPLOYED, EXTERNALLY VERIFIED, PRODUCTION APPROVED, REAL-CUSTOMER PROVEN;
- record durable decisions/issues/rejected approaches immediately;
- never claim completion without acceptance evidence;
- never mark real-prospect-ready while #284/#296 gate is open.

## Session end
Update as applicable:
- `PROJECT_STATE.json`;
- `TEST_STATUS.json`;
- `KNOWN_ISSUES.md`;
- `ROADMAP.md` if milestone status changed;
- `DECISIONS.md` for durable decisions;
- `REJECTED_APPROACHES.md` for abandoned approaches;
- `OPERABILITY.md` if readiness changed.

Record what changed, what was verified, what remains, tested/current commit and next action. If code changed after the last CI run, do not leave `latest_tested_commit` pointing at the new commit until tests actually pass.

Run `python tools/build_ai_context.py` to refresh deterministic bootstrap summary after state updates.

A chat ending or hitting context limits must not cause state loss. Repository `.ai/` is authoritative; chat is disposable.