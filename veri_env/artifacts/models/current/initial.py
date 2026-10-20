"""Evidence notes for the inferred issue-management transition model.

Observed: sort changes sort and visible_ids; visible IDs follow numeric issue-ID
order in either direction. Filtering uses status and label and clears selection.
Select keeps requested IDs that exist; select_all takes visible IDs. Successful
label, close, reopen, and comment operations affect selected records. Labels are
appended without replacing existing labels. Successful close/reopen clears
selection. A close touching a blocked issue fails atomically; reopen with any
selected non-closed issue fails atomically. Empty close and viewer label attempts
fail with the observed feedback codes.

Uncertainties: permission behavior beyond the observed viewer label case,
feedback reset behavior after a later successful action, duplicate selections,
invalid action values, close reasons, and any semantics not represented in the
provided examples are not established. The model preserves unobserved fields.
"""
import copy


def _visible_ids(state, filter_value=None, direction=None):
    filt = filter_value if filter_value is not None else state.get("filter", {})
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
    # The examples establish numeric ID order for both sort directions.
    visible.sort(reverse=(direction if direction is not None else state.get("sort", "asc")) == "desc")
    return visible


def _feedback(state, ok, code):
    state["feedback"] = {"ok": ok, "code": code}


def predict(state: dict, action: dict) -> dict:
    """Return a deep-copied observation after one evidence-based transition."""
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
        known = {issue.get("id") for issue in nxt.get("issues", [])}
        selected = []
        for issue_id in action.get("ids", []):
            if issue_id in known and issue_id not in selected:
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
        _feedback(nxt, False, "permission_denied")
        return nxt
    if not selected:
        _feedback(nxt, False, "empty_selection")
        return nxt

    by_id = {issue.get("id"): issue for issue in nxt.get("issues", [])}
    targets = [by_id[i] for i in selected if i in by_id]

    if kind == "close":
        if any(issue.get("blocked", False) for issue in targets):
            _feedback(nxt, False, "blocked")
            return nxt
        for issue in targets:
            issue["status"] = "closed"
        nxt["selected"] = []
        return nxt

    if kind == "reopen":
        if any(issue.get("status") != "closed" for issue in targets):
            _feedback(nxt, False, "not_all_closed")
            return nxt
        for issue in targets:
            issue["status"] = "open"
        nxt["selected"] = []
        return nxt

    if kind == "label":
        value = action.get("value", "")
        for issue in targets:
            labels = issue.setdefault("labels", [])
            if value not in labels:
                labels.append(value)
        return nxt

    text = action.get("text", "")
    for issue in targets:
        issue.setdefault("comments", []).append(text)
    return nxt
