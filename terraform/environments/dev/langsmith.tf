# LangSmith secret + Cloud Run mount — fully Terraform-managed (no gcloud wiring).

module "langsmith_secret" {
  count  = var.enable_serving ? 1 : 0
  source = "../../modules/langsmith_secret"

  project_id  = var.project_id
  secret_id   = var.langsmith_secret_id
  secret_data = var.langsmith_api_key
}
