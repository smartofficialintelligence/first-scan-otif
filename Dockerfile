FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY pyproject.toml README.md ./
COPY src ./src
RUN mkdir -p artifacts && uv sync --no-dev

EXPOSE 8080
CMD ["uv", "run", "uvicorn", "olist_ml.api.app:app", "--host", "0.0.0.0", "--port", "8080"]
