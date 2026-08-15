{{ config(alias='stg_order_items') }}

select
  cast(order_id as string) as order_id,
  cast(order_item_id as int64) as order_item_id,
  cast(product_id as string) as product_id,
  cast(seller_id as string) as seller_id,
  timestamp(shipping_limit_date) as shipping_limit_date,
  cast(price as float64) as price,
  cast(freight_value as float64) as freight_value
from {{ source('olist_raw', 'order_items') }}
