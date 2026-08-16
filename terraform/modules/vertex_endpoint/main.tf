# Vertex AI Endpoint scaffold.
#
# Intended resources (when enable_serving=true and H7 approved):
#   - google_vertex_ai_endpoint (or google_vertex_ai_endpoint_with_model_garden_config)
#   - Model upload / deploy via gcloud or aiplatform SDK (often outside Terraform)
#   - Optional: google_vertex_ai_endpoint_iam_member for Cloud Run invoker SA
#
# Provider shapes for Vertex vary; this module exposes variables + outputs so
# environments can wire serving without applying undeployed resources by default.
# Uncomment the resource below when ready to manage the endpoint in Terraform.

variable "project_id" {
  type        = string
  description = "GCP project id"
}

variable "region" {
  type        = string
  description = "Vertex AI region"
  default     = "us-central1"
}

variable "display_name" {
  type        = string
  description = "Endpoint display name"
  default     = "olist-ml-late-delivery"
}

variable "endpoint_id" {
  type        = string
  description = "Optional explicit endpoint id (resource id)"
  default     = "olist-ml-endpoint"
}

# Minimal Vertex endpoint resource. Safe when module is only instantiated
# behind enable_serving=true; still requires APIs enabled and IAM.
resource "google_vertex_ai_endpoint" "main" {
  name         = var.endpoint_id
  display_name = var.display_name
  location     = var.region
  project      = var.project_id
  description  = "Olist late-delivery risk endpoint (scaffold)"
  labels = {
    project = "olist-ml"
  }
}

output "endpoint_id" {
  value = google_vertex_ai_endpoint.main.name
}

output "endpoint_name" {
  value = google_vertex_ai_endpoint.main.id
}

output "region" {
  value = var.region
}
