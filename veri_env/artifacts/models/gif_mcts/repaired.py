"""Deterministic issue-board transition model inferred from the supplied examples.

Observed rules: filtering matches status and (when nonempty) label, and clears
selection; sorting reorders visible IDs by issue ID; selection is constrained to
visible issues. Editor mutations apply to selected issues. Labels are stripped
of surrounding whitespace before being added and duplicates are avoided.
Comments containing only whitespace fail with ``empty_comment`` and leave issue
records untouched; nonempty comments append. Close is atomic and rejects a
selection containing a blocked issue, while reopen requires every selected issue
to be closed. Viewer labeling is denied. Failed actions change feedback only.

Uncertainty: examples do not exercise invalid action parameters, missing or
empty selections for every mutation, non-editor permissions for every mutation,
all combinations of preexisting comments/labels, or close/reopen of mixed
already-transitioned statuses. Optional close reasons have no evidenced effect.
For a nonempty comment the model trims surrounding whitespace, a conservative
normalization inferred from the whitespace-only rejection. This models a single
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
        nxt["selected"] = []
        nxt["visible_ids"] = _visible(nxt)
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
