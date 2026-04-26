FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DOMINION_ENV=container

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        git \
        curl \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

FROM base AS builder
COPY pyproject.toml requirements.txt README.md ./
COPY aphelion ./aphelion
COPY mt5pipe ./mt5pipe
COPY machinelearning ./machinelearning
RUN python -m venv /opt/venv \
    && . /opt/venv/bin/activate \
    && pip install --upgrade pip \
    && pip install -e ".[ml,dev]"

FROM base AS runtime
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY aphelion ./aphelion
COPY mt5pipe ./mt5pipe
COPY machinelearning ./machinelearning
COPY scripts ./scripts
COPY config ./config
COPY pyproject.toml pytest.ini README.md ./

RUN groupadd -g 10001 dominion && useradd -u 10001 -g dominion -s /bin/bash -m dominion \
    && mkdir -p /app/data /app/logs /app/models \
    && chown -R dominion:dominion /app
USER dominion

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import aphelion, mt5pipe, machinelearning" || exit 1

EXPOSE 8000

CMD ["python", "-m", "aphelion"]
