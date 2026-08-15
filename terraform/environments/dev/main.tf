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

output "raw_bucket" {
  value = module.storage.raw_bucket_name
}

output "datasets" {
  value = module.bigquery.dataset_ids
}

output "dbt_runner_email" {
  value = module.iam.dbt_runner_email
}
