{{ config(alias='fct_order_labels') }}

-- Label mart. Customer delivery is LABEL-ONLY — never join into features as predictors.
-- Primary target (ADR 0006): promise_miss at first carrier scan (handoff_ts).
select
  order_id,
  prediction_ts,
  handoff_ts,
  order_delivered_customer_date,
  order_estimated_delivery_date,
  timestamp_diff(order_delivered_customer_date, prediction_ts, hour) / 24.0 as delivery_days,
  case
    when order_delivered_customer_date is null then null
    when order_estimated_delivery_date is null then null
    when order_delivered_customer_date > order_estimated_delivery_date then 1
    else 0
  end as promise_miss,
  case
    when order_delivered_customer_date is null then null
    when prediction_ts is null then null
    when timestamp_diff(order_delivered_customer_date, prediction_ts, hour) / 24.0 > 14
      then 1
    else 0
  end as long_delivery
from {{ ref('int_order_summary') }}
where order_delivered_customer_date is not null
  and order_estimated_delivery_date is not null
  and prediction_ts is not null
  and handoff_ts is not null
