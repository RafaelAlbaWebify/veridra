from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Protocol
from uuid import uuid4

from .prospect_discovery import ObservedBusiness


class AssistedDiscoveryState(StrEnum):
    idle = "idle"
    launching = "launching"
    awaiting_operator = "awaiting_operator"
    ready = "ready"
    collecting = "collecting"
    review = "review"
    stopped = "stopped"
    failed = "failed"


_ACTIVE_STATES = {
    AssistedDiscoveryState.launching,
    AssistedDiscoveryState.awaiting_operator,
    AssistedDiscoveryState.ready,
    AssistedDiscoveryState.collecting,
    AssistedDiscoveryState.review,
}


class TraversalStopReason(StrEnum):
    end_of_list = "end_of_list"
    no_new_results = "no_new_results"
    max_results = "max_results"
    max_scrolls = "max_scrolls"
    timeout = "timeout"
    operator_stop = "operator_stop"
    provider_error = "provider_error"


@dataclass(frozen=True, slots=True)
class BoundedDiscoveryLimits:
    max_results: int = 100
    max_scrolls: int = 40
    max_elapsed_seconds: float = 90.0
    max_stagnant_scrolls: int = 3

    def __post_init__(self) -> None:
        if self.max_results < 1 or self.max_results > 200:
            raise ValueError("max_results must be between 1 and 200.")
        if self.max_scrolls < 0 or self.max_scrolls > 100:
            raise ValueError("max_scrolls must be between 0 and 100.")
        if self.max_elapsed_seconds <= 0 or self.max_elapsed_seconds > 300:
            raise ValueError("max_elapsed_seconds must be between 0 and 300.")
        if self.max_stagnant_scrolls < 1 or self.max_stagnant_scrolls > 20:
            raise ValueError("max_stagnant_scrolls must be between 1 and 20.")


@dataclass(frozen=True, slots=True)
class TraversalObservation:
    business: ObservedBusiness
    query_text: str
    query_sequence: int
    result_rank: int
    first_seen_scroll_step: int


@dataclass(frozen=True, slots=True)
class TraversalProgress:
    query_text: str
    query_sequence: int
    scroll_step: int
    unique_results: int
    stagnant_scrolls: int
    elapsed_seconds: float
    stop_reason: TraversalStopReason | None = None


@dataclass(frozen=True, slots=True)
class TraversalResult:
    observations: tuple[TraversalObservation, ...]
    progress: TraversalProgress


class OrderedObservationAccumulator:
    """Preserve first-seen provider order while enforcing server-owned bounds."""

    def __init__(
        self,
        *,
        query_text: str,
        query_sequence: int,
        limits: BoundedDiscoveryLimits,
    ) -> None:
        clean_query = query_text.strip()
        if not clean_query:
            raise ValueError("query_text cannot be blank.")
        if query_sequence < 1:
            raise ValueError("query_sequence must be at least 1.")
        self._query_text = clean_query
        self._query_sequence = query_sequence
        self._limits = limits
        self._observations: list[TraversalObservation] = []
        self._seen_provider_keys: set[tuple[str, str]] = set()
        self._stagnant_scrolls = 0

    @property
    def observations(self) -> tuple[TraversalObservation, ...]:
        return tuple(self._observations)

    @property
    def stagnant_scrolls(self) -> int:
        return self._stagnant_scrolls

    def add_batch(
        self,
        businesses: list[ObservedBusiness],
        *,
        scroll_step: int,
    ) -> int:
        if scroll_step < 0:
            raise ValueError("scroll_step cannot be negative.")
        added = 0
        for business in businesses:
            identity = (business.provider.casefold(), business.provider_key.casefold())
            if identity in self._seen_provider_keys:
                continue
            if len(self._observations) >= self._limits.max_results:
                break
            self._seen_provider_keys.add(identity)
            self._observations.append(
                TraversalObservation(
                    business=business,
                    query_text=self._query_text,
                    query_sequence=self._query_sequence,
                    result_rank=len(self._observations) + 1,
                    first_seen_scroll_step=scroll_step,
                )
            )
            added += 1
        self._stagnant_scrolls = 0 if added else self._stagnant_scrolls + 1
        return added

    def evaluate_stop(
        self,
        *,
        scroll_step: int,
        elapsed_seconds: float,
        end_of_list: bool = False,
        operator_stop: bool = False,
        provider_error: bool = False,
    ) -> TraversalStopReason | None:
        if operator_stop:
            return TraversalStopReason.operator_stop
        if provider_error:
            return TraversalStopReason.provider_error
        if end_of_list:
            return TraversalStopReason.end_of_list
        if len(self._observations) >= self._limits.max_results:
            return TraversalStopReason.max_results
        if elapsed_seconds >= self._limits.max_elapsed_seconds:
            return TraversalStopReason.timeout
        if scroll_step >= self._limits.max_scrolls:
            return TraversalStopReason.max_scrolls
        if self._stagnant_scrolls >= self._limits.max_stagnant_scrolls:
            return TraversalStopReason.no_new_results
        return None

    def result(
        self,
        *,
        scroll_step: int,
        elapsed_seconds: float,
        stop_reason: TraversalStopReason,
    ) -> TraversalResult:
        return TraversalResult(
            observations=self.observations,
            progress=TraversalProgress(
                query_text=self._query_text,
                query_sequence=self._query_sequence,
                scroll_step=scroll_step,
                unique_results=len(self._observations),
                stagnant_scrolls=self._stagnant_scrolls,
                elapsed_seconds=elapsed_seconds,
                stop_reason=stop_reason,
            ),
        )


class AssistedDiscoveryProvider(Protocol):
    def launch(self, *, start_url: str) -> None: ...

    def collect_bounded(
        self,
        *,
        query_text: str,
        query_sequence: int,
        limits: BoundedDiscoveryLimits,
    ) -> TraversalResult: ...

    def stop(self) -> None: ...


@dataclass(frozen=True, slots=True)
class AssistedDiscoverySession:
    session_id: str | None
    state: AssistedDiscoveryState
    query_text: str = ""
    query_sequence: int = 0
    start_url: str = ""
    observations: tuple[TraversalObservation, ...] = ()
    progress: TraversalProgress | None = None
    error: str = ""


class AssistedDiscoveryConflict(RuntimeError):
    pass


class AssistedDiscoveryTransitionError(RuntimeError):
    pass


class AssistedDiscoveryManager:
    """Operator-controlled lifecycle around one bounded discovery provider session."""

    def __init__(self, provider: AssistedDiscoveryProvider) -> None:
        self._provider = provider
        self._session = AssistedDiscoverySession(
            session_id=None,
            state=AssistedDiscoveryState.idle,
        )

    def snapshot(self) -> AssistedDiscoverySession:
        return self._session

    def launch(
        self,
        *,
        query_text: str,
        query_sequence: int,
        start_url: str,
    ) -> AssistedDiscoverySession:
        if self._session.state in _ACTIVE_STATES:
            raise AssistedDiscoveryConflict("An assisted discovery session is already active.")
        clean_query = query_text.strip()
        clean_url = start_url.strip()
        if not clean_query:
            raise ValueError("query_text cannot be blank.")
        if query_sequence < 1:
            raise ValueError("query_sequence must be at least 1.")
        if not clean_url:
            raise ValueError("start_url cannot be blank.")

        session = AssistedDiscoverySession(
            session_id=str(uuid4()),
            state=AssistedDiscoveryState.launching,
            query_text=clean_query,
            query_sequence=query_sequence,
            start_url=clean_url,
        )
        self._session = session
        try:
            self._provider.launch(start_url=clean_url)
        except Exception as exc:
            self._session = replace(
                session,
                state=AssistedDiscoveryState.failed,
                error=str(exc),
            )
            raise
        self._session = replace(session, state=AssistedDiscoveryState.awaiting_operator)
        return self._session

    def mark_ready(self, session_id: str) -> AssistedDiscoverySession:
        self._require_current(session_id)
        if self._session.state is not AssistedDiscoveryState.awaiting_operator:
            raise AssistedDiscoveryTransitionError(
                "The session can be marked ready only while awaiting the operator."
            )
        self._session = replace(self._session, state=AssistedDiscoveryState.ready)
        return self._session

    def collect(
        self,
        session_id: str,
        *,
        limits: BoundedDiscoveryLimits,
    ) -> AssistedDiscoverySession:
        self._require_current(session_id)
        if self._session.state is not AssistedDiscoveryState.ready:
            raise AssistedDiscoveryTransitionError(
                "Discovery can run only after the operator marks the browser ready."
            )
        self._session = replace(
            self._session,
            state=AssistedDiscoveryState.collecting,
            observations=(),
            progress=None,
            error="",
        )
        try:
            result = self._provider.collect_bounded(
                query_text=self._session.query_text,
                query_sequence=self._session.query_sequence,
                limits=limits,
            )
            self._validate_provider_result(
                result,
                limits=limits,
                expected_query_text=self._session.query_text,
                expected_query_sequence=self._session.query_sequence,
            )
        except Exception as exc:
            self._restore_ready_after_error(exc)
            raise
        self._session = replace(
            self._session,
            state=AssistedDiscoveryState.review,
            observations=result.observations,
            progress=result.progress,
            error="",
        )
        return self._session

    def stop(self, session_id: str | None = None) -> AssistedDiscoverySession:
        if self._session.session_id is None:
            return self._session
        if session_id is not None:
            self._require_current(session_id)
        if self._session.state in {
            AssistedDiscoveryState.stopped,
            AssistedDiscoveryState.failed,
        }:
            return self._session
        self._provider.stop()
        self._session = replace(self._session, state=AssistedDiscoveryState.stopped)
        return self._session

    def included_businesses(self, session_id: str) -> tuple[ObservedBusiness, ...]:
        self._require_current(session_id)
        if self._session.state is not AssistedDiscoveryState.review:
            raise AssistedDiscoveryTransitionError(
                "Discovery observations are available only during review."
            )
        return tuple(item.business for item in self._session.observations)

    def _restore_ready_after_error(self, exc: Exception) -> None:
        self._session = replace(
            self._session,
            state=AssistedDiscoveryState.ready,
            observations=(),
            error=str(exc),
            progress=TraversalProgress(
                query_text=self._session.query_text,
                query_sequence=self._session.query_sequence,
                scroll_step=0,
                unique_results=0,
                stagnant_scrolls=0,
                elapsed_seconds=0.0,
                stop_reason=TraversalStopReason.provider_error,
            ),
        )

    def _require_current(self, session_id: str) -> None:
        if not session_id or self._session.session_id != session_id:
            raise AssistedDiscoveryTransitionError(
                "The assisted discovery session does not exist."
            )

    @staticmethod
    def _validate_provider_result(
        result: TraversalResult,
        *,
        limits: BoundedDiscoveryLimits,
        expected_query_text: str,
        expected_query_sequence: int,
    ) -> None:
        if len(result.observations) > limits.max_results:
            raise ValueError("Discovery provider exceeded the configured result limit.")
        if result.progress.unique_results != len(result.observations):
            raise ValueError("Discovery provider returned inconsistent progress evidence.")
        if result.progress.query_text != expected_query_text:
            raise ValueError("Discovery provider returned mismatched query text provenance.")
        if result.progress.query_sequence != expected_query_sequence:
            raise ValueError("Discovery provider returned mismatched query sequence provenance.")
        for index, observation in enumerate(result.observations, start=1):
            if observation.query_text != expected_query_text:
                raise ValueError("Discovery observation returned mismatched query text provenance.")
            if observation.query_sequence != expected_query_sequence:
                raise ValueError(
                    "Discovery observation returned mismatched query sequence provenance."
                )
            if observation.result_rank != index:
                raise ValueError("Discovery observation ranks must be contiguous and ordered.")
