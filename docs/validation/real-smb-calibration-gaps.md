# First real-SMB calibration gaps

Evidence basis: first #297 Ireland dental batch, 25 no-contact public sites, 2026-09-05.

## Gap 1 — owner-facing content defects are not represented strongly enough
The independent manual seed contained stale/default/placeholder content and cross-page opening-hours inconsistencies. On the successfully audited seed sites, the current 77-check assessment emitted no dedicated finding matching those exact defects.

Required design direction:
- detect obvious default/placeholder public content where evidence is deterministic;
- detect stale-date indicators without asserting that old content is necessarily wrong;
- compare repeated business-critical public facts (especially opening hours/contact information) across crawled pages and surface contradictions with affected URLs;
- preserve uncertainty and require owner confirmation before changing canonical business facts;
- keep cosmetic low-value staleness (for example an old copyright year) informational or below commercial priority unless corroborated.

## Gap 2 — acquisition failures need useful first-class evidence
Five of 25 real sites did not produce normal assessments: three DNS-resolution failures and two TLS certificate-verification failures. For a Presence Care workflow those failures can themselves be owner-understandable website-health evidence, but the current prospect batch records them only as audit failures and produces no normal per-site assessment/evidence package.

Required design direction:
- preserve strict TLS/DNS safety;
- do not bypass certificate verification merely to obtain content;
- represent externally observable DNS/TLS acquisition failure as structured evidence suitable for manual validation and customer-safe reporting;
- distinguish target-host acquisition failure from internal VERIDRA execution failure.

## Gap 3 — mixed-content/insecure-resource calibration requires verification
Nine successful sites received high-severity insecure-resource/mixed-content findings. The raw evidence includes a mixture of likely active resources, ordinary HTTP hyperlinks/share URLs, and metadata/reference URLs such as `http://gmpg.org/xfn/11`.

Required design direction:
- only call something browser mixed content when an HTTP subresource is actually loadable/loaded in a context that qualifies;
- ordinary anchor/share links and metadata namespace/profile URLs must not be conflated with active mixed content;
- downgrade or relabel non-active HTTP references separately if they remain useful observations;
- add regression fixtures for XFN/profile URLs, social-share links, stylesheet/script/image subresources and ordinary anchors.

## Gate impact
These gaps block a strong #297 value conclusion. Complete 10–15 human validations only after enough calibration is implemented to avoid measuring an already-known defect pattern repeatedly.
