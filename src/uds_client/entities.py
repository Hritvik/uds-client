"""The normalized view of one registry row.

UDS records are plain JSON objects. The only thing this library asserts about
them is the identity field, because everything else is schema the *caller*
owns — this client has no opinion about what a "model" is.

The normalization here is the part that used to be copy-pasted into every
consumer:

* ``id`` or ``_id`` — Mongo-shaped rows carry the latter.
* ``parent_id`` or ``parentId`` — the registry is inconsistent about casing.
* timestamps arrive as strings *or* datetimes depending on the serializer.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .errors import UDSPayloadError


def _first_present(record: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        value = record.get(key)
        if value is not None:
            return value
    return None


def normalize_id(record: Mapping[str, Any], fallback: str = "") -> str:
    """The record's identity, or ``fallback`` when it has none.

    Truthiness rather than presence: a record whose ``id`` is ``0`` or ``""``
    has no usable identity, and a caller that passed a fallback meant it.
    """
    return str(record.get("id") or record.get("_id") or fallback)


def normalize_timestamp(value: Any) -> str:
    """Timestamps arrive as strings *or* datetimes; both become ISO strings."""
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _as_text(value: Any) -> str | None:
    """Optional variant of :func:`normalize_timestamp`, for model fields."""
    return None if value is None else normalize_timestamp(value)


@dataclass(frozen=True, slots=True)
class UDSEntity:
    """One normalized row.

    ``raw`` is the record exactly as received, which is what a consumer hands to
    its own model (``ModelInfo.model_validate(entity.raw)``). The parsed fields
    exist so nobody has to re-derive ``_id``/``parentId`` again.
    """

    id: str
    raw: dict[str, Any] = field(repr=False)
    name: str | None = None
    parent_id: str | None = None
    created_at: str | None = None
    updated_at: str | None = None

    @classmethod
    def from_record(
        cls, record: Mapping[str, Any], *, service: str | None = None
    ) -> UDSEntity:
        """Build an entity, or fail loudly if it has no identity.

        A record without ``id``/``_id`` cannot be addressed, so a client that
        accepted it would hand back an entity that ``get()`` can never fetch.
        """
        if not isinstance(record, Mapping):
            raise UDSPayloadError(
                f"UDS record is {type(record).__name__}, expected an object",
                service=service,
            )
        entity_id = normalize_id(record)
        if entity_id == "":
            raise UDSPayloadError(
                "UDS record has no 'id' or '_id'",
                service=service,
            )
        return cls(
            id=entity_id,
            raw=dict(record),
            name=_as_text(record.get("name")),
            parent_id=_as_text(_first_present(record, "parent_id", "parentId")),
            created_at=_as_text(_first_present(record, "created_at", "createdAt")),
            updated_at=_as_text(_first_present(record, "updated_at", "updatedAt")),
        )

    def attribute(self, key: str, default: Any = None) -> Any:
        """Read an arbitrary field from the raw record."""
        return self.raw.get(key, default)
