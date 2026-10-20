"""Behavior inferred from the supplied transition examples.

Uncertainty: filter fields not supplied by an action are preserved; permission
checks are generalized to all record-mutating actions. Close reasons are required
and checked for non-whitespace content; their persistence is not visible.
"""

from copy import deepcopy


def predict(state: dict, action: dict) -> dict:
    """Return the next complete observation without mutating the arguments."""
    out = deepcopy(state)
    kind = action.get("type")

    def refresh_visible():
        filt = out.get("filter", {})
        status = filt.get("status", "all")
        label = filt.get("label", "")
        rows = []
        for issue in out.get("issues", []):
            if status != "all" and issue.get("status") != status:
                continue
            if label and label not in issue.get("labels", []):
                continue
            rows.append(issue)
        rows.sort(key=lambda row: row.get("id"), reverse=out.get("sort", "asc") == "desc")
        out["visible_ids"] = [row.get("id") for row in rows]

    if kind == "sort":
        out["sort"] = action.get("direction", out.get("sort", "asc"))
        refresh_visible()
        return out

    if kind == "filter":
        filt = deepcopy(out.get("filter", {"status": "all", "label": ""}))
        if "status" in action:
            filt["status"] = action["status"]
        if "label" in action:
            filt["label"] = action["label"]
        out["filter"] = filt
        refresh_visible()
        visible = set(out.get("visible_ids", []))
        out["selected"] = [i for i in out.get("selected", []) if i in visible]
        return out

    if kind == "select":
        visible = set(out.get("visible_ids", []))
        selected = []
        for issue_id in action.get("ids", []):
            if issue_id in visible and issue_id not in selected:
                selected.append(issue_id)
        out["selected"] = selected
        return out

    if kind == "select_all":
        out["selected"] = list(out.get("visible_ids", []))
        return out

    if kind not in {"label", "close", "reopen", "comment"}:
        return out

    def fail(code):
        out["feedback"] = {"ok": False, "code": code}
        return out

    if out.get("role") != "editor":
        return fail("permission_denied")

    selected = list(out.get("selected", []))
    if not selected:
        return fail("empty_selection")

    by_id = {issue.get("id"): issue for issue in out.get("issues", [])}
    targets = [by_id[i] for i in selected if i in by_id]

    if kind == "close" and not action.get("reason", "").strip():
        return fail("reason_required")
    if kind == "close" and any(issue.get("blocked", False) for issue in targets):
        return fail("blocked")
    if kind == "reopen" and any(issue.get("status") != "closed" for issue in targets):
        return fail("not_all_closed")

    if kind == "label":
        value = action.get("value", "").strip()
        for issue in targets:
            labels = issue.setdefault("labels", [])
            if value not in labels:
                labels.append(value)
    elif kind == "comment":
        text = action.get("text", "").strip()
        if not text:
            return fail("empty_comment")
        for issue in targets:
            issue.setdefault("comments", []).append(text)
    elif kind == "close":
        for issue in targets:
            issue["status"] = "closed"
        out["selected"] = []
    elif kind == "reopen":
        for issue in targets:
            issue["status"] = "open"
        out["selected"] = []

    out["feedback"] = {"ok": True, "code": "ok"}
    refresh_visible()
    return out
