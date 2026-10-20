"""Issue-list transition model adapted to the latest observed rule changes.

Labels are stripped before insertion; whitespace-only comments fail with
empty_comment. Filtering now retains selected IDs that remain visible. Closing
requires a nonblank reason after empty-selection and blocked checks; the reason is
not stored in the visible issue record. Other unobserved permission and validation
precedence combinations remain uncertain.
"""
import copy


def predict(state: dict, action: dict) -> dict:
    """Return the complete next observation after one issue-management action."""
    out = copy.deepcopy(state)
    action_type = action.get("type")
    issues = out.get("issues", [])
    by_id = {issue.get("id"): issue for issue in issues}

    def visible_ids():
        filt = out.get("filter", {})
        status = filt.get("status", "all")
        label = filt.get("label", "")
        rows = []
        for issue in issues:
            if status not in (None, "all") and issue.get("status") != status:
                continue
            if label and label not in issue.get("labels", []):
                continue
            rows.append(issue)
        rows.sort(key=lambda row: row.get("id"), reverse=out.get("sort", "asc") == "desc")
        return [row.get("id") for row in rows]

    def success():
        out["feedback"] = {"ok": True, "code": "ok"}

    def fail(code):
        out["feedback"] = {"ok": False, "code": code}

    def refresh_visible():
        out["visible_ids"] = visible_ids()

    if action_type == "sort":
        out["sort"] = action.get("direction", out.get("sort", "asc"))
        refresh_visible()
        success()
    elif action_type == "filter":
        filt = copy.deepcopy(out.get("filter", {}))
        if "status" in action:
            filt["status"] = action["status"]
        if "label" in action:
            filt["label"] = action["label"]
        out["filter"] = filt
        refresh_visible()
        visible = set(out["visible_ids"])
        out["selected"] = [i for i in out.get("selected", []) if i in visible]
        success()
    elif action_type == "select":
        available = set(out.get("visible_ids", visible_ids()))
        chosen = []
        for issue_id in action.get("ids", []):
            if issue_id in available and issue_id not in chosen:
                chosen.append(issue_id)
        out["selected"] = chosen
        success()
    elif action_type == "select_all":
        out["selected"] = list(out.get("visible_ids", visible_ids()))
        success()
    elif action_type in ("label", "close", "reopen", "comment"):
        # Viewer denial is observed for label and generalized to issue mutations.
        if out.get("role") == "viewer":
            fail("permission_denied")
            return out
        selected = list(out.get("selected", []))
        if not selected:
            fail("empty_selection")
            return out
        targets = [by_id[i] for i in selected if i in by_id]
        if action_type == "close":
            # Retain established error precedence for empty and blocked selections.
            if any(issue.get("blocked", False) for issue in targets):
                fail("blocked")
                return out
            reason = action.get("reason")
            if not isinstance(reason, str) or not reason.strip():
                fail("reason_required")
                return out
            for issue in targets:
                if issue.get("status") != "closed":
                    issue["status"] = "closed"
            out["selected"] = []
            refresh_visible()
            success()
        elif action_type == "reopen":
            if any(issue.get("status") != "closed" for issue in targets):
                fail("not_all_closed")
                return out
            for issue in targets:
                issue["status"] = "open"
            out["selected"] = []
            refresh_visible()
            success()
        elif action_type == "label":
            value = action.get("value", "")
            value = value.strip() if isinstance(value, str) else value
            for issue in targets:
                labels = list(issue.get("labels", []))
                if value not in labels:
                    labels.append(value)
                    issue["labels"] = labels
            refresh_visible()
            success()
        else:  # comment
            text = action.get("text", "")
            if not isinstance(text, str) or not text.strip():
                fail("empty_comment")
                return out
            for issue in targets:
                comments = list(issue.get("comments", []))
                comments.append(text)
                issue["comments"] = comments
            success()
    return out
