from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from pydantic import ValidationError
import pytest

from veridra.recurring_service import (
    BillingCadence,
    RecurringServiceRecord,
    RecurringServiceStatus,
    RecurringServiceStore,
    RecurringServiceVersion,
    RenewalBehavior,
)


PROJECT_ID = "a" * 24
CUSTOMER_ID = "b" * 24


def _version(version: int = 1) -> RecurringServiceVersion:
    return RecurringServiceVersion(
        version=version,
        scope=("Monthly website health review", "Monitoring review"),
        exclusions=("New page builds", "Third-party paid media"),
        deliverables=("Monthly monitoring review", "Monthly client summary"),
        cadence_description="Monthly review and report.",
        response_time="Operational issues reviewed within two business days.",
        escalation_expectations="Critical availability evidence is surfaced first.",
        fee=Decimal("99.00"),
        currency="EUR",
        billing_cadence=BillingCadence.monthly,
        effective_from=date(2026, 9, 4),
    )


def _active() -> RecurringServiceRecord:
    return RecurringServiceRecord(
        project_id=PROJECT_ID,
        customer_id=CUSTOMER_ID,
        status=RecurringServiceStatus.active,
        versions=(_version(),),
        current_version=1,
        offered_at=datetime(2026, 9, 4, 9, 0, tzinfo=UTC),
        accepted_at=datetime(2026, 9, 4, 10, 0, tzinfo=UTC),
        acceptance_reference="Synthetic customer approval.",
        start_date=date(2026, 9, 5),
        minimum_term_months=0,
        renewal_behavior=RenewalBehavior.manual,
        renewal_date=date(2026, 10, 5),
        next_billing_date=date(2026, 10, 5),
        invoice_reference="INV-RECUR-001",
        payment_reference="PAY-RECUR-001",
        last_payment_state="paid",
        monitoring_cadence="Monthly",
        report_cadence="Monthly",
        next_action="Run next monthly monitoring review.",
    )


def test_active_service_requires_real_acceptance_evidence() -> None:
    with pytest.raises(ValidationError, match="acceptance evidence"):
        RecurringServiceRecord(
            project_id=PROJECT_ID,
            customer_id=CUSTOMER_ID,
            status=RecurringServiceStatus.active,
            versions=(_version(),),
            current_version=1,
            offered_at=datetime(2026, 9, 4, 9, 0, tzinfo=UTC),
            accepted_at=datetime(2026, 9, 4, 10, 0, tzinfo=UTC),
            start_date=date(2026, 9, 5),
        )


def test_paid_service_requires_bounded_scope() -> None:
    with pytest.raises(ValidationError, match="bounded service scope"):
        RecurringServiceVersion(
            version=1,
            fee=Decimal("99.00"),
            currency="EUR",
        )


def test_payment_blocked_pause_and_cancellation_require_evidence() -> None:
    active = _active()
    blocked = RecurringServiceRecord.model_validate(
        {
            **active.model_dump(mode="json"),
            "status": "payment_blocked",
            "last_payment_state": "failed: invoice INV-RECUR-002",
        }
    )
    assert blocked.status is RecurringServiceStatus.payment_blocked

    paused = RecurringServiceRecord.model_validate(
        {
            **active.model_dump(mode="json"),
            "status": "paused",
            "pause_reference": "Synthetic customer-requested pause.",
        }
    )
    assert paused.pause_reference

    with pytest.raises(ValidationError, match="Cancellation requires"):
        RecurringServiceRecord.model_validate(
            {
                **active.model_dump(mode="json"),
                "status": "cancellation_pending",
            }
        )


def test_cancelled_service_requires_exit_handoff() -> None:
    active = _active()
    pending = RecurringServiceRecord.model_validate(
        {
            **active.model_dump(mode="json"),
            "status": "cancellation_pending",
            "cancellation_notice_date": "2026-09-20",
            "cancellation_reference": "Synthetic cancellation notice.",
        }
    )
    with pytest.raises(ValidationError, match="exit/handoff evidence"):
        RecurringServiceRecord.model_validate(
            {
                **pending.model_dump(mode="json"),
                "status": "cancelled",
                "cancellation_effective_date": "2026-10-05",
            }
        )


def test_version_history_preserves_scope_and_price_change() -> None:
    first = _version(1)
    second = first.model_copy(
        update={
            "version": 2,
            "fee": Decimal("129.00"),
            "scope": (*first.scope, "Quarterly conversion-path review"),
            "effective_from": date(2026, 10, 5),
        }
    )
    record = _active().model_copy(
        update={"versions": (first, second), "current_version": 2}
    )
    assert record.active_version == second
    assert record.versions[0].fee == Decimal("99.00")


def test_store_round_trip_is_atomic_json(tmp_path) -> None:
    store = RecurringServiceStore(tmp_path / "recurring")
    record = _active()
    store.save(record)
    loaded = store.load(PROJECT_ID)
    assert loaded == record
    assert (tmp_path / "recurring" / f"{PROJECT_ID}.json").exists()
