# Shared image for core-api, core-worker, core-executor. The compose command
# picks the entrypoint module per service.
FROM python:3.12.13-slim-bookworm

WORKDIR /app

COPY apps/core/pyproject.toml ./
COPY apps/core/aegis ./aegis

RUN pip install --no-cache-dir .

EXPOSE 8080

CMD ["python", "-m", "uvicorn", "aegis.api:app", "--host", "0.0.0.0", "--port", "8080"]
