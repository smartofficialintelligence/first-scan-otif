{{ config(alias='fct_order_features') }}

select
  s.order_id,
  s.seller_id,
  s.prediction_ts,
  cast(s.purchase_hour as float64) as purchase_hour,
  cast(s.purchase_dow as float64) as purchase_dow,
  cast(s.purchase_month as float64) as purchase_month,
  cast(s.is_weekend as float64) as is_weekend,
  cast(s.item_count as float64) as item_count,
  cast(s.basket_value as float64) as basket_value,
  cast(s.freight_value as float64) as freight_value,
  cast(s.seller_count as float64) as seller_count,
  cast(s.category_count as float64) as category_count,
  cast(coalesce(s.installment_count, 1) as float64) as installment_count,
  cast(s.estimated_delivery_horizon_days as float64) as estimated_delivery_horizon_days,
  cast(coalesce(s.geo_distance_km, 0) as float64) as geo_distance_km,
  lower(coalesce(s.payment_type_primary, 'unknown')) as payment_type_primary,
  coalesce(s.customer_state, 'unknown') as customer_state,
  coalesce(s.seller_state_primary, 'unknown') as seller_state_primary,
  coalesce(h.seller_order_count_7d, 0) as seller_order_count_7d,
  coalesce(h.seller_order_count_30d, 0) as seller_order_count_30d,
  coalesce(h.seller_order_count_90d, 0) as seller_order_count_90d,
  coalesce(h.seller_late_rate_7d, 0.0) as seller_late_rate_7d,
  coalesce(h.seller_late_rate_30d, 0.0) as seller_late_rate_30d,
  coalesce(h.seller_late_rate_90d, 0.0) as seller_late_rate_90d,
  l.late_delivery
from {{ ref('int_order_summary') }} s
inner join {{ ref('fct_order_labels') }} l using (order_id)
left join {{ ref('int_seller_history') }} h using (order_id)
