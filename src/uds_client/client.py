"""Transport-level client: one endpoint family, five verbs, four errors.

This layer knows about URLs, auth, JSON and status codes. It does **not** know
what a "model" is, does not retry, and does not cache — see the README for why
those belong one layer up.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, overload

import httpx

from .config import UDSPaths
from .errors import (
    UDSHTTPError,
    UDSNotFound,
    UDSPayloadError,
    UDSTransportError,
)

if TYPE_CHECKING:
    from .service import UDSService, ValidatingModel

DEFAULT_TIMEOUT_SECONDS = 30.0


#: A request body: a mapping, or anything pydantic can serialize. Typed as
#: ``Any`` because the honest alternative is a Protocol that pydantic's
#: ``model_dump(*, mode: Literal[...])`` signature cannot satisfy structurally.
#: :func:`_encode` is the real check and raises ``TypeError`` for anything else,
#: rather than sending a body the server cannot read.
Body = Any


def _encode(body: Any) -> dict[str, Any]:
    """Serialize a request body, refusing anything we cannot send faithfully."""
    if hasattr(body, "model_dump"):
        return dict(body.model_dump(mode="json"))
    if isinstance(body, Mapping):
        return dict(body)
    raise TypeError(
        f"request body must be a mapping or pydantic model, got {type(body).__name__}"
    )


def _payload_list(payload: Any, *, service: str) -> list[dict[str, Any]]:
    """Flatten the two list shapes the service uses."""
    records: Any
    if isinstance(payload, list):
        records = payload
    elif isinstance(payload, dict):
        records = payload.get("items")
        if records is None:
            records = payload.get("data")
        if not isinstance(records, list):
            raise UDSPayloadError(
                f"expected 'items' or 'data' to be a list, got {sorted(payload)}",
                service=service,
            )
    else:
        raise UDSPayloadError(
            f"expected a list or an object, got {type(payload).__name__}",
            service=service,
        )
    for record in records:
        if not isinstance(record, Mapping):
            raise UDSPayloadError(
                f"expected object records, got {type(record).__name__}",
                service=service,
            )
    return [dict(record) for record in records]


class UDSClient:
    """Async CRUD client for one unified-data-service deployment.

    Owns its ``httpx.AsyncClient`` unless one is injected; ``aclose()`` only
    closes what it created, so a caller sharing a pooled client keeps it.
    """

    def __init__(
        self,
        base_url: str,
        *,
        token: str | None = None,
        headers: Mapping[str, str] | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        transport: httpx.AsyncBaseTransport | None = None,
        paths: UDSPaths | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not base_url:
            raise ValueError("base_url is required")
        if not base_url.startswith(("http://", "https://")):
            raise ValueError(f"base_url must be absolute, got {base_url!r}")

        self._base_url = base_url.rstrip("/")
        self._paths = paths or UDSPaths()
        self._headers: dict[str, str] = {
            "Accept": "application/json",
            **dict(headers or {}),
        }
        if token:
            self._headers["Authorization"] = f"Bearer {token}"

        # Absolute URLs are always used, so an injected client does not need a
        # matching base_url and an owned one does not need one either.
        self._owns_client = client is None
        self._http = client or httpx.AsyncClient(
            timeout=timeout,
            transport=transport,
            headers=self._headers,
        )

    @property
    def base_url(self) -> str:
        return self._base_url

    @overload
    def service(
        self, name: str, *, model: None = None
    ) -> UDSService[dict[str, Any]]: ...

    @overload
    def service[T](
        self, name: str, *, model: type[ValidatingModel[T]]
    ) -> UDSService[T]: ...

    def service(self, name: str, *, model: Any = None) -> Any:
        """A handle on one service.

        Without ``model=`` the rows are raw dictionaries; with it, every payload
        is validated by the caller's model and the handle is typed by it.
        """
        from .service import UDSService

        return UDSService(self, name, model=model)

    # --- reads ------------------------------------------------------------

    async def list_records(
        self, service: str, *, params: Mapping[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Every record in one service, normalizing both list shapes."""
        response = await self._request(
            "GET",
            self._paths.collection_path(service),
            service=service,
            params=params,
        )
        return _payload_list(self._decode(response, service=service), service=service)

    async def get_record(self, service: str, entity_id: str) -> dict[str, Any]:
        """One record. Raises :class:`UDSNotFound` when it does not exist."""
        response = await self._request(
            "GET",
            self._paths.item_path(service, entity_id),
            service=service,
            entity_id=entity_id,
        )
        payload = self._decode(response, service=service, entity_id=entity_id)
        if not isinstance(payload, Mapping):
            raise UDSPayloadError(
                f"expected an object, got {type(payload).__name__}",
                service=service,
                entity_id=entity_id,
            )
        return dict(payload)

    # --- writes -----------------------------------------------------------

    async def create_record(self, service: str, body: Body) -> dict[str, Any]:
        """Create one record. An empty response body becomes ``{}``."""
        response = await self._request(
            "POST",
            self._paths.collection_path(service),
            service=service,
            json=_encode(body),
        )
        return self._decode_object(response, service=service)

    async def update_record(
        self,
        service: str,
        entity_id: str,
        body: Body,
        *,
        method: str = "PATCH",
    ) -> dict[str, Any]:
        """Update one record. ``PATCH`` by default; pass ``PUT`` to replace."""
        if method not in {"PATCH", "PUT"}:
            raise ValueError(f"update method must be PATCH or PUT, got {method!r}")
        response = await self._request(
            method,
            self._paths.item_path(service, entity_id),
            service=service,
            entity_id=entity_id,
            json=_encode(body),
        )
        return self._decode_object(response, service=service, entity_id=entity_id)

    async def delete_record(self, service: str, entity_id: str) -> None:
        """Delete one record. Raises :class:`UDSNotFound` when already gone."""
        await self._request(
            "DELETE",
            self._paths.item_path(service, entity_id),
            service=service,
            entity_id=entity_id,
        )

    # --- lifecycle --------------------------------------------------------

    async def aclose(self) -> None:
        if self._owns_client:
            await self._http.aclose()

    async def __aenter__(self) -> UDSClient:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()

    # --- internals --------------------------------------------------------

    async def _request(
        self,
        method: str,
        path: str,
        *,
        service: str,
        entity_id: str | None = None,
        params: Mapping[str, Any] | None = None,
        json: Any = None,
    ) -> httpx.Response:
        try:
            response = await self._http.request(
                method,
                f"{self._base_url}{path}",
                params=params,
                json=json,
            )
        except httpx.TimeoutException as e:
            raise UDSTransportError(
                f"UDS request timed out: {method} {service}",
                service=service,
                entity_id=entity_id,
            ) from e
        except httpx.TransportError as e:
            raise UDSTransportError(
                f"UDS transport failed: {method} {service}: {e}",
                service=service,
                entity_id=entity_id,
            ) from e

        if response.status_code == httpx.codes.NOT_FOUND:
            raise UDSNotFound(
                f"UDS {service} entity not found: {entity_id or path}",
                status_code=response.status_code,
                service=service,
                entity_id=entity_id,
            )
        if response.status_code >= httpx.codes.BAD_REQUEST:
            raise UDSHTTPError(
                f"UDS {service} returned {response.status_code}",
                status_code=response.status_code,
                service=service,
                entity_id=entity_id,
                body=response.text[:500],
            )
        return response

    @staticmethod
    def _decode(
        response: httpx.Response,
        *,
        service: str,
        entity_id: str | None = None,
    ) -> Any:
        if not response.content:
            return None
        try:
            return response.json()
        except ValueError as e:
            raise UDSPayloadError(
                "response body is not JSON",
                service=service,
                entity_id=entity_id,
            ) from e

    def _decode_object(
        self,
        response: httpx.Response,
        *,
        service: str,
        entity_id: str | None = None,
    ) -> dict[str, Any]:
        payload = self._decode(response, service=service, entity_id=entity_id)
        if payload is None:
            return {}
        if not isinstance(payload, Mapping):
            raise UDSPayloadError(
                f"expected an object, got {type(payload).__name__}",
                service=service,
                entity_id=entity_id,
            )
        return dict(payload)
