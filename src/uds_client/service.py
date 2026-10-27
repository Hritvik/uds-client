"""The layer consumers actually use: identity + typing over the transport.

Two deliberate asymmetries with the client layer:

* **Reads map 404 to ``None``.** A missing registry row is a fact the caller
  handles (cold start, a deployment that has not been onboarded), not an
  exception to unwind through a request path.
* **Delete maps 404 to ``False``.** Deleting something already gone is a
  successful outcome, and callers that retry deletes expect that.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol, cast

from .client import Body, UDSClient
from .entities import UDSEntity
from .errors import UDSNotFound


class ValidatingModel[T](Protocol):
    """The one thing this library needs from a caller's model.

    Structural rather than ``type[BaseModel]`` so the package keeps its single
    dependency, and so any object with a pydantic-style ``model_validate``
    works — pydantic itself, a stub in a test, or a hand-written class.
    """

    @classmethod
    def model_validate(cls, obj: Any) -> T: ...


class UDSService[T]:
    """A named service on a :class:`UDSClient`, optionally typed.

    With ``model=`` every payload is validated by the caller's own model, so
    this library never needs to know the registry schema. Without it, results
    are raw dictionaries.
    """

    def __init__(
        self,
        client: UDSClient,
        name: str,
        *,
        model: type[ValidatingModel[T]] | None = None,
    ) -> None:
        if not name:
            raise ValueError("service name is required")
        self._client = client
        self._name = name
        self._model = model

    @property
    def name(self) -> str:
        return self._name

    # --- entities (normalized, schema-free) -------------------------------

    async def list_entities(
        self, *, params: Mapping[str, Any] | None = None
    ) -> list[UDSEntity]:
        records = await self._client.list_records(self._name, params=params)
        return [UDSEntity.from_record(record, service=self._name) for record in records]

    async def get_entity(self, entity_id: str) -> UDSEntity | None:
        """One normalized entity, or ``None`` when it does not exist."""
        try:
            record = await self._client.get_record(self._name, entity_id)
        except UDSNotFound:
            return None
        return UDSEntity.from_record(record, service=self._name)

    # --- typed rows -------------------------------------------------------

    async def list(self, *, params: Mapping[str, Any] | None = None) -> list[T]:
        """Every row, validated against ``model`` when one was given."""
        records = await self._client.list_records(self._name, params=params)
        return [self._coerce(record) for record in records]

    async def get(self, entity_id: str) -> T | None:
        """One row, or ``None`` when it does not exist."""
        try:
            record = await self._client.get_record(self._name, entity_id)
        except UDSNotFound:
            return None
        return self._coerce(record)

    # --- writes -----------------------------------------------------------

    async def create(self, body: Body) -> T:
        record = await self._client.create_record(self._name, body)
        return self._coerce(record)

    async def update(
        self,
        entity_id: str,
        body: Body,
        *,
        method: str = "PATCH",
    ) -> T:
        record = await self._client.update_record(
            self._name, entity_id, body, method=method
        )
        return self._coerce(record)

    async def delete(self, entity_id: str) -> bool:
        """``True`` when a row was removed, ``False`` when it was already gone."""
        try:
            await self._client.delete_record(self._name, entity_id)
        except UDSNotFound:
            return False
        return True

    # --- internals --------------------------------------------------------

    def _coerce(self, record: dict[str, Any]) -> T:
        if self._model is None:
            return cast(T, record)
        return self._model.model_validate(record)
