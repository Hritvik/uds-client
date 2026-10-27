# uds-client

Typed async CRUD client for a unified-data-service (UDS). One dependency: `httpx`.

```python
from uds_client import UDSClient

async with UDSClient(base_url="http://uds:8080", token="...") as client:
    models = client.service("model-bridge-model")

    await models.list_entities()                 # list[UDSEntity]
    await models.get_entity("text-embedding-3")  # UDSEntity | None
    await models.create({"name": "..."})         # raw dict
    await models.update("text-embedding-3", {"weight": 2})
    await models.delete("text-embedding-3")      # bool
```

Typed variant — pass a pydantic model and the payload is validated for you:

```python
models = client.service("model-bridge-model", model=ModelInfo)
await models.list()                              # list[ModelInfo]
```

## Two invariants

**No retry, no circuit breaker, no metrics.** Policy belongs to the layer above
(a generic REST client). This library does transport, typing and error
classification only, so it can be used *to bootstrap* that layer — a client that
needed the registry to know how to reach the registry could never start.

**`httpx` is the only dependency.** In particular, nothing here may import the
application, its DI container, or its REST client. The dependency arrow points
one way: `app → rest_client → uds_client → httpx`.

## Errors

| Error | When |
|---|---|
| `UDSTransportError` | connection refused, DNS, timeout |
| `UDSHTTPError` | any non-2xx, carries `status_code` and `service` |
| `UDSNotFound` | 404 at the *client* layer |
| `UDSPayloadError` | a body that is not a list, not an object with `items`/`data`, or has no `id`/`_id` |

The service layer maps 404 to `None` on reads and `False` on delete, because the
callers that matter treat both as "absent" rather than as failures.

## Paths

Defaults match the service's documented generic endpoint:

```
collection  /api/v1/services/{service}/entities
item        /api/v1/services/{service}/entities/{entity_id}
```

Override via `UDSPaths(collection=..., item=...)` if a deployment differs. Path
segments are URL-quoted, so an id containing `/` cannot escape the item route.
