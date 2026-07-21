# Report profile selection

Saved report profiles are optional and loopback-local.

- The assessment console lists profiles stored under the configured Veridra data directory.
- Selecting a profile preserves it through target assessment, area and status filters, printable reports, and evidence exports.
- No profile selection uses the default Veridra report.
- Missing profile identifiers fail explicitly instead of silently falling back.
- Profiles contain presentation metadata only; they do not contain credentials, cookies, request bodies, or remote assets.
