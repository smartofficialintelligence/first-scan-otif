.PHONY: sync lint typecheck test train-local serve-local smoke-local fixtures download-olist

sync:
	uv sync --all-extras

lint:
	uv run ruff check src tests scripts

typecheck:
	uv run mypy src/olist_ml

test:
	uv run pytest -q

fixtures:
	uv run python scripts/generate_fixtures.py

download-olist:
	uv run python scripts/download_olist.py --dest data/raw

train-local:
	uv run olist-train --data-dir data/fixtures --trials 5

train-olist:
	uv run olist-train --data-dir data/raw --trials 25

serve-local:
	uv run uvicorn olist_ml.api.app:app --host 0.0.0.0 --port 8080

smoke-local:
	curl -sf http://127.0.0.1:8080/health
	curl -sf http://127.0.0.1:8080/ready
