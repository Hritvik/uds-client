"""Error taxonomy for the UDS client.

Every failure is one of four shapes, because callers act on exactly four
things: "cannot reach it", "it said no", "it said 404", and "the body is not
what we agreed on". Nothing here retries — see the README.

All errors carry the service name (and the entity id where relevant) so a log
line identifies *which* registry row failed without the caller rebuilding that
context by hand.
"""

from __future__ import annotations

from typing import Any


class UDSError(Exception):
    """Base class. Carries the request context shared by every failure."""

    def __init__(
        self,
        message: str,
        *,
        service: str | None = None,
        entity_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.service = service
        self.entity_id = entity_id

    def context(self) -> dict[str, Any]:
        """Structured context for logging."""
        return {
            key: value
            for key, value in (("service", self.service), ("entity_id", self.entity_id))
            if value is not None
        }


class UDSTransportError(UDSError):
    """The request never produced a response: refused, DNS, timeout, reset."""


class UDSHTTPError(UDSError):
    """The service answered with an error status."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int,
        service: str | None = None,
        entity_id: str | None = None,
        body: str = "",
    ) -> None:
        super().__init__(message, service=service, entity_id=entity_id)
        self.status_code = status_code
        self.body = body

    def context(self) -> dict[str, Any]:
        return {**super().context(), "status_code": self.status_code}


class UDSNotFound(UDSHTTPError):
    """404. The client layer raises it; the service layer turns it into None."""


class UDSPayloadError(UDSError):
    """A body that does not match the shape this client can interpret.

    Deliberately loud: silently coercing an unexpected payload is how a
    registry returns empty data and routing quietly degrades.
    """
