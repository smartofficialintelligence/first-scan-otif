# H9 / H10 — Economics assumption gates

**Status:** H9/H10 **approved as simulation defaults** for this portfolio (`econ-sim-v3`).  
**Causal ROI claims:** still **disallowed** (`allow_causal_roi_claims: false`).

These gates unlock *simulation claim language* (NOC policy replay, demo $). They do **not** turn simulation into causal proof. Hero policy is deterministic P0–P3 bands, not EV-argmax.

## What each gate covers

| Gate | Topic | Config fields | Portfolio status |
|---|---|---|---|
| **H9** | Business loss if long delivery | `business_loss.*` | approved (simulation) |
| **H10** | Intervention effectiveness | per-action cost / prevent / impact | approved (simulation) |
| **H11** | Agent action scope / mandatory human review | `routing.*`, `/v1/agent/review` | defaults locked |
| **H12** | Real external execution | `real_external_execution_enabled` | **false** (forbidden) |

## How to re-approve after changing numbers

1. Edit assumptions in `config/policy_economics.yaml`.
2. Bump `policy_config_version`.
3. Set `economics_gate` fields (`approved_by`, `approved_at`, notes).
4. Keep `allow_causal_roi_claims: false` unless you have a measured lift study.
5. Verify:

```bash
make economics-gate
uv run python scripts/check_economics_gate.py --require-approved
curl -s localhost:8080/v1/policies/current | jq '.economics_gate, .simulation_claims_allowed, .causal_roi_claim_allowed'
```

## Demo rule

Interviewer language: **“simulated under versioned assumptions (econ-sim-v3) — not measured causal ROI.”**
