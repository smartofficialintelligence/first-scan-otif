variable "project_id" { type = string }
variable "name_prefix" { type = string }
variable "location" { type = string }

resource "google_storage_bucket" "raw" {
  name                        = "${var.name_prefix}-raw-${var.project_id}"
  location                    = var.location
  force_destroy               = true
  uniform_bucket_level_access = true
  labels = {
    project = "olist-ml"
  }
  lifecycle_rule {
    condition {
      age = 30
    }
    action {
      type = "Delete"
    }
  }
}

output "raw_bucket_name" {
  value = google_storage_bucket.raw.name
}
