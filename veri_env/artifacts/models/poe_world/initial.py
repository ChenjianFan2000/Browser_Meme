"""Deterministic issue-management experts inferred from the initial examples.

Evidence supports sorting and filtering the visible issue list, selecting only
visible IDs, additive labels and comments on selected records, closing selected
unblocked issues, and reopening only an all-closed selection. Viewer label
changes are denied; the examples do not directly establish permission rules for
the other write actions. For those, this model applies the same editor guard.
The examples do not show close-on-closed, empty write selections except close,
duplicate labels, comments on records with prior comments, or filters with a
nonempty label; behavior for these cases follows the simplest consistent rules.
This is a deterministic rule model, not a fitted probabilistic product of
experts.
"""

import copy


_WRITE_ACTIONS = {"label", "close", "reopen", "comment"}


def _visible_ids(state):
    filt = state.get("filter", {})
    status = filt.get("status", "all")
    label = filt.get("label", "")
    issues = state.get("issues", [])
    visible = []
    for issue in issues:
        if status != "all" and issue.get("status") != status:
            continue
        if label and label not in issue.get("labels", []):
            continue
        visible.append(issue.get("id"))
    visible.sort(reverse=state.get("sort", "asc") == "desc")
    return visible


def _feedback(state, ok, code):
    state["feedback"] = {"ok": ok, "code": code}


def predict(state: dict, action: dict) -> dict:
    """Return the complete predicted next observation without mutating inputs."""
    result = copy.deepcopy(state)
    action_type = action.get("type")

    if action_type == "sort":
        result["sort"] = action.get("direction", result.get("sort", "asc"))
        result["visible_ids"] = _visible_ids(result)
        _feedback(result, True, "ok")
        return result

    if action_type == "filter":
        previous = result.get("filter", {})
        result["filter"] = {
            "status": action.get("status", previous.get("status", "all")),
            "label": action.get("label", previous.get("label", "")),
        }
        result["selected"] = []
        result["visible_ids"] = _visible_ids(result)
        _feedback(result, True, "ok")
        return result

    if action_type == "select":
        visible = set(result.get("visible_ids", []))
        selected = []
        seen = set()
        for issue_id in action.get("ids", []):
            if issue_id in visible and issue_id not in seen:
                selected.append(issue_id)
                seen.add(issue_id)
        result["selected"] = selected
        _feedback(result, True, "ok")
        return result

    if action_type == "select_all":
        result["selected"] = list(result.get("visible_ids", []))
        _feedback(result, True, "ok")
        return result

    if action_type not in _WRITE_ACTIONS:
        return result

    # The sole direct permission example is a viewer attempting to add a label.
    if result.get("role") == "viewer":
        _feedback(result, False, "permission_denied")
        return result

    selected = list(result.get("selected", []))
    if not selected:
        _feedback(result, False, "empty_selection")
        return result

    by_id = {issue.get("id"): issue for issue in result.get("issues", [])}
    selected_issues = [by_id[i] for i in selected if i in by_id]

    if action_type == "close":
        if any(issue.get("blocked", False) for issue in selected_issues):
            _feedback(result, False, "blocked")
            return result
        if any(issue.get("status") != "open" for issue in selected_issues):
            _feedback(result, False, "not_all_open")
            return result
        for issue in selected_issues:
            issue["status"] = "closed"
        result["selected"] = []

    elif action_type == "reopen":
        if any(issue.get("status") != "closed" for issue in selected_issues):
            _feedback(result, False, "not_all_closed")
            return result
        for issue in selected_issues:
            issue["status"] = "open"
        result["selected"] = []

    elif action_type == "label":
        value = action.get("value", "")
        for issue in selected_issues:
            labels = list(issue.get("labels", []))
            if value not in labels:
                labels.append(value)
            issue["labels"] = labels

    elif action_type == "comment":
        text = action.get("text", "")
        for issue in selected_issues:
            comments = list(issue.get("comments", []))
            comments.append(text)
            issue["comments"] = comments

    result["visible_ids"] = _visible_ids(result)
    _feedback(result, True, "ok")
    return result
