"""
Structured gateway security decision events.

Only fixed reason codes and allowlisted model labels are logged.
Each event receives a server-generated UUID and UTC timestamp.

This is application logging, not a durable or tamper-evident
audit storage system.
"""

import json
import logging
from datetime import datetime, timezone
from uuid import uuid4


logger = logging.getLogger("uvicorn.error")

REASON_OUTCOMES = {
    "authentication_required": "denied",
    "invalid_authorization_header": "denied",
    "authentication_failed": "denied",
    "model_access_denied": "denied",
    "quota_exceeded": "denied",
    "admission_capacity_unavailable": "unavailable",
    "quota_configuration_unavailable": "unavailable",
    "concurrency_exceeded": "unavailable",
    "backend_unavailable": "unavailable",
    "backend_configuration_unavailable": "unavailable",
    "inference_succeeded": "allowed",
}

MODEL_LABELS = frozenset({
    "research-model",
    "restricted-model",
})


def audit_decision(
    reason: str,
    model: str | None = None,
) -> str:
    if reason not in REASON_OUTCOMES:
        raise ValueError("Unsupported audit reason")

    event_id = str(uuid4())
    model_label = model if model in MODEL_LABELS else "unrecognized"

    event = {
        "event": "inference_decision",
        "event_id": event_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "outcome": REASON_OUTCOMES[reason],
        "reason": reason,
        "model": model_label,
    }

    logger.info(json.dumps(event, sort_keys=True))
    return event_id