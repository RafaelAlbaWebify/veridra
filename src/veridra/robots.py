from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlsplit


@dataclass(frozen=True)
class RobotsPolicy:
    user_agent: str
    disallow_all: bool
    allow_all: bool
    matched_group: bool


def _groups(robots_text: str) -> list[tuple[list[str], list[tuple[str, str]]]]:
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
        if key_lower == "user-agent":
            if directives:
                flush()
            agents.append(value.lower())
        elif agents and key_lower in {"allow", "disallow"}:
            directives.append((key_lower, value))
    flush()
    return groups


def _matching_directives(
    robots_text: str,
    user_agent: str,
) -> tuple[list[tuple[str, str]], bool]:
    target = user_agent.strip().lower()
    groups = _groups(robots_text)
    specific = [group for group in groups if target in group[0]]
    matching = specific or [group for group in groups if "*" in group[0]]
    return [item for _, rules in matching for item in rules], bool(matching)


def evaluate_robots_policy(robots_text: str, user_agent: str) -> RobotsPolicy:
    target = user_agent.strip().lower()
    directives, matched_group = _matching_directives(robots_text, target)
    if not matched_group:
        return RobotsPolicy(
            user_agent=target,
            disallow_all=False,
            allow_all=True,
            matched_group=False,
        )

    disallow_all = any(
        key == "disallow" and value.strip() == "/"
        for key, value in directives
    )
    allow_all = not disallow_all
    return RobotsPolicy(
        user_agent=target,
        disallow_all=disallow_all,
        allow_all=allow_all,
        matched_group=True,
    )


def _rule_matches(path: str, rule: str) -> bool:
    anchored = rule.endswith("$")
    pattern = rule[:-1] if anchored else rule
    escaped = re.escape(pattern).replace(r"\*", ".*")
    suffix = "$" if anchored else ""
    return re.match(f"^{escaped}{suffix}", path) is not None


def robots_allows_url(robots_text: str, user_agent: str, url: str) -> bool:
    """Apply deterministic longest-match robots rules to one public URL."""

    if not robots_text.strip():
        return True
    directives, matched_group = _matching_directives(robots_text, user_agent)
    if not matched_group:
        return True

    parsed = urlsplit(url)
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"

    matches: list[tuple[int, bool]] = []
    for key, raw_rule in directives:
        rule = raw_rule.strip()
        if not rule:
            continue
        if _rule_matches(path, rule):
            specificity = len(rule.rstrip("$").replace("*", ""))
            matches.append((specificity, key == "allow"))
    if not matches:
        return True

    best_specificity = max(specificity for specificity, _ in matches)
    return any(
        allowed
        for specificity, allowed in matches
        if specificity == best_specificity
    )
