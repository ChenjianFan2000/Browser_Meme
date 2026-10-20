"""Observed issue tracker transition rules.

Visible IDs are filtered by status and label, then sorted by numeric ID; select
keeps only currently visible requested IDs in request order. Text labels and
comments are stripped before use, and blank comments fail without mutation.
Other observed selection, permission, blocked-close, and reopen checks follow
the prior model. Uncertainty remains for unobserved invalid inputs and failure
precedence when multiple conditions apply.
"""
import copy


def _visible_ids(state, filter_value=None, direction=None):
    filt = filter_value if filter_value is not None else state.get("filter", {})
    status = filt.get("status", "all")
    label = filt.get("label", "")
    result = []
    for issue in state.get("issues", []):
        if status != "all" and issue.get("status") != status:
            continue
        if label and label not in issue.get("labels", []):
            continue
        result.append(issue.get("id"))
    result.sort(reverse=(direction if direction is not None else state.get("sort", "asc")) == "desc")
    return result


def _set_feedback(state, ok, code):
    state["feedback"] = {"ok": ok, "code": code}


def predict(state: dict, action: dict) -> dict:
    """Return the complete next observation without mutating the input."""
    nxt = copy.deepcopy(state)
    kind = action.get("type")

    if kind == "sort":
        direction = action.get("direction", nxt.get("sort", "asc"))
        if direction in ("asc", "desc"):
            nxt["sort"] = direction
            nxt["visible_ids"] = _visible_ids(nxt, direction=direction)
        return nxt

    if kind == "filter":
        old = nxt.get("filter", {})
        filt = {
            "status": action.get("status", old.get("status", "all")),
            "label": action.get("label", old.get("label", "")),
        }
        nxt["filter"] = filt
        nxt["selected"] = []
        nxt["visible_ids"] = _visible_ids(nxt, filter_value=filt)
        return nxt

    if kind == "select":
        visible = set(nxt.get("visible_ids", []))
        selected = []
        for issue_id in action.get("ids", []):
            if issue_id in visible and issue_id not in selected:
                selected.append(issue_id)
        nxt["selected"] = selected
        return nxt

    if kind == "select_all":
        nxt["selected"] = list(nxt.get("visible_ids", []))
        return nxt

    if kind not in ("label", "close", "reopen", "comment"):
        return nxt

    selected = list(nxt.get("selected", []))
    if nxt.get("role") == "viewer":
        _set_feedback(nxt, False, "permission_denied")
        return nxt
    if not selected:
        _set_feedback(nxt, False, "empty_selection")
        return nxt

    by_id = {issue.get("id"): issue for issue in nxt.get("issues", [])}
    targets = [by_id[i] for i in selected if i in by_id]

    if kind == "close":
        if any(issue.get("blocked", False) for issue in targets):
            _set_feedback(nxt, False, "blocked")
            return nxt
        for issue in targets:
            issue["status"] = "closed"
        nxt["selected"] = []
        return nxt

    if kind == "reopen":
        if any(issue.get("status") != "closed" for issue in targets):
            _set_feedback(nxt, False, "not_all_closed")
            return nxt
        for issue in targets:
            issue["status"] = "open"
        nxt["selected"] = []
        return nxt

    if kind == "label":
        value = action.get("value", "")
        value = value.strip() if isinstance(value, str) else value
        for issue in targets:
            labels = issue.setdefault("labels", [])
            if value not in labels:
                labels.append(value)
        return nxt

    comment = action.get("text", "")
    comment = comment.strip() if isinstance(comment, str) else comment
    if not comment:
        _set_feedback(nxt, False, "empty_comment")
        return nxt
    for issue in targets:
        issue.setdefault("comments", []).append(comment)
    return nxt
