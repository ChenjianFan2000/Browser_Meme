"""Deterministic issue-board transition model adapted to recent evidence.

The model retains the observed filtering, sorting, selection, labeling, comment,
permission, blocked-close, and all-closed-reopen rules. Filtering now retains
the portion of the prior selection that remains visible. Closing requires a
nonblank reason; a successful close changes status and clears selection, while
the reason itself is not recorded in the visible issue fields. Labels are
stripped before addition, duplicates are avoided, and whitespace-only comments
fail with ``empty_comment``. Failed actions change feedback only.

Uncertainty: the new evidence does not establish validation precedence when a
close has multiple simultaneous problems, whether successful nonempty comments
are stored trimmed, or the ordering of retained selections when sort changes.
This model checks permission and nonempty selection before the required close
reason, and keeps surviving selection IDs in their prior order. It models one
transition and makes no claim to implement a search procedure.
"""

from copy import deepcopy


def _visible(state):
    issues = state.get("issues", [])
    filt = state.get("filter", {})
    status = filt.get("status", "all")
    label = filt.get("label", "")
    matches = []
    for issue in issues:
        if status not in (None, "all") and issue.get("status") != status:
            continue
        if label and label not in issue.get("labels", []):
            continue
        matches.append(issue.get("id"))
    matches.sort(reverse=state.get("sort", "asc") == "desc")
    return matches


def _feedback(state, ok, code):
    state["feedback"] = {"ok": ok, "code": code}
    return state


def predict(state: dict, action: dict) -> dict:
    """Return the complete next observation without mutating either input."""
    nxt = deepcopy(state)
    action = action or {}
    kind = action.get("type")

    if kind == "filter":
        old = nxt.get("filter", {})
        nxt["filter"] = {
            "status": action.get("status", old.get("status", "all")),
            "label": action.get("label", old.get("label", "")),
        }
        nxt["visible_ids"] = _visible(nxt)
        visible = set(nxt["visible_ids"])
        nxt["selected"] = [
            issue_id for issue_id in nxt.get("selected", [])
            if issue_id in visible
        ]
        return nxt

    if kind == "sort":
        nxt["sort"] = action.get("direction", nxt.get("sort", "asc"))
        nxt["visible_ids"] = _visible(nxt)
        return nxt

    if kind == "select":
        wanted = action.get("ids", []) or []
        wanted_set = set(wanted)
        nxt["selected"] = [
            issue_id for issue_id in nxt.get("visible_ids", [])
            if issue_id in wanted_set
        ]
        return nxt

    if kind == "select_all":
        nxt["selected"] = list(nxt.get("visible_ids", []))
        return nxt

    if kind not in {"label", "close", "reopen", "comment"}:
        return _feedback(nxt, False, "invalid_action")

    if nxt.get("role") != "editor":
        return _feedback(nxt, False, "permission_denied")

    selected = list(nxt.get("selected", []))
    if not selected:
        return _feedback(nxt, False, "empty_selection")

    by_id = {issue.get("id"): issue for issue in nxt.get("issues", [])}
    selected_issues = [by_id[i] for i in selected if i in by_id]

    if kind == "close":
        reason = action.get("reason", "")
        if not isinstance(reason, str) or not reason.strip():
            return _feedback(nxt, False, "reason_required")
        if any(issue.get("blocked", False) for issue in selected_issues):
            return _feedback(nxt, False, "blocked")
        for issue in selected_issues:
            issue["status"] = "closed"
        nxt["selected"] = []
        return nxt

    if kind == "reopen":
        if any(issue.get("status") != "closed" for issue in selected_issues):
            return _feedback(nxt, False, "not_all_closed")
        for issue in selected_issues:
            issue["status"] = "open"
        nxt["selected"] = []
        return nxt

    if kind == "label":
        value = action.get("value", "")
        value = value.strip() if isinstance(value, str) else value
        for issue in selected_issues:
            labels = issue.setdefault("labels", [])
            if value not in labels:
                labels.append(value)
        return nxt

    text = action.get("text", "")
    normalized_text = text.strip() if isinstance(text, str) else text
    if not normalized_text:
        return _feedback(nxt, False, "empty_comment")
    for issue in selected_issues:
        issue.setdefault("comments", []).append(normalized_text)
    return nxt
