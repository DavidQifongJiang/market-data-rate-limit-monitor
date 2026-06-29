from __future__ import annotations

from typing import Any

import requests

from .monitor import RateLimitMonitor


class HttpRateLimitedClient:
    def __init__(self, monitor: RateLimitMonitor, session: requests.Session | None = None) -> None:
        self.monitor = monitor
        self.session = session or requests.Session()

    def request(self, method: str, url: str, **kwargs: Any) -> requests.Response:
        self.monitor.before_request()
        response = self.session.request(method, url, **kwargs)
        self.monitor.after_response(response)
        return response

    def get(self, url: str, **kwargs: Any) -> requests.Response:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> requests.Response:
        return self.request("POST", url, **kwargs)
