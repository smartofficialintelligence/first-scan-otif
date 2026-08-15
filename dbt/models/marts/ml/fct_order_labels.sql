{{ config(alias='fct_order_labels') }}

-- Label mart. Delivery timestamps are LABEL-ONLY — never join into features as predictors.
select
  order_id,
  prediction_ts,
  order_delivered_customer_date,
  order_estimated_delivery_date,
  case
    when order_delivered_customer_date is null then null
    when order_estimated_delivery_date is null then null
    when order_delivered_customer_date > order_estimated_delivery_date then 1
    else 0
  end as late_delivery
from {{ ref('int_order_summary') }}
where order_delivered_customer_date is not null
  and order_estimated_delivery_date is not null
  and prediction_ts is not null
