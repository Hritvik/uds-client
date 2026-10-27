"""Normalization rules, pinned.

These four rules used to be copy-pasted into every consumer; a regression in
any of them silently changes how a registry row is addressed.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from uds_client import UDSEntity
from uds_client.errors import UDSPayloadError


def test_id_is_read_from_id() -> None:
    entity = UDSEntity.from_record({"id": "abc", "name": "n"})
    assert entity.id == "abc"


def test_id_falls_back_to_mongo_style_underscore_id() -> None:
    entity = UDSEntity.from_record({"_id": "abc"})
    assert entity.id == "abc"


def test_id_is_coerced_to_text() -> None:
    assert UDSEntity.from_record({"id": 42}).id == "42"


def test_a_record_without_identity_fails_loudly() -> None:
    with pytest.raises(UDSPayloadError, match="no 'id' or '_id'"):
        UDSEntity.from_record({"name": "nameless"})


def test_an_empty_id_is_not_an_identity() -> None:
    with pytest.raises(UDSPayloadError):
        UDSEntity.from_record({"id": ""})


def test_a_non_mapping_record_fails_loudly() -> None:
    with pytest.raises(UDSPayloadError, match="expected an object"):
        UDSEntity.from_record(["not", "a", "record"])  # type: ignore[arg-type]


def test_parent_id_is_read_from_snake_case() -> None:
    assert UDSEntity.from_record({"id": "a", "parent_id": "p"}).parent_id == "p"


def test_parent_id_is_read_from_camel_case() -> None:
    assert UDSEntity.from_record({"id": "a", "parentId": "p"}).parent_id == "p"


def test_absent_optional_fields_are_none() -> None:
    entity = UDSEntity.from_record({"id": "a"})
    assert (entity.name, entity.parent_id, entity.created_at, entity.updated_at) == (
        None,
        None,
        None,
        None,
    )


def test_string_timestamps_pass_through() -> None:
    entity = UDSEntity.from_record(
        {"id": "a", "created_at": "2026-01-02T03:04:05", "updatedAt": "2026-01-03"}
    )
    assert entity.created_at == "2026-01-02T03:04:05"
    assert entity.updated_at == "2026-01-03"


def test_datetime_timestamps_are_isoformatted() -> None:
    moment = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
    entity = UDSEntity.from_record({"id": "a", "created_at": moment})
    assert entity.created_at == moment.isoformat()


def test_the_raw_record_is_preserved_for_the_consumer_s_model() -> None:
    record = {"id": "a", "weight": 40, "nested": {"x": 1}}
    assert UDSEntity.from_record(record).raw == record


def test_attribute_reads_arbitrary_fields() -> None:
    entity = UDSEntity.from_record({"id": "a", "weight": 40})
    assert entity.attribute("weight") == 40
    assert entity.attribute("missing", default="fallback") == "fallback"
