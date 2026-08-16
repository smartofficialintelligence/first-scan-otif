{{ config(alias='stg_sellers') }}

select
  cast(seller_id as string) as seller_id,
  lpad(cast(seller_zip_code_prefix as string), 5, '0') as seller_zip_code_prefix,
  cast(seller_city as string) as seller_city,
  cast(seller_state as string) as seller_state
from {{ source('olist_raw', 'sellers') }}
