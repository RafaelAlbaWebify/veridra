from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CommercialOfferTemplate:
    key: str
    title: str
    scope: str
    deliverables: str
    exclusions: str
    assumptions: str
    timeline: str
    recurring: bool = False


INITIAL_IMPROVEMENT = CommercialOfferTemplate(
    key="initial_improvement",
    title="Webify Digital Presence Assessment & Improvement",
    scope=(
        "Assess the agreed public website and digital-presence scope, prioritise material "
        "issues, implement only the bounded improvements explicitly agreed with the client, "
        "and verify the resulting state."
    ),
    deliverables=(
        "Baseline assessment and evidence; prioritised findings; agreed bounded remediation; "
        "verification/re-assessment; customer-facing final report and handoff."
    ),
    exclusions=(
        "Unlimited remediation; platform replacement; unrestricted copywriting or redesign; "
        "paid media; penetration testing; legal, accessibility or security certification; "
        "third-party fees; and work outside the accepted proposal/change-control scope."
    ),
    assumptions=(
        "The client controls or is authorised to change the target, provides approved access "
        "when remediation requires it, keeps third-party subscriptions/services available, "
        "and approves material scope changes before additional work starts."
    ),
    timeline="Confirmed after discovery and required access; bounded in the accepted proposal.",
)

PRESENCE_CARE = CommercialOfferTemplate(
    key="presence_care",
    title="Webify Presence Care",
    scope=(
        "Ongoing monitoring and bounded care for an agreed digital-presence scope where "
        "recurring risk/value has been explicitly qualified."
    ),
    deliverables=(
        "Scheduled monitoring/re-assessment; change and regression review; periodic progress "
        "reporting; bounded included maintenance/remediation defined in the accepted service "
        "version; escalation or separate quotation for work beyond that allowance."
    ),
    exclusions=(
        "Unlimited development or redesign; major migrations; new functionality; third-party "
        "fees; penetration testing; legal, accessibility or security certification; and work "
        "outside the accepted recurring-service scope or included allowance."
    ),
    assumptions=(
        "Presence Care is offered only when recurring value is evidenced. Exact cadence, "
        "included work allowance, response/escalation expectations and fee must be stated in "
        "the accepted recurring-service version."
    ),
    timeline="Recurring cadence and service start are confirmed in the accepted service version.",
    recurring=True,
)

COMMERCIAL_OFFERS = {item.key: item for item in (INITIAL_IMPROVEMENT, PRESENCE_CARE)}
