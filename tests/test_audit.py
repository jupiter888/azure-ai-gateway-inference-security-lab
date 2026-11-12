"""
Structured audit event contract and data-exclusion tests.
"""

import json
import logging
from datetime import datetime
from uuid import UUID

import pytest

from src.gateway.audit import audit_decision


@pytest.mark.parametrize(
    "reason,outcome",
    [
        ("authentication_required", "denied"),
        ("invalid_authorization_header", "denied"),
        ("authentication_failed", "denied"),
        ("model_access_denied", "denied"),
        ("quota_exceeded", "denied"),
        ("admission_capacity_unavailable", "unavailable"),
        ("quota_configuration_unavailable", "unavailable"),
        ("backend_unavailable", "unavailable"),
        ("backend_configuration_unavailable", "unavailable"),
        ("inference_succeeded", "allowed"),
    ],
)
def test_audit_event_contract(caplog, reason, outcome):
    with caplog.at_level(logging.INFO, logger="uvicorn.error"):
        event_id = audit_decision(reason, "research-model")

    records = [
        record
        for record in caplog.records
        if record.name == "uvicorn.error"
    ]
    assert len(records) == 1

    event = json.loads(records[0].getMessage())

    assert set(event) == {
        "event",
        "event_id",
        "timestamp",
        "outcome",
        "reason",
        "model",
    }
    assert event["event"] == "inference_decision"
    assert event["event_id"] == event_id
    assert UUID(event_id).version == 4
    assert datetime.fromisoformat(event["timestamp"]).utcoffset().total_seconds() == 0
    assert event["outcome"] == outcome
    assert event["reason"] == reason
    assert event["model"] == "research-model"
    assert records[0].exc_info is None


def test_untrusted_model_is_not_logged(caplog):
    canary = (
        "SYNTHETIC_SECRET_CANARY\n"
        '{"event":"forged","outcome":"allowed"}'
    )

    with caplog.at_level(logging.INFO, logger="uvicorn.error"):
        audit_decision("model_access_denied", canary)

    event = json.loads(caplog.records[-1].getMessage())

    assert event["model"] == "unrecognized"
    assert canary not in caplog.text
    assert "SYNTHETIC_SECRET_CANARY" not in caplog.text
    assert "forged" not in caplog.text


def test_invalid_reason_is_not_logged(caplog):
    canary = "SYNTHETIC_PRIVATE_REASON_CANARY"

    with caplog.at_level(logging.INFO, logger="uvicorn.error"):
        with pytest.raises(ValueError) as exc:
            audit_decision(canary, "research-model")

    assert canary not in str(exc.value)
    assert not [
        record
        for record in caplog.records
        if record.name == "uvicorn.error"
    ]


def test_event_ids_are_unique(caplog):
    with caplog.at_level(logging.INFO, logger="uvicorn.error"):
        first = audit_decision("inference_succeeded", "research-model")
        second = audit_decision("inference_succeeded", "research-model")

    assert first != second


def test_restricted_model_label_is_preserved(caplog):
    with caplog.at_level(logging.INFO, logger="uvicorn.error"):
        audit_decision("model_access_denied", "restricted-model")

    event = json.loads(caplog.records[-1].getMessage())

    assert event["model"] == "restricted-model"