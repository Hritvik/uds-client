"""Shared fixtures: a scripted UDS over ``httpx.MockTransport``.

No network, no server. The transport seam is the library's supported test
entry point, which is why the production client takes one.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any

import httpx
import pytest

from uds_client import UDSClient

Handler = Callable[[httpx.Request], httpx.Response]


@dataclass
class FakeUDS:
    """A route table keyed by ``(method, path)``, recording every request."""

    routes: dict[tuple[str, str], Handler | httpx.Response] = field(
        default_factory=dict
    )
    calls: list[httpx.Request] = field(default_factory=list)
    token: str | None = None

    def route(self, method: str, path: str, response: httpx.Response) -> FakeUDS:
        self.routes[(method, path)] = response
        return self

    def route_with(self, method: str, path: str, handler: Handler) -> FakeUDS:
        self.routes[(method, path)] = handler
        return self

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        # ``url.path`` is decoded, so an entity id containing %2F would silently
        # match the wrong route here. Key on the wire form, minus the query.
        wire_path = request.url.raw_path.decode().split("?", 1)[0]
        entry = self.routes.get((request.method, wire_path))
        if entry is None:
            return httpx.Response(404, json={"detail": "no route"})
        if isinstance(entry, httpx.Response):
            return entry
        return entry(request)

    def client(self, **kwargs: Any) -> UDSClient:
        return UDSClient(
            "http://uds.test",
            token=self.token,
            transport=httpx.MockTransport(self._handle),
            **kwargs,
        )


@pytest.fixture
def uds() -> Iterator[FakeUDS]:
    yield FakeUDS()


def url_path(service: str, entity_id: str | None = None) -> str:
    """The default item/collection path, so tests do not hardcode the template."""
    base = f"/api/v1/services/{service}/entities"
    return base if entity_id is None else f"{base}/{entity_id}"
