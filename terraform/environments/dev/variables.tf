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
