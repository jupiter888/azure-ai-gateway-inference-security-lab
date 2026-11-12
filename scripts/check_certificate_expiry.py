"""
Check the local public client certificate validity.

Exit codes:
0: healthy
1: expiration warning
2: expired
3: not yet valid
4: check failed

Reads the public certificate only. Does not contact Entra,
load private keys, schedule checks, or send notifications.
"""

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography import x509


DEFAULT_CERTIFICATE = (
    Path.home()
    / ".config"
    / "project09"
    / "credentials"
    / "client-cert.pem"
)


def check_certificate(
    path: Path,
    warning_days: int = 7,
    now: datetime | None = None,
) -> dict:
    if type(warning_days) is not int or not 0 <= warning_days <= 365:
        raise ValueError("Invalid warning interval")

    current = now if now is not None else datetime.now(timezone.utc)

    if current.tzinfo is None or current.utcoffset() is None:
        raise ValueError("Timezone-aware check time required")

    current = current.astimezone(timezone.utc)
    certificate = x509.load_pem_x509_certificate(path.read_bytes())

    starts = certificate.not_valid_before_utc
    expires = certificate.not_valid_after_utc
    remaining = expires - current

    if current < starts:
        status, exit_code = "not_yet_valid", 3
    elif current >= expires:
        status, exit_code = "expired", 2
    elif remaining <= timedelta(days=warning_days):
        status, exit_code = "expiring", 1
    else:
        status, exit_code = "healthy", 0

    return {
        "status": status,
        "exit_code": exit_code,
        "checked_at": current.isoformat(),
        "not_before": starts.isoformat(),
        "expires_at": expires.isoformat(),
        "seconds_remaining": int(remaining.total_seconds()),
        "warning_days": warning_days,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Check local public client certificate expiration."
    )
    parser.add_argument(
        "--certificate",
        type=Path,
        default=DEFAULT_CERTIFICATE,
    )
    parser.add_argument("--warning-days", type=int, default=7)
    args = parser.parse_args()

    try:
        result = check_certificate(
            args.certificate,
            warning_days=args.warning_days,
        )
    except (OSError, ValueError, OverflowError):
        print(json.dumps({
            "status": "check_failed",
            "exit_code": 4,
        }))
        raise SystemExit(4) from None

    print(json.dumps(result, sort_keys=True))
    raise SystemExit(result["exit_code"])

if __name__ == "__main__":
    main()