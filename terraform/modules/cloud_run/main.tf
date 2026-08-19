# Cloud Run v2 API. Instantiated only when enable_cloud_run=true.
# min_instance_count=0 so idle cost is near zero after traffic stops.

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
  description = "Container image URI (Artifact Registry)"
}

variable "invoker_sa_email" {
  type        = string
  description = "Service account that may invoke the service (identity-token smoke)."
  default     = ""
}

variable "extra_invoker_members" {
  type        = list(string)
  description = "Additional IAM members granted roles/run.invoker (e.g. user:you@gmail.com)."
  default     = []
}

resource "google_cloud_run_v2_service" "api" {
  name     = var.name
  location = var.region
  project  = var.project_id
  ingress  = "INGRESS_TRAFFIC_ALL"

  labels = {
    app     = "olist-ml"
    purpose = "serving-proof"
  }

  template {
    timeout                          = "60s"
    max_instance_request_concurrency = 40
    scaling {
      min_instance_count = 0
      max_instance_count = 2
    }
    containers {
      image = var.image
      ports {
        container_port = 8080
      }
      env {
        name  = "ENVIRONMENT"
        value = "gcp"
      }
      env {
        name  = "MODEL_PATH"
        value = "/app/artifacts/model.joblib"
      }
      env {
        name  = "MODEL_META_PATH"
        value = "/app/artifacts/model_meta.json"
      }
      env {
        name  = "AUTH_MODE"
        value = "off"
      }
      resources {
        limits = {
          cpu    = "1"
          memory = "1Gi"
        }
        cpu_idle          = true
        startup_cpu_boost = true
      }
      startup_probe {
        http_get {
          # /ready verifies the model artifact actually loaded; /health is a
          # static ok and would pass a revision that can only serve 503s.
          path = "/ready"
          port = 8080
        }
        initial_delay_seconds = 10
        timeout_seconds       = 5
        period_seconds        = 5
        failure_threshold     = 24
      }
    }
  }

  timeouts {
    create = "10m"
    update = "10m"
    delete = "10m"
  }
}

resource "google_cloud_run_v2_service_iam_member" "invoker" {
  count = var.invoker_sa_email != "" ? 1 : 0

  project  = var.project_id
  location = google_cloud_run_v2_service.api.location
  name     = google_cloud_run_v2_service.api.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${var.invoker_sa_email}"
}

resource "google_cloud_run_v2_service_iam_member" "extra_invokers" {
  for_each = toset(var.extra_invoker_members)

  project  = var.project_id
  location = google_cloud_run_v2_service.api.location
  name     = google_cloud_run_v2_service.api.name
  role     = "roles/run.invoker"
  member   = each.value
}

output "service_name" {
  value = google_cloud_run_v2_service.api.name
}

output "uri" {
  value = try(google_cloud_run_v2_service.api.uri, null)
}
