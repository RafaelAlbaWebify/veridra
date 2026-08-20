from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

from pydantic import ValidationError

from .subscription_authority import (
    SubscriptionAuthority,
    SubscriptionAuthorityError,
    SubscriptionUpdate,
)
from .tenant_project_store import default_tenant_data_directory
from .workspace_policy import PlanName, WorkspaceStatus


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Project an already authenticated billing-provider event into tenant entitlements."
        )
    )
    parser.add_argument("--tenant-id", required=True)
    parser.add_argument("--provider", required=True)
    parser.add_argument("--event-id", required=True)
    parser.add_argument("--subscription-id", required=True)
    parser.add_argument("--plan", required=True, choices=[plan.value for plan in PlanName])
    parser.add_argument(
        "--status",
        required=True,
        choices=[status.value for status in WorkspaceStatus],
    )
    parser.add_argument("--cycle-anchor-day", required=True, type=int)
    parser.add_argument(
        "--occurred-at",
        required=True,
        help="Provider event timestamp as timezone-aware ISO-8601 text.",
    )
    parser.add_argument(
        "--tenant-data-root",
        type=Path,
        default=None,
        help="Override the configured tenant-data root.",
    )
    return parser


def main() -> None:
    parser = _parser()
    arguments = parser.parse_args()
    root = (
        arguments.tenant_data_root.expanduser().resolve()
        if arguments.tenant_data_root is not None
        else default_tenant_data_directory()
    )
    try:
        update = SubscriptionUpdate(
            tenant_id=arguments.tenant_id,
            provider=arguments.provider,
            provider_event_id=arguments.event_id,
            external_subscription_id=arguments.subscription_id,
            plan=PlanName(arguments.plan),
            status=WorkspaceStatus(arguments.status),
            cycle_anchor_day=arguments.cycle_anchor_day,
            occurred_at=datetime.fromisoformat(arguments.occurred_at),
        )
        result = SubscriptionAuthority(root).apply(update)
    except (ValueError, ValidationError, SubscriptionAuthorityError) as exc:
        parser.error(str(exc))

    state = "applied" if result.applied else "already applied"
    print(
        f"Subscription event {state}: {result.event_key}; "
        f"plan={result.workspace.plan.value}; status={result.workspace.status.value}"
    )


if __name__ == "__main__":
    main()
