"""
Deterministic quota tests using synthetic subjects and a fake clock.
"""

from concurrent.futures import ThreadPoolExecutor

from src.policy.inference_quota import InferenceQuota


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def test_limit_and_retry_after():
    clock = Clock()
    quota = InferenceQuota(
        {"research-model": 2},
        clock=clock,
    )

    assert quota.admit("subject-a", "research-model").allowed
    assert quota.admit("subject-a", "research-model").allowed

    clock.now = 10.2
    decision = quota.admit("subject-a", "research-model")

    assert decision.allowed is False
    assert decision.reason == "quota_exceeded"
    assert decision.retry_after == 50


def test_rejected_requests_do_not_extend_window():
    clock = Clock()
    quota = InferenceQuota(
        {"research-model": 1},
        clock=clock,
    )

    assert quota.admit("subject-a", "research-model").allowed

    clock.now = 59.9
    assert not quota.admit("subject-a", "research-model").allowed

    clock.now = 60.0
    assert quota.admit("subject-a", "research-model").allowed


def test_subjects_have_independent_quotas():
    quota = InferenceQuota({"research-model": 1})

    assert quota.admit("subject-a", "research-model").allowed
    assert not quota.admit("subject-a", "research-model").allowed
    assert quota.admit("subject-b", "research-model").allowed


def test_models_have_independent_limits():
    quota = InferenceQuota({
        "research-model": 2,
        "restricted-model": 1,
    })

    assert quota.admit("subject-a", "restricted-model").allowed
    assert not quota.admit("subject-a", "restricted-model").allowed

    assert quota.admit("subject-a", "research-model").allowed
    assert quota.admit("subject-a", "research-model").allowed
    assert not quota.admit("subject-a", "research-model").allowed


def test_unknown_model_and_invalid_subject_fail_closed():
    quota = InferenceQuota({"research-model": 1})

    unknown = quota.admit("subject-a", "unknown-model")
    invalid = quota.admit("", "research-model")

    assert not unknown.allowed
    assert unknown.reason == "unknown_model"
    assert not invalid.allowed
    assert invalid.reason == "invalid_subject"


def test_full_state_does_not_evict_active_quota():
    quota = InferenceQuota(
        {"research-model": 1},
        max_entries=1,
    )

    assert quota.admit("subject-a", "research-model").allowed

    blocked = quota.admit("subject-b", "research-model")

    assert not blocked.allowed
    assert blocked.reason == "capacity_exhausted"
    assert not quota.admit("subject-a", "research-model").allowed


def test_expired_state_releases_capacity():
    clock = Clock()
    quota = InferenceQuota(
        {"research-model": 1},
        max_entries=1,
        clock=clock,
    )

    assert quota.admit("subject-a", "research-model").allowed

    clock.now = 60.0

    assert quota.admit("subject-b", "research-model").allowed


def test_concurrent_requests_cannot_exceed_limit():
    quota = InferenceQuota(
        {"research-model": 10},
        clock=lambda: 0.0,
    )

    with ThreadPoolExecutor(max_workers=20) as executor:
        decisions = list(
            executor.map(
                lambda _: quota.admit(
                    "subject-a",
                    "research-model",
                ),
                range(100),
            )
        )

    assert sum(decision.allowed for decision in decisions) == 10
    assert sum(
        decision.reason == "quota_exceeded"
        for decision in decisions
    ) == 90