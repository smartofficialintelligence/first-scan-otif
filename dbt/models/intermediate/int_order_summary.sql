{{ config(alias='int_order_summary') }}

with items as (
  select
    i.order_id,
    count(*) as item_count,
    sum(i.price) as basket_value,
    sum(i.freight_value) as freight_value,
    count(distinct i.seller_id) as seller_count,
    count(distinct p.product_category_name) as category_count,
    array_agg(i.seller_id order by i.order_item_id limit 1)[offset(0)] as primary_seller_id,
    min(i.shipping_limit_date) as shipping_limit_date
  from {{ ref('stg_order_items') }} i
  left join {{ ref('stg_products') }} p using (product_id)
  group by 1
),

payments as (
  select
    order_id,
    array_agg(payment_type order by payment_value desc limit 1)[offset(0)] as payment_type_primary,
    max(payment_installments) as installment_count
  from {{ ref('stg_payments') }}
  group by 1
),

geo as (
  select
    geolocation_zip_code_prefix,
    avg(geolocation_lat) as lat,
    avg(geolocation_lng) as lng
  from {{ ref('stg_geolocation') }}
  group by 1
)

select
  o.order_id,
  o.customer_id,
  o.order_status,
  o.prediction_ts,
  o.order_delivered_carrier_date as handoff_ts,
  o.order_purchase_timestamp,
  o.order_approved_at,
  o.order_delivered_customer_date,
  o.order_estimated_delivery_date,
  i.shipping_limit_date,
  timestamp_diff(o.order_estimated_delivery_date, o.prediction_ts, hour) / 24.0
    as estimated_delivery_horizon_days,
  greatest(
    timestamp_diff(o.order_delivered_carrier_date, o.prediction_ts, hour) / 24.0,
    -1.0
  ) as handling_days,
  timestamp_diff(o.order_estimated_delivery_date, o.order_delivered_carrier_date, hour) / 24.0
    as remaining_to_promise_days,
  case
    when timestamp_diff(o.order_estimated_delivery_date, o.prediction_ts, hour) = 0 then 0.0
    else (
      greatest(timestamp_diff(o.order_delivered_carrier_date, o.prediction_ts, hour) / 24.0, -1.0)
      / (timestamp_diff(o.order_estimated_delivery_date, o.prediction_ts, hour) / 24.0)
    )
  end as handling_frac_of_promise,
  case
    when i.shipping_limit_date is null then 0
    when o.order_delivered_carrier_date > i.shipping_limit_date then 1
    else 0
  end as limit_miss,
  i.item_count,
  i.basket_value,
  i.freight_value,
  i.seller_count,
  i.category_count,
  i.primary_seller_id as seller_id,
  pay.payment_type_primary,
  pay.installment_count,
  c.customer_state,
  s.seller_state as seller_state_primary,
  -- haversine km (BigQuery has no radians(); convert deg -> rad via acos(-1)/180)
  6371 * 2 * asin(sqrt(
    pow(sin(((acos(-1) / 180) * (sg.lat - cg.lat)) / 2), 2)
    + cos((acos(-1) / 180) * cg.lat) * cos((acos(-1) / 180) * sg.lat)
      * pow(sin(((acos(-1) / 180) * (sg.lng - cg.lng)) / 2), 2)
  )) as geo_distance_km,
  extract(hour from o.prediction_ts) as purchase_hour,
  extract(dayofweek from o.prediction_ts) - 1 as purchase_dow,
  extract(month from o.prediction_ts) as purchase_month,
  case when extract(dayofweek from o.prediction_ts) in (1, 7) then 1 else 0 end as is_weekend
from {{ ref('stg_orders') }} o
inner join items i using (order_id)
left join payments pay using (order_id)
left join {{ ref('stg_customers') }} c using (customer_id)
left join {{ ref('stg_sellers') }} s on s.seller_id = i.primary_seller_id
left join geo cg on cg.geolocation_zip_code_prefix = c.customer_zip_code_prefix
left join geo sg on sg.geolocation_zip_code_prefix = s.seller_zip_code_prefix
where o.prediction_ts is not null
