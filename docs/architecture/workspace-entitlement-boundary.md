# Workspace entitlement boundary

Veridra's workspace policy is a local enforcement and usage-evidence layer.

It may block local routes after the operator explicitly activates a plan. It does not authenticate users, isolate tenants, verify payments, issue invoices or provide production subscription security.

Anonymous `/free/*` routes are deliberately excluded from local paid-workspace counters. Profile-aware `/crawl/*` routes perform their own metering and are excluded from the commercial middleware to prevent double counting.

Commercial route usage is recorded only after a successful response. Quota capacity is checked before execution.
