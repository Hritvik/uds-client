"""The service layer: 404 semantics, typing, request bodies, URL safety."""

from __future__ import annotations

import httpx
import pytest
from pydantic import BaseModel

from uds_client import UDSEntity

from .conftest import FakeUDS, url_path

SERVICE = "model-bridge-deployment"


class Row(BaseModel):
    id: str
    weight: int = 0


# --- reads ---------------------------------------------------------------


async def test_get_entity_returns_none_when_absent(uds: FakeUDS) -> None:
    uds.route("GET", url_path(SERVICE, "gone"), httpx.Response(404))
    assert await uds.client().service(SERVICE).get_entity("gone") is None


async def test_get_entity_normalizes_the_record(uds: FakeUDS) -> None:
    uds.route(
        "GET",
        url_path(SERVICE, "d1"),
        httpx.Response(200, json={"_id": "d1", "name": "east", "parentId": "m1"}),
    )
    entity = await uds.client().service(SERVICE).get_entity("d1")
    assert isinstance(entity, UDSEntity)
    assert (entity.id, entity.name, entity.parent_id) == ("d1", "east", "m1")


async def test_list_entities_normalizes_every_row(uds: FakeUDS) -> None:
    uds.route(
        "GET",
        url_path(SERVICE),
        httpx.Response(200, json={"items": [{"id": "a"}, {"_id": "b"}]}),
    )
    entities = await uds.client().service(SERVICE).list_entities()
    assert [entity.id for entity in entities] == ["a", "b"]


async def test_a_typed_list_validates_each_row(uds: FakeUDS) -> None:
    uds.route(
        "GET",
        url_path(SERVICE),
        httpx.Response(200, json=[{"id": "a", "weight": 40}]),
    )
    rows = await uds.client().service(SERVICE, model=Row).list()
    assert rows == [Row(id="a", weight=40)]


async def test_a_typed_row_is_none_when_absent(uds: FakeUDS) -> None:
    uds.route("GET", url_path(SERVICE, "gone"), httpx.Response(404))
    assert await uds.client().service(SERVICE, model=Row).get("gone") is None


async def test_without_a_model_the_row_is_the_raw_dict(uds: FakeUDS) -> None:
    uds.route("GET", url_path(SERVICE), httpx.Response(200, json=[{"id": "a"}]))
    rows = await uds.client().service(SERVICE).list()
    assert rows == [{"id": "a"}]


# --- writes --------------------------------------------------------------


async def test_create_posts_and_returns_the_record(uds: FakeUDS) -> None:
    uds.route(
        "POST",
        url_path(SERVICE),
        httpx.Response(201, json={"id": "new", "weight": 10}),
    )
    row = await uds.client().service(SERVICE, model=Row).create({"weight": 10})
    assert row == Row(id="new", weight=10)
    assert uds.calls[0].method == "POST"


async def test_create_serializes_a_pydantic_body(uds: FakeUDS) -> None:
    uds.route("POST", url_path(SERVICE), httpx.Response(201, json={"id": "x"}))
    await uds.client().service(SERVICE).create(Row(id="x", weight=7))
    assert b'"weight":7' in uds.calls[0].content


async def test_create_tolerates_an_empty_response(uds: FakeUDS) -> None:
    uds.route("POST", url_path(SERVICE), httpx.Response(204))
    assert await uds.client().service(SERVICE).create({"id": "x"}) == {}


async def test_create_rejects_a_body_that_cannot_be_serialized(uds: FakeUDS) -> None:
    with pytest.raises(TypeError, match="mapping or pydantic model"):
        await uds.client().service(SERVICE).create(["not", "a", "body"])


async def test_update_defaults_to_patch(uds: FakeUDS) -> None:
    uds.route("PATCH", url_path(SERVICE, "d1"), httpx.Response(200, json={"id": "d1"}))
    await uds.client().service(SERVICE).update("d1", {"weight": 5})
    assert uds.calls[0].method == "PATCH"


async def test_update_can_use_put(uds: FakeUDS) -> None:
    uds.route("PUT", url_path(SERVICE, "d1"), httpx.Response(200, json={"id": "d1"}))
    await uds.client().service(SERVICE).update("d1", {"weight": 5}, method="PUT")
    assert uds.calls[0].method == "PUT"


async def test_update_rejects_an_unknown_method(uds: FakeUDS) -> None:
    with pytest.raises(ValueError, match="PATCH or PUT"):
        await uds.client().service(SERVICE).update("d1", {}, method="POST")


async def test_delete_returns_true(uds: FakeUDS) -> None:
    uds.route("DELETE", url_path(SERVICE, "d1"), httpx.Response(204))
    assert await uds.client().service(SERVICE).delete("d1") is True


async def test_delete_of_a_missing_row_is_false_not_an_error(uds: FakeUDS) -> None:
    uds.route("DELETE", url_path(SERVICE, "gone"), httpx.Response(404))
    assert await uds.client().service(SERVICE).delete("gone") is False


# --- safety and construction --------------------------------------------


async def test_an_entity_id_cannot_escape_the_item_route(uds: FakeUDS) -> None:
    uds.route(
        "GET", url_path(SERVICE, "a%2Fb"), httpx.Response(200, json={"id": "a/b"})
    )
    await uds.client().service(SERVICE).get_entity("a/b")
    # ``url.path`` would decode %2F back to a separator; the wire form must not.
    assert uds.calls[0].url.raw_path.decode() == url_path(SERVICE, "a%2Fb")


def test_a_service_name_is_required() -> None:
    from uds_client import UDSClient

    with pytest.raises(ValueError, match="service name is required"):
        UDSClient("http://uds.test").service("")


async def test_custom_paths_are_honoured(uds: FakeUDS) -> None:
    from uds_client import UDSPaths

    uds.route("GET", "/v2/rows", httpx.Response(200, json=[]))
    client = uds.client(
        paths=UDSPaths(collection="/v2/rows", item="/v2/rows/{entity_id}")
    )
    assert await client.list_records(SERVICE) == []
