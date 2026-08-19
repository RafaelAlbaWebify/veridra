from veridra.robots import evaluate_robots_policy, robots_allows_url


def test_specific_group_takes_precedence_over_wildcard() -> None:
    policy = evaluate_robots_policy(
        """
        User-agent: *
        Disallow: /

        User-agent: OAI-SearchBot
        Allow: /
        """,
        "OAI-SearchBot",
    )
    assert policy.matched_group is True
    assert policy.allow_all is True
    assert policy.disallow_all is False


def test_wildcard_applies_when_specific_group_is_missing() -> None:
    policy = evaluate_robots_policy(
        "User-agent: *\nDisallow: /\n",
        "GPTBot",
    )
    assert policy.matched_group is True
    assert policy.disallow_all is True


def test_missing_group_defaults_to_allowed() -> None:
    policy = evaluate_robots_policy("", "Google-Extended")
    assert policy.matched_group is False
    assert policy.allow_all is True


def test_path_level_robots_policy_blocks_disallowed_url() -> None:
    robots = "User-agent: *\nDisallow: /private/\nAllow: /private/public/\n"

    assert robots_allows_url(
        robots,
        "Veridra",
        "https://example.com/private/secret",
    ) is False
    assert robots_allows_url(
        robots,
        "Veridra",
        "https://example.com/private/public/info",
    ) is True


def test_empty_robots_policy_allows_crawl() -> None:
    assert robots_allows_url("", "Veridra", "https://example.com/page") is True
