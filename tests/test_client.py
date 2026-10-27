"""Transport behaviour: payload shapes, status mapping, auth, ownership."""

from __future__ import annotations

import httpx
import pytest

from uds_client import UDSClient
from uds_client.errors import (
    UDSHTTPError,
    UDSNotFound,
    UDSPayloadError,
    UDSTransportError,
)

from .conftest import FakeUDS, url_path

SERVICE = "model-bridge-model"


# --- list shapes ---------------------------------------------------------


async def test_a_bare_list_is_accepted(uds: FakeUDS) -> None:
    uds.route("GET", url_path(SERVICE), httpx.Response(200, json=[{"id": "a"}]))
    records = await uds.client().list_records(SERVICE)
    assert records == [{"id": "a"}]


async def test_an_items_envelope_is_accepted(uds: FakeUDS) -> None:
    uds.route(
        "GET", url_path(SERVICE), httpx.Response(200, json={"items": [{"id": "a"}]})
    )
    assert await uds.client().list_records(SERVICE) == [{"id": "a"}]


async def test_a_data_envelope_is_accepted(uds: FakeUDS) -> None:
    uds.route(
        "GET", url_path(SERVICE), httpx.Response(200, json={"data": [{"id": "a"}]})
    )
    assert await uds.client().list_records(SERVICE) == [{"id": "a"}]


async def test_an_unrecognized_envelope_is_a_payload_error(uds: FakeUDS) -> None:
    uds.route("GET", url_path(SERVICE), httpx.Response(200, json={"rows": []}))
    with pytest.raises(UDSPayloadError, match="expected 'items' or 'data'"):
        await uds.client().list_records(SERVICE)


async def test_a_non_list_envelope_is_a_payload_error(uds: FakeUDS) -> None:
    uds.route("GET", url_path(SERVICE), httpx.Response(200, json={"items": {}}))
    with pytest.raises(UDSPayloadError):
        await uds.client().list_records(SERVICE)


async def test_a_non_object_record_is_a_payload_error(uds: FakeUDS) -> None:
    uds.route("GET", url_path(SERVICE), httpx.Response(200, json=["nope"]))
    with pytest.raises(UDSPayloadError, match="object records"):
        await uds.client().list_records(SERVICE)


async def test_query_parameters_are_forwarded(uds: FakeUDS) -> None:
    uds.route("GET", url_path(SERVICE), httpx.Response(200, json=[]))
    await uds.client().list_records(SERVICE, params={"limit": 10})
    assert uds.calls[0].url.params["limit"] == "10"


# --- status mapping ------------------------------------------------------


async def test_a_missing_entity_raises_not_found(uds: FakeUDS) -> None:
    uds.route("GET", url_path(SERVICE, "gone"), httpx.Response(404))
    with pytest.raises(UDSNotFound) as caught:
        await uds.client().get_record(SERVICE, "gone")
    assert caught.value.status_code == 404
    assert caught.value.entity_id == "gone"


async def test_a_server_error_carries_the_body(uds: FakeUDS) -> None:
    uds.route("GET", url_path(SERVICE), httpx.Response(503, text="upstream is down"))
    with pytest.raises(UDSHTTPError) as caught:
        await uds.client().list_records(SERVICE)
    assert caught.value.status_code == 503
    assert "upstream is down" in caught.value.body


async def test_a_timeout_becomes_a_transport_error(uds: FakeUDS) -> None:
    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("too slow", request=request)

    uds.route_with("GET", url_path(SERVICE), timeout)
    with pytest.raises(UDSTransportError, match="timed out"):
        await uds.client().list_records(SERVICE)


async def test_a_refused_connection_becomes_a_transport_error(uds: FakeUDS) -> None:
    def refused(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    uds.route_with("GET", url_path(SERVICE), refused)
    with pytest.raises(UDSTransportError, match="transport failed"):
        await uds.client().list_records(SERVICE)


async def test_a_non_json_body_is_a_payload_error(uds: FakeUDS) -> None:
    uds.route("GET", url_path(SERVICE), httpx.Response(200, text="<html>"))
    with pytest.raises(UDSPayloadError, match="not JSON"):
        await uds.client().list_records(SERVICE)


async def test_an_empty_body_is_a_payload_error_on_read(uds: FakeUDS) -> None:
    uds.route("GET", url_path(SERVICE), httpx.Response(204))
    with pytest.raises(UDSPayloadError):
        await uds.client().list_records(SERVICE)


# --- construction --------------------------------------------------------


def test_base_url_is_required() -> None:
    with pytest.raises(ValueError, match="base_url is required"):
        UDSClient("")


def test_base_url_must_be_absolute() -> None:
    with pytest.raises(ValueError, match="must be absolute"):
        UDSClient("uds.test")


def test_a_trailing_slash_is_normalized() -> None:
    assert UDSClient("http://uds.test/").base_url == "http://uds.test"


async def test_a_token_becomes_a_bearer_header(uds: FakeUDS) -> None:
    uds.token = "s3cret"
    uds.route("GET", url_path(SERVICE), httpx.Response(200, json=[]))

    await uds.client().list_records(SERVICE)

    assert uds.calls[0].headers["authorization"] == "Bearer s3cret"


async def test_no_token_means_no_authorization_header(uds: FakeUDS) -> None:
    uds.route("GET", url_path(SERVICE), httpx.Response(200, json=[]))

    await uds.client().list_records(SERVICE)

    assert "authorization" not in uds.calls[0].headers


async def test_extra_headers_are_sent(uds: FakeUDS) -> None:
    uds.route("GET", url_path(SERVICE), httpx.Response(200, json=[]))

    await uds.client(headers={"X-Trace": "t1"}).list_records(SERVICE)

    assert uds.calls[0].headers["x-trace"] == "t1"


# --- lifecycle -----------------------------------------------------------


async def test_aclose_leaves_an_injected_client_open(uds: FakeUDS) -> None:
    shared = httpx.AsyncClient(transport=httpx.MockTransport(uds._handle))
    client = uds.client(client=shared)

    await client.aclose()

    assert not shared.is_closed
    await shared.aclose()


async def test_aclose_closes_an_owned_client(uds: FakeUDS) -> None:
    client = uds.client()
    await client.aclose()
    # A closed httpx client refuses further use; that is the observable effect.
    assert client._http.is_closed


async def test_the_client_is_an_async_context_manager(uds: FakeUDS) -> None:
    uds.route("GET", url_path(SERVICE), httpx.Response(200, json=[]))
    async with uds.client() as client:
        assert await client.list_records(SERVICE) == []
