from veridra.robots import evaluate_robots_policy


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
