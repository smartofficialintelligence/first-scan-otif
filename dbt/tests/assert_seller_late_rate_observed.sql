-- Fails if seller_late_rate_90d disagrees with the observed-outcome PIT rate
-- (prior customer delivery strictly before current handoff_ts).
with labeled as (
  select
    order_id,
    seller_id,
    handoff_ts,
    order_delivered_customer_date,
    case
      when timestamp_diff(order_delivered_customer_date, prediction_ts, second) / 86400.0 > 14
        then 1
      else 0
    end as long_delivery
  from {{ ref('int_order_summary') }}
  where order_delivered_customer_date is not null
    and handoff_ts is not null
    and seller_id is not null
),

expected as (
  select
    cur.order_id,
    safe_divide(
      countif(
        hist.handoff_ts >= timestamp_sub(cur.handoff_ts, interval 90 day)
        and hist.order_delivered_customer_date < cur.handoff_ts
        and hist.long_delivery = 1
      ),
      nullif(
        countif(
          hist.handoff_ts >= timestamp_sub(cur.handoff_ts, interval 90 day)
          and hist.order_delivered_customer_date < cur.handoff_ts
        ),
        0
      )
    ) as expected_late_rate_90d
  from labeled cur
  left join labeled hist
    on hist.seller_id = cur.seller_id
   and hist.handoff_ts < cur.handoff_ts
  group by 1
)

select
  f.order_id,
  f.seller_late_rate_90d,
  e.expected_late_rate_90d
from {{ ref('fct_order_features') }} f
join expected e using (order_id)
where abs(coalesce(f.seller_late_rate_90d, 0.0) - coalesce(e.expected_late_rate_90d, 0.0)) > 1e-6
