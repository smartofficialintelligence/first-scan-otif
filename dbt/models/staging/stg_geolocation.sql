{{ config(alias='stg_geolocation') }}

select
  lpad(cast(geolocation_zip_code_prefix as string), 5, '0') as geolocation_zip_code_prefix,
  cast(geolocation_lat as float64) as geolocation_lat,
  cast(geolocation_lng as float64) as geolocation_lng,
  cast(geolocation_city as string) as geolocation_city,
  cast(geolocation_state as string) as geolocation_state
from {{ source('olist_raw', 'geolocation') }}
