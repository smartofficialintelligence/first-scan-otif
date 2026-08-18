.PHONY: sync lint typecheck test train-local serve-local smoke-local fixtures download-olist
.PHONY: m2-env-check gcp-auth tf-fmt tf-validate tf-plan dbt-deps dbt-compile dbt-build ingest-bq ingest-fixtures-bq
.PHONY: feast-apply feast-historical feast-parity demo-up demo-down mcp-serve
.PHONY: train-pipeline airflow-train-local replay-baseline canary-bad drift-check teardown-endpoint
.PHONY: demo-decision agent-evals decision-eval demo-decision-api economics-gate overrun-experiment miss-history-experiment short-promise-experiment

export PATH := $(HOME)/.local/bin:/opt/google-cloud-sdk/bin:$(PATH)

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

train-pipeline:
	uv run python scripts/run_train_pipeline.py --data-dir data/fixtures --trials 3

serve-local:
	uv run uvicorn olist_ml.api.app:app --host 0.0.0.0 --port 8080

smoke-local:
	curl -sf http://127.0.0.1:8080/health
	curl -sf http://127.0.0.1:8080/ready

demo-up:
	bash scripts/demo_up.sh

demo-down:
	bash scripts/demo_down.sh

mcp-serve:
	uv run olist-mcp

demo-decision:
	uv run --extra agent python scripts/demo_decision_chain.py

demo-decision-api:
	bash scripts/demo_decision_api.sh

agent-evals:
	uv run --extra agent python evals/run_agent_evals.py

decision-eval:
	uv run python airflow/dags/olist_decision_eval_dag.py

economics-gate:
	uv run python scripts/check_economics_gate.py

overrun-experiment:
	uv run python scripts/experiment_overrun_ranker.py

miss-history-experiment:
	uv run python scripts/experiment_promise_miss_history.py

short-promise-experiment:
	uv run python scripts/experiment_short_promise_miss.py

replay-baseline:
	uv run python scripts/replay_traffic.py --inprocess true --scenario baseline --no-challenger

canary-bad:
	uv run python scripts/create_bad_challenger.py
	uv run python scripts/replay_traffic.py --inprocess true --scenario bad_canary
	uv run python scripts/canary_decide.py

drift-check:
	uv run python airflow/dags/olist_drift_dag.py

airflow-train-local:
	uv run python airflow/dags/olist_train_dag.py --local --data-dir data/fixtures --trials 3

teardown-endpoint:
	uv run python scripts/teardown_endpoint.py

# --- Milestone 2 (requires GCP secrets; do not terraform apply without H7) ---

m2-env-check:
	bash scripts/check_gcp_env.sh

gcp-auth: m2-env-check
	bash -lc 'source <(bash scripts/materialize_gcp_creds.sh) && \
	  gcloud auth activate-service-account --key-file="$$GOOGLE_APPLICATION_CREDENTIALS" && \
	  gcloud config set project "$$GCP_PROJECT_ID"'

tf-fmt:
	terraform -chdir=terraform/environments/dev fmt -recursive

tf-validate:
	terraform -chdir=terraform/environments/dev init -backend=false
	terraform -chdir=terraform/environments/dev validate

tf-plan: m2-env-check
	@test -n "$$GOOGLE_APPLICATION_CREDENTIALS" || (echo "Run: source <(bash scripts/materialize_gcp_creds.sh)" >&2; exit 1)
	cd terraform/environments/dev && \
	  cp -n terraform.tfvars.example terraform.tfvars && \
	  terraform init && \
	  terraform plan -out=tfplan

dbt-deps:
	cd dbt && uv run dbt deps || true

dbt-compile:
	cd dbt && uv run dbt compile --profiles-dir .

dbt-build:
	cd dbt && uv run dbt build --profiles-dir .

ingest-bq:
	uv run python scripts/ingest_olist.py --data-dir data/raw

ingest-fixtures-bq:
	uv run python scripts/ingest_olist.py --data-dir data/fixtures

# --- Milestone 3 (Feast; online = SQLite demo-off; Redis later for demo-on) ---

feast-apply: m2-env-check
	@test -n "$$GOOGLE_APPLICATION_CREDENTIALS" || (echo "Run: source <(bash scripts/materialize_gcp_creds.sh)" >&2; exit 1)
	mkdir -p data/feast
	uv run python scripts/feast_apply_materialize.py --repo feature_repo

feast-historical: m2-env-check
	@test -n "$$GOOGLE_APPLICATION_CREDENTIALS" || (echo "Run: source <(bash scripts/materialize_gcp_creds.sh)" >&2; exit 1)
	uv run python scripts/feast_historical.py

feast-parity: m2-env-check
	@test -n "$$GOOGLE_APPLICATION_CREDENTIALS" || (echo "Run: source <(bash scripts/materialize_gcp_creds.sh)" >&2; exit 1)
	uv run python scripts/feast_parity.py
