{{ config(alias='fct_training_snapshot') }}

-- Immutable training snapshot view/table: currently a thin pass-through of features.
-- Future: pin by snapshot_id / as-of date in an incremental snapshot table.
select
  *,
  current_timestamp() as snapshot_created_at
from {{ ref('fct_order_features') }}
