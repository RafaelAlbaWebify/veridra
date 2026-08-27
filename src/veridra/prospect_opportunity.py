from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .prospect_discovery import ObservedBusiness


class OpportunityBand(StrEnum):
    priority = "priority"
    high = "high"
    medium = "medium"
    low = "low"


@dataclass(frozen=True, slots=True)
class OpportunityAssessment:
    score: int
    band: OpportunityBand
    digital_gap_score: int
    business_activity_score: int
    reasons: tuple[str, ...]


def _review_activity(review_count: int | None) -> tuple[int, str | None]:
    if review_count is None:
        return 0, None
    if review_count >= 200:
        return 30, "Strong customer activity signal: 200+ Google reviews observed."
    if review_count >= 50:
        return 24, "Healthy customer activity signal: 50+ Google reviews observed."
    if review_count >= 20:
        return 18, "Established customer activity signal: 20+ Google reviews observed."
    if review_count >= 5:
        return 12, "Some customer activity is visible in Google reviews."
    if review_count > 0:
        return 6, "Limited customer activity is visible in Google reviews."
    return 0, "No Google reviews were observed in discovery."


def _review_gap(review_count: int | None) -> tuple[int, str | None]:
    if review_count is None:
        return 0, None
    if review_count == 0:
        return 12, "No Google reviews were observed; reputation presence appears undeveloped."
    if review_count < 5:
        return 10, "Very few Google reviews were observed."
    if review_count < 20:
        return 7, "Google review presence is still relatively small."
    if review_count < 50:
        return 4, "Google review presence is moderate rather than strong."
    return 0, None


def _photo_gap(photo_count: int | None) -> tuple[int, str | None]:
    if photo_count is None:
        return 0, None
    if photo_count <= 1:
        return 13, "Very weak Google Maps photo signal was observed."
    if photo_count <= 3:
        return 8, "Only a small Google Maps photo signal was observed."
    if photo_count <= 5:
        return 4, "Google Maps photo presence appears limited."
    return 0, None


def assess_opportunity(business: ObservedBusiness) -> OpportunityAssessment:
    """Rank observable Webify opportunity without inventing unobserved GBP facts.

    The model deliberately separates the digital gap from evidence that a real business
    has customer activity. A missing website is a large gap, but a business with no
    activity evidence is not automatically promoted to the highest-priority band.
    """

    reasons: list[str] = []
    gap = 0

    if business.website is None:
        gap += 45
        reasons.append("No business website was observed from the Google Maps profile.")

    review_gap, review_reason = _review_gap(business.review_count)
    gap += review_gap
    if review_reason:
        reasons.append(review_reason)

    photo_gap, photo_reason = _photo_gap(business.profile_photo_signal_count)
    gap += photo_gap
    if photo_reason:
        reasons.append(photo_reason)

    activity, activity_reason = _review_activity(business.review_count)
    if activity_reason:
        reasons.append(activity_reason)

    if business.rating is not None and business.review_count and business.review_count >= 10:
        if business.rating >= 4.5:
            reasons.append(
                "Strong rating suggests the underlying customer experience may be "
                "healthier than the digital gap."
            )
        elif business.rating < 4.2:
            reasons.append(
                "Lower rating is a reputation signal only; it is not treated as a "
                "Webify-fixable problem by itself."
            )

    score = min(100, gap + activity)

    if score >= 65 and activity >= 12:
        band = OpportunityBand.priority
    elif score >= 50 and activity >= 6:
        band = OpportunityBand.high
    elif score >= 30:
        band = OpportunityBand.medium
    else:
        band = OpportunityBand.low

    return OpportunityAssessment(
        score=score,
        band=band,
        digital_gap_score=gap,
        business_activity_score=activity,
        reasons=tuple(reasons),
    )
