{{ config(alias='int_seller_history', materialized='table') }}

-- Point-in-time seller history: aggregates over prior orders only (closed left).
-- Positive class = long_delivery (>14d). Feature names keep seller_*_late_rate_* for
-- online-contract stability; values are long-delivery rates.
with labeled as (
  select
    order_id,
    seller_id,
    prediction_ts,
    case
      when timestamp_diff(order_delivered_customer_date, prediction_ts, hour) / 24.0 > 14
        then 1
      else 0
    end as long_delivery
  from {{ ref('int_order_summary') }}
  where order_delivered_customer_date is not null
    and order_estimated_delivery_date is not null
    and prediction_ts is not null
    and seller_id is not null
),

priors as (
  select
    cur.order_id,
    cur.seller_id,
    cur.prediction_ts,
    hist.long_delivery as hist_positive,
    hist.prediction_ts as hist_ts
  from labeled cur
  left join labeled hist
    on hist.seller_id = cur.seller_id
   and hist.prediction_ts < cur.prediction_ts
)

select
  order_id,
  seller_id,
  prediction_ts,
  countif(hist_ts >= timestamp_sub(prediction_ts, interval 7 day)) as seller_order_count_7d,
  countif(hist_ts >= timestamp_sub(prediction_ts, interval 30 day)) as seller_order_count_30d,
  countif(hist_ts >= timestamp_sub(prediction_ts, interval 90 day)) as seller_order_count_90d,
  safe_divide(
    countif(hist_ts >= timestamp_sub(prediction_ts, interval 7 day) and hist_positive = 1),
    nullif(countif(hist_ts >= timestamp_sub(prediction_ts, interval 7 day)), 0)
  ) as seller_late_rate_7d,
  safe_divide(
    countif(hist_ts >= timestamp_sub(prediction_ts, interval 30 day) and hist_positive = 1),
    nullif(countif(hist_ts >= timestamp_sub(prediction_ts, interval 30 day)), 0)
  ) as seller_late_rate_30d,
  safe_divide(
    countif(hist_ts >= timestamp_sub(prediction_ts, interval 90 day) and hist_positive = 1),
    nullif(countif(hist_ts >= timestamp_sub(prediction_ts, interval 90 day)), 0)
  ) as seller_late_rate_90d
from priors
group by 1, 2, 3
