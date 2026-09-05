# Assessment & Evidence Contract
Responsibility: bounded public website/domain assessment and evidence normalization.
Inputs: approved public URL/domain, crawl profile, assessment settings.
Outputs: observations/findings/evidence/affected URLs suitable for downstream report/task workflows.
Guarantees: DNS/IP/redirect safety validation, bounded requests/crawl, no active exploitation, evidence labels preserve uncertainty.
Dependencies: HTTP/DNS/parsing/accessibility/trust/security modules.
Failure behavior: reject non-public/unsafe targets; surface incomplete/blocked evidence rather than fabricate success.
Constraints: technical readiness/crawler policy are not proof of universal AI visibility.
Non-responsibilities: prospect outreach, legal compliance certification, penetration testing, billing.