"""Typed async CRUD client for a unified-data-service.

Two invariants shape this package:

* only ``httpx`` is imported — no application, no DI container, no REST client,
  so the client can bootstrap the config that describes everything else;
* policy (retry, circuit breaking, metrics, caching) lives one layer up.

See the README for the error taxonomy and the route templates.
"""

from .client import DEFAULT_TIMEOUT_SECONDS, UDSClient
from .config import UDSPaths
from .entities import UDSEntity, normalize_id, normalize_timestamp
from .errors import (
    UDSError,
    UDSHTTPError,
    UDSNotFound,
    UDSPayloadError,
    UDSTransportError,
)
from .service import UDSService

__all__ = [
    "DEFAULT_TIMEOUT_SECONDS",
    "UDSClient",
    "UDSEntity",
    "UDSError",
    "UDSHTTPError",
    "UDSNotFound",
    "UDSPaths",
    "UDSPayloadError",
    "UDSService",
    "UDSTransportError",
    "normalize_id",
    "normalize_timestamp",
]

__version__ = "0.1.0"
