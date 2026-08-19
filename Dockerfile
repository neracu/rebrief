# syntax=docker/dockerfile:1

FROM python:3.12-slim AS builder

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

COPY pyproject.toml README.md LICENSE MANIFEST.in ./
COPY rebrief ./rebrief

RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir --upgrade pip \
    && /opt/venv/bin/pip install --no-cache-dir . \
    && find /opt/venv -type d -name __pycache__ -exec rm -rf {} +


FROM python:3.12-slim AS runtime

ARG REBRIEF_UID=1000
ARG REBRIEF_GID=1000

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        git \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid "${REBRIEF_GID}" rebrief \
    && useradd --uid "${REBRIEF_UID}" --gid "${REBRIEF_GID}" \
        --create-home --shell /usr/sbin/nologin rebrief

COPY --from=builder /opt/venv /opt/venv

ENV PATH="/opt/venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

USER rebrief

LABEL org.opencontainers.image.source="https://github.com/neracu/rebrief" \
    org.opencontainers.image.description="rebrief CLI for repository scanning and REBRIEF report generation" \
    org.opencontainers.image.licenses="MIT"

ENTRYPOINT ["rebrief"]
CMD ["scan", "."]
