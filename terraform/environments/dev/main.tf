terraform {
  required_version = ">= 1.5.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.40"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

module "storage" {
  source      = "../../modules/storage"
  project_id  = var.project_id
  name_prefix = var.name_prefix
  location    = var.region
}

module "bigquery" {
  source     = "../../modules/bigquery"
  project_id = var.project_id
  location   = var.location
}

module "iam" {
  source      = "../../modules/iam"
  project_id  = var.project_id
  name_prefix = var.name_prefix
}

module "cloud_run" {
  count  = var.enable_serving ? 1 : 0
  source = "../../modules/cloud_run"

  project_id                   = var.project_id
  region                       = var.region
  name                         = "${var.name_prefix}-api"
  image                        = var.serving_image
  service_account_email        = module.iam.api_runner_email
  langsmith_secret_resource_id = module.langsmith_secret[0].secret_resource_id
  langsmith_project            = var.langsmith_project

  depends_on = [module.langsmith_secret]
}

module "vertex_endpoint" {
  count  = var.enable_serving ? 1 : 0
  source = "../../modules/vertex_endpoint"

  project_id   = var.project_id
  region       = var.region
  display_name = "${var.name_prefix}-late-delivery"
  endpoint_id  = "${var.name_prefix}-endpoint"
}

output "raw_bucket" {
  value = module.storage.raw_bucket_name
}

output "datasets" {
  value = module.bigquery.dataset_ids
}

output "dbt_runner_email" {
  value = module.iam.dbt_runner_email
}

output "api_runner_email" {
  value = module.iam.api_runner_email
}

output "cloud_run_uri" {
  value = var.enable_serving ? module.cloud_run[0].uri : null
}

output "vertex_endpoint_id" {
  value = var.enable_serving ? module.vertex_endpoint[0].endpoint_id : null
}
