"""Stdlib SDK in VeriEnv's discoverable websites/<site>/sdk/python layout."""
from __future__ import annotations

import json
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


class IssueLabClient:
    def __init__(self, base_url='http://127.0.0.1:8877', timeout=10):
        parts = urlsplit(base_url)
        if parts.scheme != 'http' or parts.hostname not in ('127.0.0.1', 'localhost', '::1'):
            raise ValueError('This experiment SDK only accepts a local HTTP server.')
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout

    def _request(self, path, payload=None):
        body = None if payload is None else json.dumps(payload).encode('utf-8')
        request = Request(self.base_url + path, data=body,
                          headers={'Content-Type': 'application/json'})
        with urlopen(request, timeout=self.timeout) as response:
            return json.load(response)

    def health(self):
        return self._request('/health')

    def observe(self):
        return self._request('/api/state')

    def step(self, action):
        return self._request('/api/action', action)

    def reset(self, seed=0, version=1, role='editor'):
        """Evaluator administration only; not exposed as a learner action."""
        return self._request('/admin/reset', {'seed': seed, 'version': version, 'role': role})
