# Cloud Monitoring dashboard for serving + ML signals.
# Instantiated only when enable_monitoring=true (H7 apply). Local demos use
# artifacts/monitoring_dashboard.json instead.

variable "project_id" {
  type        = string
  description = "GCP project id"
}

variable "name_prefix" {
  type        = string
  description = "Resource name prefix (Cloud Run service is name_prefix-api)"
}

variable "cloud_run_service" {
  type        = string
  description = "Cloud Run service name to filter request metrics"
  default     = ""
}

locals {
  service_name = var.cloud_run_service != "" ? var.cloud_run_service : "${var.name_prefix}-api"
  run_filter   = "resource.type=\"cloud_run_revision\" resource.labels.service_name=\"${local.service_name}\""
}

resource "google_monitoring_dashboard" "olist" {
  project = var.project_id

  dashboard_json = jsonencode({
    displayName = "${var.name_prefix} serving and ML"
    mosaicLayout = {
      columns = 12
      tiles = [
        {
          width  = 6
          height = 4
          widget = {
            title = "Cloud Run request count"
            xyChart = {
              dataSets = [{
                timeSeriesQuery = {
                  timeSeriesFilter = {
                    filter = "${local.run_filter} metric.type=\"run.googleapis.com/request_count\""
                    aggregation = {
                      alignmentPeriod  = "60s"
                      perSeriesAligner = "ALIGN_RATE"
                    }
                  }
                }
                plotType = "LINE"
              }]
            }
          }
        },
        {
          xPos   = 6
          width  = 6
          height = 4
          widget = {
            title = "Cloud Run request latency"
            xyChart = {
              dataSets = [{
                timeSeriesQuery = {
                  timeSeriesFilter = {
                    filter = "${local.run_filter} metric.type=\"run.googleapis.com/request_latencies\""
                    aggregation = {
                      alignmentPeriod    = "60s"
                      perSeriesAligner   = "ALIGN_DELTA"
                      crossSeriesReducer = "REDUCE_PERCENTILE_95"
                    }
                  }
                }
                plotType = "LINE"
              }]
            }
          }
        },
        {
          yPos   = 4
          width  = 6
          height = 4
          widget = {
            title = "Cloud Run billable instance time"
            xyChart = {
              dataSets = [{
                timeSeriesQuery = {
                  timeSeriesFilter = {
                    filter = "${local.run_filter} metric.type=\"run.googleapis.com/container/billable_instance_time\""
                    aggregation = {
                      alignmentPeriod  = "60s"
                      perSeriesAligner = "ALIGN_RATE"
                    }
                  }
                }
                plotType = "LINE"
              }]
            }
          }
        },
        {
          xPos   = 6
          yPos   = 4
          width  = 6
          height = 4
          widget = {
            title = "ML signals (local export + this dashboard)"
            text  = {
              content = "Service: volume, error rate, p95 latency.\nML: feature PSI, high-band mix, stale features, delayed-label PR-AUC.\nDrift alarms do not auto-retrain (H5). Quality uses released labels only.\nLocal: make export-monitoring → artifacts/monitoring_dashboard.json"
              format  = "MARKDOWN"
            }
          }
        }
      ]
    }
  })
}

output "dashboard_id" {
  value = google_monitoring_dashboard.olist.id
}
