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

resource "google_cloud_run_v2_service" "api" {
  name     = var.name
  location = var.region
  project  = var.project_id

  template {
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
    }
    scaling {
      min_instance_count = 0
      max_instance_count = 2
    }
  }

  ingress = "INGRESS_TRAFFIC_ALL"
}

output "service_name" {
  value = google_cloud_run_v2_service.api.name
}

output "uri" {
  value = try(google_cloud_run_v2_service.api.uri, null)
}
