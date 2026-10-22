"""Sanitize browser evidence for the registered phase-two observation condition.

This exporter is not an OS sandbox. The runner must separately prevent access to
raw private files and audit the browser interfaces available to the learner.
"""
from __future__ import annotations

from html import escape
from html.parser import HTMLParser
import json
import re

SECRET_KEYS = frozenset({"authorization", "proxy-authorization", "cookie", "set-cookie",
                         "access_token", "refresh_token", "password", "password_hash",
                         "jwt_secret", "client_secret", "token"})
JWT = re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b")
SECRET_CONTROL_SELECTOR = ('input[type="password"], input[name*="password" i], '
                           'input[name*="token" i], input[name*="secret" i]')


def redact(value, *, secrets=()):
    if isinstance(value, dict):
        if str(value.get("name", "")).lower() in SECRET_KEYS:
            return {key: "[REDACTED]" if key == "value" else redact(item, secrets=secrets)
                    for key, item in value.items()}
        return {key: "[REDACTED]" if str(key).lower() in SECRET_KEYS else redact(item, secrets=secrets)
                for key, item in value.items()}
    if isinstance(value, list):
        return [redact(item, secrets=secrets) for item in value]
    if isinstance(value, str):
        value = JWT.sub("[REDACTED-JWT]", value)
        for secret in secrets:
            if secret:
                value = value.replace(secret, "[REDACTED]")
        return value
    return value


class PublicDOM(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.script_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag == "script":
            self.script_depth += 1
            return
        if self.script_depth:
            return
        values = dict(attrs)
        secret_input = tag == "input" and any(
            word in ((values.get("type") or "") + " " + (values.get("name") or "")).lower()
            for word in ("password", "token", "secret")
        )
        public = []
        for key, value in attrs:
            if key.lower().startswith("on") or key.lower() == "srcdoc":
                continue
            if value is not None and value.lstrip().lower().startswith("javascript:"):
                continue
            if secret_input and key.lower() == "value":
                value = "[REDACTED]"
            public.append(key if value is None else key + '="' + escape(redact(value), quote=True) + '"')
        self.parts.append("<" + tag + (" " + " ".join(public) if public else "") + ">")

    def handle_startendtag(self, tag, attrs):
        if tag == "script" or self.script_depth:
            return
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        if tag == "script":
            self.script_depth = max(0, self.script_depth - 1)
        elif not self.script_depth:
            self.parts.append("</" + tag + ">")

    def handle_data(self, data):
        if not self.script_depth:
            self.parts.append(escape(redact(data)))


def public_dom(raw: str) -> str:
    parser = PublicDOM()
    parser.feed(raw)
    parser.close()
    return "".join(parser.parts)


def public_response(url: str, method: str, status: int, content_type: str, body: bytes,
                    resource_type: str) -> dict:
    """Only export allowed textual responses, never downloaded source or maps."""
    value = {"url": redact(url), "method": method, "status": status,
             "content_type": content_type, "resource_type": resource_type}
    media = content_type.lower().split(";", 1)[0]
    if resource_type == "script" or "javascript" in media or url.split("?", 1)[0].endswith(".map"):
        value["body_omitted"] = "client_code_excluded_by_protocol"
        return value
    try:
        text = body.decode("utf-8")
        if media == "application/json" or media.endswith("+json"):
            value["body"] = redact(json.loads(text))
        elif media == "text/html":
            value["body"] = public_dom(text)
        else:
            value["body_omitted"] = "unregistered_media_type"
    except (UnicodeDecodeError, ValueError):
        value["body_omitted"] = "unreadable_response"
    return value
