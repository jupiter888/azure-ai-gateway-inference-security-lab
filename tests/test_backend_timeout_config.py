"""
Backend timeout configuration tests.

No network requests or real credentials are used.
"""

import pytest

from src.gateway.config import load_backend_timeout_config


VARIABLES = {
    "connect": "P9_BACKEND_CONNECT_TIMEOUT_SECONDS",
    "read": "P9_BACKEND_READ_TIMEOUT_SECONDS",
    "write": "P9_BACKEND_WRITE_TIMEOUT_SECONDS",
    "pool": "P9_BACKEND_POOL_TIMEOUT_SECONDS",
}


@pytest.fixture(autouse=True)
def clear_timeout_environment(monkeypatch):
    for name in VARIABLES.values():
        monkeypatch.delenv(name, raising=False)


def test_default_timeouts():
    config = load_backend_timeout_config()

    assert config.connect == 10.0
    assert config.read == 60.0
    assert config.write == 10.0
    assert config.pool == 5.0


def test_explicit_timeouts(monkeypatch):
    values = {
        "connect": "3",
        "read": "45",
        "write": "4",
        "pool": "2",
    }

    for field, value in values.items():
        monkeypatch.setenv(VARIABLES[field], value)

    config = load_backend_timeout_config()

    assert config.connect == 3.0
    assert config.read == 45.0
    assert config.write == 4.0
    assert config.pool == 2.0


@pytest.mark.parametrize(
    "raw",
    ["", "invalid", "nan", "inf", "-inf", "0", "-1", "0.09", "121"],
)
def test_invalid_read_timeout_rejected(monkeypatch, raw):
    monkeypatch.setenv(VARIABLES["read"], raw)

    with pytest.raises(ValueError):
        load_backend_timeout_config()


@pytest.mark.parametrize("field", ["connect", "write", "pool"])
def test_other_phase_upper_bounds(monkeypatch, field):
    monkeypatch.setenv(VARIABLES[field], "31")

    with pytest.raises(ValueError):
        load_backend_timeout_config()


def test_allowed_boundaries(monkeypatch):
    monkeypatch.setenv(VARIABLES["connect"], "0.1")
    monkeypatch.setenv(VARIABLES["read"], "120")
    monkeypatch.setenv(VARIABLES["write"], "30")
    monkeypatch.setenv(VARIABLES["pool"], "30")

    config = load_backend_timeout_config()

    assert config.connect == 0.1
    assert config.read == 120.0
    assert config.write == 30.0
    assert config.pool == 30.0