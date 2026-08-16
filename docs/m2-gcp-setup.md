# Milestone 2 setup (BigQuery + dbt)

## Credentials on Cloud Agents

Required Cursor environment secrets (injected at pod boot only):

| Secret | Expected |
|---|---|
| `GCP_PROJECT_ID` | `production-ml-model` |
| `GOOGLE_APPLICATION_CREDENTIALS_JSON` | Full service-account JSON as one string |

This repo ships `.cursor/environment.json` so Cloud Agents install `uv`, Terraform, and `gcloud`.

**Important:** secrets saved in the Cursor UI are **not** visible to a run whose `environment-info` reports `environment: null`. Start (or restart) the agent with the saved environment that holds those secrets. Do not paste the SA JSON into chat.

Sanity check:

```bash
bash scripts/check_gcp_env.sh
# expect: GCP_PROJECT_ID set (demo project) and JSON present
# note: materialize script trims accidental whitespace on the project id
```

## After secrets are injected

```bash
# 1) materialize key file (gitignored); source-safe (exports only on stdout)
source <(bash scripts/materialize_gcp_creds.sh)

# 2) activate SA + project
export PATH="/opt/google-cloud-sdk/bin:$PATH"
gcloud auth activate-service-account --key-file="$GOOGLE_APPLICATION_CREDENTIALS"
gcloud config set project "$GCP_PROJECT_ID"

# 3) copy dbt profile
cp dbt/profiles.yml.example dbt/profiles.yml

# 4) H7: review terraform plan before apply
cd terraform/environments/dev
cp terraform.tfvars.example terraform.tfvars
terraform init
terraform plan -out=tfplan
# ONLY after human H7 approval:
# terraform apply tfplan

# 5) load + transform (fixtures work without apply; ingest creates olist_raw)
make download-olist   # or use fixtures first
make ingest-fixtures-bq   # safe smoke path
# make ingest-bq          # full Olist
cd dbt && uv run dbt build --profiles-dir .
```

## Dataset naming

Terraform owns these BigQuery datasets:

| Dataset | Role |
|---|---|
| `olist_raw` | Landing zone (ingest) |
| `olist_dbt` | dbt profile default (unused by models with `+schema`) |
| `staging` / `intermediate` / `ml` | dbt model datasets |

`dbt/macros/generate_schema_name.sql` maps `+schema: staging` → dataset `staging` (not `olist_dbt_staging`).

## Makefile helpers

- `make m2-env-check` — verify secrets without printing key material
- `make tf-fmt` / `make tf-validate` — offline Terraform checks
- `make tf-plan` — live plan (needs secrets; does **not** apply)
- `make ingest-fixtures-bq` / `make ingest-bq` — load raw CSVs to BQ
- `make dbt-build` — `dbt build` against BigQuery

## What is already in the repo

- dbt staging / intermediate / ml marts with PIT seller history + leakage test
- Terraform modules: BigQuery datasets, GCS raw bucket, dbt runner SA + IAM
- `scripts/ingest_olist.py`, `scripts/materialize_gcp_creds.sh`, `scripts/check_gcp_env.sh`
