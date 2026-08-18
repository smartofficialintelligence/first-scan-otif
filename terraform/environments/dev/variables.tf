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

variable "enable_serving" {
  type        = bool
  description = "When true, instantiate Cloud Run + Vertex endpoint modules (default false for validate-without-serving)."
  default     = false
}

variable "serving_image" {
  type        = string
  description = "Container image for Cloud Run when enable_serving=true"
  default     = "us-docker.pkg.dev/cloudrun/container/hello"
}

variable "enable_monitoring" {
  type        = bool
  description = "When true, instantiate the Cloud Monitoring dashboard module (default false; H7 apply)."
  default     = false
}
