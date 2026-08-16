{{ config(alias='stg_orders') }}

with src as (
  select * from {{ source('olist_raw', 'orders') }}
)

select
  cast(order_id as string) as order_id,
  cast(customer_id as string) as customer_id,
  cast(order_status as string) as order_status,
  timestamp(order_purchase_timestamp) as order_purchase_timestamp,
  timestamp(order_approved_at) as order_approved_at,
  timestamp(order_delivered_carrier_date) as order_delivered_carrier_date,
  timestamp(order_delivered_customer_date) as order_delivered_customer_date,
  timestamp(order_estimated_delivery_date) as order_estimated_delivery_date,
  -- H1 prediction timestamp
  coalesce(
    timestamp(order_approved_at),
    timestamp(order_purchase_timestamp)
  ) as prediction_ts
from src
