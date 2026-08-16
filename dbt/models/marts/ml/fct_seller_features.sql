{{ config(alias='fct_seller_features', materialized='table') }}

-- Seller features at order grain for Feast (entity=seller_id, ts=prediction_ts).
-- Values are PIT-safe (from int_seller_history); Feast historical retrieval
-- joins on seller_id + event_timestamp for training-time correctness.
select
  seller_id,
  prediction_ts as event_timestamp,
  prediction_ts as feature_timestamp,
  cast(seller_order_count_7d as float64) as seller_order_count_7d,
  cast(seller_order_count_30d as float64) as seller_order_count_30d,
  cast(seller_order_count_90d as float64) as seller_order_count_90d,
  cast(seller_late_rate_7d as float64) as seller_late_rate_7d,
  cast(seller_late_rate_30d as float64) as seller_late_rate_30d,
  cast(seller_late_rate_90d as float64) as seller_late_rate_90d
from {{ ref('fct_order_features') }}
where seller_id is not null
  and prediction_ts is not null
