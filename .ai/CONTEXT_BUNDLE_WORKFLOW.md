# AI Context Bundle Workflow

The repository and canonical `.ai/` files are project memory. Chat is temporary. `AI_CONTEXT_BUNDLE.md` is only a transport snapshot for starting or continuing an AI session.

## Modes

- `bootstrap` — default for a new chat. Includes Git identity, repository map and canonical project-state files.
- `delta` — use after local code changes or when continuing implementation. Adds currently changed tracked text files.
- `full` — deep debugging/audit only. Adds tracked repository text until the configured size limit is reached.

## Standard flow

1. Pull/sync the intended branch and make sure the local checkout is the code you want reviewed.
2. Run `AI_CONTEXT.bat bootstrap` for a new chat.
3. Attach `.ai/generated/AI_CONTEXT_BUNDLE.md` and state the objective for that session.
4. During active implementation, regenerate with `AI_CONTEXT.bat delta` after meaningful code changes if a new chat or context reset is needed.
5. Use `full` only when the problem cannot be localized from canonical state + targeted source.
6. At session end, update the authoritative `.ai/` state required by `SESSION_PROTOCOL.md`; do not treat the generated bundle as durable memory.
7. Regenerate after any change to branch/commit, canonical `.ai/` state, or relevant working-tree files before relying on the bundle again.

## Rules

- Never commit the generated bundle or manifest.
- Never use the bundle to override fresher runtime/test/source evidence.
- Prefer targeted source inspection over `full` mode.
- If bundle content conflicts with current source or runtime evidence, record the discrepancy and trust the fresher evidence.
