from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RobotsPolicy:
    user_agent: str
    disallow_all: bool
    allow_all: bool
    matched_group: bool


def evaluate_robots_policy(robots_text: str, user_agent: str) -> RobotsPolicy:
    target = user_agent.strip().lower()
    groups: list[tuple[list[str], list[tuple[str, str]]]] = []
    agents: list[str] = []
    directives: list[tuple[str, str]] = []

    def flush() -> None:
        nonlocal agents, directives
        if agents:
            groups.append((agents, directives))
        agents = []
        directives = []

    for raw_line in robots_text.splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        key, value = (part.strip() for part in line.split(":", 1))
        key_lower = key.lower()
        value_lower = value.lower()
        if key_lower == "user-agent":
            if directives:
                flush()
            agents.append(value_lower)
        elif agents and key_lower in {"allow", "disallow"}:
            directives.append((key_lower, value))

    flush()

    matching = [group for group in groups if target in group[0]]
    if not matching:
        matching = [group for group in groups if "*" in group[0]]
    if not matching:
        return RobotsPolicy(
            user_agent=target,
            disallow_all=False,
            allow_all=True,
            matched_group=False,
        )

    group_directives = [item for _, rules in matching for item in rules]
    disallow_all = any(key == "disallow" and value.strip() == "/" for key, value in group_directives)
    allow_all = not disallow_all
    return RobotsPolicy(
        user_agent=target,
        disallow_all=disallow_all,
        allow_all=allow_all,
        matched_group=True,
    )
