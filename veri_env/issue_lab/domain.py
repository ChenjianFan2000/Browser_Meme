"""Fully observable miniature issue workflow; this is not GitLab.

IssueDomain(seed=0, version=1, role='editor') exposes reset(), observe(), and
step(action). All returned observations are independent deep copies. Observations
contain issues, filter, sort, selected, role, feedback, and visible_ids.
Every issue is public, including filtered-out rows, with id, title, status
('open'/'closed'), labels, blocked, priority (1..3), and comments. Issues, labels,
and selected IDs are canonically sorted; comments retain insertion order.
visible_ids follows the current id sort ('asc'/'desc'). No hidden issue state
affects transitions within a fixed rule version. The rule version is supplied by
the evaluator and is not in observations. from_observation(obs, version=1)
reconstructs the public business state under an explicitly chosen rule version.

Actions use a 'type' key:
  filter(status='all'|'open'|'closed', label=''): replace the filter. Version 1
    clears selection; version 2 retains only selected IDs still visible.
  sort(direction='asc'|'desc'): change row order, preserving selection.
  select(ids=[...]): replace selection with the intersection with visible IDs.
  select_all: select all visible IDs.
  label(value=nonempty string): add a label to selected issues, without repeats.
  close(reason=optional string): close the batch and clear selection. Version 2
    requires a nonblank reason. Any blocked issue rejects the whole batch.
  reopen: require every selected issue closed, then open and clear selection.
  comment(text=nonempty string): append to all selected issues; repeats allowed.
Label and comment preserve selection. Mutation checks are ordered: editor role,
nonempty selection, operation-specific validation, then blocked for close.
Every transition sets feedback {ok: bool, code: str}; codes are 'ok',
'permission_denied', 'empty_selection', 'blocked', 'reason_required',
'not_all_closed', 'empty_comment', and 'invalid_action'. Rejected actions are
atomic: only feedback changes. Invalid action shapes yield 'invalid_action'.
"""

from __future__ import annotations

from copy import deepcopy
import random
from typing import Any


class IssueDomain:
    """Deterministic public-state simulator for controlled workflow experiments."""

    def __init__(self, seed: int = 0, version: int = 1, role: str = "editor"):
        self.seed = seed
        self.version = version
        self.role = role
        self.reset()

    def reset(self, seed: int | None = None, version: int | None = None,
              role: str | None = None) -> dict[str, Any]:
        seed = self.seed if seed is None else seed
        version = self.version if version is None else version
        role = self.role if role is None else role
        if type(seed) is not int or type(version) is not int or version not in (1, 2):
            raise ValueError("seed must be an integer and version must be 1 or 2")
        if role not in ("editor", "viewer"):
            raise ValueError("role must be editor or viewer")
        self.seed, self.version, self.role = seed, version, role
        rng = random.Random(seed)
        ids = rng.sample(range(100, 1000), 6)
        subjects = rng.sample(["Export report", "Search indexing", "Profile settings",
                               "Email alerts", "Archive cleanup", "Import records",
                               "Access review", "Activity history", "Table layout"], 6)
        statuses = ["open", "open", "open", "closed", rng.choice(["open", "closed"]),
                    rng.choice(["open", "closed"])]
        self.issues = []
        for i, issue_id in enumerate(ids):
            self.issues.append({"id": issue_id, "title": subjects[i],
                                "status": statuses[i],
                                "labels": sorted(rng.sample(["bug", "docs", "feature"],
                                                            rng.randint(0, 2))),
                                "blocked": i == 2,
                                "priority": rng.randint(1, 3), "comments": []})
        self.issues.sort(key=lambda issue: issue["id"])
        self.filter = {"status": "all", "label": ""}
        self.sort = "asc"
        self.selected: list[int] = []
        self.feedback = {"ok": True, "code": "ok"}
        return self.observe()

    @classmethod
    def from_observation(cls, observation: dict[str, Any],
                         version: int = 1) -> "IssueDomain":
        """Restore transition state from public data; seed only controls reset()."""
        domain = cls(version=version, role=observation["role"])
        domain.issues = deepcopy(observation["issues"])
        domain.issues.sort(key=lambda issue: issue["id"])
        for issue in domain.issues:
            issue["labels"] = sorted(set(issue["labels"]))
        domain.filter = deepcopy(observation["filter"])
        domain.sort = observation["sort"]
        domain.selected = sorted(set(observation["selected"]))
        domain.feedback = deepcopy(observation["feedback"])
        return domain

    def _visible_ids(self) -> list[int]:
        return sorted((issue["id"] for issue in self.issues
                       if (self.filter["status"] == "all"
                           or issue["status"] == self.filter["status"])
                       and (not self.filter["label"]
                            or self.filter["label"] in issue["labels"])),
                      reverse=self.sort == "desc")

    def observe(self) -> dict[str, Any]:
        return deepcopy({"issues": self.issues,
                         "filter": self.filter, "sort": self.sort,
                         "selected": self.selected, "role": self.role,
                         "feedback": self.feedback, "visible_ids": self._visible_ids()})

    def _result(self, code: str = "ok") -> dict[str, Any]:
        self.feedback = {"ok": code == "ok", "code": code}
        return self.observe()

    def step(self, action: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(action, dict) or not isinstance(action.get("type"), str):
            return self._result("invalid_action")
        kind = action["type"]
        if kind == "filter":
            status, label = action.get("status", "all"), action.get("label", "")
            if status not in ("all", "open", "closed") or not isinstance(label, str):
                return self._result("invalid_action")
            self.filter = {"status": status, "label": label}
            self.selected = ([] if self.version == 1 else
                             sorted(set(self.selected).intersection(self._visible_ids())))
        elif kind == "sort":
            if action.get("direction") not in ("asc", "desc"):
                return self._result("invalid_action")
            self.sort = action["direction"]
        elif kind == "select":
            ids = action.get("ids")
            if not isinstance(ids, list) or any(type(i) is not int for i in ids):
                return self._result("invalid_action")
            self.selected = sorted(set(ids).intersection(self._visible_ids()))
        elif kind == "select_all":
            self.selected = sorted(self._visible_ids())
        elif kind in ("label", "close", "reopen", "comment"):
            if self.role != "editor":
                return self._result("permission_denied")
            if not self.selected:
                return self._result("empty_selection")
            selected = set(self.selected)
            rows = [issue for issue in self.issues if issue["id"] in selected]
            if kind == "label":
                value = action.get("value")
                if not isinstance(value, str) or not value.strip():
                    return self._result("invalid_action")
                for issue in rows:
                    issue["labels"] = sorted(set(issue["labels"]) | {value.strip()})
            elif kind == "close":
                reason = action.get("reason", "")
                if self.version == 2 and (not isinstance(reason, str) or not reason.strip()):
                    return self._result("reason_required")
                if any(issue["blocked"] for issue in rows):
                    return self._result("blocked")
                for issue in rows:
                    issue["status"] = "closed"
                self.selected = []
            elif kind == "reopen":
                if any(issue["status"] != "closed" for issue in rows):
                    return self._result("not_all_closed")
                for issue in rows:
                    issue["status"] = "open"
                self.selected = []
            elif kind == "comment":
                value = action.get("text")
                if not isinstance(value, str) or not value.strip():
                    return self._result("empty_comment")
                for issue in rows:
                    issue["comments"].append(value)
        else:
            return self._result("invalid_action")
        return self._result()
