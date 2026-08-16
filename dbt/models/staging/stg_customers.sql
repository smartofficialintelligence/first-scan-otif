{{ config(alias='stg_customers') }}

select
  cast(customer_id as string) as customer_id,
  cast(customer_unique_id as string) as customer_unique_id,
  lpad(cast(customer_zip_code_prefix as string), 5, '0') as customer_zip_code_prefix,
  cast(customer_city as string) as customer_city,
  cast(customer_state as string) as customer_state
from {{ source('olist_raw', 'customers') }}
