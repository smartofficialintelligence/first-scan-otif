{{ config(alias='stg_products') }}

select
  cast(product_id as string) as product_id,
  cast(product_category_name as string) as product_category_name
from {{ source('olist_raw', 'products') }}
