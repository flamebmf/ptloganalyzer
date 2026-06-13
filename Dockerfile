# ============================================================
# ptloganalyzer — Base image (dependencies only)
# Пересобирается только при изменении requirements.txt
# ============================================================
FROM python:3.12-slim AS base
# Copyright (c) 2026 PlurumTech.com
# SPDX-License-Identifier: LicenseRef-Personal-Use-Only

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc curl ca-certificates && \
    update-ca-certificates --fresh 2>/dev/null && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
# Offline mode: PIP_NO_INDEX=true PIP_FIND_LINKS=/tmp/wheelhouse
# Online mode:  PIP_INDEX_URL=... PIP_TRUSTED_HOST=...
ARG PIP_INDEX_URL=https://pypi.org/simple/
ARG PIP_TRUSTED_HOST=
ARG PIP_NO_INDEX=false
ARG PIP_FIND_LINKS=
RUN PIP_OPTS="--no-cache-dir --default-timeout=120 --index-url $PIP_INDEX_URL" && \
    if [ "$PIP_NO_INDEX" = "true" ] && [ -d "${PIP_FIND_LINKS:-/dev/null}" ]; then \
      PIP_OPTS="--no-cache-dir --no-index --find-links $PIP_FIND_LINKS"; \
    elif [ -n "$PIP_TRUSTED_HOST" ]; then \
      PIP_OPTS="$PIP_OPTS --trusted-host $PIP_TRUSTED_HOST"; \
    fi && \
    pip install $PIP_OPTS -r requirements.txt

# ── App image (наследует base) ──
FROM base AS app

ARG VERSION=0.0.0
ARG BUILD_DATE=unknown
ARG COMMIT=unknown

LABEL app="ptloganalyzer" \
      version="$VERSION" \
      build-date="$BUILD_DATE" \
      commit="$COMMIT" \
      vendor="Plurumtech.com" \
      description="Log analysis system with AI summarization"

COPY VERSION /app/VERSION
COPY app/ ./app/

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
