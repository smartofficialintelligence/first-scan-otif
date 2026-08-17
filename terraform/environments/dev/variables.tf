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

variable "langsmith_secret_id" {
  type        = string
  description = "Secret Manager secret id (short name) with raw LangSmith API key"
  default     = "langsmith-api-key"
}

variable "langsmith_project" {
  type        = string
  description = "LangSmith project for agent traces"
  default     = "olist-ml-agent"
}

variable "langsmith_api_key" {
  type        = string
  description = "Optional raw LangSmith API key — when set, Terraform writes SM secret version. Omit to use existing secret."
  sensitive   = true
  default     = null
}
