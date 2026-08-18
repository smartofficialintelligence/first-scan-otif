-- Assert seller 90d history never exceeds count of earlier labeled orders for that seller.
-- Fails if PIT leakage includes the current order.

with feats as (
  select * from {{ ref('fct_order_features') }}
),

earlier as (
  select
    a.order_id,
    count(*) as earlier_count
  from feats a
  join feats b
    on a.seller_id = b.seller_id
   and b.handoff_ts < a.handoff_ts
  group by 1
)

select
  f.order_id,
  f.seller_order_count_90d,
  coalesce(e.earlier_count, 0) as earlier_count
from feats f
left join earlier e using (order_id)
where f.seller_order_count_90d > coalesce(e.earlier_count, 0)
