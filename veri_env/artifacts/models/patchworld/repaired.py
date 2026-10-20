"""PatchWorld deterministic transition model, repaired from development evidence.

Inferred transition rules:
- Visible issue IDs are filtered by status (all/open/closed) and exact label,
  then sorted numerically according to the current direction.
- filter updates supplied dimensions, retains omitted ones, recalculates visible
  IDs, and clears selection. sort recalculates visible IDs. select intersects
  requested IDs with visible IDs; select_all selects every visible ID.
- label strips surrounding whitespace from its value, then adds it to selected
  issues only when it is not already present. comment appends the original text
  to selected issues. A comment containing only whitespace fails with
  feedback={ok: false, code: "empty_comment"} and leaves issues and selection
  untouched.
- Write actions are denied to viewers. Empty selections fail with
  empty_selection. close fails atomically if any selected issue is blocked;
  otherwise it closes all selected issues and clears selection. reopen requires
  every selected issue to be closed; success opens them and clears selection.
- Other observation fields are preserved. Successful actions set feedback to
  {ok: true, code: "ok"}.

Uncertainty: evidence does not specify close(reason=...), invalid action values,
all failure precedence combinations, or behavior for non-string label/comment
payloads. A close reason is ignored because no destination field or effect is
shown. Invalid/unobserved inputs use conservative no-op behavior.
"""
from copy import deepcopy


def predict(state: dict, action: dict) -> dict:
    """Return the complete next observation after one action."""
    out = deepcopy(state)
    issues = out.get("issues", [])
    by_id = {issue.get("id"): issue for issue in issues}
    current_filter = out.get("filter", {}) or {}
    sort_direction = out.get("sort", "asc")
    visible = list(out.get("visible_ids", []))
    selected = list(out.get("selected", []))
    role = out.get("role", "editor")
    action = action or {}
    kind = action.get("type")

    def filtered_ids(filter_value=None, direction=None):
        f = current_filter if filter_value is None else filter_value
        status = f.get("status", "all")
        label = f.get("label", "")
        if status not in ("all", "open", "closed"):
            return []
        rows = []
        for issue in issues:
            if status != "all" and issue.get("status") != status:
                continue
            if label and label not in (issue.get("labels") or []):
                continue
            rows.append(issue.get("id"))
        reverse = (sort_direction if direction is None else direction) == "desc"
        try:
            return sorted(rows, reverse=reverse)
        except TypeError:
            return sorted(rows, key=lambda value: str(value), reverse=reverse)

    def set_feedback(ok=True, code="ok"):
        out["feedback"] = {"ok": ok, "code": code}

    def selected_issues():
        return [by_id[issue_id] for issue_id in selected if issue_id in by_id]

    if kind == "filter":
        new_filter = deepcopy(current_filter)
        if "status" in action:
            new_filter["status"] = action["status"]
        if "label" in action:
            new_filter["label"] = action["label"]
        out["filter"] = new_filter
        out["selected"] = []
        out["visible_ids"] = filtered_ids(new_filter)
        set_feedback()
    elif kind == "sort":
        direction = action.get("direction", sort_direction)
        if direction in ("asc", "desc"):
            out["sort"] = direction
            out["visible_ids"] = filtered_ids(direction=direction)
            set_feedback()
    elif kind == "select":
        requested_set = set(action.get("ids", []) or [])
        out["selected"] = [issue_id for issue_id in visible if issue_id in requested_set]
        set_feedback()
    elif kind == "select_all":
        out["selected"] = list(visible)
        set_feedback()
    elif kind in ("label", "comment", "close", "reopen"):
        if role == "viewer":
            set_feedback(False, "permission_denied")
            return out
        targets = selected_issues()
        if not targets:
            set_feedback(False, "empty_selection")
            return out
        if kind == "close":
            if any(issue.get("blocked", False) for issue in targets):
                set_feedback(False, "blocked")
                return out
            for issue in targets:
                issue["status"] = "closed"
            out["selected"] = []
        elif kind == "reopen":
            if any(issue.get("status") != "closed" for issue in targets):
                set_feedback(False, "not_all_closed")
                return out
            for issue in targets:
                issue["status"] = "open"
            out["selected"] = []
        elif kind == "label":
            value = action.get("value", "")
            if isinstance(value, str):
                value = value.strip()
            for issue in targets:
                labels = list(issue.get("labels") or [])
                if value not in labels:
                    labels.append(value)
                issue["labels"] = labels
        else:
            value = action.get("text", "")
            if isinstance(value, str) and not value.strip():
                set_feedback(False, "empty_comment")
                return out
            for issue in targets:
                comments = list(issue.get("comments") or [])
                comments.append(value)
                issue["comments"] = comments
        set_feedback()
    return out
