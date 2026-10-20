"""Reusable deterministic model of the observed issue-management workflow.

Visible issues are filtered by exact status and label membership and sorted by
numeric id. Selection is restricted to visible ids; applying a filter now
retains the previously selected ids that remain visible. Editors can mutate
selected issues. Closing requires a nonblank reason and is rejected when any
selected issue is blocked. Reopening requires every selected issue to be
closed. Labels are trimmed before insertion, and whitespace-only comments fail
with ``empty_comment``.

Uncertainty: the traces do not establish precedence between close-reason and
blocked validation, so a blocked close continues to report ``blocked`` first.
They also do not show whether the reason is stored elsewhere; observed successful
closes change only status. Unknown actions preserve the observation.
"""

from copy import deepcopy
from typing import Any


def _visible_ids(
    state: dict[str, Any], filter_value: dict[str, Any], sort_value: str
) -> list[int]:
    status = filter_value.get("status", "all")
    label = filter_value.get("label", "")
    matching = []
    for issue in state.get("issues", []):
        if status in ("open", "closed") and issue.get("status") != status:
            continue
        if label and label not in issue.get("labels", []):
            continue
        matching.append(issue.get("id"))
    matching.sort(reverse=(sort_value == "desc"))
    return matching


def predict(state: dict, action: dict) -> dict:
    """Return the complete next observation after one action."""
    result = deepcopy(state)
    action_type = action.get("type")

    if action_type == "filter":
        old_filter = result.get("filter", {})
        new_filter = {
            "status": action.get("status", old_filter.get("status", "all")),
            "label": action.get("label", old_filter.get("label", "")),
        }
        result["filter"] = new_filter
        visible_ids = _visible_ids(result, new_filter, result.get("sort", "asc"))
        visible_set = set(visible_ids)
        result["selected"] = [
            issue_id
            for issue_id in result.get("selected", [])
            if issue_id in visible_set
        ]
        result["visible_ids"] = visible_ids
        result["feedback"] = {"ok": True, "code": "ok"}
        return result

    if action_type == "sort":
        direction = action.get("direction", result.get("sort", "asc"))
        result["sort"] = direction
        result["visible_ids"] = _visible_ids(
            result, result.get("filter", {}), direction
        )
        result["feedback"] = {"ok": True, "code": "ok"}
        return result

    visible = result.get("visible_ids", [])
    if action_type == "select":
        allowed = set(visible)
        selected = []
        for issue_id in action.get("ids", []):
            if issue_id in allowed and issue_id not in selected:
                selected.append(issue_id)
        result["selected"] = selected
        result["feedback"] = {"ok": True, "code": "ok"}
        return result

    if action_type == "select_all":
        result["selected"] = list(visible)
        result["feedback"] = {"ok": True, "code": "ok"}
        return result

    if action_type not in {"label", "close", "reopen", "comment"}:
        return result

    if result.get("role") != "editor":
        result["feedback"] = {"ok": False, "code": "permission_denied"}
        return result

    selected = list(result.get("selected", []))
    if not selected:
        result["feedback"] = {"ok": False, "code": "empty_selection"}
        return result

    by_id = {issue.get("id"): issue for issue in result.get("issues", [])}
    selected_issues = [by_id[item] for item in selected if item in by_id]

    if action_type == "comment" and not action.get("text", "").strip():
        result["feedback"] = {"ok": False, "code": "empty_comment"}
        return result

    if action_type == "close" and any(
        issue.get("blocked") is True for issue in selected_issues
    ):
        result["feedback"] = {"ok": False, "code": "blocked"}
        return result
    if action_type == "close" and not action.get("reason", "").strip():
        result["feedback"] = {"ok": False, "code": "reason_required"}
        return result
    if action_type == "reopen" and any(
        issue.get("status") != "closed" for issue in selected_issues
    ):
        result["feedback"] = {"ok": False, "code": "not_all_closed"}
        return result

    for issue in selected_issues:
        if action_type == "label":
            value = action.get("value", "").strip()
            labels = list(issue.get("labels", []))
            if value and value not in labels:
                labels.append(value)
                issue["labels"] = labels
        elif action_type == "close":
            issue["status"] = "closed"
        elif action_type == "reopen":
            issue["status"] = "open"
        elif action_type == "comment":
            comments = list(issue.get("comments", []))
            comments.append(action.get("text", ""))
            issue["comments"] = comments

    if action_type in {"close", "reopen"}:
        result["selected"] = []
    result["feedback"] = {"ok": True, "code": "ok"}
    return result
