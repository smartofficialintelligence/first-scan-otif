# Cloud Monitoring dashboard for serving + ML signals.
# Instantiated only when enable_monitoring=true. Local demos use
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
            title = "Cloud Run request latency (p95)"
            xyChart = {
              dataSets = [{
                timeSeriesQuery = {
                  timeSeriesFilter = {
                    filter = "${local.run_filter} metric.type=\"run.googleapis.com/request_latencies\""
                    aggregation = {
                      alignmentPeriod = "60s"
                      # Distribution metric: p95 must be computed per series
                      # (ALIGN_DELTA + cross-series p95 plots garbage at idle).
                      perSeriesAligner   = "ALIGN_PERCENTILE_95"
                      crossSeriesReducer = "REDUCE_MEAN"
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
            text = {
              content = "Service: volume, error rate, p95 latency.\nML: feature PSI, high-band mix, stale features, delayed-label PR-AUC.\nDrift alarms do not auto-retrain. Quality uses released labels only.\nSimulated ops (action mix, late→on-time, spend) are local: make decision-eval → artifacts/decision_impact.md. Not this dashboard."
              format  = "MARKDOWN"
            }
          }
        }
      ]
    }
  })
}

# Service-health alert policies. Deliberately no notification channels: these
# raise incidents in Cloud Monitoring, which is the demonstrable part without a
# paid pager. ML-quality alarms (drift PSI, delayed-label PR-AUC) stay local
# JSON by design — they are computed from replay, not from Cloud Run metrics.
resource "google_monitoring_alert_policy" "error_rate" {
  project      = var.project_id
  display_name = "${var.name_prefix} Cloud Run 5xx rate"
  combiner     = "OR"

  conditions {
    display_name = "5xx responses over 5 minutes"
    condition_threshold {
      filter = join(" ", [
        local.run_filter,
        "metric.type=\"run.googleapis.com/request_count\"",
        "metric.labels.response_code_class=\"5xx\"",
      ])
      comparison      = "COMPARISON_GT"
      threshold_value = 0
      duration        = "300s"
      aggregations {
        alignment_period   = "300s"
        per_series_aligner = "ALIGN_RATE"
      }
    }
  }

  documentation {
    content = join("\n", [
      "Cloud Run is returning 5xx. Check the revision's /ready endpoint: it",
      "fails when the champion joblib did not load, which serves 503s.",
      "Feast lookups fail open and should NOT surface here.",
    ])
    mime_type = "text/markdown"
  }
}

resource "google_monitoring_alert_policy" "latency_p95" {
  project      = var.project_id
  display_name = "${var.name_prefix} Cloud Run p95 latency"
  combiner     = "OR"

  conditions {
    display_name = "p95 request latency above 2s"
    condition_threshold {
      filter = join(" ", [
        local.run_filter,
        "metric.type=\"run.googleapis.com/request_latencies\"",
      ])
      comparison      = "COMPARISON_GT"
      threshold_value = 2000
      duration        = "300s"
      aggregations {
        alignment_period   = "300s"
        per_series_aligner = "ALIGN_PERCENTILE_95"
      }
    }
  }

  documentation {
    content = join("\n", [
      "p95 latency above 2s. Scale-to-zero cold starts dominate low-traffic",
      "windows; sustained breaches mean the model or SHAP path is slow.",
    ])
    mime_type = "text/markdown"
  }
}

output "dashboard_id" {
  value = google_monitoring_dashboard.olist.id
}

output "alert_policy_ids" {
  value = [
    google_monitoring_alert_policy.error_rate.id,
    google_monitoring_alert_policy.latency_p95.id,
  ]
}
