# Feature Architecture

Status: **candidate set locked**; **H2 audit completed for portfolio v1** — see [h2-feature-audit.md](h2-feature-audit.md).

## Layers (dbt)

```text
raw
 └── staging
      stg_orders, stg_order_items, stg_customers, stg_products,
      stg_sellers, stg_payments, stg_geolocation, stg_category_translation
 └── intermediate
      int_order_summary, int_seller_history, int_customer_history,
      int_category_history, int_geo_features
 └── marts/ml
      fct_order_features, fct_order_labels, fct_training_snapshot
```

Grain of ML marts: one row per `order_id` at `prediction_ts`.

## Point-in-time rule

Historical features use only events with `event_ts < prediction_ts` (strict).  
Windows: **7d / 30d / 90d**. Rolling logic must be `closed="left"` equivalent in SQL.

## Request-native / order features (offline + request path)

| Feature | Notes | Leakage risk |
|---|---|---|
| `purchase_hour`, `purchase_dow`, `purchase_month` | From `prediction_ts` / purchase ts | Low |
| `is_weekend` | Derived | Low |
| `item_count` | From order_items at order creation | Low |
| `basket_value` | Sum of item prices | Low |
| `freight_value` | Sum freight | Low — confirm known at approval |
| `seller_count` | Distinct sellers on order | Low |
| `category_count` | Distinct categories | Low |
| `payment_type_primary` | Dominant payment type | Low |
| `installment_count` | From payments | Low |
| `estimated_delivery_horizon_days` | `order_estimated_delivery_date - prediction_ts` | Low — promise known at purchase |
| `approval_lag_hours` | `prediction_ts - order_purchase_timestamp` (clipped ≥0) | Low |
| `freight_to_basket_ratio` | `freight_value / basket_value` | Low |
| `same_state` | customer_state == seller_state_primary | Low |
| `avg_product_weight_g` | Mean item weight on order | Low |
| `primary_category` | First / primary product category (categorical) | Low |
| `customer_state` | From customer | Low |
| `seller_state_primary` | Primary seller state | Low |
| `geo_distance_km` | Haversine customer↔seller centroid/proxy | Medium — use only geolocation available historically; document zip aggregation |

## Historical features (offline; seller subset also online)

Computed per entity with PIT correctness.

| Feature | Entity | Windows | Online? | Leakage risk |
|---|---|---|---|---|
| `seller_order_count_*` | seller | 7/30/90d | Yes | Low if PIT |
| `seller_late_rate_*` | seller | 7/30/90d | Yes | Low if PIT; **exclude current order** |
| `seller_avg_freight_*` | seller | 30/90d | Optional | Low if PIT |
| `seller_avg_basket_*` | seller | 30/90d | Optional | Low if PIT |
| `category_late_rate_*` | category | 30/90d | No (v1) | Low if PIT |
| `category_order_count_*` | category | 90d | No (v1) | Low if PIT |
| `customer_order_count_*` | customer | 30/90d | No (v1) | Low if PIT; cold-start common |
| `customer_late_rate_*` | customer | 90d | No (v1) | Low if PIT; sparse |

### Online Feast entity (v1)

Entity key: `seller_id`  
Feature view name: `seller_liveness_v1` (name flexible; versioned)

Fields (minimum):

- `seller_order_count_30d`
- `seller_late_rate_30d`
- `seller_order_count_90d`
- `seller_late_rate_90d`
- `feature_timestamp`

Missing entity → documented default (global prior or null + model default handling).  
Stale feature → if `now - feature_timestamp > freshness_sla` (default 36h during demo), count as stale and record metric; still predict with fallback policy.

## Explicit non-features (blocked)

- Review score / comment
- Delivery carrier/customer actual timestamps (except as label)
- Anything computed with `closed="right"` or inclusive of current order
- Post-outcome order status

## Training–serving consistency

- Single feature contract module (`features/contracts.py`) shared by training assembly and API assembly
- Offline training rows come from Feast historical retrieval or the dbt snapshot that Feast reads — **not** a parallel pandas feature script
- Parity test: sample keys, compare offline vs online values within tolerance

## H2 checklist (human)

For every feature:

1. Source table(s)
2. Timestamp column used
3. Window + closed semantics
4. Knowable at `prediction_ts`? (yes/no)
5. Online or offline only
6. Owner / docstring in Feast registry

**Portfolio v1:** checklist recorded as passed in [h2-feature-audit.md](h2-feature-audit.md) (2026-08-16). Re-run before live production promote.
