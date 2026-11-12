# Project 9 — Hardened inference gateway
# Runtime Python packages installed from a hashed Linux lockfile.

FROM python:3.11-slim-trixie@sha256:07d4824036af339fa1b6ef769cc99d9c10a141769538b52b3b597c84f7a7b535

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app

WORKDIR /app

RUN apt-get update \
    && apt-get upgrade -y \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --system appgroup \
    && useradd \
        --system \
        --gid appgroup \
        --home-dir /app \
        --no-create-home \
        appuser

COPY requirements-runtime.lock /app/requirements-runtime.lock

RUN python -m pip install \
        --no-cache-dir \
        --upgrade \
        "pip==26.3" \
        "setuptools==84.1.0" \
    && python -m pip install \
        --no-cache-dir \
        --require-hashes \
        --only-binary=:all: \
        -r /app/requirements-runtime.lock

COPY src/ /app/src/

RUN chown -R root:root /app \
    && chmod -R a=rX /app \
    && find / -xdev -type f -perm /6000 -exec chmod a-s {} +

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s \
    --timeout=5s \
    --start-period=10s \
    --retries=3 \
    CMD python -c \
    "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)" \
    || exit 1

CMD ["uvicorn", "src.gateway.app:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--no-access-log"]