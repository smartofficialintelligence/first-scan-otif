# Artifact Registry for Cloud Run images (cheap idle; keep across on/off).

variable "project_id" {
  type        = string
  description = "GCP project id"
}

variable "region" {
  type        = string
  description = "Registry location"
  default     = "us-central1"
}

variable "repository_id" {
  type        = string
  description = "Artifact Registry repository id"
  default     = "olist-ml"
}

data "google_project" "current" {
  project_id = var.project_id
}

resource "google_artifact_registry_repository" "images" {
  project       = var.project_id
  location      = var.region
  repository_id = var.repository_id
  description   = "Olist ML API images"
  format        = "DOCKER"
}

# Cloud Run service agent pulls during deploy; default compute SA runs the revision.
resource "google_artifact_registry_repository_iam_member" "cloudrun_agent" {
  project    = var.project_id
  location   = var.region
  repository = google_artifact_registry_repository.images.repository_id
  role       = "roles/artifactregistry.reader"
  member     = "serviceAccount:service-${data.google_project.current.number}@serverless-robot-prod.iam.gserviceaccount.com"
}

resource "google_artifact_registry_repository_iam_member" "compute_default" {
  project    = var.project_id
  location   = var.region
  repository = google_artifact_registry_repository.images.repository_id
  role       = "roles/artifactregistry.reader"
  member     = "serviceAccount:${data.google_project.current.number}-compute@developer.gserviceaccount.com"
}

output "repository" {
  value = google_artifact_registry_repository.images.name
}

output "image_base" {
  value = "${var.region}-docker.pkg.dev/${var.project_id}/${var.repository_id}"
}
