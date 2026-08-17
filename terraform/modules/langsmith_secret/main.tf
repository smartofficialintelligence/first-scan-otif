# LangSmith API key in Secret Manager — create from tfvars or reference existing.

variable "project_id" {
  type        = string
  description = "GCP project id"
}

variable "secret_id" {
  type        = string
  description = "Secret Manager secret short name"
  default     = "langsmith-api-key"
}

variable "secret_data" {
  type        = string
  description = "Raw LangSmith API key. When set, Terraform creates/updates the secret version."
  sensitive   = true
  default     = null
}

resource "google_secret_manager_secret" "managed" {
  count = local.manage_secret ? 1 : 0

  project   = var.project_id
  secret_id = var.secret_id

  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "managed" {
  count = local.manage_secret ? 1 : 0

  secret      = google_secret_manager_secret.managed[0].id
  secret_data = var.secret_data
}

data "google_secret_manager_secret" "existing" {
  count = local.manage_secret ? 0 : 1

  project   = var.project_id
  secret_id = var.secret_id
}

locals {
  manage_secret      = var.secret_data != null && var.secret_data != ""
  secret_resource_id = local.manage_secret ? google_secret_manager_secret.managed[0].id : data.google_secret_manager_secret.existing[0].id
}

output "secret_resource_id" {
  value       = local.secret_resource_id
  description = "Full Secret Manager resource id for IAM + Cloud Run mounts"
}

output "secret_id" {
  value = var.secret_id
}
