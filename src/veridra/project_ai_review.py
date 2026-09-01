from __future__ import annotations

from typing import Any

from .ai_review_exchange import (
    AIReviewBundle,
    DeterministicScore,
    EvidenceItem,
    ReviewContextType,
    build_review_bundle,
)
from .core import Assessment
from .observations import ObservedAssessment
from .project_store import ClientProject


def _finding_evidence(assessment_id: str, assessment: Assessment) -> tuple[EvidenceItem, ...]:
    items: list[EvidenceItem] = []
    for finding in assessment.findings:
        facts: dict[str, Any] = {
            "area": finding.area,
            "title": finding.title,
            "status": finding.status.value,
            "severity": finding.severity,
            "summary": finding.summary,
            "recommendation": finding.recommendation,
            "evidence": finding.evidence,
        }
        items.append(
            EvidenceItem(
                evidence_id=f"finding:{finding.id}",
                source_type="saved_finding",
                source_ref=f"assessment:{assessment_id}:finding:{finding.id}",
                observed_at=assessment.generated_at,
                facts=facts,
            )
        )
    return tuple(items)


def _scores(assessment: Assessment) -> tuple[DeterministicScore, ...]:
    values: list[DeterministicScore] = []
    for key in ("passed", "attention", "unavailable", "total"):
        if key in assessment.summary:
            values.append(
                DeterministicScore(
                    key=f"findings.{key}",
                    value=assessment.summary[key],
                    basis="saved assessment summary",
                )
            )
    for area, counts in sorted(assessment.area_summary.items()):
        for key in ("passed", "attention", "unavailable", "total"):
            if key in counts:
                values.append(
                    DeterministicScore(
                        key=f"area.{area}.{key}",
                        value=counts[key],
                        basis="saved deterministic area summary",
                    )
                )
    return tuple(values)


def build_project_review_bundle(
    *,
    project_id: str,
    project: ClientProject,
    assessment_id: str,
    assessment: Assessment,
) -> AIReviewBundle:
    provenance: dict[str, Any] = {
        "assessment_id": assessment_id,
        "assessment_schema_version": assessment.schema_version,
        "assessment_generated_at": assessment.generated_at.isoformat(),
        "assessment_mode": assessment.mode,
        "source_rule": "saved VERIDRA assessment and deterministic finding summaries remain authoritative",
    }
    context: dict[str, Any] = {
        "project_name": project.name,
        "target_url": project.target_url,
        "client_label": project.client_label,
        "contact_label": project.contact_label,
        "crawl_profile": project.crawl_profile.value,
        "assessment_id": assessment_id,
        "assessment_summary": assessment.summary,
        "assessment_area_summary": assessment.area_summary,
    }
    if isinstance(assessment, ObservedAssessment):
        provenance["collector_version"] = assessment.collector_version
        provenance["crawl_profile"] = assessment.crawl_profile
        provenance["effective_crawl_limits"] = assessment.effective_crawl_limits
        context["observed_page_count"] = len(assessment.pages)
        context["observation_count"] = len(assessment.observations)

    return build_review_bundle(
        context_type=ReviewContextType.project,
        context_id=project_id,
        context_label=project.name,
        target=project.target_url,
        context=context,
        deterministic_scores=_scores(assessment),
        evidence=_finding_evidence(assessment_id, assessment),
        provenance=provenance,
        generated_at=assessment.generated_at,
    )
