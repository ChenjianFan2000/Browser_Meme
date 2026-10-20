"""Behavior tests for the miniature issue workflow's public transition contract."""

from copy import deepcopy

from issue_lab.domain import IssueDomain


def pick(domain, **fields):
    return [row["id"] for row in domain.observe()["issues"]
            if all(row[key] == value for key, value in fields.items())]


def select(domain, ids):
    return domain.step({"type": "select", "ids": ids})


def business_state(observation):
    return {key: value for key, value in observation.items() if key != "feedback"}


def test_reset_is_reproducible_complete_and_returns_independent_copies():
    domain = IssueDomain(817)
    original = domain.observe()
    assert len(original["issues"]) == len(set(original["visible_ids"])) == 6
    assert len(pick(domain, status="open", blocked=False)) >= 2
    assert pick(domain, status="open", blocked=True)
    assert pick(domain, status="closed")
    assert "version" not in original
    assert original != IssueDomain(818).observe()
    select(domain, original["visible_ids"][:1])
    changed = domain.step({"type": "comment", "text": "Seen"})
    changed["issues"][0]["labels"].append("external")
    changed["selected"].clear()
    assert "external" not in domain.observe()["issues"][0]["labels"]
    assert domain.observe()["selected"]
    assert domain.reset() == original
    assert domain.reset(seed=818) == IssueDomain(818).observe()


def test_filter_version_one_clears_and_version_two_intersects_selection():
    for version in (1, 2):
        domain = IssueDomain(33, version)
        all_ids = domain.observe()["visible_ids"]
        select(domain, all_ids)
        result = domain.step({"type": "filter", "status": "open", "label": ""})
        assert result["selected"] == ([] if version == 1 else sorted(result["visible_ids"]))
        assert len(result["issues"]) == 6
        assert len(result["visible_ids"]) < 6
        if version == 2:
            again = domain.step({"type": "filter", "status": "all"})
            assert again["selected"] == result["selected"]


def test_sort_preserves_selection_and_select_uses_only_visible_ids():
    domain = IssueDomain()
    domain.step({"type": "filter", "status": "open"})
    opens = domain.observe()["visible_ids"]
    closed = pick(domain, status="closed")[0]
    result = select(domain, [opens[-1], opens[-1], closed, -1])
    assert result["selected"] == [opens[-1]]
    result = domain.step({"type": "sort", "direction": "desc"})
    assert result["selected"] == [opens[-1]]
    assert result["visible_ids"] == sorted(opens, reverse=True)
    result = domain.step({"type": "select_all"})
    assert result["selected"] == sorted(opens)


def test_label_filter_matches_labels_and_empty_result_is_selectable():
    domain = IssueDomain()
    target = domain.observe()["visible_ids"][0]
    select(domain, [target])
    domain.step({"type": "label", "value": "unique"})
    result = domain.step({"type": "filter", "status": "all", "label": "unique"})
    assert result["visible_ids"] == [target]
    assert domain.step({"type": "select_all"})["selected"] == [target]
    domain.step({"type": "filter", "label": "missing"})
    assert domain.step({"type": "select_all"})["selected"] == []


def test_permission_precedes_selection_and_specific_validation():
    domain = IssueDomain(version=2, role="viewer")
    for kind in ("label", "close", "reopen", "comment"):
        before = domain.observe()
        result = domain.step({"type": kind})
        assert result["feedback"]["code"] == "permission_denied"
        assert business_state(result) == business_state(before)
    domain.step({"type": "select_all"})
    assert domain.step({"type": "close"})["feedback"]["code"] == "permission_denied"
    domain = IssueDomain(version=2)
    for kind in ("label", "close", "reopen", "comment"):
        assert domain.step({"type": kind})["feedback"]["code"] == "empty_selection"


def test_blocked_close_is_atomic_and_reason_checked_before_blocked():
    for version in (1, 2):
        domain = IssueDomain(version=version)
        ids = pick(domain, status="open", blocked=False)[:1] + pick(domain, blocked=True)
        before = select(domain, ids)
        result = domain.step({"type": "close"})
        assert result["feedback"]["code"] == ("blocked" if version == 1 else "reason_required")
        assert business_state(result) == business_state(before)
        result = domain.step({"type": "close", "reason": "Reviewed"})
        assert result["feedback"]["code"] == "blocked"
        assert business_state(result) == business_state(before)


def test_close_version_two_requires_reason_and_success_clears_selection():
    for version in (1, 2):
        domain = IssueDomain(version=version)
        ids = pick(domain, status="open", blocked=False)
        select(domain, ids)
        result = domain.step({"type": "close", "reason": "  "})
        if version == 2:
            assert result["feedback"]["code"] == "reason_required"
            result = domain.step({"type": "close", "reason": "Done"})
        assert result["feedback"] == {"ok": True, "code": "ok"}
        assert result["selected"] == []
        assert all(row["status"] == "closed" for row in result["issues"] if row["id"] in ids)


def test_reopen_rejects_mixed_batch_atomically_then_reopens_closed_batch():
    domain = IssueDomain()
    closed = pick(domain, status="closed")
    mixed = closed + pick(domain, status="open")[:1]
    before = select(domain, mixed)
    result = domain.step({"type": "reopen"})
    assert result["feedback"]["code"] == "not_all_closed"
    assert business_state(result) == business_state(before)
    select(domain, closed)
    result = domain.step({"type": "reopen"})
    assert result["feedback"]["ok"]
    assert result["selected"] == []
    assert all(row["status"] == "open" for row in result["issues"] if row["id"] in closed)


def test_label_is_idempotent_and_comment_is_not():
    domain = IssueDomain()
    chosen = domain.observe()["visible_ids"][:2]
    select(domain, chosen)
    first = domain.step({"type": "label", "value": "reviewed"})
    assert domain.step({"type": "label", "value": "reviewed"}) == first
    for _ in range(2):
        result = domain.step({"type": "comment", "text": "Reviewed"})
    assert result["selected"] == chosen
    assert all(row["comments"] == ["Reviewed", "Reviewed"] for row in result["issues"]
               if row["id"] in chosen)
    assert all(row["labels"] == sorted(set(row["labels"])) for row in result["issues"])


def test_invalid_actions_and_empty_comment_never_change_business_state():
    domain = IssueDomain()
    domain.step({"type": "select_all"})
    for action in (None, {}, {"type": "unknown"}, {"type": "sort", "direction": "up"},
                   {"type": "filter", "status": "unknown"}, {"type": "select", "ids": [True]},
                   {"type": "label", "value": " "}):
        before = domain.observe()
        result = domain.step(action)
        assert result["feedback"]["code"] == "invalid_action"
        assert business_state(result) == business_state(before)
    for text in ("", "  ", None):
        before = domain.observe()
        result = domain.step({"type": "comment", "text": text})
        assert result["feedback"]["code"] == "empty_comment"
        assert business_state(result) == business_state(before)


def test_from_observation_restores_state_and_future_behavior_without_aliasing():
    domain = IssueDomain(103, version=2)
    domain.step({"type": "select_all"})
    domain.step({"type": "filter", "status": "open"})
    domain.step({"type": "sort", "direction": "desc"})
    domain.step({"type": "comment", "text": "History"})
    observation = domain.observe()
    restored = IssueDomain.from_observation(observation, version=2)
    assert restored.observe() == observation
    for action in ({"type": "close"}, {"type": "label", "value": "shared"},
                   {"type": "filter", "status": "closed"}, {"type": "select_all"},
                   {"type": "reopen"}):
        assert restored.step(action) == domain.step(action)
    observation["issues"][0]["title"] = "Changed outside"
    assert restored.observe()["issues"][0]["title"] != "Changed outside"


def test_filter_does_not_mutate_full_public_issue_list():
    domain = IssueDomain(48, version=2)
    initial_issues = deepcopy(domain.observe()["issues"])
    domain.step({"type": "select_all"})
    for status in ("closed", "open", "all"):
        observation = domain.step({"type": "filter", "status": status})
        assert observation["issues"] == initial_issues
        assert set(observation["selected"]) <= set(observation["visible_ids"])
