# Simulated policy impact — holdout replay snapshot

> Snapshot of `artifacts/decision_impact.md` from `make decision-eval` after a full holdout policy replay (n = 9,647 orders, champion `local-20260819T170145Z`, econ-sim-v3, 2026-08-19). Regenerate: score the replay holdout, run `scripts/policy_replay.py --ledger`, then `make decision-eval`.


Performed 196 late notices, 338 at-risk notices, 96 remaining-leg upgrades, and 9017 no-action; moved 27 deliveries from late to on-time; spent $1,432.35 to do it.

On this ledger the frozen NOC policy performed 196 late notices, 338 at-risk notices, 96 remaining-leg upgrades, and 9017 no-action. Simulation moved 27 of 882 observed-late deliveries to on-time and avoided 88.8 delay-days. Intervention spend was $1,432.35; simulated net value was $550.34.

## Action mix

| Action | Count |
|---|---:|
| `LATE_NOTICE` | 196 |
| `AT_RISK_NOTICE` | 338 |
| `REMAINING_LEG_UPGRADE` | 96 |
| `NO_ACTION` | 9017 |

## Outcomes (simulated)

- Observed late deliveries: **882**
- Still late after simulation: **855**
- Moved late → on-time: **27**
- Delay-days avoided: **88.8**
- Spend: **$1,432.35**
- Net simulated value: **$550.34**

_Simulated under econ-sim-v3. Not observed P&L and not a causal ROI claim. Upgrade flips use an assumed Bernoulli prevent rate; notices do not change on-time status or days late._
