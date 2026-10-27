"""Route templates.

Defaults follow the service's generic endpoint. They live in a value object
rather than as module constants so a deployment whose URLs differ can override
them without monkeypatching, and so the template is visible at the call site
that constructs the client.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote


@dataclass(frozen=True, slots=True)
class UDSPaths:
    """URL templates. `{service}` and `{entity_id}` are the only placeholders."""

    collection: str = "/api/v1/services/{service}/entities"
    item: str = "/api/v1/services/{service}/entities/{entity_id}"

    def collection_path(self, service: str) -> str:
        """Path for the collection of one service."""
        return self.collection.format(service=quote(service, safe=""))

    def item_path(self, service: str, entity_id: str) -> str:
        """Path for one entity.

        Both segments are quoted, so an id containing ``/`` cannot escape the
        item route and address a different entity.
        """
        return self.item.format(
            service=quote(service, safe=""),
            entity_id=quote(str(entity_id), safe=""),
        )
