FROM python:3.12-slim AS base

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY pyproject.toml uv.lock README.md ./
COPY src ./src
COPY config ./config
COPY feature_repo ./feature_repo
# Feast online store + registry when `make feast-apply` has run; the .gitkeep
# keeps this path present (and the lookup failing open) when it has not.
COPY data/feast ./data/feast

# feature_store.serving.yaml (online store only) ships alongside the full
# config; FeastSellerClient prefers it, so the container never imports the
# BigQuery offline driver and local runs take the identical path.

# mcp is a core dep so Streamable HTTP (/mcp) is in the same image as REST.
# `feast` = SQLite online lookups in the request path; `agent` = the LangGraph
# review graph. Both are named in the README stack, so both ship — the gcp
# extra (BigQuery, dbt, Vertex) deliberately does not.
RUN mkdir -p artifacts && uv sync --frozen --no-dev --extra feast --extra agent

EXPOSE 8080
CMD ["uvicorn", "olist_ml.api.app:app", "--host", "0.0.0.0", "--port", "8080"]

# Production image: champion artifact baked in (not used by CI).
FROM base AS serving
COPY artifacts/model.joblib artifacts/model_meta.json ./artifacts/
