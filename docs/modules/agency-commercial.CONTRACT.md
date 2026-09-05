# Agency & Commercial Lifecycle Contract
Responsibility: tenant-qualified prospect -> lead/deal -> proposal/terms -> customer/project -> remediation/change -> acceptance -> recurring/offboarding operational workflow.
Inputs: authenticated tenant/user, qualified records, evidence, commercial/operator decisions.
Outputs: durable tenant records and supported UI state transitions.
Guarantees: tenant isolation, explicit state transitions, supported operator path, evidence references.
Dependencies: identity, persistence, assessment, reports, monitoring, billing authority.
Failure behavior: invalid ownership/tenant/state transitions fail rather than silently cross boundaries.
Constraints: synthetic lifecycle does not imply external/legal readiness.
Non-responsibilities: external payment truth, tax calculation, legal approval.