variable "project_id" { type = string }
variable "name_prefix" { type = string }

resource "google_service_account" "dbt_runner" {
  account_id   = "${var.name_prefix}-dbt"
  display_name = "Olist ML dbt runner"
}

resource "google_project_iam_member" "bq_job_user" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.dbt_runner.email}"
}

resource "google_project_iam_member" "bq_data_editor" {
  project = var.project_id
  role    = "roles/bigquery.dataEditor"
  member  = "serviceAccount:${google_service_account.dbt_runner.email}"
}

resource "google_project_iam_member" "storage_object_admin" {
  project = var.project_id
  role    = "roles/storage.objectAdmin"
  member  = "serviceAccount:${google_service_account.dbt_runner.email}"
}

output "dbt_runner_email" {
  value = google_service_account.dbt_runner.email
}
