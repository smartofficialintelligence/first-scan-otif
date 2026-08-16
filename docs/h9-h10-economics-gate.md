# H9 / H10 — Economics assumption gates

**Status:** Gate machinery complete. Portfolio defaults remain **`pending_approval`** until a human stakeholder signs off.

These gates unlock *claim language* about intervention value. They do **not** turn simulation into causal proof.

## What each gate covers

| Gate | Topic | Config fields |
|---|---|---|
| **H9** | Business loss if long delivery | `business_loss.fixed_long_delivery_cost`, `order_value_loss_rate` |
| **H10** | Intervention effectiveness | per-action `cost`, `risk_prevention_probability`, `customer_impact_reduction` |
| **H11** | Agent action scope / mandatory human review | `routing.*`, human gate on `/v1/agent/review` |
| **H12** | Real external execution | `routing.real_external_execution_enabled` — **must stay false** |

## How to approve (human only)

1. Review assumptions in `config/policy_economics.yaml`.
2. Edit `economics_gate`:

```yaml
economics_gate:
  status: approved
  h9_business_loss: approved
  h10_intervention_effectiveness: approved
  approved_by: "<name or email>"
  approved_at: "<ISO-8601 timestamp>"
  notes: "Approved for demo simulation claims under stated assumptions."
```

3. Bump `policy_config_version` (e.g. `econ-sim-v2`).
4. Verify:

```bash
uv run python scripts/check_economics_gate.py
uv run python scripts/check_economics_gate.py --require-approved  # exit 1 while pending
curl -s localhost:8080/v1/policies/current | jq '.economics_gate, .causal_roi_claim_allowed'
```

## Demo rule

Until approved, interviewer scripts must say: **“simulated under versioned assumptions — not measured ROI.”**  
`GET /v1/policies/current` exposes `causal_roi_claim_allowed: false` while pending.
