from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256
from pathlib import Path

from veridra.commercial_dashboard import build_commercial_snapshot
from veridra.core import Assessment, Finding, Status
from veridra.customer_store import (
    CustomerAgreementState,
    CustomerBillingState,
    CustomerBillingStatus,
    CustomerOnboardingChecklist,
    CustomerStatus,
)
from veridra.email_delivery import EmailStatus
from veridra.identity_tenancy import RequestIdentity, TenantRole
from veridra.monitoring_schedule import MonitoringCadence, MonitoringSchedule
from veridra.project_store import ClientProject
from veridra.prospect import Prospect, ProspectStatus
from veridra.report_delivery import ReportDeliveryAttempt, ReportDeliveryStore
from veridra.reports import render_report
from veridra.task_store import RemediationTask, TaskStatus
from veridra.tenant_customer_store import TenantCustomerStore
from veridra.tenant_history_store import TenantHistoryStore
from veridra.tenant_project_store import TenantProjectStore
from veridra.tenant_prospect_store import TenantProspectStore
from veridra.tenant_task_store import TenantTaskStore

NOW = datetime(2026, 8, 28, 10, 30, tzinfo=UTC)


def _identity(tenant: str, user: str) -> RequestIdentity:
    return RequestIdentity(
        user_id=user * 24,
        tenant_id=tenant * 24,
        membership_role=TenantRole.owner,
        session_id="f" * 24,
        authenticated_at=NOW,
    )


def _report_store(root: Path, identity: RequestIdentity) -> ReportDeliveryStore:
    return ReportDeliveryStore(root / identity.tenant_id / "report-deliveries")


def test_full_first_customer_delivery_survives_restart(tmp_path: Path) -> None:
    identity = _identity("a", "b")
    other_tenant = _identity("c", "d")

    prospects = TenantProspectStore(tmp_path)
    customers = TenantCustomerStore(tmp_path)
    projects = TenantProjectStore(tmp_path)
    history = TenantHistoryStore(tmp_path)
    tasks = TenantTaskStore(tmp_path)

    prospect = Prospect(
        business_name="First Customer Dental",
        website=None,
        contact_name="Practice Owner",
        contact_email="owner@example.com",
        phone="+353 1 555 0100",
        locality="Dublin",
        country_code="IE",
        status=ProspectStatus.proposal,
        outreach_offer="Website Improvement Sprint",
        human_verified=True,
    )
    prospect_id = prospects.save(identity, prospect)
    won = prospect.model_copy(
        update={
            "status": ProspectStatus.customer,
            "commercial_note": "Accepted Website Improvement Sprint.",
            "updated_at": NOW,
        }
    )
    prospects.replace(identity, prospects.ref(identity, prospect_id), won)
    customer_id, customer = customers.list(identity)[0]
    assert customer.booking_gate_required is True
    assert customer.work_may_start is False

    project = ClientProject.build(
        name="First Customer Dental website",
        target_url="https://first-customer-dental.example",
        client_label="First Customer Dental",
        monitoring_schedule=MonitoringSchedule(
            cadence=MonitoringCadence.weekly,
            timezone="Europe/Dublin",
            hour=9,
            minute=0,
            weekday=0,
        ),
        monitoring_email="owner@example.com",
    )
    project_id = projects.save(identity, project)

    completed = CustomerOnboardingChecklist(
        contact_confirmed=True,
        scope_confirmed=True,
        commercial_terms_confirmed=True,
        access_requirements_confirmed=True,
        kickoff_completed=True,
    )
    paid_at = NOW
    active_customer = customer.model_copy(
        update={
            "status": CustomerStatus.active,
            "project_ids": (project_id,),
            "onboarding": completed,
            "agreement": CustomerAgreementState(
                terms_reference="WEBIFY-MSA-001",
                terms_version="2026-09",
                accepted_at=NOW,
                acceptance_evidence="Synthetic acceptance evidence.",
                signature_reference="SIGN-SYNTHETIC-001",
            ),
            "billing": CustomerBillingState(
                status=CustomerBillingStatus.paid,
                invoice_reference="WEB-2026-001",
                invoice_amount=Decimal("650.00"),
                currency="EUR",
                deposit_required=True,
                deposit_amount=Decimal("325.00"),
                amount_paid=Decimal("650.00"),
                payment_reference="PAY-SYNTHETIC-001",
                payment_method_reference="bank transfer",
                payment_provider_reference="BANK-SYNTHETIC-001",
                paid_at=paid_at,
                note="Synthetic acceptance payment.",
            ),
            "activated_at": NOW,
            "updated_at": NOW,
        }
    )
    assert active_customer.work_may_start is True
    customers.replace(identity, customers.ref(identity, customer_id), active_customer)

    finding = Finding(
        id="missing-contact-cta",
        area="Conversion",
        title="Primary contact action is unclear",
        status=Status.attention,
        severity="high",
        summary="The primary contact action is not prominent.",
        recommendation="Add a prominent contact action to the primary page.",
        evidence={"source": "synthetic first-customer acceptance"},
    )
    assessment = Assessment.build(
        "https://first-customer-dental.example",
        [finding],
        mode="demo",
        generated_at=NOW,
        elapsed_ms=25,
    )
    assessment_id = history.save(identity, project_id, assessment)

    task = RemediationTask(
        project_id=project_id,
        finding_id=finding.id,
        title="Add prominent contact CTA",
        status=TaskStatus.planned,
        notes="Created from the first saved assessment.",
        source_assessment_id=assessment_id,
    )
    task_id = tasks.save(identity, task)

    report_html = render_report(assessment)
    assert "Primary contact action is unclear" in report_html
    assert "assessment report" in report_html.lower()

    report_store = _report_store(tmp_path, identity)
    delivery = ReportDeliveryAttempt(
        recipient="owner@example.com",
        attempted_at=NOW,
        status=EmailStatus.delivered,
        subject="First Customer Dental assessment report",
        message_sha256=sha256(report_html.encode("utf-8")).hexdigest(),
        attempt_number=1,
        project_id=project_id,
        assessment_id=assessment_id,
        filename="first-customer-dental-assessment.pdf",
    )
    delivery_id = report_store.save(delivery)

    snapshot = build_commercial_snapshot(
        [won],
        [],
        [active_customer],
        projects=projects.list(identity),
        as_of=NOW,
    )
    assert snapshot.project_count == 1
    assert snapshot.customer_counts[CustomerStatus.active] == 1
    assert snapshot.paid_total == {"EUR": Decimal("650.00")}

    # Simulate an application restart: reconstruct every persistence boundary.
    fresh_prospects = TenantProspectStore(tmp_path)
    fresh_customers = TenantCustomerStore(tmp_path)
    fresh_projects = TenantProjectStore(tmp_path)
    fresh_history = TenantHistoryStore(tmp_path)
    fresh_tasks = TenantTaskStore(tmp_path)
    fresh_reports = _report_store(tmp_path, identity)

    reloaded_prospect = fresh_prospects.load(
        identity,
        fresh_prospects.ref(identity, prospect_id),
    )
    reloaded_customer = fresh_customers.load(
        identity,
        fresh_customers.ref(identity, customer_id),
    )
    reloaded_project = fresh_projects.load(
        identity,
        fresh_projects.ref(identity, project_id),
    )
    reloaded_assessment = fresh_history.load(
        identity,
        fresh_history.ref(identity, project_id, assessment_id),
    )
    reloaded_task = fresh_tasks.load(identity, fresh_tasks.ref(identity, task_id))
    report_entries = fresh_reports.list_for_project(project_id)

    assert reloaded_prospect.status is ProspectStatus.customer
    assert reloaded_customer.status is CustomerStatus.active
    assert reloaded_customer.onboarding.complete is True
    assert reloaded_customer.agreement.accepted is True
    assert reloaded_customer.work_may_start is True
    assert reloaded_customer.project_ids == (project_id,)
    assert reloaded_customer.billing.status is CustomerBillingStatus.paid
    assert reloaded_customer.billing.invoice_amount == Decimal("650.00")
    assert reloaded_customer.billing.deposit_amount == Decimal("325.00")
    assert reloaded_customer.billing.payment_reference == "PAY-SYNTHETIC-001"
    assert reloaded_customer.billing.paid_at == paid_at
    assert reloaded_project.monitoring_schedule.cadence is MonitoringCadence.weekly
    assert reloaded_project.monitoring_schedule.timezone == "Europe/Dublin"
    assert str(reloaded_project.monitoring_email) == "owner@example.com"
    assert reloaded_assessment.findings[0].id == finding.id
    assert reloaded_task.source_assessment_id == assessment_id
    assert reloaded_task.status is TaskStatus.planned
    assert len(report_entries) == 1
    assert report_entries[0][0] == delivery_id
    assert report_entries[0][1].status is EmailStatus.delivered
    assert report_entries[0][1].assessment_id == assessment_id

    # Key persistence boundaries remain tenant-isolated after restart.
    assert fresh_customers.list(other_tenant) == []
    assert fresh_projects.list(other_tenant) == []
    assert fresh_tasks.list(other_tenant) == []
    assert _report_store(tmp_path, other_tenant).list_for_project(project_id) == []
