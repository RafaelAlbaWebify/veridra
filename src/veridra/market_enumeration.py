from __future__ import annotations

from dataclasses import dataclass

from .assisted_discovery import TraversalObservation, TraversalResult
from .prospect_discovery import ObservedBusiness


@dataclass(frozen=True, slots=True)
class MarketBusiness:
    business: ObservedBusiness
    first_query_text: str
    first_query_sequence: int
    first_result_rank: int
    seen_in_queries: tuple[str, ...]
    observation_count: int


@dataclass(frozen=True, slots=True)
class QueryCoverage:
    query_text: str
    query_sequence: int
    captured: int
    new_unique: int
    duplicate_observations: int
    stop_reason: str | None


@dataclass(frozen=True, slots=True)
class MarketEnumeration:
    businesses: tuple[MarketBusiness, ...]
    coverage: tuple[QueryCoverage, ...]
    raw_observation_count: int


def _identity(observation: TraversalObservation) -> tuple[str, str]:
    business = observation.business
    return business.provider.casefold(), business.provider_key.casefold()


def aggregate_market(results: list[TraversalResult]) -> MarketEnumeration:
    first_seen: dict[tuple[str, str], TraversalObservation] = {}
    query_hits: dict[tuple[str, str], list[str]] = {}
    observation_counts: dict[tuple[str, str], int] = {}
    coverage: list[QueryCoverage] = []
    raw_count = 0

    for result in results:
        new_unique = 0
        duplicate_observations = 0
        for observation in result.observations:
            raw_count += 1
            key = _identity(observation)
            observation_counts[key] = observation_counts.get(key, 0) + 1
            queries = query_hits.setdefault(key, [])
            if observation.query_text not in queries:
                queries.append(observation.query_text)
            if key in first_seen:
                duplicate_observations += 1
                continue
            first_seen[key] = observation
            new_unique += 1

        reason = result.progress.stop_reason
        coverage.append(
            QueryCoverage(
                query_text=result.progress.query_text,
                query_sequence=result.progress.query_sequence,
                captured=len(result.observations),
                new_unique=new_unique,
                duplicate_observations=duplicate_observations,
                stop_reason=reason.value if reason is not None else None,
            )
        )

    businesses = tuple(
        MarketBusiness(
            business=observation.business,
            first_query_text=observation.query_text,
            first_query_sequence=observation.query_sequence,
            first_result_rank=observation.result_rank,
            seen_in_queries=tuple(query_hits[key]),
            observation_count=observation_counts[key],
        )
        for key, observation in first_seen.items()
    )
    return MarketEnumeration(
        businesses=businesses,
        coverage=tuple(coverage),
        raw_observation_count=raw_count,
    )


def dublin_dentist_queries() -> tuple[str, ...]:
    geographic = tuple(f"dentist in Dublin {district}, IE" for district in range(1, 25))
    return (
        "dentist in Dublin, IE",
        *geographic,
        "dentist in Dublin 6W, IE",
        "dental clinic in Dublin, IE",
        "family dentist in Dublin, IE",
        "emergency dentist in Dublin, IE",
        "orthodontist in Dublin, IE",
    )
