# Data limitations, assumptions, and proxies

**Status:** working contract for the carrier-handoff NOC demo (not a measured cost study).  
**Claims:** `allow_causal_roi_claims: false`. Simulated $ and “misses avoided” are **not** causal ROI.

This section exists so business KPIs can include **upgrade cost and net $** without pretending Olist billed a remaining-leg service change.

## Data limitations (what is not in the public tables)

| Missing | Consequence |
|---|---|
| Carrier name / service type (PAC, Sedex, etc.) | Cannot know if a faster **remaining-leg product** exists |
| Parcel scan beyond first carrier handoff | “Still at origin hub” is **assumed** at this scan |
| Invoice for expedite, insurance, delay indemnity | No observed upgrade or SLA payout |
| CS handle time, voucher ledger, conversion | No observed action P&L or GMV lift |
| Checkout / listing impressions | No conversion-from-tighter-ETA KPI |

What **is** observed: order value (`price` / basket), `freight_value` (charge, not service tier), promise vs actual **dates**, review score **after** delivery.

## Proxies (observed → business meaning)

| Business idea | Proxy in data |
|---|---|
| $ at risk if the promise breaks | Basket (`sum(price)`); optional + freight |
| Customer impact | Review mean and **1–2★** rate on miss vs on-time (association, not lift) |
| Date impact | Days after `order_estimated_delivery_date` (median ~6d late on misses; on-time ~13d early) |
| Paid more for a faster SLA | **None** — do not infer from `freight_value` |
| Origin-hub upgrade window | **All** scores at `order_delivered_carrier_date` (first scan ≈ handoff) |

## Assumptions (versioned; change in config, not in prose)

Defaults below are **placeholders** for demo economics. Tune in `config/policy_economics.yaml` (or successor) and keep this table in sync.

### Miss cost (customer/date failure)

If an order **misses the customer promise**, simulated loss:

```text
miss_cost = fixed_miss_cost + order_value_loss_rate * basket_value
```

Initial placeholder: `fixed_miss_cost = 10`, `order_value_loss_rate = 0.10` (10% of basket — goodwill / repeat / CS lump).  
**Not** estimated from Olist.

### Remaining-leg upgrade cost (network spend)

Olist has **no** upgrade tariff. Demo uses a **placeholder draw** so the KPI is a distribution, not a fake point invoice.

Per P1-eligible upgrade attempt:

```text
upgrade_cost = clip(
  upgrade_cost_lognormal_draw,
  min = upgrade_cost_min,
  max = min(upgrade_cost_cap, upgrade_cost_basket_frac * basket_value)
)
```

Initial placeholder:

| Parameter | Value | Intent |
|---|---|---|
| Distribution | Lognormal, median **R$12**, σ_log **0.45** | Most bumps cheap; some long-haul |
| `upgrade_cost_min` | R$5 | Floor |
| `upgrade_cost_cap` | R$40 | Don’t pretend air charters |
| `upgrade_cost_basket_frac` | 0.08 | Never spend >8% of basket on a demo bump |

Seed draws by `order_id` so replay is deterministic.

**Eligibility (also an assumption):** P1 **and** `0 < remaining_to_promise_days ≤ 7` **and** (`geo_distance_km ≥ 100` or not `same_state`). Otherwise no upgrade SKU — comms/trace only.

**Effect of upgrade (assumption, not data):** `risk_prevention_probability` e.g. **0.35** if eligible (chance the miss is avoided). If not eligible, **0**.

### Cheap actions

| Action | Assumed cost | Assumed effect |
|---|---|---|
| At-risk / revised-ETA notice | R$1 (or 0) | **0** OTIF recovery; customer-impact reduction e.g. 0.20 on the review-loss term only |
| Carrier trace (no retariff) | R$2 | 0 OTIF recovery |
| P0 already-late notice | R$1 | Containment, not recovered OTIF |
| P3 | R$0 | None |

### Agent

Executes the **policy-selected** action only. Human approval only if `upgrade_cost ≥ human_spend_threshold` (placeholder **R$20**). Not a capacity ration on the agent.

## Business KPIs (what we report)

**Observed (history, no action):** GMV on missed promises; days after promise; 1–2★ rate on miss vs on-time.

**Simulated (policy on a replay window, assumptions above):**

| KPI | Definition |
|---|---|
| Simulated upgrade spend | Sum of `upgrade_cost` draws on orders that took `REMAINING_LEG_UPGRADE` |
| Simulated miss cost avoided | `miss_cost × 1{would_miss} × Bernoulli(prevention)` (or EV form) |
| Simulated net | avoided miss cost − upgrade spend − cheap-action spend |
| Date (sim) | Expected reduction in **days-after-promise** among prevented misses (use observed overrun on misses, e.g. median 6d, as the avoided-delay proxy) |
| Customer (sim) | Expected 1–2★ events avoided × (miss 1–2★ rate − on-time rate), **associational rates applied in sim only** |

Always show **assumption version** next to simulated net. Sensitivity: replay at median upgrade R$8 / R$12 / R$20.

## What we will not say

- That upgrade cost or prevention rate was fit on Olist  
- That `freight_value` is a service upgrade  
- That simulated net is measured P&L or causal lift  
