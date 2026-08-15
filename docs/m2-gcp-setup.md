# Milestone 2 setup (BigQuery + dbt)

## Blocker in this Cloud Agent

Other Cursor projects’ GCP credentials are **not** shared automatically. This run has:

- no linked environment
- no `gcloud` SDK installed yet
- no `GCP_PROJECT_ID` / SA JSON secrets injected

Secrets requested via Cursor environment setup:

- `GCP_PROJECT_ID`
- `GOOGLE_APPLICATION_CREDENTIALS_JSON`

## After secrets are added

```bash
# 1) materialize key file (gitignored)
source <(bash scripts/materialize_gcp_creds.sh)

# 2) install gcloud if missing, then:
# gcloud auth activate-service-account --key-file="$GOOGLE_APPLICATION_CREDENTIALS"
# gcloud config set project "$GCP_PROJECT_ID"

# 3) copy dbt profile
cp dbt/profiles.yml.example dbt/profiles.yml

# 4) H7: review terraform plan before apply
cd terraform/environments/dev
cp terraform.tfvars.example terraform.tfvars   # set project_id
terraform init
terraform plan
# ONLY after human H7 approval:
# terraform apply

# 5) load + transform
make download-olist   # or use fixtures first
make ingest-bq        # or make ingest-fixtures-bq
cd dbt && dbt build --profiles-dir .
```

## What is already in the repo

- dbt staging / intermediate / ml marts with PIT seller history + leakage test
- Terraform modules: BigQuery datasets, GCS raw bucket, dbt runner SA + IAM
- `scripts/ingest_olist.py`
