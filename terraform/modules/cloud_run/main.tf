# Cloud Run v2 service (scaffold — do not apply without H7 / enable_serving).

variable "project_id" {
  type        = string
  description = "GCP project id"
}

variable "region" {
  type        = string
  description = "Cloud Run region"
  default     = "us-central1"
}

variable "name" {
  type        = string
  description = "Cloud Run service name"
  default     = "olist-ml-api"
}

variable "image" {
  type        = string
  description = "Container image URI"
}

variable "service_account_email" {
  type        = string
  description = "Runtime service account for Cloud Run (needs secretmanager.secretAccessor)"
}

variable "langsmith_secret_resource_id" {
  type        = string
  description = "Full Secret Manager resource id for LangSmith API key"
}

variable "langsmith_project" {
  type        = string
  description = "LangSmith / LangChain project name for traces"
  default     = "olist-ml-agent"
}

resource "google_secret_manager_secret_iam_member" "cloud_run_langsmith" {
  secret_id = var.langsmith_secret_resource_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${var.service_account_email}"
}

resource "google_cloud_run_v2_service" "api" {
  name     = var.name
  location = var.region
  project  = var.project_id

  template {
    service_account = var.service_account_email

    containers {
      image = var.image
      ports {
        container_port = 8080
      }
      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
      }
      env {
        name = "LANGSMITH_API_KEY"
        value_source {
          secret_key_ref {
            secret  = var.langsmith_secret_resource_id
            version = "latest"
          }
        }
      }
      env {
        name  = "LANGCHAIN_PROJECT"
        value = var.langsmith_project
      }
      env {
        name  = "LANGCHAIN_TRACING_V2"
        value = "true"
      }
    }
    scaling {
      min_instance_count = 0
      max_instance_count = 2
    }
  }

  ingress = "INGRESS_TRAFFIC_ALL"

  depends_on = [google_secret_manager_secret_iam_member.cloud_run_langsmith]
}

output "service_name" {
  value = google_cloud_run_v2_service.api.name
}

output "uri" {
  value = try(google_cloud_run_v2_service.api.uri, null)
}
