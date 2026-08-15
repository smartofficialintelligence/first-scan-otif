variable "project_id" { type = string }
variable "location" { type = string }

resource "google_bigquery_dataset" "raw" {
  dataset_id                 = "olist_raw"
  friendly_name              = "Olist raw"
  description                = "Raw Olist tables loaded from GCS/CSV"
  location                   = var.location
  delete_contents_on_destroy = true
  labels = {
    project = "olist-ml"
    tier    = "raw"
  }
}

resource "google_bigquery_dataset" "dbt" {
  dataset_id                 = "olist_dbt"
  friendly_name              = "Olist dbt default"
  description                = "dbt target dataset (models land in staging/intermediate/ml schemas)"
  location                   = var.location
  delete_contents_on_destroy = true
}

resource "google_bigquery_dataset" "staging" {
  dataset_id                 = "staging"
  location                   = var.location
  delete_contents_on_destroy = true
}

resource "google_bigquery_dataset" "intermediate" {
  dataset_id                 = "intermediate"
  location                   = var.location
  delete_contents_on_destroy = true
}

resource "google_bigquery_dataset" "ml" {
  dataset_id                 = "ml"
  location                   = var.location
  delete_contents_on_destroy = true
}

output "dataset_ids" {
  value = [
    google_bigquery_dataset.raw.dataset_id,
    google_bigquery_dataset.dbt.dataset_id,
    google_bigquery_dataset.staging.dataset_id,
    google_bigquery_dataset.intermediate.dataset_id,
    google_bigquery_dataset.ml.dataset_id,
  ]
}
