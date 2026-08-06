# Shared image for core-api, core-worker, core-executor. The compose command
# picks the entrypoint module per service.
FROM python:3.12.13-slim-bookworm

# git: core-worker's list_recent_changes diagnosis tool reads commit
# history from the repo mounted read-only at /repo (deploy/docker-compose.yml).
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY apps/core/pyproject.toml ./
COPY apps/core/aegis ./aegis
COPY apps/core/fixtures ./fixtures
COPY scripts/verify_chain.py ./scripts/verify_chain.py

RUN pip install --no-cache-dir .

EXPOSE 8080

CMD ["python", "-m", "uvicorn", "aegis.api:app", "--host", "0.0.0.0", "--port", "8080"]
