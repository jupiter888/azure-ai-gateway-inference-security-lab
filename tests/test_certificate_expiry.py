"""
Certificate expiration checks using synthetic validity dates.
"""

from datetime import datetime, timedelta, timezone

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from scripts.check_certificate_expiry import check_certificate


START = datetime(2030, 1, 1, tzinfo=timezone.utc)
END = datetime(2030, 2, 1, tzinfo=timezone.utc)


@pytest.fixture(scope="module")
def public_certificate(tmp_path_factory):
    key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )
    name = x509.Name([
        x509.NameAttribute(
            NameOID.COMMON_NAME,
            "Synthetic Expiration Test",
        )
    ])

    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(START)
        .not_valid_after(END)
        .sign(key, hashes.SHA256())
    )

    path = tmp_path_factory.mktemp("certificate") / "public.pem"
    path.write_bytes(
        certificate.public_bytes(serialization.Encoding.PEM)
    )
    return path


@pytest.mark.parametrize(
    "now,status,code",
    [
        (START - timedelta(seconds=1), "not_yet_valid", 3),
        (START, "healthy", 0),
        (END - timedelta(days=8), "healthy", 0),
        (END - timedelta(days=7), "expiring", 1),
        (END - timedelta(seconds=1), "expiring", 1),
        (END, "expired", 2),
        (END + timedelta(seconds=1), "expired", 2),
    ],
)
def test_validity_states(public_certificate, now, status, code):
    result = check_certificate(public_certificate, now=now)

    assert result["status"] == status
    assert result["exit_code"] == code
    assert result["expires_at"] == END.isoformat()


@pytest.mark.parametrize("warning_days", [-1, 366, True, 1.5])
def test_invalid_warning_interval(public_certificate, warning_days):
    with pytest.raises(ValueError):
        check_certificate(
            public_certificate,
            warning_days=warning_days,
            now=START,
        )


def test_naive_check_time_rejected(public_certificate):
    with pytest.raises(ValueError):
        check_certificate(
            public_certificate,
            now=datetime(2030, 1, 2),
        )


def test_missing_certificate_fails(tmp_path):
    with pytest.raises(FileNotFoundError):
        check_certificate(tmp_path / "missing.pem", now=START)


def test_invalid_certificate_fails(tmp_path):
    path = tmp_path / "invalid.pem"
    path.write_text("Synthetic invalid certificate", encoding="utf-8")

    with pytest.raises(ValueError):
        check_certificate(path, now=START)