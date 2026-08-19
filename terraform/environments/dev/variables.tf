variable "project_id" {
  type        = string
  description = "GCP project id"
}

variable "region" {
  type        = string
  description = "Primary region"
  default     = "us-central1"
}

variable "location" {
  type        = string
  description = "BigQuery dataset location"
  default     = "US"
}

variable "name_prefix" {
  type        = string
  description = "Resource name prefix"
  default     = "olist-ml"
}

variable "enable_cloud_run" {
  type        = bool
  description = "When true, deploy the API on Cloud Run (min instances 0). Vertex is separate."
  default     = false
}

variable "enable_vertex_endpoint" {
  type        = bool
  description = "When true, create an empty Vertex AI endpoint. Off by default — the API scores a joblib in Cloud Run, not this endpoint."
  default     = false
}

variable "enable_monitoring" {
  type        = bool
  description = "When true, create the Cloud Monitoring dashboard for the Cloud Run service."
  default     = false
}

variable "serving_image" {
  type        = string
  description = "Container image for Cloud Run when enable_cloud_run=true"
  default     = "us-docker.pkg.dev/cloudrun/container/hello"
}

variable "invoker_sa_email" {
  type        = string
  description = "Service account email granted roles/run.invoker on Cloud Run"
  default     = ""
}

variable "extra_invoker_members" {
  type        = list(string)
  description = "Additional Cloud Run invokers (user: or group:). Laptop testing."
  default     = ["user:mr.kuehn@gmail.com"]
}

variable "enable_serving" {
  type        = bool
  description = "Deprecated alias for enable_cloud_run (does not create Vertex)."
  default     = false
}
